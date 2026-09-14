from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from scripts.polyphonic_teacher_gold_pilot import (
    PILOT_PATH,
    REGISTRY_PATH,
    ROOT,
    TeacherGoldPilotError,
    validate_pilot,
)


SCHEMA_PATH = ROOT / "contracts" / "polyphonic-teacher-gold-pilot-v1.schema.json"


class TeacherGoldPilotTests(unittest.TestCase):
    def _payloads(self) -> tuple[dict[str, object], dict[str, object]]:
        return (
            json.loads(PILOT_PATH.read_text(encoding="utf-8")),
            json.loads(REGISTRY_PATH.read_text(encoding="utf-8")),
        )

    def _validate_mutation(
        self,
        pilot: dict[str, object],
        registry: dict[str, object] | None = None,
    ) -> dict[str, object]:
        if registry is None:
            _, registry = self._payloads()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pilot_path = root / "pilot.json"
            registry_path = root / "registry.json"
            pilot_path.write_text(json.dumps(pilot, ensure_ascii=True), encoding="utf-8")
            registry_path.write_text(json.dumps(registry, ensure_ascii=True), encoding="utf-8")
            return validate_pilot(pilot_path, registry_path=registry_path)

    def test_schema_has_nonempty_defs_and_non_counting_constants(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        self.assertIsInstance(schema.get("$defs"), dict)
        self.assertTrue(schema["$defs"])
        record_props = schema["$defs"]["record"]["properties"]
        self.assertEqual(record_props["teacherVerificationStatus"]["const"], "DRAFT")
        self.assertEqual(record_props["evaluationEligibility"]["const"], "REVIEW_REQUIRED")
        self.assertIs(record_props["countTowardTeacherGoldMinimum"]["const"], False)

    def test_baseline_has_five_real_hash_pairs_but_counts_zero(self) -> None:
        report = validate_pilot()
        self.assertEqual(report["realHashedPairCount"], 5)
        self.assertEqual(report["teacherVerifiedCount"], 0)
        self.assertEqual(report["evaluationEligibleCount"], 0)
        self.assertEqual(report["countedTowardTeacherGoldMinimum"], 0)
        self.assertEqual(report["verifiedRegistryFixtureCount"], 0)
        self.assertEqual(report["readiness"], "NOT_READY")
        self.assertIs(report["temporaryCorpusArchivePersisted"], False)
        self.assertIs(report["productionDecisionAuthority"], False)

    def test_all_pilot_records_remain_draft_review_required_and_non_counting(self) -> None:
        pilot, _ = self._payloads()
        records = pilot["records"]
        self.assertEqual(len(records), 5)
        for record in records:
            self.assertEqual(record["teacherVerificationStatus"], "DRAFT")
            self.assertEqual(record["evaluationEligibility"], "REVIEW_REQUIRED")
            self.assertIs(record["countTowardTeacherGoldMinimum"], False)
            self.assertRegex(record["source"]["sha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(record["gold"]["sha256"], r"^[0-9a-f]{64}$")

    def test_counting_tamper_fails_closed(self) -> None:
        pilot, _ = self._payloads()
        pilot["records"][0]["countTowardTeacherGoldMinimum"] = True
        with self.assertRaisesRegex(TeacherGoldPilotError, "pilot_record_invalid"):
            self._validate_mutation(pilot)

    def test_teacher_verification_cannot_be_claimed_by_pilot(self) -> None:
        pilot, _ = self._payloads()
        pilot["records"][0]["teacherVerificationStatus"] = "VERIFIED"
        with self.assertRaisesRegex(TeacherGoldPilotError, "pilot_record_invalid"):
            self._validate_mutation(pilot)

    def test_rights_cannot_be_promoted_without_separate_review(self) -> None:
        pilot, _ = self._payloads()
        pilot["datasetRights"]["evaluationAllowed"] = "YES"
        with self.assertRaisesRegex(TeacherGoldPilotError, "pilot_rights_invalid"):
            self._validate_mutation(pilot)

    def test_discovery_evidence_requires_temporary_archive_deletion(self) -> None:
        pilot, _ = self._payloads()
        pilot["discoveryEvidence"]["temporaryArchiveDeleted"] = False
        with self.assertRaisesRegex(TeacherGoldPilotError, "pilot_discovery_evidence_invalid"):
            self._validate_mutation(pilot)

    def test_pilot_cannot_silently_populate_verified_registry(self) -> None:
        pilot, registry = self._payloads()
        registry["fixtureRecords"] = [
            {
                "fixtureId": "poly_fixture_fake0001",
                "metadataRef": "fixtures/fake.json",
                "metadataSha256": "a" * 64,
            }
        ]
        with self.assertRaisesRegex(
            TeacherGoldPilotError, "verified_registry_must_remain_empty_during_pilot"
        ):
            self._validate_mutation(pilot, registry)


if __name__ == "__main__":
    unittest.main()
