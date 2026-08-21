from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import secrets
import sys
import tempfile
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SERVICE_ROOT.parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "services" / "omr-gateway" / "src"))

from scoremosaic_gateway.config import EngineEndpoint
from scoremosaic_gateway.controlled_staging_dispatch_wire import (
    serialize_controlled_staging_dispatch_wire,
)
from scoremosaic_gateway.credential_rotation import (
    MAX_REPLAY_RESERVATION_SECONDS,
    build_replay_reservation,
    build_rotation_set,
    resolve_engine_credential_generation,
    sign_rotation_authenticated_request,
)
from scoremosaic_gateway.dispatch_identity import (
    build_dispatch_identity,
    dispatch_identity_payload,
)
from scoremosaic_gateway.dispatch_input_capsule import canonical_orchestration_plan_bytes
from scoremosaic_gateway.dispatch_target import (
    APPROVED_ENGINE_ORIGINS,
    build_engine_dispatch_target,
)
from scoremosaic_gateway.orchestration import build_orchestration_plan
from scoremosaic_gateway.service_auth import build_engine_auth_binding

if SERVICE_ROOT.name == "audiveris-service":
    from scoremosaic_audiveris.authenticated_dispatch_receiver import (
        AuthenticatedDispatchReceiverError,
        ReceiverCredentialRotation,
        accept_authenticated_dispatch,
    )
    from scoremosaic_audiveris.receiver_authority import EngineReceiverAuthority
    ENGINE = "audiveris"
elif SERVICE_ROOT.name == "homr-service":
    from scoremosaic_homr.authenticated_dispatch_receiver import (
        AuthenticatedDispatchReceiverError,
        ReceiverCredentialRotation,
        accept_authenticated_dispatch,
    )
    from scoremosaic_homr.receiver_authority import EngineReceiverAuthority
    ENGINE = "homr"
elif SERVICE_ROOT.name == "clarity-service":
    from scoremosaic_clarity.authenticated_dispatch_receiver import (
        AuthenticatedDispatchReceiverError,
        ReceiverCredentialRotation,
        accept_authenticated_dispatch,
    )
    from scoremosaic_clarity.receiver_authority import EngineReceiverAuthority
    ENGINE = "clarity"
else:
    raise RuntimeError("unexpected engine service root")


class AuthenticatedDispatchReceiverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.authority = EngineReceiverAuthority(
            root=Path(self.temp.name) / "receiver-authority",
            integrity_key=secrets.token_bytes(32),
        )
        self.now = 1_800_300_000
        self.generation = "gen-stage4c-current"
        self.secret = secrets.token_bytes(32)
        self.endpoint = EngineEndpoint(
            ENGINE,
            APPROVED_ENGINE_ORIGINS["staging"][ENGINE],
        )
        self.binding = build_engine_auth_binding(self.endpoint, "staging")
        self.target = build_engine_dispatch_target(self.binding, self.endpoint)
        self.gateway_credential = resolve_engine_credential_generation(
            self.binding,
            self.generation,
            lambda key, generation: (
                self.secret
                if key == self.binding.credential_key
                and generation == self.generation
                else None
            ),
        )
        self.gateway_rotation = build_rotation_set(
            current=self.gateway_credential,
            previous=None,
            rotation_started_at=self.now - 10,
            previous_valid_until=None,
        )
        self.receiver_rotation = ReceiverCredentialRotation(
            current_generation_id=self.generation,
            current_activated_at=self.now - 10,
        )
        self.plan = build_orchestration_plan(
            "job_stage4creceiver01",
            source_artifact_ref="sources/job_stage4creceiver01/source.pdf",
            source_sha256="a" * 64,
            source_size_bytes=4096,
            source_media_type="application/pdf",
        ).as_dict()
        self.identity = build_dispatch_identity(self.plan, ENGINE)
        self.payload = dispatch_identity_payload(self.identity)
        self.authority.register_trusted_plan(
            job_id=self.identity.job_id,
            canonical_plan_bytes=canonical_orchestration_plan_bytes(self.plan),
        )
        self.request = sign_rotation_authenticated_request(
            self.gateway_rotation,
            method=self.target.method,
            path=self.target.path,
            timestamp=self.now,
            nonce="0123456789abcdef0123456789abcdef",
            payload=self.payload,
            now_seconds=self.now,
        )
        self.wire = serialize_controlled_staging_dispatch_wire(
            target=self.target,
            request=self.request,
            payload=self.payload,
        )
        self.resolver_calls = 0

    def resolver(self, key: str, generation: str):
        self.resolver_calls += 1
        if key == self.binding.credential_key and generation == self.generation:
            return self.secret
        return None

    def accept(self, *, headers=None, body=None, now=None, resolver=None):
        return accept_authenticated_dispatch(
            authority=self.authority,
            rotation=self.receiver_rotation,
            headers=self.wire.headers if headers is None else headers,
            body=self.payload if body is None else body,
            observed_method="POST",
            observed_path="/internal/transcribe",
            now_seconds=self.now if now is None else now,
            credential_resolver=self.resolver if resolver is None else resolver,
        )

    @staticmethod
    def replace_header(headers, name: str, value: str):
        return tuple(
            (observed, value if observed.lower() == name else original)
            for observed, original in headers
        )

    def test_gateway_wire_is_accepted_against_engine_owned_trusted_plan(self) -> None:
        result = self.accept()
        self.assertTrue(result.receiver_authenticated)
        self.assertTrue(result.trusted_plan_converged)
        self.assertTrue(result.replay_reserved)
        self.assertFalse(result.engine_execution_allowed)
        self.assertFalse(result.retry_allowed)
        self.assertFalse(result.source_access_allowed)
        self.assertFalse(result.job_state_mutation_allowed)
        self.assertEqual(result.job_id, self.identity.job_id)
        self.assertEqual(result.run_id, self.identity.run_id)
        self.assertEqual(result.dispatch_identity_sha256, self.identity.identity_sha256)

        expected_replay = build_replay_reservation(
            self.binding,
            self.generation,
            self.request.envelope.nonce,
            request_timestamp=self.now,
            max_request_age_seconds=MAX_REPLAY_RESERVATION_SECONDS,
        )
        self.assertEqual(result.replay_reservation_key, expected_replay.key)
        self.assertEqual(result.replay_expires_at, expected_replay.expires_at)

    def test_semantic_tamper_fails_before_credential_resolution(self) -> None:
        tampered = self.payload.replace(
            self.identity.job_id.encode("ascii"),
            b"job_stage4creceiver99",
        )
        with self.assertRaises(AuthenticatedDispatchReceiverError):
            self.accept(body=tampered)
        self.assertEqual(self.resolver_calls, 0)

    def test_generation_proof_failure_does_not_consume_replay(self) -> None:
        headers = self.replace_header(
            self.wire.headers,
            "x-scoremosaic-request-signature",
            "0" * 64,
        )
        with self.assertRaises(AuthenticatedDispatchReceiverError) as context:
            self.accept(headers=headers)
        self.assertEqual(
            context.exception.category,
            "dispatch_receiver_generation_signature_invalid",
        )
        self.assertTrue(self.accept().replay_reserved)

    def test_exact_replay_is_rejected_durably(self) -> None:
        self.accept()
        with self.assertRaises(AuthenticatedDispatchReceiverError) as context:
            self.accept()
        self.assertEqual(context.exception.category, "dispatch_receiver_replay_detected")

    def test_duplicate_missing_and_unexpected_headers_fail_closed(self) -> None:
        with self.assertRaises(AuthenticatedDispatchReceiverError):
            self.accept(headers=self.wire.headers[:-1])
        duplicated = list(self.wire.headers)
        duplicated[-1] = (duplicated[0][0].upper(), duplicated[-1][1])
        with self.assertRaises(AuthenticatedDispatchReceiverError):
            self.accept(headers=tuple(duplicated))
        unexpected = list(self.wire.headers)
        unexpected[-1] = ("x-scoremosaic-unexpected", unexpected[-1][1])
        with self.assertRaises(AuthenticatedDispatchReceiverError):
            self.accept(headers=tuple(unexpected))

    def test_wrong_generation_and_backend_diagnostic_fail_closed(self) -> None:
        headers = self.replace_header(
            self.wire.headers,
            "x-scoremosaic-credential-generation",
            "gen-unknown",
        )
        with self.assertRaises(AuthenticatedDispatchReceiverError) as context:
            self.accept(headers=headers)
        self.assertEqual(context.exception.category, "dispatch_receiver_generation_unknown")

        sensitive = "TOKEN_DO_NOT_LEAK /private/credential/path"
        def exploding(_key, _generation):
            raise RuntimeError(sensitive)
        with self.assertRaises(AuthenticatedDispatchReceiverError) as context:
            self.accept(resolver=exploding)
        self.assertEqual(context.exception.category, "dispatch_receiver_credential_unavailable")
        self.assertNotIn(sensitive, str(context.exception))

    def test_stale_request_fails_before_replay(self) -> None:
        with self.assertRaises(AuthenticatedDispatchReceiverError) as context:
            self.accept(now=self.now + 121)
        self.assertEqual(context.exception.category, "dispatch_receiver_timestamp_expired")
        self.assertTrue(self.accept().replay_reserved)

    def test_cross_engine_payload_is_rejected_before_secret_resolution(self) -> None:
        other_engine = next(
            candidate for candidate in ("audiveris", "homr", "clarity")
            if candidate != ENGINE
        )
        other_payload = dispatch_identity_payload(build_dispatch_identity(self.plan, other_engine))
        with self.assertRaises(AuthenticatedDispatchReceiverError):
            self.accept(body=other_payload)
        self.assertEqual(self.resolver_calls, 0)

    def test_previous_generation_is_bounded_by_rotation_grace(self) -> None:
        previous_generation = "gen-stage4c-previous"
        previous_secret = secrets.token_bytes(32)
        previous_credential = resolve_engine_credential_generation(
            self.binding,
            previous_generation,
            lambda key, generation: (
                previous_secret
                if key == self.binding.credential_key and generation == previous_generation
                else None
            ),
        )
        previous_request = sign_rotation_authenticated_request(
            build_rotation_set(
                current=previous_credential,
                previous=None,
                rotation_started_at=self.now - 20,
                previous_valid_until=None,
            ),
            method=self.target.method,
            path=self.target.path,
            timestamp=self.now,
            nonce="abcdef0123456789abcdef0123456789",
            payload=self.payload,
            now_seconds=self.now,
        )
        previous_wire = serialize_controlled_staging_dispatch_wire(
            target=self.target,
            request=previous_request,
            payload=self.payload,
        )
        receiver_rotation = ReceiverCredentialRotation(
            current_generation_id=self.generation,
            current_activated_at=self.now - 10,
            previous_generation_id=previous_generation,
            previous_valid_until=self.now + 100,
        )
        resolver = lambda key, generation: (
            previous_secret
            if key == self.binding.credential_key and generation == previous_generation
            else self.secret
            if key == self.binding.credential_key and generation == self.generation
            else None
        )
        result = accept_authenticated_dispatch(
            authority=self.authority,
            rotation=receiver_rotation,
            headers=previous_wire.headers,
            body=self.payload,
            observed_method="POST",
            observed_path="/internal/transcribe",
            now_seconds=self.now,
            credential_resolver=resolver,
        )
        self.assertEqual(result.credential_generation_id, previous_generation)

        later_authority = EngineReceiverAuthority(
            root=Path(self.temp.name) / "receiver-authority-later",
            integrity_key=secrets.token_bytes(32),
        )
        later_authority.register_trusted_plan(
            job_id=self.identity.job_id,
            canonical_plan_bytes=canonical_orchestration_plan_bytes(self.plan),
        )
        with self.assertRaises(AuthenticatedDispatchReceiverError) as context:
            accept_authenticated_dispatch(
                authority=later_authority,
                rotation=receiver_rotation,
                headers=previous_wire.headers,
                body=self.payload,
                observed_method="POST",
                observed_path="/internal/transcribe",
                now_seconds=self.now + 100,
                credential_resolver=resolver,
            )
        self.assertEqual(context.exception.category, "dispatch_receiver_generation_expired")

    def test_concurrent_exact_dispatch_has_one_authoritative_winner(self) -> None:
        def attempt(_index: int) -> str:
            try:
                self.accept()
                return "accepted"
            except AuthenticatedDispatchReceiverError as exc:
                return exc.category
        with ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = list(pool.map(attempt, range(8)))
        self.assertEqual(outcomes.count("accepted"), 1)
        self.assertEqual(outcomes.count("dispatch_receiver_replay_detected"), 7)

    def test_safe_result_redacts_secret_nonce_signatures_and_payload(self) -> None:
        safe = self.accept().as_safe_dict()
        rendered = repr(safe)
        for sensitive in (
            self.secret.hex(),
            self.request.envelope.nonce,
            self.request.envelope.signature,
            self.request.generation_signature,
            self.payload.decode("ascii"),
        ):
            self.assertNotIn(sensitive, rendered)
        self.assertFalse(safe["engineExecutionAllowed"])
        self.assertFalse(safe["sourceAccessAllowed"])


if __name__ == "__main__":
    unittest.main()
