from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from scripts.polyphonic_reference_batch_100_evidence import (
    EVIDENCE,
    REGISTRY,
    WORKFLOW,
    ReferenceBatchEvidenceError,
    validate,
)


class ReferenceBatch100EvidenceTests(unittest.TestCase):
    def test_repository_evidence_is_non_counting_and_not_ready(self) -> None:
        report = validate(EVIDENCE, REGISTRY, WORKFLOW)
        self.assertEqual("openscore-lieder-reference-100-v1", report["batchId"])
        self.assertEqual(100, report["successfulPairCount"])
        self.assertEqual(10, report["auditSampleCount"])
        self.assertEqual(10, report["teacherGoldFixtureCount"])
        self.assertEqual("NOT_READY", report["teacherGoldReadiness"])
        self.assertEqual("PENDING", report["teacherReviewStatus"])
        self.assertFalse(report["trainingAuthorized"])
        self.assertFalse(report["productionDecisionAuthority"])

    def _mutated_evidence(self, mutate) -> Path:
        data = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        mutate(data)
        handle = tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False)
        with handle:
            json.dump(data, handle, sort_keys=True)
        return Path(handle.name)

    def test_cannot_turn_reference_batch_into_teacher_gold(self) -> None:
        path = self._mutated_evidence(lambda d: d["boundaries"].__setitem__("referenceBatchIsNotTeacherGold", False))
        self.addCleanup(path.unlink, missing_ok=True)
        with self.assertRaisesRegex(ReferenceBatchEvidenceError, "authority_boundary_invalid"):
            validate(path, REGISTRY, WORKFLOW)

    def test_cannot_authorize_training(self) -> None:
        path = self._mutated_evidence(lambda d: d["boundaries"].__setitem__("automaticTrainingAuthorization", True))
        self.addCleanup(path.unlink, missing_ok=True)
        with self.assertRaisesRegex(ReferenceBatchEvidenceError, "authority_boundary_invalid"):
            validate(path, REGISTRY, WORKFLOW)

    def test_audit_sample_must_remain_exactly_ten(self) -> None:
        path = self._mutated_evidence(lambda d: d["auditPolicy"].__setitem__("sampleCount", 9))
        self.addCleanup(path.unlink, missing_ok=True)
        with self.assertRaisesRegex(ReferenceBatchEvidenceError, "audit_policy_invalid"):
            validate(path, REGISTRY, WORKFLOW)

    def test_artifact_digest_is_pinned(self) -> None:
        path = self._mutated_evidence(lambda d: d["discoveryEvidence"].__setitem__("artifactZipSha256", "0" * 64))
        self.addCleanup(path.unlink, missing_ok=True)
        with self.assertRaisesRegex(ReferenceBatchEvidenceError, "discovery_lineage_invalid"):
            validate(path, REGISTRY, WORKFLOW)

    def test_registry_count_change_fails_closed(self) -> None:
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        registry["fixtureRecords"] = registry["fixtureRecords"][:-1]
        handle = tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False)
        with handle:
            json.dump(registry, handle, sort_keys=True)
        path = Path(handle.name)
        self.addCleanup(path.unlink, missing_ok=True)
        with self.assertRaisesRegex(ReferenceBatchEvidenceError, "teacher_gold_registry_count_changed"):
            validate(EVIDENCE, path, WORKFLOW)

    def test_direction_system_coverage_is_pinned(self) -> None:
        path = self._mutated_evidence(lambda d: d["coverageSummary"]["directionSystemCoverage"].__setitem__("invalid", 1))
        self.addCleanup(path.unlink, missing_ok=True)
        with self.assertRaisesRegex(ReferenceBatchEvidenceError, "direction_system_coverage_invalid"):
            validate(path, REGISTRY, WORKFLOW)


if __name__ == "__main__":
    unittest.main()
