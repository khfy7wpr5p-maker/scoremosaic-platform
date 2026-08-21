from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_gateway.dispatch_identity import build_dispatch_identity
from scoremosaic_gateway.dispatch_input_capsule import (
    DISPATCH_INPUT_CAPSULE_VERSION,
    MAX_CAPSULE_SOURCE_CHUNK_BYTES,
    DispatchInputCapsuleError,
    build_dispatch_input_capsule,
    canonical_orchestration_plan_bytes,
    verify_dispatch_input_capsule,
)
from scoremosaic_gateway.orchestration import build_orchestration_plan


class DispatchInputCapsuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = b"%PDF-1.7\nscoremosaic-capsule-source"
        self.source_sha256 = hashlib.sha256(self.source).hexdigest()
        self.plan = build_orchestration_plan(
            "job_capsule01",
            source_artifact_ref="sources/job_capsule01/source.pdf",
            source_sha256=self.source_sha256,
            source_size_bytes=len(self.source),
            source_media_type="application/pdf",
        ).as_dict()
        self.identity = build_dispatch_identity(self.plan, "homr")

    def _capsule(self):
        return build_dispatch_input_capsule(
            self.plan,
            self.identity,
            [self.source[:8], self.source[8:]],
        )

    def test_capsule_is_deterministic_verified_and_non_executable(self) -> None:
        capsule = self._capsule()
        rebuilt = build_dispatch_input_capsule(
            deepcopy(self.plan),
            build_dispatch_identity(deepcopy(self.plan), "homr"),
            [self.source],
        )

        self.assertEqual(capsule.version, DISPATCH_INPUT_CAPSULE_VERSION)
        self.assertEqual(capsule, rebuilt)
        self.assertEqual(verify_dispatch_input_capsule(capsule), self.plan)
        self.assertFalse(capsule.credential_access_allowed)
        self.assertFalse(capsule.replay_side_effect_allowed)
        self.assertFalse(capsule.state_mutation_allowed)
        self.assertFalse(capsule.network_dispatch_allowed)
        self.assertFalse(capsule.engine_execution_allowed)
        self.assertNotIn(self.source.decode("ascii"), repr(capsule))

        safe = capsule.as_safe_dict()
        self.assertNotIn("sourceBytes", safe)
        self.assertNotIn("canonicalPlan", safe)
        self.assertEqual(safe["sourceSizeBytes"], len(self.source))

    def test_exact_canonical_plan_bytes_are_stable(self) -> None:
        first = canonical_orchestration_plan_bytes(self.plan)
        second = canonical_orchestration_plan_bytes(deepcopy(self.plan))

        self.assertEqual(first, second)
        self.assertEqual(
            first,
            json.dumps(
                self.plan,
                ensure_ascii=True,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("ascii"),
        )

    def test_noncanonical_plan_bytes_fail_closed(self) -> None:
        capsule = self._capsule()
        pretty = json.dumps(self.plan, sort_keys=True, indent=2).encode("ascii")

        with self.assertRaisesRegex(DispatchInputCapsuleError, "capsule_plan_not_canonical"):
            verify_dispatch_input_capsule(
                replace(capsule, canonical_plan_bytes=pretty)
            )

    def test_duplicate_json_key_fails_before_plan_trust(self) -> None:
        capsule = self._capsule()
        canonical = capsule.canonical_plan_bytes
        duplicate = (
            b'{"jobId":"'
            + self.plan["jobId"].encode("ascii")
            + b'",'
            + canonical[1:]
        )

        with self.assertRaisesRegex(DispatchInputCapsuleError, "capsule_plan_json_invalid"):
            verify_dispatch_input_capsule(
                replace(capsule, canonical_plan_bytes=duplicate)
            )

    def test_plan_contract_tamper_fails_closed(self) -> None:
        tampered = deepcopy(self.plan)
        tampered["sourceArtifact"]["sha256"] = "f" * 64

        with self.assertRaisesRegex(DispatchInputCapsuleError, "capsule_plan_contract_invalid"):
            canonical_orchestration_plan_bytes(tampered)

    def test_dispatch_identity_must_converge_to_exact_plan(self) -> None:
        other_plan = build_orchestration_plan(
            "job_capsule02",
            source_artifact_ref="sources/job_capsule02/source.pdf",
            source_sha256=self.source_sha256,
            source_size_bytes=len(self.source),
            source_media_type="application/pdf",
        ).as_dict()
        other_identity = build_dispatch_identity(other_plan, "homr")

        with self.assertRaisesRegex(
            DispatchInputCapsuleError,
            "capsule_dispatch_identity_mismatch",
        ):
            build_dispatch_input_capsule(self.plan, other_identity, [self.source])

    def test_source_hash_tamper_fails_closed(self) -> None:
        tampered = bytearray(self.source)
        tampered[-1] ^= 1

        with self.assertRaisesRegex(
            DispatchInputCapsuleError,
            "capsule_source_sha256_mismatch",
        ):
            build_dispatch_input_capsule(
                self.plan,
                self.identity,
                [bytes(tampered)],
            )

    def test_source_signature_must_match_declared_media_type(self) -> None:
        fake_source = b"not-a-pdf-but-same-length-as-source!!"
        fake_source = fake_source[: len(self.source)].ljust(len(self.source), b"x")
        fake_sha256 = hashlib.sha256(fake_source).hexdigest()
        plan = build_orchestration_plan(
            "job_capsule03",
            source_artifact_ref="sources/job_capsule03/source.pdf",
            source_sha256=fake_sha256,
            source_size_bytes=len(fake_source),
            source_media_type="application/pdf",
        ).as_dict()
        identity = build_dispatch_identity(plan, "homr")

        with self.assertRaisesRegex(
            DispatchInputCapsuleError,
            "capsule_source_media_type_mismatch",
        ):
            build_dispatch_input_capsule(plan, identity, [fake_source])

    def test_stream_fails_immediately_when_exact_declared_size_is_exceeded(self) -> None:
        first = self.source[:-1]
        second = b"zz"

        with self.assertRaisesRegex(
            DispatchInputCapsuleError,
            "capsule_source_size_mismatch",
        ):
            build_dispatch_input_capsule(
                self.plan,
                self.identity,
                [first, second],
            )

    def test_stream_rejects_mutable_empty_and_oversized_chunks(self) -> None:
        bad_streams = (
            ([bytearray(self.source)], "capsule_source_chunk_invalid"),
            ([b"", self.source], "capsule_source_chunk_invalid"),
            ([b"x" * (MAX_CAPSULE_SOURCE_CHUNK_BYTES + 1)], "capsule_source_chunk_too_large"),
        )
        for chunks, category in bad_streams:
            with self.subTest(category=category):
                with self.assertRaisesRegex(DispatchInputCapsuleError, category):
                    build_dispatch_input_capsule(self.plan, self.identity, chunks)

    def test_capsule_metadata_tamper_is_rejected(self) -> None:
        capsule = self._capsule()
        variants = (
            replace(capsule, canonical_plan_sha256="f" * 64),
            replace(capsule, source_size_bytes=capsule.source_size_bytes + 1),
            replace(capsule, source_sha256="f" * 64),
            replace(capsule, source_media_type="image/png"),
        )
        expected = (
            "capsule_plan_sha256_mismatch",
            "capsule_source_metadata_mismatch",
            "capsule_source_metadata_mismatch",
            "capsule_source_metadata_mismatch",
        )
        for variant, category in zip(variants, expected, strict=True):
            with self.subTest(category=category):
                with self.assertRaisesRegex(DispatchInputCapsuleError, category):
                    verify_dispatch_input_capsule(variant)


if __name__ == "__main__":
    unittest.main()
