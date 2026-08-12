from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import replace
import hashlib
from pathlib import Path
import sys
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_gateway.config import EngineEndpoint
from scoremosaic_gateway.dispatch_identity import (
    DISPATCH_IDENTITY_CONTRACT_VERSION,
    DISPATCH_RESULT_IDENTITY_CONTRACT_VERSION,
    DispatchIdentityError,
    build_dispatch_identity,
    build_dispatch_result_identity,
    dispatch_identity_payload,
    require_authenticated_dispatch_identity,
    require_dispatch_result_identity,
)
from scoremosaic_gateway.dispatch_target import (
    APPROVED_ENGINE_ORIGINS,
    build_engine_dispatch_target,
    sign_authenticated_dispatch_request,
)
from scoremosaic_gateway.orchestration import build_orchestration_plan
from scoremosaic_gateway.service_auth import (
    EngineCredential,
    MIN_CREDENTIAL_BYTES,
    build_engine_auth_binding,
)


class _SwitchingPlanMapping(Mapping):
    """Expose a different valid mapping snapshot on each top-level iteration."""

    def __init__(self, first: dict, second: dict) -> None:
        self._snapshots = (first, second)
        self._iteration = 0
        self._active = first

    def __iter__(self):
        index = min(self._iteration, len(self._snapshots) - 1)
        self._active = self._snapshots[index]
        self._iteration += 1
        return iter(self._active)

    def __len__(self) -> int:
        return len(self._active)

    def __getitem__(self, key):
        return self._active[key]


class DispatchIdentityContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.endpoints = {
            engine: EngineEndpoint(engine, origin)
            for engine, origin in APPROVED_ENGINE_ORIGINS["staging"].items()
        }
        self.plan = build_orchestration_plan(
            "job_c2cbind01",
            source_artifact_ref="sources/job_c2cbind01/source.pdf",
            source_sha256="1" * 64,
            source_size_bytes=4096,
            source_media_type="application/pdf",
        ).as_dict()

    def _credential(self, engine: str) -> EngineCredential:
        binding = build_engine_auth_binding(self.endpoints[engine], "staging")
        return EngineCredential(binding=binding, _secret=b"K" * MIN_CREDENTIAL_BYTES)

    def _signed_request(self, engine: str, payload: bytes):
        credential = self._credential(engine)
        target = build_engine_dispatch_target(
            credential.binding,
            self.endpoints[engine],
        )
        envelope = sign_authenticated_dispatch_request(
            credential,
            self.endpoints[engine],
            timestamp=1_700_000_000,
            nonce={
                "audiveris": "a" * 32,
                "homr": "b" * 32,
                "clarity": "c" * 32,
            }[engine],
            payload=payload,
        )
        return target, envelope

    def test_each_planned_engine_has_one_deterministic_identity_payload(self) -> None:
        for engine in ("audiveris", "homr", "clarity"):
            with self.subTest(engine=engine):
                identity = build_dispatch_identity(self.plan, engine)
                payload = dispatch_identity_payload(identity)
                rebuilt = build_dispatch_identity(deepcopy(self.plan), engine)

                self.assertEqual(identity.version, DISPATCH_IDENTITY_CONTRACT_VERSION)
                self.assertEqual(identity.engine, engine)
                self.assertEqual(identity.job_id, self.plan["jobId"])
                self.assertEqual(identity.plan_id, self.plan["planId"])
                self.assertEqual(identity.plan_sha256, self.plan["planSha256"])
                self.assertEqual(identity.source_sha256, "1" * 64)
                self.assertEqual(payload, dispatch_identity_payload(rebuilt))
                self.assertEqual(identity.identity_sha256, rebuilt.identity_sha256)

    def test_plan_is_snapshotted_once_before_verification_and_derivation(self) -> None:
        other_plan = build_orchestration_plan(
            "job_c2cbind02",
            source_artifact_ref="sources/job_c2cbind02/source.pdf",
            source_sha256="2" * 64,
            source_size_bytes=8192,
            source_media_type="application/pdf",
        ).as_dict()
        switching = _SwitchingPlanMapping(self.plan, other_plan)

        identity = build_dispatch_identity(switching, "homr")

        self.assertEqual(identity.job_id, self.plan["jobId"])
        self.assertEqual(identity.plan_id, self.plan["planId"])
        self.assertEqual(identity.source_sha256, self.plan["sourceArtifact"]["sha256"])

    def test_signed_identity_payload_matches_exact_plan_run(self) -> None:
        identity = build_dispatch_identity(self.plan, "homr")
        payload = dispatch_identity_payload(identity)
        target, envelope = self._signed_request("homr", payload)

        verified = require_authenticated_dispatch_identity(
            self.plan,
            target,
            envelope,
            payload,
        )

        self.assertEqual(verified, identity)

    def test_signed_body_from_other_job_is_rejected(self) -> None:
        other_plan = build_orchestration_plan(
            "job_c2cbind02",
            source_artifact_ref="sources/job_c2cbind02/source.pdf",
            source_sha256="1" * 64,
            source_size_bytes=4096,
            source_media_type="application/pdf",
        ).as_dict()
        payload = dispatch_identity_payload(
            build_dispatch_identity(other_plan, "homr")
        )
        target, envelope = self._signed_request("homr", payload)

        with self.assertRaisesRegex(
            DispatchIdentityError,
            "dispatch_identity_payload_mismatch",
        ):
            require_authenticated_dispatch_identity(
                self.plan,
                target,
                envelope,
                payload,
            )

    def test_source_sha_swap_is_rejected_even_when_payload_is_signed(self) -> None:
        identity = build_dispatch_identity(self.plan, "homr")
        forged = replace(identity, source_sha256="2" * 64)
        payload = dispatch_identity_payload(forged)
        target, envelope = self._signed_request("homr", payload)

        with self.assertRaisesRegex(
            DispatchIdentityError,
            "dispatch_identity_payload_mismatch",
        ):
            require_authenticated_dispatch_identity(
                self.plan,
                target,
                envelope,
                payload,
            )

    def test_cross_engine_run_identity_is_rejected(self) -> None:
        clarity_identity = build_dispatch_identity(self.plan, "clarity")
        payload = dispatch_identity_payload(clarity_identity)
        target, envelope = self._signed_request("homr", payload)

        with self.assertRaisesRegex(
            DispatchIdentityError,
            "dispatch_identity_payload_mismatch",
        ):
            require_authenticated_dispatch_identity(
                self.plan,
                target,
                envelope,
                payload,
            )

    def test_run_candidate_and_artifact_swaps_are_rejected(self) -> None:
        homr = build_dispatch_identity(self.plan, "homr")
        clarity = build_dispatch_identity(self.plan, "clarity")
        forged_variants = (
            replace(homr, run_id=clarity.run_id),
            replace(
                homr,
                candidate_id=clarity.candidate_id,
                candidate_namespace=(
                    f"candidates/{homr.job_id}/homr/{clarity.candidate_id}"
                ),
            ),
            replace(homr, musicxml_artifact_id=clarity.musicxml_artifact_id),
            replace(homr, diagnostic_artifact_id=clarity.diagnostic_artifact_id),
        )

        for forged in forged_variants:
            with self.subTest(forged=forged):
                payload = dispatch_identity_payload(forged)
                target, envelope = self._signed_request("homr", payload)
                with self.assertRaisesRegex(
                    DispatchIdentityError,
                    "dispatch_identity_payload_mismatch",
                ):
                    require_authenticated_dispatch_identity(
                        self.plan,
                        target,
                        envelope,
                        payload,
                    )

    def test_malformed_identifier_and_duplicate_artifact_identity_fail_closed(self) -> None:
        identity = build_dispatch_identity(self.plan, "homr")

        with self.assertRaisesRegex(DispatchIdentityError, "run_id_invalid"):
            dispatch_identity_payload(replace(identity, run_id="run_bad"))

        with self.assertRaisesRegex(
            DispatchIdentityError,
            "artifact_identity_collision",
        ):
            dispatch_identity_payload(
                replace(
                    identity,
                    diagnostic_artifact_id=identity.musicxml_artifact_id,
                )
            )

    def test_tampered_orchestration_plan_is_rejected_before_identity_build(self) -> None:
        tampered = deepcopy(self.plan)
        tampered["sourceArtifact"]["sha256"] = "2" * 64

        with self.assertRaisesRegex(
            DispatchIdentityError,
            "orchestration_plan_invalid",
        ):
            build_dispatch_identity(tampered, "homr")

    def test_envelope_payload_digest_mismatch_is_rejected(self) -> None:
        identity = build_dispatch_identity(self.plan, "homr")
        payload = dispatch_identity_payload(identity)
        target, envelope = self._signed_request("homr", payload)

        with self.assertRaisesRegex(
            DispatchIdentityError,
            "authenticated_payload_digest_mismatch",
        ):
            require_authenticated_dispatch_identity(
                self.plan,
                target,
                replace(envelope, payload_sha256="f" * 64),
                payload,
            )

    def test_result_identity_is_authenticated_and_binds_exact_result_bytes(self) -> None:
        credential = self._credential("audiveris")
        identity = build_dispatch_identity(self.plan, "audiveris")
        result_payload = b"immutable-engine-result"
        result = build_dispatch_result_identity(
            credential,
            identity,
            result_payload,
        )

        self.assertEqual(
            result.version,
            DISPATCH_RESULT_IDENTITY_CONTRACT_VERSION,
        )
        self.assertTrue(result.signature)
        self.assertNotIn("signature", result.as_safe_dict())
        self.assertTrue(result.as_safe_dict()["signaturePresent"])
        require_dispatch_result_identity(
            credential,
            identity,
            result,
            result_payload,
        )

    def test_result_from_other_run_is_rejected(self) -> None:
        homr = build_dispatch_identity(self.plan, "homr")
        clarity = build_dispatch_identity(self.plan, "clarity")
        clarity_credential = self._credential("clarity")
        clarity_result = build_dispatch_result_identity(
            clarity_credential,
            clarity,
            b"clarity-result",
        )

        with self.assertRaisesRegex(
            DispatchIdentityError,
            "result_dispatch_identity_mismatch",
        ):
            require_dispatch_result_identity(
                self._credential("homr"),
                homr,
                clarity_result,
                b"clarity-result",
            )

    def test_result_artifact_identity_tamper_is_rejected(self) -> None:
        credential = self._credential("homr")
        homr = build_dispatch_identity(self.plan, "homr")
        result_payload = b"homr-result"
        result = build_dispatch_result_identity(credential, homr, result_payload)
        clarity = build_dispatch_identity(self.plan, "clarity")

        with self.assertRaisesRegex(
            DispatchIdentityError,
            "result_artifact_identity_mismatch",
        ):
            require_dispatch_result_identity(
                credential,
                homr,
                replace(
                    result,
                    musicxml_artifact_id=clarity.musicxml_artifact_id,
                ),
                result_payload,
            )

    def test_result_payload_tamper_is_rejected(self) -> None:
        credential = self._credential("clarity")
        identity = build_dispatch_identity(self.plan, "clarity")
        result = build_dispatch_result_identity(
            credential,
            identity,
            b"original-result",
        )

        with self.assertRaisesRegex(
            DispatchIdentityError,
            "result_payload_digest_mismatch",
        ):
            require_dispatch_result_identity(
                credential,
                identity,
                result,
                b"tampered-result",
            )

    def test_recomputed_result_digest_without_valid_mac_is_rejected(self) -> None:
        credential = self._credential("homr")
        identity = build_dispatch_identity(self.plan, "homr")
        result = build_dispatch_result_identity(
            credential,
            identity,
            b"original-result",
        )
        tampered_payload = b"attacker-replacement"
        forged = replace(
            result,
            result_payload_bytes=len(tampered_payload),
            result_payload_sha256=hashlib.sha256(tampered_payload).hexdigest(),
        )

        with self.assertRaisesRegex(
            DispatchIdentityError,
            "result_signature_invalid",
        ):
            require_dispatch_result_identity(
                credential,
                identity,
                forged,
                tampered_payload,
            )

    def test_result_signature_tamper_is_rejected(self) -> None:
        credential = self._credential("homr")
        identity = build_dispatch_identity(self.plan, "homr")
        payload = b"homr-result"
        result = build_dispatch_result_identity(credential, identity, payload)

        with self.assertRaisesRegex(
            DispatchIdentityError,
            "result_signature_invalid",
        ):
            require_dispatch_result_identity(
                credential,
                identity,
                replace(result, signature="f" * 64),
                payload,
            )

    def test_cross_engine_result_credential_is_rejected(self) -> None:
        homr = build_dispatch_identity(self.plan, "homr")
        payload = b"homr-result"

        with self.assertRaisesRegex(
            DispatchIdentityError,
            "credential_engine_mismatch",
        ):
            build_dispatch_result_identity(
                self._credential("clarity"),
                homr,
                payload,
            )


if __name__ == "__main__":
    unittest.main()
