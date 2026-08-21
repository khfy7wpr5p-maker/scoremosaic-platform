from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_gateway.config import EngineEndpoint
from scoremosaic_gateway.dispatch_identity import build_dispatch_identity
from scoremosaic_gateway.dispatch_input_capsule import build_dispatch_input_capsule
from scoremosaic_gateway.dispatch_target import APPROVED_ENGINE_ORIGINS
from scoremosaic_gateway.orchestration import build_orchestration_plan
from scoremosaic_gateway.service_auth import build_engine_auth_binding
from scoremosaic_gateway.trusted_plan_provisioning import (
    TRUSTED_PLAN_PROVISIONING_PATH,
    TrustedPlanProvisioningError,
    build_trusted_plan_provisioning_binding,
    build_trusted_plan_provisioning_request,
    resolve_trusted_plan_provisioning_credential,
)


class TrustedPlanProvisioningTests(unittest.TestCase):
    def _capsule(self, engine: str = "homr"):
        source = b"\x89PNG\r\n\x1a\nscoremosaic-stage-4b"
        job_id = "job_stage4b1234567890"
        plan = build_orchestration_plan(
            job_id,
            source_artifact_ref="sources/stage4b.png",
            source_sha256=hashlib.sha256(source).hexdigest(),
            source_size_bytes=len(source),
            source_media_type="image/png",
        ).as_dict()
        identity = build_dispatch_identity(plan, engine)
        return build_dispatch_input_capsule(plan, identity, [source])

    def _credential(self, engine: str = "homr", secret: bytes = b"P" * 32):
        endpoint = EngineEndpoint(engine, APPROVED_ENGINE_ORIGINS["staging"][engine])
        binding = build_trusted_plan_provisioning_binding(
            endpoint,
            environment="staging",
        )
        observed: list[tuple[str, str]] = []

        def resolver(key: str, generation: str):
            observed.append((key, generation))
            return secret

        credential = resolve_trusted_plan_provisioning_credential(
            binding,
            generation_id="gen1",
            resolver=resolver,
        )
        return binding, credential, observed

    def test_builds_canonical_authenticated_request_from_verified_capsule(self) -> None:
        capsule = self._capsule()
        binding, credential, observed = self._credential()
        request = build_trusted_plan_provisioning_request(
            capsule=capsule,
            credential=credential,
            issued_at=1000,
            nonce="01" * 16,
        )

        body = json.loads(request.canonical_request_bytes.decode("ascii"))
        self.assertEqual(body["engine"], "homr")
        self.assertEqual(body["jobId"], capsule.dispatch_identity.job_id)
        self.assertEqual(body["runId"], capsule.dispatch_identity.run_id)
        self.assertEqual(body["path"], TRUSTED_PLAN_PROVISIONING_PATH)
        self.assertEqual(body["canonicalPlanSha256"], capsule.canonical_plan_sha256)
        self.assertEqual(
            request.canonical_request_bytes,
            json.dumps(
                body,
                ensure_ascii=True,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("ascii"),
        )
        self.assertEqual(observed, [(binding.credential_key, "gen1")])
        self.assertFalse(request.network_provisioning_allowed)
        self.assertFalse(request.network_dispatch_allowed)
        self.assertFalse(request.engine_execution_allowed)

    def test_provisioning_credential_key_is_distinct_from_dispatch_credential_key(self) -> None:
        endpoint = EngineEndpoint("homr", APPROVED_ENGINE_ORIGINS["staging"]["homr"])
        provisioning = build_trusted_plan_provisioning_binding(endpoint, environment="staging")
        dispatch = build_engine_auth_binding(endpoint, "staging")
        self.assertNotEqual(provisioning.credential_key, dispatch.credential_key)
        self.assertIn("trusted-plan-provisioning", provisioning.credential_key)

    def test_production_is_not_allowlisted(self) -> None:
        endpoint = EngineEndpoint("homr", "http://homr-foundation:8080")
        with self.assertRaises(TrustedPlanProvisioningError) as ctx:
            build_trusted_plan_provisioning_binding(endpoint, environment="production")
        self.assertEqual(ctx.exception.category, "trusted_plan_provisioning_endpoint_invalid")

    def test_caller_cannot_select_arbitrary_origin(self) -> None:
        endpoint = EngineEndpoint("homr", "http://169.254.169.254")
        with self.assertRaises(TrustedPlanProvisioningError):
            build_trusted_plan_provisioning_binding(endpoint, environment="staging")

    def test_cross_engine_credential_cannot_sign_capsule(self) -> None:
        capsule = self._capsule("homr")
        _, credential, _ = self._credential("clarity")
        with self.assertRaises(TrustedPlanProvisioningError) as ctx:
            build_trusted_plan_provisioning_request(
                capsule=capsule,
                credential=credential,
                issued_at=1000,
                nonce="02" * 16,
            )
        self.assertEqual(ctx.exception.category, "trusted_plan_provisioning_engine_mismatch")

    def test_bad_nonce_fails_closed(self) -> None:
        capsule = self._capsule()
        _, credential, _ = self._credential()
        with self.assertRaises(TrustedPlanProvisioningError):
            build_trusted_plan_provisioning_request(
                capsule=capsule,
                credential=credential,
                issued_at=1000,
                nonce="not-a-nonce",
            )

    def test_resolver_exception_does_not_leak(self) -> None:
        endpoint = EngineEndpoint("homr", APPROVED_ENGINE_ORIGINS["staging"]["homr"])
        binding = build_trusted_plan_provisioning_binding(endpoint, environment="staging")

        def resolver(_key: str, _generation: str):
            raise RuntimeError("SECRET_DO_NOT_LEAK /private/path")

        with self.assertRaises(TrustedPlanProvisioningError) as ctx:
            resolve_trusted_plan_provisioning_credential(
                binding,
                generation_id="gen1",
                resolver=resolver,
            )
        self.assertEqual(ctx.exception.category, "trusted_plan_provisioning_credential_unavailable")
        self.assertNotIn("SECRET_DO_NOT_LEAK", str(ctx.exception))

    def test_repr_and_safe_dict_do_not_expose_secret_or_raw_plan(self) -> None:
        capsule = self._capsule()
        _, credential, _ = self._credential(secret=b"S" * 32)
        request = build_trusted_plan_provisioning_request(
            capsule=capsule,
            credential=credential,
            issued_at=1000,
            nonce="03" * 16,
        )
        text = repr(credential) + repr(request) + repr(request.as_safe_dict())
        self.assertNotIn("S" * 32, text)
        self.assertNotIn(capsule.canonical_plan_bytes.decode("ascii"), text)
        self.assertNotIn(request.signature, text)


if __name__ == "__main__":
    unittest.main()
