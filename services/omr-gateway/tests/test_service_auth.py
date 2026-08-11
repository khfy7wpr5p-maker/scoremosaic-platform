from __future__ import annotations

from dataclasses import replace
import sys
from pathlib import Path
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_gateway.config import EngineEndpoint
from scoremosaic_gateway.service_auth import (
    AUTH_CONTRACT_VERSION,
    CALLER_SERVICE_IDENTITY,
    ENGINE_SERVICE_IDENTITIES,
    MAX_CREDENTIAL_BYTES,
    MIN_CREDENTIAL_BYTES,
    ServiceAuthError,
    build_engine_auth_binding,
    require_binding_for_endpoint,
    resolve_engine_credential,
)


class ServiceAuthContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.endpoints = {
            "audiveris": EngineEndpoint(
                "audiveris", "http://audiveris-foundation:8082"
            ),
            "homr": EngineEndpoint("homr", "http://homr-foundation:8080"),
            "clarity": EngineEndpoint(
                "clarity", "http://clarity-foundation:8081"
            ),
        }

    def test_each_engine_has_distinct_identity_and_credential_key(self) -> None:
        bindings = [
            build_engine_auth_binding(endpoint, "staging")
            for endpoint in self.endpoints.values()
        ]

        self.assertEqual(
            {binding.engine for binding in bindings},
            set(ENGINE_SERVICE_IDENTITIES),
        )
        self.assertEqual(
            {binding.audience_identity for binding in bindings},
            set(ENGINE_SERVICE_IDENTITIES.values()),
        )
        self.assertEqual(len({binding.credential_key for binding in bindings}), 3)
        for binding in bindings:
            self.assertEqual(binding.version, AUTH_CONTRACT_VERSION)
            self.assertEqual(binding.caller_identity, CALLER_SERVICE_IDENTITY)
            self.assertEqual(binding.environment, "staging")

    def test_environment_is_part_of_credential_binding(self) -> None:
        endpoint = self.endpoints["homr"]
        staging = build_engine_auth_binding(endpoint, "staging")
        production = build_engine_auth_binding(endpoint, "production")

        self.assertNotEqual(staging.credential_key, production.credential_key)

    def test_unknown_engine_is_rejected(self) -> None:
        with self.assertRaisesRegex(ServiceAuthError, "engine_not_allowed"):
            build_engine_auth_binding(
                EngineEndpoint("unknown", "http://unknown-foundation:8099"),
                "staging",
            )

    def test_unknown_or_normalized_environment_is_not_accepted(self) -> None:
        endpoint = self.endpoints["homr"]
        for environment in ("", "dev", "STAGING", " staging "):
            with self.subTest(environment=environment):
                with self.assertRaisesRegex(
                    ServiceAuthError, "environment_not_allowed"
                ):
                    build_engine_auth_binding(endpoint, environment)

    def test_cross_engine_binding_is_rejected(self) -> None:
        homr_binding = build_engine_auth_binding(
            self.endpoints["homr"], "staging"
        )

        with self.assertRaisesRegex(
            ServiceAuthError, "engine_identity_mismatch"
        ):
            require_binding_for_endpoint(
                homr_binding,
                self.endpoints["audiveris"],
            )

    def test_caller_and_audience_tampering_is_rejected(self) -> None:
        endpoint = self.endpoints["clarity"]
        binding = build_engine_auth_binding(endpoint, "staging")

        with self.assertRaisesRegex(
            ServiceAuthError, "caller_identity_mismatch"
        ):
            require_binding_for_endpoint(
                replace(binding, caller_identity="other-caller"), endpoint
            )

        with self.assertRaisesRegex(
            ServiceAuthError, "audience_identity_mismatch"
        ):
            require_binding_for_endpoint(
                replace(binding, audience_identity="other-audience"), endpoint
            )

    def test_contract_version_tampering_is_rejected(self) -> None:
        endpoint = self.endpoints["audiveris"]
        binding = build_engine_auth_binding(endpoint, "staging")

        with self.assertRaisesRegex(
            ServiceAuthError, "auth_contract_version_mismatch"
        ):
            require_binding_for_endpoint(
                replace(binding, version="scoremosaic-s2s-auth-v0"), endpoint
            )

    def test_missing_credential_fails_closed(self) -> None:
        binding = build_engine_auth_binding(
            self.endpoints["homr"], "staging"
        )

        with self.assertRaisesRegex(
            ServiceAuthError, "credential_unavailable"
        ):
            resolve_engine_credential(binding, lambda key: None)

    def test_provider_exception_does_not_leak_provider_message(self) -> None:
        binding = build_engine_auth_binding(
            self.endpoints["homr"], "staging"
        )
        leaked_value = "super-secret-provider-message"

        def resolver(key: str) -> bytes:
            raise RuntimeError(leaked_value)

        with self.assertRaises(ServiceAuthError) as context:
            resolve_engine_credential(binding, resolver)

        self.assertEqual(context.exception.category, "credential_unavailable")
        self.assertNotIn(leaked_value, str(context.exception))

    def test_invalid_credential_type_and_length_are_rejected(self) -> None:
        binding = build_engine_auth_binding(
            self.endpoints["homr"], "staging"
        )
        invalid_values = (
            "not-bytes",
            b"x" * (MIN_CREDENTIAL_BYTES - 1),
            b"x" * (MAX_CREDENTIAL_BYTES + 1),
        )

        for value in invalid_values:
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaisesRegex(
                    ServiceAuthError, "credential_invalid"
                ):
                    resolve_engine_credential(binding, lambda key, v=value: v)

    def test_valid_credential_is_scoped_and_repr_is_redacted(self) -> None:
        binding = build_engine_auth_binding(
            self.endpoints["audiveris"], "staging"
        )
        secret = b"A" * MIN_CREDENTIAL_BYTES
        requested_keys: list[str] = []

        def resolver(key: str) -> bytes:
            requested_keys.append(key)
            return secret

        credential = resolve_engine_credential(binding, resolver)

        self.assertEqual(requested_keys, [binding.credential_key])
        self.assertEqual(credential.binding, binding)
        self.assertEqual(credential.secret_bytes_for_transport(), secret)
        self.assertNotIn(secret.decode("ascii"), repr(credential))
        self.assertIn("<redacted>", repr(credential))

    def test_safe_diagnostic_metadata_contains_no_secret_material(self) -> None:
        binding = build_engine_auth_binding(
            self.endpoints["clarity"], "staging"
        )
        secret = b"Z" * MIN_CREDENTIAL_BYTES
        credential = resolve_engine_credential(binding, lambda key: secret)

        metadata = credential.binding.as_safe_dict()
        serialized = repr(metadata)
        self.assertNotIn(secret.decode("ascii"), serialized)
        self.assertEqual(metadata["engine"], "clarity")
        self.assertEqual(metadata["environment"], "staging")


if __name__ == "__main__":
    unittest.main()
