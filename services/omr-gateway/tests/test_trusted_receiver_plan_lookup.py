from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sys
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_gateway.config import EngineEndpoint
from scoremosaic_gateway.credential_rotation import (
    build_rotation_set,
    resolve_engine_credential_generation,
    sign_rotation_authenticated_request,
)
from scoremosaic_gateway.dispatch_identity import (
    DISPATCH_IDENTITY_CONTRACT_VERSION,
    build_dispatch_identity,
    dispatch_identity_payload,
)
from scoremosaic_gateway.dispatch_target import (
    APPROVED_ENGINE_ORIGINS,
    build_engine_dispatch_target,
)
from scoremosaic_gateway.orchestration import build_orchestration_plan
from scoremosaic_gateway.receiver_verification import verify_receiver_dispatch_request
from scoremosaic_gateway.service_auth import (
    MIN_CREDENTIAL_BYTES,
    build_engine_auth_binding,
)
from scoremosaic_gateway.trusted_receiver_plan_lookup import (
    ReceiverPlanLookupHint,
    TrustedReceiverPlanLookupError,
    TrustedReceiverPlanResolution,
    parse_receiver_plan_lookup_hint,
    resolve_trusted_receiver_plan,
)


class TrustedReceiverPlanLookupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = build_orchestration_plan(
            "job_receiverlookup01",
            source_artifact_ref="sources/job_receiverlookup01/source.pdf",
            source_sha256="9" * 64,
            source_size_bytes=8192,
            source_media_type="application/pdf",
        ).as_dict()
        self.engine = "homr"
        self.identity = build_dispatch_identity(self.plan, self.engine)
        self.payload = dispatch_identity_payload(self.identity)
        self.resolver_calls: list[ReceiverPlanLookupHint] = []

    def resolver(self, hint: ReceiverPlanLookupHint):
        self.resolver_calls.append(hint)
        return deepcopy(self.plan)

    def test_hint_is_bounded_untrusted_lookup_evidence_only(self) -> None:
        hint = parse_receiver_plan_lookup_hint(self.payload)
        self.assertEqual(hint.plan_id, self.identity.plan_id)
        self.assertEqual(hint.plan_sha256, self.identity.plan_sha256)
        self.assertEqual(hint.job_id, self.identity.job_id)
        self.assertEqual(hint.run_id, self.identity.run_id)
        self.assertEqual(hint.engine, self.engine)
        self.assertEqual(hint.body_sha256, self.identity.identity_sha256)
        self.assertEqual(hint.body_bytes, len(self.payload))
        self.assertFalse(hint.trusted)
        self.assertFalse(hint.authorization_allowed)
        self.assertFalse(hint.network_dispatch_allowed)
        self.assertFalse(hint.engine_execution_allowed)
        safe = hint.as_safe_dict()
        self.assertFalse(safe["trusted"])
        self.assertFalse(safe["authorizationAllowed"])

    def test_exact_trusted_plan_resolves_once_and_reproduces_complete_body(self) -> None:
        resolution = resolve_trusted_receiver_plan(
            payload=self.payload,
            expected_engine=self.engine,
            resolver=self.resolver,
        )
        self.assertEqual(len(self.resolver_calls), 1)
        self.assertEqual(self.resolver_calls[0], resolution.hint)
        self.assertEqual(resolution.plan_id, self.identity.plan_id)
        self.assertEqual(resolution.plan_sha256, self.identity.plan_sha256)
        self.assertEqual(resolution.job_id, self.identity.job_id)
        self.assertEqual(resolution.run_id, self.identity.run_id)
        self.assertEqual(resolution.engine, self.engine)
        self.assertEqual(
            resolution.dispatch_identity_sha256,
            self.identity.identity_sha256,
        )
        self.assertTrue(resolution.trusted_plan_resolved)
        self.assertFalse(resolution.receiver_authentication_passed)
        self.assertFalse(resolution.network_dispatch_allowed)
        self.assertFalse(resolution.job_state_mutation_allowed)
        self.assertFalse(resolution.engine_execution_allowed)
        restored = resolution.plan_mapping()
        self.assertEqual(restored, self.plan)
        self.assertEqual(
            dispatch_identity_payload(build_dispatch_identity(restored, self.engine)),
            self.payload,
        )

    def test_resolution_plan_mapping_returns_fresh_detached_copy(self) -> None:
        resolution = resolve_trusted_receiver_plan(
            payload=self.payload,
            expected_engine=self.engine,
            resolver=self.resolver,
        )
        first = resolution.plan_mapping()
        first["jobId"] = "job_mutatedcopy01"
        second = resolution.plan_mapping()
        self.assertEqual(second, self.plan)
        self.assertNotEqual(first, second)

    def test_provider_result_is_snapshotted_before_later_caller_mutation(self) -> None:
        returned = deepcopy(self.plan)

        def resolver(hint):
            self.resolver_calls.append(hint)
            return returned

        resolution = resolve_trusted_receiver_plan(
            payload=self.payload,
            expected_engine=self.engine,
            resolver=resolver,
        )
        returned["jobId"] = "job_provider_mutated_after_return"
        self.assertEqual(resolution.plan_mapping(), self.plan)

    def test_duplicate_json_key_and_noncanonical_json_fail_before_resolver(self) -> None:
        text = self.payload.decode("ascii")
        duplicated = text[:-1] + ',"planId":"' + self.identity.plan_id + '"}'
        with self.assertRaises(TrustedReceiverPlanLookupError) as context:
            resolve_trusted_receiver_plan(
                payload=duplicated.encode("ascii"),
                expected_engine=self.engine,
                resolver=self.resolver,
            )
        self.assertEqual(context.exception.category, "receiver_plan_payload_invalid")
        self.assertEqual(self.resolver_calls, [])

        parsed = json.loads(text)
        noncanonical = json.dumps(parsed, indent=2, sort_keys=False).encode("ascii")
        with self.assertRaises(TrustedReceiverPlanLookupError) as context:
            resolve_trusted_receiver_plan(
                payload=noncanonical,
                expected_engine=self.engine,
                resolver=self.resolver,
            )
        self.assertEqual(
            context.exception.category,
            "receiver_plan_payload_not_canonical",
        )
        self.assertEqual(self.resolver_calls, [])

    def test_wrong_identity_version_and_shape_fail_before_resolver(self) -> None:
        parsed = json.loads(self.payload.decode("ascii"))
        parsed["version"] = "other"
        wrong_version = json.dumps(
            parsed,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
        with self.assertRaises(TrustedReceiverPlanLookupError) as context:
            resolve_trusted_receiver_plan(
                payload=wrong_version,
                expected_engine=self.engine,
                resolver=self.resolver,
            )
        self.assertEqual(
            context.exception.category,
            "receiver_plan_identity_version_invalid",
        )
        self.assertEqual(self.resolver_calls, [])

        parsed = json.loads(self.payload.decode("ascii"))
        parsed["extra"] = True
        extra = json.dumps(
            parsed,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
        with self.assertRaises(TrustedReceiverPlanLookupError) as context:
            resolve_trusted_receiver_plan(
                payload=extra,
                expected_engine=self.engine,
                resolver=self.resolver,
            )
        self.assertEqual(context.exception.category, "receiver_plan_payload_shape_invalid")
        self.assertEqual(self.resolver_calls, [])

    def test_cross_engine_hint_fails_before_provider_lookup(self) -> None:
        with self.assertRaises(TrustedReceiverPlanLookupError) as context:
            resolve_trusted_receiver_plan(
                payload=self.payload,
                expected_engine="clarity",
                resolver=self.resolver,
            )
        self.assertEqual(context.exception.category, "receiver_plan_engine_mismatch")
        self.assertEqual(self.resolver_calls, [])

    def test_missing_and_throwing_provider_fail_closed_without_detail_leakage(self) -> None:
        with self.assertRaises(TrustedReceiverPlanLookupError) as context:
            resolve_trusted_receiver_plan(
                payload=self.payload,
                expected_engine=self.engine,
                resolver=lambda hint: None,
            )
        self.assertEqual(context.exception.category, "trusted_receiver_plan_unavailable")

        leaked = "private-provider-diagnostic"

        def exploding(hint):
            raise RuntimeError(leaked)

        with self.assertRaises(TrustedReceiverPlanLookupError) as context:
            resolve_trusted_receiver_plan(
                payload=self.payload,
                expected_engine=self.engine,
                resolver=exploding,
            )
        self.assertEqual(context.exception.category, "trusted_receiver_plan_unavailable")
        self.assertNotIn(leaked, str(context.exception))

    def test_malformed_or_different_trusted_plan_cannot_authorize_body(self) -> None:
        malformed = deepcopy(self.plan)
        malformed["boundaries"]["networkDispatchEnabled"] = True
        with self.assertRaises(TrustedReceiverPlanLookupError) as context:
            resolve_trusted_receiver_plan(
                payload=self.payload,
                expected_engine=self.engine,
                resolver=lambda hint: malformed,
            )
        self.assertEqual(context.exception.category, "trusted_receiver_plan_invalid")

        other = build_orchestration_plan(
            "job_receiverlookup02",
            source_artifact_ref="sources/job_receiverlookup02/source.pdf",
            source_sha256="a" * 64,
            source_size_bytes=8192,
            source_media_type="application/pdf",
        ).as_dict()
        with self.assertRaises(TrustedReceiverPlanLookupError) as context:
            resolve_trusted_receiver_plan(
                payload=self.payload,
                expected_engine=self.engine,
                resolver=lambda hint: other,
            )
        self.assertEqual(context.exception.category, "trusted_receiver_plan_mismatch")

    def test_valid_plan_for_same_job_but_different_timeout_cannot_match_body(self) -> None:
        different = build_orchestration_plan(
            self.plan["jobId"],
            source_artifact_ref=self.plan["sourceArtifact"]["artifactRef"],
            source_sha256=self.plan["sourceArtifact"]["sha256"],
            source_size_bytes=self.plan["sourceArtifact"]["sizeBytes"],
            source_media_type=self.plan["sourceArtifact"]["mediaType"],
            timeout_seconds_by_engine={"homr": 120},
        ).as_dict()
        with self.assertRaises(TrustedReceiverPlanLookupError) as context:
            resolve_trusted_receiver_plan(
                payload=self.payload,
                expected_engine=self.engine,
                resolver=lambda hint: different,
            )
        self.assertEqual(context.exception.category, "trusted_receiver_plan_mismatch")

    def test_hint_value_tamper_can_drive_lookup_but_never_pass_trusted_convergence(self) -> None:
        parsed = json.loads(self.payload.decode("ascii"))
        parsed["planSha256"] = "0" * 64
        tampered = json.dumps(
            parsed,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
        seen: list[ReceiverPlanLookupHint] = []

        def resolver(hint):
            seen.append(hint)
            return deepcopy(self.plan)

        with self.assertRaises(TrustedReceiverPlanLookupError) as context:
            resolve_trusted_receiver_plan(
                payload=tampered,
                expected_engine=self.engine,
                resolver=resolver,
            )
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0].plan_sha256, "0" * 64)
        self.assertFalse(seen[0].trusted)
        self.assertEqual(context.exception.category, "trusted_receiver_plan_mismatch")

    def test_direct_trusted_resolution_forgery_is_rejected(self) -> None:
        hint = parse_receiver_plan_lookup_hint(self.payload)
        with self.assertRaises(TrustedReceiverPlanLookupError):
            TrustedReceiverPlanResolution(
                version=hint.version,
                hint=hint,
                plan_id=hint.plan_id,
                plan_sha256=hint.plan_sha256,
                job_id=hint.job_id,
                run_id=hint.run_id,
                engine=hint.engine,
                dispatch_identity_sha256=hint.body_sha256,
                canonical_plan_sha256="0" * 64,
                _canonical_plan_json=b"{}",
                _seal=object(),
            )

    def test_result_exact_types_and_safe_authority_boundaries(self) -> None:
        resolution = resolve_trusted_receiver_plan(
            payload=self.payload,
            expected_engine=self.engine,
            resolver=self.resolver,
        )
        safe = resolution.as_safe_dict()
        self.assertTrue(safe["trustedPlanResolved"])
        self.assertFalse(safe["receiverAuthenticationPassed"])
        self.assertFalse(safe["networkDispatchAllowed"])
        self.assertFalse(safe["jobStateMutationAllowed"])
        self.assertFalse(safe["engineExecutionAllowed"])
        with self.assertRaises(TrustedReceiverPlanLookupError):
            replace(resolution, run_id=True)

    def test_resolved_plan_composes_with_existing_c2e_receiver_verification(self) -> None:
        resolution = resolve_trusted_receiver_plan(
            payload=self.payload,
            expected_engine=self.engine,
            resolver=self.resolver,
        )
        endpoint = EngineEndpoint(
            self.engine,
            APPROVED_ENGINE_ORIGINS["staging"][self.engine],
        )
        binding = build_engine_auth_binding(endpoint, "staging")
        target = build_engine_dispatch_target(binding, endpoint)
        generation_id = "gen-2026-08-planlookup"
        timestamp = 1_800_200_000
        secret = b"P" * MIN_CREDENTIAL_BYTES
        credential = resolve_engine_credential_generation(
            binding,
            generation_id,
            lambda credential_key, observed_generation: (
                secret
                if credential_key == binding.credential_key
                and observed_generation == generation_id
                else None
            ),
        )
        rotation = build_rotation_set(
            current=credential,
            previous=None,
            rotation_started_at=timestamp - 1,
            previous_valid_until=None,
        )
        request = sign_rotation_authenticated_request(
            rotation,
            method=target.method,
            path=target.path,
            timestamp=timestamp,
            nonce="1234567890abcdef1234567890abcdef",
            payload=self.payload,
            now_seconds=timestamp,
        )
        verified = verify_receiver_dispatch_request(
            resolution.plan_mapping(),
            target,
            rotation,
            request,
            observed_method="POST",
            observed_path="/internal/transcribe",
            payload=self.payload,
            now_seconds=timestamp,
            replay_checker=lambda binding, generation, nonce, request_timestamp: True,
        )
        self.assertEqual(verified.dispatch_identity, self.identity)
        self.assertEqual(verified.generation_credential.generation_id, generation_id)


if __name__ == "__main__":
    unittest.main()
