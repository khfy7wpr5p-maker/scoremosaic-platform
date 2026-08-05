from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_ROOT = SERVICE_ROOT / "tests" / "fixtures" / "real-engines"
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_ensemble import (
    REPORT_SCHEMA_VERSION,
    REPORT_TYPE,
    ComparisonReportError,
    build_comparison_report,
    compare_candidates,
    normalize_musicxml,
    validate_comparison_report_payload,
)


class EnsembleComparisonReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(
            (FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8")
        )

    def _candidates(self):
        candidates = []
        for expected in self.manifest["candidates"]:
            document = (REPOSITORY_ROOT / expected["musicXmlPath"]).read_bytes()
            candidates.append(
                normalize_musicxml(
                    document,
                    engine=expected["engine"],
                    engine_version=expected["engineVersion"],
                    model_version=expected["modelVersion"],
                    artifact_ref=f"fixtures/real-engines/{expected['engine']}.musicxml",
                )
            )
        return tuple(candidates)

    def test_schema_is_versioned_closed_and_neutral(self) -> None:
        schema = json.loads(
            (
                REPOSITORY_ROOT
                / "contracts"
                / "ensemble-comparison-report-v1.schema.json"
            ).read_text(encoding="utf-8")
        )

        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["properties"]["schemaVersion"]["const"], "1.0")
        self.assertEqual(
            schema["properties"]["reportType"]["const"],
            "scoremosaic.ensemble.comparison-report",
        )
        neutrality = schema["$defs"]["neutrality"]["properties"]
        self.assertTrue(neutrality["readOnly"]["const"])
        self.assertTrue(neutrality["provenancePreserved"]["const"])
        for field in (
            "accuracyClaim",
            "engineRanking",
            "winnerSelection",
            "preferredCandidate",
            "automaticMerge",
            "automaticCorrection",
        ):
            self.assertFalse(neutrality[field]["const"])

    def test_real_fixture_report_is_deterministic_and_pinned(self) -> None:
        candidates = self._candidates()
        report = build_comparison_report(compare_candidates(candidates))
        reversed_report = build_comparison_report(
            compare_candidates(tuple(reversed(candidates)))
        )
        payload = report.as_dict()

        self.assertEqual(REPORT_SCHEMA_VERSION, "1.0")
        self.assertEqual(REPORT_TYPE, "scoremosaic.ensemble.comparison-report")
        self.assertEqual(report.to_json(indent=None), reversed_report.to_json(indent=None))
        self.assertEqual(
            payload["reportId"],
            "ensemble_report_1a0cef269ff2f052f0ab46f0",
        )
        self.assertEqual(
            report.report_sha256,
            "c5f55c03e963f61d4f03193f68e4ec9e8c924e2ce64e0a59b8ba7db4774ae718",
        )

    def test_report_hashes_and_counts_verify(self) -> None:
        report = build_comparison_report(compare_candidates(self._candidates()))
        payload = validate_comparison_report_payload(report.as_dict())

        self.assertEqual(
            payload["comparisonResultSha256"],
            payload["comparison"]["resultSha256"],
        )
        self.assertEqual(
            payload["comparison"]["candidateCount"],
            len(payload["comparison"]["candidates"]),
        )
        self.assertEqual(
            payload["comparison"]["differenceCount"],
            len(payload["comparison"]["differences"]),
        )
        self.assertEqual(payload["reportSha256"], report.report_sha256)

    def test_report_preserves_all_difference_provenance(self) -> None:
        payload = build_comparison_report(
            compare_candidates(self._candidates())
        ).as_dict()

        self.assertEqual(payload["comparison"]["differenceCount"], 2)
        for difference in payload["comparison"]["differences"]:
            self.assertEqual(difference["category"], "tie")
            self.assertEqual(len(difference["observations"]), 3)
            for observation in difference["observations"]:
                self.assertTrue(observation["source"]["engine"])
                self.assertEqual(len(observation["canonicalSha256"]), 64)
                self.assertTrue(observation["provenance"]["xmlPath"])
                self.assertIsNotNone(
                    observation["provenance"]["sourceEventIndex"]
                )

    def test_report_rejects_tampering(self) -> None:
        payload = build_comparison_report(
            compare_candidates(self._candidates())
        ).as_dict()
        tampered = deepcopy(payload)
        tampered["comparison"]["differenceCount"] = 99

        with self.assertRaises(ComparisonReportError):
            validate_comparison_report_payload(tampered)

    def test_report_generation_does_not_mutate_candidates(self) -> None:
        candidates = self._candidates()
        before = tuple(candidate.canonical_sha256 for candidate in candidates)

        build_comparison_report(compare_candidates(candidates)).as_dict()

        self.assertEqual(
            before,
            tuple(candidate.canonical_sha256 for candidate in candidates),
        )


if __name__ == "__main__":
    unittest.main()
