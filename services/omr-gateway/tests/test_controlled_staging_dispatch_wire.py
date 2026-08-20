from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_gateway.app import route_request
from scoremosaic_gateway.config import EngineEndpoint, load_config
from scoremosaic_gateway.controlled_staging_dispatch_wire import (
    ControlledStagingDispatchWireError,
    ControlledStagingDispatchWireRequest,
    WIRE_HEADER_NAMES,
    parse_controlled_staging_dispatch_wire,
    serialize_controlled_staging_dispatch_wire,
)
from scoremosaic_gateway.credential_rotation import (
    build_rotation_set,
    resolve_engine_credential_generation,
    sign_rotation_authenticated_request,
)
from scoremosaic_gateway.dispatch_identity import (
    build_dispatch_identity,
    dispatch_identity_payload,
)
from scoremosaic_gateway.dispatch_target import (
    APPROVED_ENGINE_ORIGINS,
    build_engine_dispatch_target,
)
from scoremosaic_gateway.orchestration import build_orchestration_plan
from scoremosaic_gateway.receiver_verification import (
    ReceiverVerificationError,
    verify_receiver_dispatch_request,
)
from scoremosaic_gateway.service_auth import (
    MIN_CREDENTIAL_BYTES,
    build_engine_auth_binding,
)


class ControlledStagingDispatchWireTests(unittest.TestCase):
    def setUp(self) -> None:
        self.endpoint = EngineEndpoint(
            "homr",
            APPROVED_ENGINE_ORIGINS["staging"]["homr"],
        )
        self.binding = build_engine_auth_binding(self.endpoint, "staging")
        self.target = build_engine_dispatch_target(self.binding, self.endpoint)
        self.timestamp = 1_800_100_000
        self.nonce = "abcdef0123456789abcdef0123456789"
        self.generation_id = "gen-2026-08-wire"
        self.secret = b"W" * MIN_CREDENTIAL_BYTES
        self.credential = resolve_engine_credential_generation(
            self.binding,
            self.generation_id,
            lambda credential_key, generation_id: (
                self.secret
                if credential_key == self.binding.credential_key
                and generation_id == self.generation_id
                else None
            ),
        )
        self.rotation = build_rotation_set(
            current=self.credential,
            previous=None,
            rotation_started_at=self.timestamp - 1,
            previous_valid_until=None,
        )
        self.plan = build_orchestration_plan(
            "job_wirecontract01",
            source_artifact_ref="sources/job_wirecontract01/source.pdf",
            source_sha256="8" * 64,
            source_size_bytes=4096,
            source_media_type="application/pdf",
        ).as_dict()
        self.identity = build_dispatch_identity(self.plan, "homr")
        self.payload = dispatch_identity_payload(self.identity)
        self.request = sign_rotation_authenticated_request(
            self.rotation,
            method=self.target.method,
            path=self.target.path,
            timestamp=self.timestamp,
            nonce=self.nonce,
            payload=self.payload,
            now_seconds=self.timestamp,
        )
        self.wire = serialize_controlled_staging_dispatch_wire(
            target=self.target,
            request=self.request,
            payload=self.payload,
        )

    def _parse(self, *, headers=None, body=None, method="POST", path="/internal/transcribe", target=None):
        return parse_controlled_staging_dispatch_wire(
            target=self.target if target is None else target,
            headers=self.wire.headers if headers is None else headers,
            body=self.payload if body is None else body,
            observed_method=method,
            observed_path=path,
        )

    @staticmethod
    def _replace_header(headers, name: str, value: str):
        return tuple((key, value if key.lower() == name else observed) for key, observed in headers)

    def test_exact_round_trip_reconstructs_generation_bound_request(self) -> None:
        parsed = self._parse()
        self.assertEqual(parsed, self.request)
        self.assertEqual(self.wire.body, self.payload)
        self.assertEqual(tuple(name for name, _ in self.wire.headers), WIRE_HEADER_NAMES)
        self.assertTrue(self.wire.contains_authentication_proof)
        self.assertFalse(self.wire.network_send_allowed)
        self.assertFalse(self.wire.persistence_allowed)
        self.assertFalse(self.wire.logging_allowed)
        self.assertFalse(self.wire.job_state_mutation_allowed)
        self.assertFalse(self.wire.engine_execution_allowed)

    def test_round_trip_is_deterministic_ten_of_ten(self) -> None:
        for attempt in range(10):
            with self.subTest(attempt=attempt + 1):
                observed = serialize_controlled_staging_dispatch_wire(
                    target=self.target,
                    request=self.request,
                    payload=self.payload,
                )
                self.assertEqual(observed, self.wire)
                self.assertEqual(self._parse(headers=observed.headers), self.request)

    def test_wire_repr_and_safe_diagnostics_redact_transport_proofs(self) -> None:
        rendered = repr(self.wire)
        safe = self.wire.as_safe_dict()
        for sensitive in (
            self.nonce,
            self.request.envelope.signature,
            self.request.generation_signature,
            self.secret.decode("ascii"),
            self.payload.decode("ascii"),
        ):
            self.assertNotIn(sensitive, rendered)
            self.assertNotIn(sensitive, repr(safe))
        self.assertTrue(safe["authenticationProofRedacted"])
        self.assertFalse(safe["networkSendAllowed"])
        self.assertFalse(safe["persistenceAllowed"])
        self.assertFalse(safe["loggingAllowed"])

    def test_only_minimal_wire_fields_are_transmitted(self) -> None:
        names = {name.lower() for name, _ in self.wire.headers}
        self.assertEqual(names, set(WIRE_HEADER_NAMES))
        for forbidden_name in (
            "caller",
            "engine",
            "audience",
            "environment",
            "credential-key",
            "method",
            "path",
        ):
            self.assertFalse(any(forbidden_name in name for name in names))
        values = [value for _, value in self.wire.headers]
        self.assertNotIn(self.binding.caller_identity, values)
        self.assertNotIn(self.binding.engine, values)
        self.assertNotIn(self.binding.audience_identity, values)
        self.assertNotIn(self.binding.environment, values)
        self.assertNotIn(self.binding.credential_key, values)

    def test_header_order_and_case_are_not_security_significant(self) -> None:
        reordered = tuple((name.upper(), value) for name, value in reversed(self.wire.headers))
        self.assertEqual(self._parse(headers=reordered), self.request)

    def test_duplicate_missing_and_unexpected_headers_fail_closed(self) -> None:
        headers = list(self.wire.headers)
        headers[1] = (headers[0][0].upper(), headers[1][1])
        with self.assertRaises(ControlledStagingDispatchWireError):
            self._parse(headers=tuple(headers))

        with self.assertRaises(ControlledStagingDispatchWireError):
            self._parse(headers=self.wire.headers[:-1])

        headers = list(self.wire.headers)
        headers[-1] = ("x-scoremosaic-unexpected", headers[-1][1])
        with self.assertRaises(ControlledStagingDispatchWireError):
            self._parse(headers=tuple(headers))

    def test_header_whitespace_control_and_unicode_fail_closed(self) -> None:
        generation_header = WIRE_HEADER_NAMES[0]
        for value in (
            " gen-2026-08-wire",
            "gen-2026-08-wire ",
            "gen-2026-08-wire\n",
            "gén-2026-08-wire",
        ):
            with self.subTest(value=repr(value)):
                headers = self._replace_header(self.wire.headers, generation_header, value)
                with self.assertRaises(ControlledStagingDispatchWireError):
                    self._parse(headers=headers)

    def test_numeric_headers_require_canonical_decimal_encoding(self) -> None:
        timestamp_header = WIRE_HEADER_NAMES[1]
        payload_bytes_header = WIRE_HEADER_NAMES[3]
        for header, value in (
            (timestamp_header, "01"),
            (timestamp_header, "-1"),
            (timestamp_header, "+1"),
            (payload_bytes_header, "0"),
            (payload_bytes_header, "0001"),
            (payload_bytes_header, "999999999999"),
        ):
            with self.subTest(header=header, value=value):
                headers = self._replace_header(self.wire.headers, header, value)
                with self.assertRaises(ControlledStagingDispatchWireError):
                    self._parse(headers=headers)

    def test_payload_size_digest_and_mutability_fail_closed(self) -> None:
        with self.assertRaises(ControlledStagingDispatchWireError):
            self._parse(body=self.payload + b"x")

        digest_header = WIRE_HEADER_NAMES[4]
        headers = self._replace_header(self.wire.headers, digest_header, "0" * 64)
        with self.assertRaises(ControlledStagingDispatchWireError):
            self._parse(headers=headers)

        with self.assertRaises(ControlledStagingDispatchWireError):
            parse_controlled_staging_dispatch_wire(
                target=self.target,
                headers=self.wire.headers,
                body=bytearray(self.payload),
                observed_method="POST",
                observed_path="/internal/transcribe",
            )

    def test_receiver_observed_method_and_path_are_authoritative(self) -> None:
        for method, path in (
            ("GET", "/internal/transcribe"),
            ("POST", "/internal/other"),
        ):
            with self.subTest(method=method, path=path):
                with self.assertRaises(ControlledStagingDispatchWireError) as context:
                    self._parse(method=method, path=path)
                self.assertEqual(context.exception.category, "staging_wire_observed_target_mismatch")

    def test_cross_engine_target_cannot_serialize_existing_request(self) -> None:
        clarity_endpoint = EngineEndpoint(
            "clarity",
            APPROVED_ENGINE_ORIGINS["staging"]["clarity"],
        )
        clarity_binding = build_engine_auth_binding(clarity_endpoint, "staging")
        clarity_target = build_engine_dispatch_target(clarity_binding, clarity_endpoint)
        with self.assertRaises(ControlledStagingDispatchWireError) as context:
            serialize_controlled_staging_dispatch_wire(
                target=clarity_target,
                request=self.request,
                payload=self.payload,
            )
        self.assertEqual(context.exception.category, "staging_wire_target_mismatch")

    def test_parsed_wire_passes_real_receiver_verification(self) -> None:
        parsed = self._parse()
        verified = verify_receiver_dispatch_request(
            self.plan,
            self.target,
            self.rotation,
            parsed,
            observed_method="POST",
            observed_path="/internal/transcribe",
            payload=self.payload,
            now_seconds=self.timestamp,
            replay_checker=lambda binding, generation_id, nonce, timestamp: True,
        )
        self.assertEqual(verified.dispatch_identity, self.identity)
        self.assertEqual(verified.generation_credential.generation_id, self.generation_id)

    def test_structurally_valid_tampered_request_signature_is_rejected_by_receiver(self) -> None:
        signature_header = WIRE_HEADER_NAMES[5]
        headers = self._replace_header(self.wire.headers, signature_header, "0" * 64)
        parsed = self._parse(headers=headers)
        with self.assertRaises(ReceiverVerificationError) as context:
            verify_receiver_dispatch_request(
                self.plan,
                self.target,
                self.rotation,
                parsed,
                observed_method="POST",
                observed_path="/internal/transcribe",
                payload=self.payload,
                now_seconds=self.timestamp,
                replay_checker=lambda binding, generation_id, nonce, timestamp: True,
            )
        # C.2-D authenticates the complete inner C.2-A envelope, including its
        # request signature, so the outer generation proof fails before the inner
        # signature verifier is reached.
        self.assertEqual(context.exception.category, "generation_request_signature_invalid")

    def test_structurally_valid_tampered_generation_signature_is_rejected_by_receiver(self) -> None:
        generation_signature_header = WIRE_HEADER_NAMES[6]
        headers = self._replace_header(
            self.wire.headers,
            generation_signature_header,
            "0" * 64,
        )
        parsed = self._parse(headers=headers)
        with self.assertRaises(ReceiverVerificationError) as context:
            verify_receiver_dispatch_request(
                self.plan,
                self.target,
                self.rotation,
                parsed,
                observed_method="POST",
                observed_path="/internal/transcribe",
                payload=self.payload,
                now_seconds=self.timestamp,
                replay_checker=lambda binding, generation_id, nonce, timestamp: True,
            )
        self.assertEqual(context.exception.category, "generation_request_signature_invalid")

    def test_result_requires_exact_immutable_wire_types(self) -> None:
        with self.assertRaises(ControlledStagingDispatchWireError):
            replace(self.wire, headers=list(self.wire.headers))
        with self.assertRaises(ControlledStagingDispatchWireError):
            replace(self.wire, body=bytearray(self.payload))
        with self.assertRaises(ControlledStagingDispatchWireError):
            replace(self.wire, version="other")

    def test_internal_transcribe_http_route_remains_disabled(self) -> None:
        response = route_request("POST", "/internal/transcribe", load_config({}))
        self.assertEqual(response.status, 405)
        self.assertEqual(response.allow, "GET")
        self.assertEqual(response.payload, {"error": "method_not_allowed"})


if __name__ == "__main__":
    unittest.main()
