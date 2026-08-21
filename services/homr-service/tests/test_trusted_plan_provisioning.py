from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import hmac
import importlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SERVICE_ROOT.parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "services" / "omr-gateway" / "src"))

PACKAGE_BY_SERVICE = {
    "audiveris-service": "scoremosaic_audiveris",
    "homr-service": "scoremosaic_homr",
    "clarity-service": "scoremosaic_clarity",
}
PACKAGE = PACKAGE_BY_SERVICE[SERVICE_ROOT.name]
receiver_authority = importlib.import_module(f"{PACKAGE}.receiver_authority")
provisioning = importlib.import_module(f"{PACKAGE}.trusted_plan_provisioning")
app_module = importlib.import_module(f"{PACKAGE}.app")
config_module = importlib.import_module(f"{PACKAGE}.config")

from scoremosaic_gateway.config import EngineEndpoint
from scoremosaic_gateway.dispatch_identity import build_dispatch_identity
from scoremosaic_gateway.dispatch_input_capsule import build_dispatch_input_capsule
from scoremosaic_gateway.dispatch_target import APPROVED_ENGINE_ORIGINS
from scoremosaic_gateway.orchestration import build_orchestration_plan
from scoremosaic_gateway.trusted_plan_provisioning import (
    build_trusted_plan_provisioning_binding,
    build_trusted_plan_provisioning_request,
    resolve_trusted_plan_provisioning_credential,
)

ENGINE_NAME = receiver_authority.ENGINE_NAME
EngineReceiverAuthority = receiver_authority.EngineReceiverAuthority
EngineReceiverAuthorityError = receiver_authority.EngineReceiverAuthorityError
TrustedPlanProvisioningError = provisioning.TrustedPlanProvisioningError
accept_trusted_plan_provisioning = provisioning.accept_trusted_plan_provisioning

PROVISIONING_SECRET = b"P" * 32
AUTHORITY_KEY = b"A" * 32
GENERATION = "gen1"
ISSUED_AT = 10_000
NOW = 10_001
NONCE = "ab" * 16


class TrustedPlanProvisioningReceiverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.authority = EngineReceiverAuthority(
            root=Path(self.temp.name) / "authority",
            integrity_key=AUTHORITY_KEY,
        )
        self.request = self._build_request()

    def _build_request(self):
        source = b"\x89PNG\r\n\x1a\nscoremosaic-stage-4b"
        plan = build_orchestration_plan(
            "job_stage4b1234567890",
            source_artifact_ref="sources/stage4b.png",
            source_sha256=hashlib.sha256(source).hexdigest(),
            source_size_bytes=len(source),
            source_media_type="image/png",
        ).as_dict()
        identity = build_dispatch_identity(plan, ENGINE_NAME)
        capsule = build_dispatch_input_capsule(plan, identity, [source])
        endpoint = EngineEndpoint(
            ENGINE_NAME,
            APPROVED_ENGINE_ORIGINS["staging"][ENGINE_NAME],
        )
        binding = build_trusted_plan_provisioning_binding(
            endpoint,
            environment="staging",
        )
        credential = resolve_trusted_plan_provisioning_credential(
            binding,
            generation_id=GENERATION,
            resolver=lambda _key, _generation: PROVISIONING_SECRET,
        )
        return build_trusted_plan_provisioning_request(
            capsule=capsule,
            credential=credential,
            issued_at=ISSUED_AT,
            nonce=NONCE,
        )

    def _resolver(self, key: str, generation: str):
        self.assertIn("trusted-plan-provisioning", key)
        self.assertEqual(generation, GENERATION)
        return PROVISIONING_SECRET

    def _accept(self, request=None, *, signature=None, now=NOW, resolver=None):
        request = self.request if request is None else request
        return accept_trusted_plan_provisioning(
            authority=self.authority,
            request_bytes=request.canonical_request_bytes,
            signature=request.signature if signature is None else signature,
            now_seconds=now,
            credential_resolver=self._resolver if resolver is None else resolver,
        )

    def test_valid_authenticated_provisioning_writes_engine_owned_plan(self) -> None:
        result = self._accept()
        stored = self.authority.load_trusted_plan(job_id=result.job_id)
        self.assertTrue(result.authenticated)
        self.assertEqual(result.engine, ENGINE_NAME)
        self.assertEqual(result.persistence_state, "written")
        self.assertEqual(stored.run_id, result.run_id)
        self.assertEqual(stored.canonical_plan_sha256, result.canonical_plan_sha256)
        self.assertFalse(result.network_provisioning_allowed)
        self.assertFalse(result.network_dispatch_allowed)
        self.assertFalse(result.engine_execution_allowed)

    def test_exact_replay_is_rejected_without_overwriting_plan(self) -> None:
        self._accept()
        path = Path(self.temp.name) / "authority" / "trusted-plans" / f"{self.request.job_id}.json"
        before = path.read_bytes()
        with self.assertRaises(TrustedPlanProvisioningError) as ctx:
            self._accept()
        self.assertEqual(ctx.exception.category, "trusted_plan_provisioning_replay_detected")
        self.assertEqual(path.read_bytes(), before)

    def test_same_request_concurrency_has_exactly_one_acceptance(self) -> None:
        def attempt(_index: int):
            try:
                self._accept()
                return "accepted"
            except TrustedPlanProvisioningError as exc:
                return exc.category
        with ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = list(pool.map(attempt, range(8)))
        self.assertEqual(outcomes.count("accepted"), 1)
        self.assertEqual(outcomes.count("trusted_plan_provisioning_replay_detected"), 7)
        self.authority.load_trusted_plan(job_id=self.request.job_id)

    def test_wrong_signature_fails_before_state_mutation(self) -> None:
        with self.assertRaises(TrustedPlanProvisioningError) as ctx:
            self._accept(signature="0" * 64)
        self.assertEqual(ctx.exception.category, "trusted_plan_provisioning_signature_invalid")
        with self.assertRaises(EngineReceiverAuthorityError):
            self.authority.load_trusted_plan(job_id=self.request.job_id)

    def test_authority_integrity_key_is_not_accepted_as_provisioning_secret(self) -> None:
        with self.assertRaises(TrustedPlanProvisioningError) as ctx:
            self._accept(resolver=lambda _key, _generation: AUTHORITY_KEY)
        self.assertEqual(ctx.exception.category, "trusted_plan_provisioning_signature_invalid")

    def test_stale_and_future_requests_fail_before_credential_resolution(self) -> None:
        for now, expected in (
            (ISSUED_AT - 1, "trusted_plan_provisioning_not_yet_valid"),
            (ISSUED_AT + provisioning.MAX_PROVISIONING_AGE_SECONDS + 1, "trusted_plan_provisioning_expired"),
        ):
            calls = []
            with self.assertRaises(TrustedPlanProvisioningError) as ctx:
                self._accept(now=now, resolver=lambda *_args: calls.append(True) or PROVISIONING_SECRET)
            self.assertEqual(ctx.exception.category, expected)
            self.assertEqual(calls, [])

    def test_cross_engine_request_fails_before_credential_resolution(self) -> None:
        other = next(name for name in ("audiveris", "homr", "clarity") if name != ENGINE_NAME)
        source = b"\x89PNG\r\n\x1a\nscoremosaic-stage-4b-other"
        plan = build_orchestration_plan(
            "job_stage4bother123456",
            source_artifact_ref="sources/other.png",
            source_sha256=hashlib.sha256(source).hexdigest(),
            source_size_bytes=len(source),
            source_media_type="image/png",
        ).as_dict()
        identity = build_dispatch_identity(plan, other)
        capsule = build_dispatch_input_capsule(plan, identity, [source])
        endpoint = EngineEndpoint(other, APPROVED_ENGINE_ORIGINS["staging"][other])
        binding = build_trusted_plan_provisioning_binding(endpoint, environment="staging")
        credential = resolve_trusted_plan_provisioning_credential(
            binding,
            generation_id=GENERATION,
            resolver=lambda *_args: PROVISIONING_SECRET,
        )
        request = build_trusted_plan_provisioning_request(
            capsule=capsule,
            credential=credential,
            issued_at=ISSUED_AT,
            nonce="cd" * 16,
        )
        calls = []
        with self.assertRaises(TrustedPlanProvisioningError):
            self._accept(request=request, resolver=lambda *_args: calls.append(True) or PROVISIONING_SECRET)
        self.assertEqual(calls, [])

    def test_duplicate_and_noncanonical_json_fail_before_credential_resolution(self) -> None:
        original = self.request.canonical_request_bytes.decode("ascii")
        duplicate = original[:-1] + ',"engine":"' + ENGINE_NAME + '"}'
        body = json.loads(original)
        noncanonical = json.dumps(body, sort_keys=False, indent=2).encode("ascii")
        calls = []
        for raw in (duplicate.encode("ascii"), noncanonical):
            with self.assertRaises(TrustedPlanProvisioningError):
                accept_trusted_plan_provisioning(
                    authority=self.authority,
                    request_bytes=raw,
                    signature=self.request.signature,
                    now_seconds=NOW,
                    credential_resolver=lambda *_args: calls.append(True) or PROVISIONING_SECRET,
                )
        self.assertEqual(calls, [])

    def test_semantically_tampered_plan_fails_before_credential_resolution_even_if_outer_hashes_match(self) -> None:
        body = json.loads(self.request.canonical_request_bytes.decode("ascii"))
        plan = json.loads(base64.b64decode(body["canonicalPlanB64"]).decode("ascii"))
        plan["boundaries"]["networkDispatchEnabled"] = True
        tampered_plan = json.dumps(
            plan,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        body["canonicalPlanB64"] = base64.b64encode(tampered_plan).decode("ascii")
        body["canonicalPlanBytes"] = len(tampered_plan)
        body["canonicalPlanSha256"] = hashlib.sha256(tampered_plan).hexdigest()
        raw = json.dumps(
            body,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        signature = hmac.new(PROVISIONING_SECRET, raw, hashlib.sha256).hexdigest()
        calls = []
        with self.assertRaises(TrustedPlanProvisioningError) as ctx:
            accept_trusted_plan_provisioning(
                authority=self.authority,
                request_bytes=raw,
                signature=signature,
                now_seconds=NOW,
                credential_resolver=lambda *_args: calls.append(True) or PROVISIONING_SECRET,
            )
        self.assertEqual(ctx.exception.category, "trusted_plan_provisioning_plan_invalid")
        self.assertEqual(calls, [])

    def test_unexpected_field_fails_before_credential_resolution(self) -> None:
        body = json.loads(self.request.canonical_request_bytes.decode("ascii"))
        body["callerUrl"] = "http://169.254.169.254/latest/meta-data"
        raw = json.dumps(body, separators=(",", ":"), sort_keys=True).encode("ascii")
        signature = hmac.new(PROVISIONING_SECRET, raw, hashlib.sha256).hexdigest()
        calls = []
        with self.assertRaises(TrustedPlanProvisioningError):
            accept_trusted_plan_provisioning(
                authority=self.authority,
                request_bytes=raw,
                signature=signature,
                now_seconds=NOW,
                credential_resolver=lambda *_args: calls.append(True) or PROVISIONING_SECRET,
            )
        self.assertEqual(calls, [])

    def test_resolver_failure_is_bounded_and_does_not_leak(self) -> None:
        def failing_resolver(_key: str, _generation: str):
            raise RuntimeError("TOKEN_DO_NOT_LEAK /private/secret")
        with self.assertRaises(TrustedPlanProvisioningError) as ctx:
            self._accept(resolver=failing_resolver)
        self.assertEqual(ctx.exception.category, "trusted_plan_provisioning_credential_unavailable")
        self.assertNotIn("TOKEN_DO_NOT_LEAK", str(ctx.exception))

    def test_safe_result_contains_no_raw_plan_signature_or_secret(self) -> None:
        result = self._accept()
        text = repr(result.as_safe_dict())
        self.assertNotIn(self.request.signature, text)
        self.assertNotIn(PROVISIONING_SECRET.decode("ascii"), text)
        self.assertNotIn("canonicalPlanB64", text)
        self.assertFalse(result.raw_plan_export_allowed)
        self.assertFalse(result.credential_export_allowed)

    def test_internal_trusted_plan_route_remains_unregistered(self) -> None:
        response = app_module.route_request(
            "POST",
            provisioning.TRUSTED_PLAN_PROVISIONING_PATH,
            config_module.load_config({}),
        )
        self.assertEqual(response.status, 405)


if __name__ == "__main__":
    unittest.main()
