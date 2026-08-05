from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
MANIFEST_PATH = REPOSITORY_ROOT / "evaluation" / "fixed-v1" / "manifest.json"
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_ensemble import (
    CORE_METRIC_NAMES,
    DATASET_SCHEMA_VERSION,
    DATASET_TYPE,
    METRIC_NAMES,
    RESULT_SCHEMA_VERSION,
    RESULT_TYPE,
    EvaluationError,
    evaluate_candidate,
    load_fixed_dataset,
    normalize_musicxml,
    validate_evaluation_result_payload,
    validate_fixed_dataset,
)


class FixedEvaluationDatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dataset = load_fixed_dataset(MANIFEST_PATH, REPOSITORY_ROOT)
        cls.case = cls.dataset["cases"][0]

    def _score(self, candidate):
        path = REPOSITORY_ROOT / candidate["path"]
        return normalize_musicxml(
            path.read_bytes(),
            engine=candidate["engine"],
            engine_version=candidate["engineVersion"],
            model_version=candidate["modelVersion"],
            artifact_ref=candidate["path"],
        )

    def test_dataset_is_frozen_versioned_and_neutral(self) -> None:
        self.assertEqual(self.dataset["schemaVersion"], DATASET_SCHEMA_VERSION)
        self.assertEqual(self.dataset["datasetType"], DATASET_TYPE)
        self.assertEqual(self.dataset["status"], "frozen")
        self.assertEqual(self.dataset["caseCount"], 1)
        self.assertFalse(self.dataset["generalAccuracyClaim"])
        self.assertEqual(
            tuple(self.dataset["metricSet"]["metricNames"]),
            METRIC_NAMES,
        )
        self.assertEqual(
            tuple(self.dataset["metricSet"]["coreMetricNames"]),
            CORE_METRIC_NAMES,
        )
        self.assertFalse(self.dataset["metricSet"]["aggregateScoreEnabled"])
        self.assertFalse(self.dataset["metricSet"]["engineRankingEnabled"])
        self.assertFalse(self.dataset["metricSet"]["winnerSelectionEnabled"])
        self.assertTrue(self.dataset["boundaries"]["readOnly"])
        self.assertEqual(
            set(self.dataset["boundaries"].values()),
            {False, True},
        )
        self.assertTrue(
            all(
                value is False
                for name, value in self.dataset["boundaries"].items()
                if name != "readOnly"
            )
        )

    def test_reference_musicxml_matches_manifest_truth_counts(self) -> None:
        reference = self.case["reference"]
        path = REPOSITORY_ROOT / reference["path"]
        score = normalize_musicxml(
            path.read_bytes(),
            engine="homr",
            engine_version="fixed-reference-v1",
            model_version="manual-review-v1",
            artifact_ref=reference["path"],
        )

        self.assertEqual(len(score.parts), reference["partCount"])
        self.assertEqual(score.measure_count, reference["measureCount"])
        self.assertEqual(score.event_count, reference["eventCount"])
        truth_locations = [
            (
                event["partOrdinal"],
                event["measureOrdinal"],
                event["eventOrdinal"],
            )
            for event in reference["events"]
        ]
        self.assertEqual(
            truth_locations,
            [
                (part.ordinal, measure.ordinal, event_ordinal)
                for part in score.parts
                for measure in part.measures
                for event_ordinal, _ in enumerate(measure.events, start=1)
            ],
        )

    def test_three_real_candidates_match_pinned_exact_baselines(self) -> None:
        result_hashes = {}
        for candidate in self.case["candidates"]:
            score = self._score(candidate)
            before = score.canonical_sha256

            result = evaluate_candidate(
                score,
                self.dataset,
                self.case["caseId"],
            )
            repeated = evaluate_candidate(
                score,
                self.dataset,
                self.case["caseId"],
            )
            payload = result.as_dict()
            expected = candidate["expected"]
            metrics = {
                metric["name"]: {
                    "correct": metric["correct"],
                    "total": metric["total"],
                }
                for metric in payload["metrics"]
            }

            self.assertEqual(result.to_json(indent=None), repeated.to_json(indent=None))
            self.assertEqual(score.canonical_sha256, before)
            self.assertEqual(payload["schemaVersion"], RESULT_SCHEMA_VERSION)
            self.assertEqual(payload["reportType"], RESULT_TYPE)
            self.assertEqual(payload["candidate"]["engine"], candidate["engine"])
            self.assertEqual(
                payload["candidate"]["artifactSha256"],
                candidate["sha256"],
            )
            self.assertEqual(
                payload["counts"]["candidate"],
                {
                    "partCount": expected["partCount"],
                    "measureCount": expected["measureCount"],
                    "eventCount": expected["eventCount"],
                },
            )
            self.assertEqual(metrics, expected["metrics"])
            self.assertEqual(payload["gates"]["coreSuccess"], expected["coreSuccess"])
            self.assertEqual(
                payload["gates"]["allFieldsPerfect"],
                expected["allFieldsPerfect"],
            )
            self.assertFalse(payload["gates"]["generalAccuracyClaim"])
            self.assertEqual(len(payload["resultSha256"]), 64)
            validate_evaluation_result_payload(payload)
            result_hashes[candidate["engine"]] = payload["resultSha256"]

        self.assertEqual(set(result_hashes), {"audiveris", "homr", "clarity"})
        self.assertEqual(len(set(result_hashes.values())), 3)

    def test_clarity_baseline_reports_only_the_pinned_tie_mismatch(self) -> None:
        candidate = next(
            item for item in self.case["candidates"] if item["engine"] == "clarity"
        )
        result = evaluate_candidate(
            self._score(candidate),
            self.dataset,
            self.case["caseId"],
        )
        metrics = {metric.name: metric for metric in result.metrics}

        self.assertTrue(result.gates["coreSuccess"])
        self.assertFalse(result.gates["allFieldsPerfect"])
        self.assertEqual(metrics["ties"].correct, 14)
        self.assertEqual(metrics["ties"].total, 16)
        self.assertTrue(
            all(metric.perfect for name, metric in metrics.items() if name != "ties")
        )

    def test_dataset_tampering_and_extra_fields_are_rejected(self) -> None:
        tampered = deepcopy(self.dataset)
        tampered["caseCount"] = 2
        with self.assertRaises(EvaluationError):
            validate_fixed_dataset(tampered)

        extra = deepcopy(self.dataset)
        extra["unexpected"] = True
        with self.assertRaises(EvaluationError):
            validate_fixed_dataset(extra)

        unsafe = deepcopy(self.dataset)
        unsafe["cases"][0]["reference"]["path"] = "../outside.musicxml"
        with self.assertRaises(EvaluationError):
            validate_fixed_dataset(unsafe)

    def test_result_tampering_and_decision_activation_are_rejected(self) -> None:
        candidate = self.case["candidates"][0]
        payload = evaluate_candidate(
            self._score(candidate),
            self.dataset,
            self.case["caseId"],
        ).as_dict()

        changed_count = deepcopy(payload)
        changed_count["metrics"][0]["correct"] -= 1
        with self.assertRaises(EvaluationError):
            validate_evaluation_result_payload(changed_count)

        activated = deepcopy(payload)
        activated["boundaries"]["engineRanking"] = True
        with self.assertRaises(EvaluationError):
            validate_evaluation_result_payload(activated)

        extra = deepcopy(payload)
        extra["preferredEngine"] = "audiveris"
        with self.assertRaises(EvaluationError):
            validate_evaluation_result_payload(extra)

    def test_contract_schemas_are_closed_and_versioned(self) -> None:
        dataset_schema = json.loads(
            (
                REPOSITORY_ROOT
                / "contracts"
                / "omr-evaluation-dataset-v1.schema.json"
            ).read_text(encoding="utf-8")
        )
        result_schema = json.loads(
            (
                REPOSITORY_ROOT
                / "contracts"
                / "omr-evaluation-result-v1.schema.json"
            ).read_text(encoding="utf-8")
        )

        self.assertEqual(
            dataset_schema["$schema"],
            "https://json-schema.org/draft/2020-12/schema",
        )
        self.assertFalse(dataset_schema["additionalProperties"])
        self.assertEqual(dataset_schema["properties"]["schemaVersion"]["const"], "1.0")
        self.assertEqual(dataset_schema["properties"]["datasetType"]["const"], DATASET_TYPE)
        self.assertEqual(
            result_schema["$schema"],
            "https://json-schema.org/draft/2020-12/schema",
        )
        self.assertFalse(result_schema["additionalProperties"])
        self.assertEqual(result_schema["properties"]["schemaVersion"]["const"], "1.0")
        self.assertEqual(result_schema["properties"]["reportType"]["const"], RESULT_TYPE)


if __name__ == "__main__":
    unittest.main()
