from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from scripts.polyphonic_teacher_gold_harness import (
    ROOT,
    TeacherGoldHarnessError,
    build_report,
    determine_readiness,
)


BASELINE_REGISTRY = ROOT / "evaluation" / "polyphonic-teacher-gold-v1" / "registry.json"
ARCHITECTURE = json.loads(
    (ROOT / "contracts" / "architecture-current-state-v1.json").read_text(encoding="utf-8")
)
REGISTRY_SCHEMA = json.loads(
    (ROOT / "contracts" / "polyphonic-teacher-gold-registry-v1.schema.json").read_text(
        encoding="utf-8"
    )
)


def _fixture(
    fixture_id: str,
    *,
    verification: str = "VERIFIED",
    evaluation_allowed: str = "YES",
    training_authorization: str = "NOT_AUTHORIZED",
) -> dict[str, object]:
    return {
        "schemaVersion": "scoremosaic-polyphonic-benchmark-fixture-v1",
        "fixtureId": fixture_id,
        "granularity": "measure",
        "location": {
            "pageIndex": 0,
            "systemId": "system.1",
            "measureId": "measure.1",
            "staffIds": ["staff.1"],
        },
        "source": {
            "sourceId": "source.sample",
            "sourceSha256": "a" * 64,
            "mediaType": "image/png",
            "originType": "PRIVATE_TEACHER_GOLD",
            "assetAvailability": "PRIVATE_REGISTRY",
            "sourceReference": "private/source.png",
            "licenseMetadata": {
                "dataset": "teacher-gold-private",
                "version": "v1",
                "source": "private/dataset-registry",
                "license": "private-evaluation-governance",
                "redistributionStatus": "NOT_ALLOWED",
                "trainingAllowed": "NO",
                "evaluationAllowed": evaluation_allowed,
                "commercialUseImplications": "REVIEW_REQUIRED",
            },
        },
        "gold": {
            "goldId": f"gold.{fixture_id}",
            "goldArtifactSha256": "b" * 64,
            "goldFormat": "MUSICXML",
            "verificationStatus": verification,
            "verifiedByRole": "TEACHER",
            "separateFromEngineOutputs": True,
            "teacherCorrectionAutomaticallyTrainingData": False,
            "trainingAuthorization": training_authorization,
        },
        "classification": {
            "notationClasses": ["VOICE_2"],
            "notationFeatures": ["TIES"],
            "scanConditions": ["CLEAN_OR_HIGH_QUALITY"],
        },
        "expectedErrorFocus": ["VOICE", "TIE"],
        "boundaries": {
            "researchEvaluationOnly": True,
            "engineOutputsStoredSeparately": True,
            "automaticWinnerSelection": False,
            "automaticMusicXmlMerge": False,
            "automaticSemanticRepair": False,
            "teacherAuthority": True,
            "productionDecisionAuthority": False,
        },
    }


def _write_registry(root: Path, fixtures: list[dict[str, object]]) -> Path:
    fixture_dir = root / "fixtures"
    fixture_dir.mkdir(parents=True)
    records: list[dict[str, str]] = []
    for fixture in sorted(fixtures, key=lambda item: str(item["fixtureId"])):
        fixture_id = str(fixture["fixtureId"])
        metadata_ref = f"fixtures/{fixture_id}.json"
        data = json.dumps(
            fixture, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")
        ).encode("ascii")
        (root / metadata_ref).write_bytes(data)
        records.append(
            {
                "fixtureId": fixture_id,
                "metadataRef": metadata_ref,
                "metadataSha256": sha256(data).hexdigest(),
            }
        )
    registry = {
        "registryVersion": "scoremosaic-polyphonic-teacher-gold-registry-v1",
        "benchmarkId": "scoremosaic-polyphonic-teacher-gold-v1",
        "fixtureSchemaVersion": "scoremosaic-polyphonic-benchmark-fixture-v1",
        "minimumVerifiedFixtures": 500,
        "targetVerifiedFixtures": 1000,
        "fixtureRecords": records,
        "boundaries": {
            "researchEvaluationOnly": True,
            "privateAssetsRemainExternal": True,
            "teacherGoldSeparateFromEngineOutputs": True,
            "teacherCorrectionAutomaticallyTrainingData": False,
            "automaticWinnerSelection": False,
            "automaticMusicXmlMerge": False,
            "automaticSemanticRepair": False,
            "teacherAuthority": True,
            "productionDecisionAuthority": False,
        },
    }
    path = root / "registry.json"
    path.write_text(json.dumps(registry, sort_keys=True), encoding="utf-8")
    return path


class SmPoly03TeacherGoldHarnessTests(unittest.TestCase):
    def test_public_baseline_has_ten_verified_but_is_not_ready(self) -> None:
        first = build_report(BASELINE_REGISTRY)
        second = build_report(BASELINE_REGISTRY)
        self.assertEqual(first, second)
        self.assertEqual("NOT_READY", first["readiness"])
        self.assertEqual(10, first["fixtureCount"])
        self.assertEqual(10, first["verifiedFixtureCount"])
        self.assertEqual(10, first["eligibleVerifiedFixtureCount"])
        self.assertEqual(0, first["separatelyTrainingAuthorizedFixtureCount"])
        self.assertGreater(sum(len(v) for v in first["missingCoverage"].values()), 0)
        self.assertIs(first["claims"]["generalAccuracyClaim"], False)
        self.assertIs(first["claims"]["productionDecisionAuthority"], False)
        self.assertIs(first["claims"]["teacherCorrectionsAutomaticallyTrainingData"], False)

    def test_verified_evaluation_allowed_fixture_counts_without_accuracy_claim(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = _write_registry(Path(temp), [_fixture("poly_fixture_sample0001")])
            report = build_report(path)
        self.assertEqual(1, report["fixtureCount"])
        self.assertEqual(1, report["verifiedFixtureCount"])
        self.assertEqual(1, report["eligibleVerifiedFixtureCount"])
        self.assertEqual(0, report["evaluationBlockedFixtureCount"])
        self.assertEqual(1, report["coverage"]["notationClasses"]["VOICE_2"])
        self.assertEqual(1, report["coverage"]["notationFeatures"]["TIES"])
        self.assertEqual(1, report["coverage"]["scanConditions"]["CLEAN_OR_HIGH_QUALITY"])
        self.assertEqual("NOT_READY", report["readiness"])

    def test_draft_or_unlicensed_evaluation_does_not_count_as_eligible_verified(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            fixtures = [
                _fixture("poly_fixture_sample0002", verification="DRAFT"),
                _fixture("poly_fixture_sample0003", evaluation_allowed="REVIEW_REQUIRED"),
            ]
            report = build_report(_write_registry(Path(temp), fixtures))
        self.assertEqual(2, report["fixtureCount"])
        self.assertEqual(1, report["verifiedFixtureCount"])
        self.assertEqual(0, report["eligibleVerifiedFixtureCount"])
        self.assertEqual(1, report["draftFixtureCount"])
        self.assertEqual(1, report["evaluationBlockedFixtureCount"])

    def test_separate_training_authorization_is_counted_but_has_no_training_effect(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            fixture = _fixture(
                "poly_fixture_sample0004", training_authorization="SEPARATELY_AUTHORIZED"
            )
            report = build_report(_write_registry(Path(temp), [fixture]))
        self.assertEqual(1, report["separatelyTrainingAuthorizedFixtureCount"])
        self.assertIs(report["claims"]["teacherCorrectionsAutomaticallyTrainingData"], False)
        self.assertIs(report["claims"]["productionDecisionAuthority"], False)

    def test_tampered_fixture_metadata_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = _write_registry(root, [_fixture("poly_fixture_sample0005")])
            fixture_path = root / "fixtures" / "poly_fixture_sample0005.json"
            fixture_path.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(TeacherGoldHarnessError, "fixture_metadata_hash_mismatch"):
                build_report(path)

    def test_unsafe_registry_reference_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = _write_registry(root, [_fixture("poly_fixture_sample0006")])
            registry = json.loads(path.read_text(encoding="utf-8"))
            registry["fixtureRecords"][0]["metadataRef"] = "../escape.json"
            path.write_text(json.dumps(registry), encoding="utf-8")
            with self.assertRaisesRegex(TeacherGoldHarnessError, "registry_record_invalid"):
                build_report(path)

    def test_teacher_training_boundary_tamper_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fixture = _fixture("poly_fixture_sample0007")
            fixture["gold"]["teacherCorrectionAutomaticallyTrainingData"] = True
            path = _write_registry(root, [fixture])
            with self.assertRaisesRegex(TeacherGoldHarnessError, "fixture_gold_invalid"):
                build_report(path)

    def test_readiness_thresholds_are_fixed_and_coverage_gated(self) -> None:
        self.assertEqual("NOT_READY", determine_readiness(499, 500, 1000, 0))
        self.assertEqual("NOT_READY", determine_readiness(500, 500, 1000, 1))
        self.assertEqual(
            "MINIMUM_RESEARCH_BENCHMARK_READY", determine_readiness(500, 500, 1000, 0)
        )
        self.assertEqual(
            "TARGET_RESEARCH_BENCHMARK_READY", determine_readiness(1000, 500, 1000, 0)
        )
        self.assertEqual(500, REGISTRY_SCHEMA["properties"]["minimumVerifiedFixtures"]["const"])
        self.assertEqual(1000, REGISTRY_SCHEMA["properties"]["targetVerifiedFixtures"]["const"])

    def test_current_score_authority_and_quorum_remain_unchanged(self) -> None:
        current_omr = ARCHITECTURE["currentOmr"]
        self.assertEqual(["audiveris", "homr", "clarity"], current_omr["productionCandidateEngines"])
        self.assertEqual(2, current_omr["stage7MinimumCanonicalCandidates"])
        self.assertIs(current_omr["stOmrIntegratedIntoGateway"], False)
        self.assertIs(current_omr["automaticWinnerAuthority"], False)
        self.assertIs(ARCHITECTURE["teacherReview"]["productionWriteActivated"], False)
        self.assertIs(ARCHITECTURE["production"]["productionReady"], False)


if __name__ == "__main__":
    unittest.main()
