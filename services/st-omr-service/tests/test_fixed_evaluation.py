from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from scoremosaic_st_omr.fixed_evaluation import FixedEvaluationError, run_fixed_evaluation


class FixedEvaluationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[3]
        self.service_root = self.repo_root / "services" / "st-omr-service"
        self.fixture_root = self.service_root / "fixtures"
        self.evaluation_root = self.service_root / "evaluations"
        self.manifest = self.evaluation_root / "fixed-evaluation-v1.json"

    def run_repository_evaluation(self):
        return run_fixed_evaluation(
            evaluation_manifest_path=self.manifest,
            evaluation_root=self.evaluation_root,
            fixture_root=self.fixture_root,
        )

    def test_repository_evaluation_is_deterministic_and_closed(self) -> None:
        first = self.run_repository_evaluation()
        second = self.run_repository_evaluation()

        self.assertEqual(first, second)
        self.assertEqual(first.fixture_count, 3)
        self.assertEqual(first.pass_count, 3)
        self.assertEqual(first.fail_count, 0)
        self.assertEqual(
            tuple(record.fixture_id for record in first.records),
            (
                "generated-chord-v1",
                "generated-rhythm-pattern-v1",
                "generated-single-staff",
            ),
        )
        self.assertEqual(len(first.evaluation_sha256), 64)
        evidence = first.as_dict()
        self.assertFalse(evidence["modelLoaded"])
        self.assertFalse(evidence["realOmrInference"])
        self.assertFalse(evidence["realOmrAccuracyMeasured"])
        self.assertFalse(evidence["generalAccuracyClaim"])
        self.assertFalse(evidence["userInputAccepted"])
        self.assertFalse(evidence["networkUsed"])

    def test_case_and_registry_order_do_not_change_canonical_evidence(self) -> None:
        baseline = self.run_repository_evaluation()
        with tempfile.TemporaryDirectory() as temp_dir:
            service_root = Path(temp_dir) / "st-omr-service"
            fixture_root = service_root / "fixtures"
            evaluation_root = service_root / "evaluations"
            shutil.copytree(self.fixture_root, fixture_root)
            shutil.copytree(self.evaluation_root, evaluation_root)

            manifest = evaluation_root / self.manifest.name
            manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
            manifest_payload["cases"].reverse()
            manifest.write_text(json.dumps(manifest_payload), encoding="utf-8")

            registry = fixture_root / "generated-fixture-suite-v1.registry.json"
            registry_payload = json.loads(registry.read_text(encoding="utf-8"))
            registry_payload["fixtures"].reverse()
            registry.write_text(json.dumps(registry_payload), encoding="utf-8")

            reordered = run_fixed_evaluation(
                evaluation_manifest_path=manifest,
                evaluation_root=evaluation_root,
                fixture_root=fixture_root,
            )
            self.assertEqual(reordered.evaluation_sha256, baseline.evaluation_sha256)
            self.assertEqual(reordered.records, baseline.records)

    def test_duplicate_unknown_and_missing_cases_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service_root = Path(temp_dir) / "st-omr-service"
            fixture_root = service_root / "fixtures"
            evaluation_root = service_root / "evaluations"
            shutil.copytree(self.fixture_root, fixture_root)
            shutil.copytree(self.evaluation_root, evaluation_root)
            manifest = evaluation_root / self.manifest.name

            original = json.loads(manifest.read_text(encoding="utf-8"))

            duplicate = json.loads(json.dumps(original))
            duplicate["cases"].append(duplicate["cases"][0])
            manifest.write_text(json.dumps(duplicate), encoding="utf-8")
            with self.assertRaises(FixedEvaluationError):
                run_fixed_evaluation(
                    evaluation_manifest_path=manifest,
                    evaluation_root=evaluation_root,
                    fixture_root=fixture_root,
                )

            unknown = json.loads(json.dumps(original))
            unknown["cases"][0]["fixtureId"] = "unknown-fixture"
            manifest.write_text(json.dumps(unknown), encoding="utf-8")
            with self.assertRaises(FixedEvaluationError):
                run_fixed_evaluation(
                    evaluation_manifest_path=manifest,
                    evaluation_root=evaluation_root,
                    fixture_root=fixture_root,
                )

            missing = json.loads(json.dumps(original))
            missing["cases"] = missing["cases"][:-1]
            manifest.write_text(json.dumps(missing), encoding="utf-8")
            with self.assertRaises(FixedEvaluationError):
                run_fixed_evaluation(
                    evaluation_manifest_path=manifest,
                    evaluation_root=evaluation_root,
                    fixture_root=fixture_root,
                )

    def test_tampered_fixture_and_closed_schema_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service_root = Path(temp_dir) / "st-omr-service"
            fixture_root = service_root / "fixtures"
            evaluation_root = service_root / "evaluations"
            shutil.copytree(self.fixture_root, fixture_root)
            shutil.copytree(self.evaluation_root, evaluation_root)
            manifest = evaluation_root / self.manifest.name

            target = fixture_root / "generated-chord-v1.txt"
            target.write_text(target.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8")
            with self.assertRaises(FixedEvaluationError):
                run_fixed_evaluation(
                    evaluation_manifest_path=manifest,
                    evaluation_root=evaluation_root,
                    fixture_root=fixture_root,
                )

        with tempfile.TemporaryDirectory() as temp_dir:
            service_root = Path(temp_dir) / "st-omr-service"
            fixture_root = service_root / "fixtures"
            evaluation_root = service_root / "evaluations"
            shutil.copytree(self.fixture_root, fixture_root)
            shutil.copytree(self.evaluation_root, evaluation_root)
            manifest = evaluation_root / self.manifest.name
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            payload["unexpectedField"] = True
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(FixedEvaluationError):
                run_fixed_evaluation(
                    evaluation_manifest_path=manifest,
                    evaluation_root=evaluation_root,
                    fixture_root=fixture_root,
                )

    def test_path_escape_and_metric_claims_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service_root = Path(temp_dir) / "st-omr-service"
            fixture_root = service_root / "fixtures"
            evaluation_root = service_root / "evaluations"
            shutil.copytree(self.fixture_root, fixture_root)
            shutil.copytree(self.evaluation_root, evaluation_root)
            manifest = evaluation_root / self.manifest.name

            outside = service_root / "outside.json"
            shutil.copyfile(manifest, outside)
            with self.assertRaises(FixedEvaluationError):
                run_fixed_evaluation(
                    evaluation_manifest_path=outside,
                    evaluation_root=evaluation_root,
                    fixture_root=fixture_root,
                )

            payload = json.loads(manifest.read_text(encoding="utf-8"))
            payload["metricContract"]["generalAccuracyClaim"] = True
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(FixedEvaluationError):
                run_fixed_evaluation(
                    evaluation_manifest_path=manifest,
                    evaluation_root=evaluation_root,
                    fixture_root=fixture_root,
                )


if __name__ == "__main__":
    unittest.main()
