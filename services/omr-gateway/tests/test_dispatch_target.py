from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import unittest
from unittest import mock

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_gateway.authenticated_request import sign_authenticated_request
from scoremosaic_gateway.config import EngineEndpoint
from scoremosaic_gateway.dispatch_target import (
    APPROVED_ENGINE_ORIGINS,
    DISPATCH_METHOD,
    DISPATCH_PATH,
    DISPATCH_TARGET_CONTRACT_VERSION,
    DispatchTargetError,
    build_engine_dispatch_target,
    require_envelope_for_dispatch_target,
    sign_authenticated_dispatch_request,
)
from scoremosaic_gateway.service_auth import (
    EngineCredential,
    MIN_CREDENTIAL_BYTES,
    build_engine_auth_binding,
)


class EngineDispatchTargetContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.endpoints = {
            engine: EngineEndpoint(engine, origin)
            for engine, origin in APPROVED_ENGINE_ORIGINS["staging"].items()
        }

    def _credential(self, engine: str, environment: str = "staging") -> EngineCredential:
        binding = build_engine_auth_binding(self.endpoints[engine], environment)
        return EngineCredential(binding=binding, _secret=b"K" * MIN_CREDENTIAL_BYTES)

    def test_each_staging_engine_has_one_exact_non_secret_target(self) -> None:
        for engine, endpoint in self.endpoints.items():
            with self.subTest(engine=engine):
                binding = build_engine_auth_binding(endpoint, "staging")
                target = build_engine_dispatch_target(binding, endpoint)

                self.assertEqual(target.version, DISPATCH_TARGET_CONTRACT_VERSION)
                self.assertEqual(target.engine, engine)
                self.assertEqual(target.origin, endpoint.base_url)
                self.assertEqual(target.method, DISPATCH_METHOD)
                self.assertEqual(target.path, DISPATCH_PATH)
                self.assertEqual(target.environment, "staging")

    def test_unknown_engine_is_rejected(self) -> None:
        endpoint = EngineEndpoint("unknown", "http://unknown-foundation:8099")
        with self.assertRaisesRegex(DispatchTargetError, "engine_not_allowed"):
            build_engine_dispatch_target(
                build_engine_auth_binding(self.endpoints["homr"], "staging"),
                endpoint,
            )

    def test_cross_engine_binding_is_rejected(self) -> None:
        homr_binding = build_engine_auth_binding(self.endpoints["homr"], "staging")

        with self.assertRaisesRegex(
            DispatchTargetError, "engine_identity_mismatch"
        ):
            build_engine_dispatch_target(
                homr_binding,
                self.endpoints["clarity"],
            )

    def test_cross_engine_origin_is_rejected(self) -> None:
        binding = build_engine_auth_binding(self.endpoints["homr"], "staging")
        endpoint = EngineEndpoint(
            "homr",
            self.endpoints["clarity"].base_url,
        )

        with self.assertRaisesRegex(DispatchTargetError, "engine_origin_mismatch"):
            build_engine_dispatch_target(binding, endpoint)

    def test_unknown_hostname_and_wrong_port_are_rejected(self) -> None:
        binding = build_engine_auth_binding(self.endpoints["homr"], "staging")
        invalid = (
            EngineEndpoint("homr", "http://unexpected-foundation:8080"),
            EngineEndpoint("homr", "http://homr-foundation:9999"),
            EngineEndpoint("homr", "https://homr-foundation:8080"),
        )

        for endpoint in invalid:
            with self.subTest(origin=endpoint.base_url):
                with self.assertRaisesRegex(
                    DispatchTargetError, "engine_origin_mismatch"
                ):
                    build_engine_dispatch_target(binding, endpoint)

    def test_unsafe_origin_shapes_are_rejected_before_allowlist_match(self) -> None:
        binding = build_engine_auth_binding(self.endpoints["homr"], "staging")
        invalid = (
            "ftp://homr-foundation:8080",
            "http://user:pass@homr-foundation:8080",
            "http://homr-foundation:8080/internal",
            "http://homr-foundation:8080?route=other",
            "http://homr-foundation:8080#fragment",
            "http://homr-foundation:bad",
        )

        for origin in invalid:
            with self.subTest(origin=origin):
                with self.assertRaisesRegex(
                    DispatchTargetError, "engine_origin_invalid"
                ):
                    build_engine_dispatch_target(
                        binding,
                        EngineEndpoint("homr", origin),
                    )

    def test_production_dispatch_origin_is_deliberately_not_configured(self) -> None:
        endpoint = self.endpoints["audiveris"]
        binding = build_engine_auth_binding(endpoint, "production")

        with self.assertRaisesRegex(
            DispatchTargetError, "dispatch_environment_not_configured"
        ):
            build_engine_dispatch_target(binding, endpoint)

    def test_signing_uses_only_fixed_post_transcribe_target(self) -> None:
        credential = self._credential("clarity")
        envelope = sign_authenticated_dispatch_request(
            credential,
            self.endpoints["clarity"],
            timestamp=1_700_000_000,
            nonce="a" * 32,
            payload=b"immutable-payload",
        )

        self.assertEqual(envelope.method, "POST")
        self.assertEqual(envelope.path, "/internal/transcribe")
        self.assertEqual(envelope.engine, "clarity")

    def test_allowlist_rejection_precedes_secret_read(self) -> None:
        credential = self._credential("homr")
        invalid_endpoint = EngineEndpoint(
            "homr",
            "http://unexpected-foundation:8080",
        )

        with mock.patch.object(
            EngineCredential,
            "secret_bytes_for_transport",
            side_effect=AssertionError("secret must not be read"),
        ):
            with self.assertRaisesRegex(
                DispatchTargetError, "engine_origin_mismatch"
            ):
                sign_authenticated_dispatch_request(
                    credential,
                    invalid_endpoint,
                    timestamp=1_700_000_000,
                    nonce="b" * 32,
                    payload=b"payload",
                )

    def test_signed_envelope_for_other_path_is_rejected_by_target(self) -> None:
        credential = self._credential("audiveris")
        target = build_engine_dispatch_target(
            credential.binding,
            self.endpoints["audiveris"],
        )
        envelope = sign_authenticated_request(
            credential,
            method="POST",
            path="/internal/other",
            timestamp=1_700_000_000,
            nonce="c" * 32,
            payload=b"payload",
        )

        with self.assertRaisesRegex(
            DispatchTargetError, "dispatch_path_mismatch"
        ):
            require_envelope_for_dispatch_target(target, envelope)

    def test_envelope_method_tamper_is_rejected_by_target(self) -> None:
        credential = self._credential("homr")
        target = build_engine_dispatch_target(
            credential.binding,
            self.endpoints["homr"],
        )
        envelope = sign_authenticated_dispatch_request(
            credential,
            self.endpoints["homr"],
            timestamp=1_700_000_000,
            nonce="d" * 32,
            payload=b"payload",
        )

        with self.assertRaisesRegex(
            DispatchTargetError, "dispatch_method_mismatch"
        ):
            require_envelope_for_dispatch_target(
                target,
                replace(envelope, method="GET"),
            )

    def test_envelope_cross_engine_identity_is_rejected_by_target(self) -> None:
        homr = self._credential("homr")
        clarity = self._credential("clarity")
        homr_target = build_engine_dispatch_target(
            homr.binding,
            self.endpoints["homr"],
        )
        clarity_envelope = sign_authenticated_dispatch_request(
            clarity,
            self.endpoints["clarity"],
            timestamp=1_700_000_000,
            nonce="e" * 32,
            payload=b"payload",
        )

        with self.assertRaisesRegex(
            DispatchTargetError, "engine_identity_mismatch"
        ):
            require_envelope_for_dispatch_target(
                homr_target,
                clarity_envelope,
            )

    def test_safe_diagnostics_contain_no_credential_secret(self) -> None:
        credential = self._credential("clarity")
        target = build_engine_dispatch_target(
            credential.binding,
            self.endpoints["clarity"],
        )
        serialized = repr(target.as_safe_dict())

        self.assertNotIn("K" * MIN_CREDENTIAL_BYTES, serialized)
        self.assertEqual(
            target.as_safe_dict()["origin"],
            self.endpoints["clarity"].base_url,
        )


if __name__ == "__main__":
    unittest.main()
