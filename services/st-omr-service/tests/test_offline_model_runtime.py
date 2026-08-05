from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from scoremosaic_st_omr.offline_model_runtime import (
    OfflineModelRuntimeError,
    disabled_offline_model_runtime_evidence,
    load_pinned_offline_test_model,
    run_pinned_offline_test_model,
)


class PinnedOfflineModelRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[3]
        self.service_root = self.repo_root / "services" / "st-omr-service"
        self.model_root = self.service_root / "models"
        self.model_manifest = self.model_root / "st-omr-test-linear-v1.manifest.json"
        self.fixture_root = self.service_root / "fixtures"
        self.fixture_manifest = (
            self.fixture_root / "generated-single-staff-v1.manifest.json"
        )

    def run_repository_model(self):
        return run_pinned_offline_test_model(
            model_manifest_path=self.model_manifest,
            model_root=self.model_root,
            fixture_manifest_path=self.fixture_manifest,
            fixture_root=self.fixture_root,
        )

    def copy_models(self) -> tuple[tempfile.TemporaryDirectory[str], Path, Path]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name) / "models"
        shutil.copytree(self.model_root, root)
        return temporary, root, root / self.model_manifest.name

    def rewrite_model(
        self,
        root: Path,
        manifest: Path,
        mutate,
    ) -> None:
        manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
        artifact = root / manifest_payload["artifactName"]
        model_payload = json.loads(artifact.read_text(encoding="utf-8"))
        mutate(model_payload)
        artifact.write_text(
            json.dumps(model_payload, indent=2) + "\n",
            encoding="utf-8",
        )
        manifest_payload["sha256"] = hashlib.sha256(artifact.read_bytes()).hexdigest()
        manifest.write_text(
            json.dumps(manifest_payload, indent=2) + "\n",
            encoding="utf-8",
        )

    def test_repository_model_loads_and_runs_deterministically(self) -> None:
        first = self.run_repository_model()
        second = self.run_repository_model()

        self.assertEqual(first, second)
        evidence = first.as_dict()
        self.assertEqual(evidence["status"], "completed_pinned_offline_test_model_only")
        self.assertEqual(evidence["predictedLabel"], "repository_fixture_shape")
        self.assertIs(evidence["modelLoaded"], True)
        self.assertIs(evidence["inferenceEnabled"], True)
        self.assertIs(evidence["offlineOnly"], True)
        self.assertIs(evidence["repositoryTestModelOnly"], True)
        self.assertIs(evidence["realOmrInference"], False)
        self.assertIs(evidence["realOmrAccuracyMeasured"], False)
        self.assertIs(evidence["generalAccuracyClaim"], False)
        self.assertIs(evidence["userInputAccepted"], False)
        self.assertIs(evidence["httpInferenceEnabled"], False)
        self.assertIs(evidence["networkUsed"], False)
        self.assertIs(evidence["gatewayIntegration"], False)
        self.assertIs(evidence["ensembleIntegration"], False)
        self.assertIs(evidence["productionEligible"], False)
        self.assertEqual(len(evidence["outputSha256"]), 64)

    def test_health_evidence_never_loads_the_model(self) -> None:
        evidence = disabled_offline_model_runtime_evidence()

        self.assertIs(evidence["offlineModelRuntimeEnabled"], True)
        self.assertIs(evidence["repositoryTestModelOnly"], True)
        self.assertIs(evidence["modelLoaded"], False)
        self.assertIs(evidence["inferenceEnabled"], False)
        self.assertIs(evidence["realOmrInference"], False)
        self.assertIs(evidence["userInputAccepted"], False)
        self.assertIs(evidence["httpInferenceEnabled"], False)

    def test_tampered_model_artifact_fails_closed(self) -> None:
        temporary, root, manifest = self.copy_models()
        self.addCleanup(temporary.cleanup)
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        artifact = root / payload["artifactName"]
        artifact.write_text(
            artifact.read_text(encoding="utf-8") + "tampered\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(
            OfflineModelRuntimeError,
            "pinned model validation failed closed",
        ):
            load_pinned_offline_test_model(
                manifest_path=manifest,
                allowed_model_root=root,
            )

    def test_provenance_and_boundary_changes_fail_closed(self) -> None:
        temporary, root, manifest = self.copy_models()
        self.addCleanup(temporary.cleanup)
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        payload["provenance"]["trainingDataUsed"] = True
        manifest.write_text(json.dumps(payload), encoding="utf-8")

        with self.assertRaisesRegex(OfflineModelRuntimeError, "provenance"):
            load_pinned_offline_test_model(
                manifest_path=manifest,
                allowed_model_root=root,
            )

        payload["provenance"]["trainingDataUsed"] = False
        payload["boundaries"]["productionEligible"] = True
        manifest.write_text(json.dumps(payload), encoding="utf-8")

        with self.assertRaisesRegex(OfflineModelRuntimeError, "boundaries"):
            load_pinned_offline_test_model(
                manifest_path=manifest,
                allowed_model_root=root,
            )

    def test_malformed_weight_vector_fails_closed(self) -> None:
        temporary, root, manifest = self.copy_models()
        self.addCleanup(temporary.cleanup)

        def mutate(model: dict[str, object]) -> None:
            weights = model["weights"]
            assert isinstance(weights, dict)
            weights["repository_fixture_shape"] = [1, 2]

        self.rewrite_model(root, manifest, mutate)

        with self.assertRaisesRegex(OfflineModelRuntimeError, "weight vector"):
            load_pinned_offline_test_model(
                manifest_path=manifest,
                allowed_model_root=root,
            )

    def test_ambiguous_tie_fails_closed(self) -> None:
        temporary, root, manifest = self.copy_models()
        self.addCleanup(temporary.cleanup)

        def mutate(model: dict[str, object]) -> None:
            model["weights"] = {
                "repository_fixture_shape": [0, 0, 0],
                "other": [0, 0, 0],
            }
            model["bias"] = {
                "repository_fixture_shape": 0,
                "other": 0,
            }

        self.rewrite_model(root, manifest, mutate)

        with self.assertRaisesRegex(OfflineModelRuntimeError, "ambiguous tie"):
            run_pinned_offline_test_model(
                model_manifest_path=manifest,
                model_root=root,
                fixture_manifest_path=self.fixture_manifest,
                fixture_root=self.fixture_root,
            )

    def test_model_artifact_symlink_fails_closed(self) -> None:
        temporary, root, manifest = self.copy_models()
        self.addCleanup(temporary.cleanup)
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        artifact = root / payload["artifactName"]
        outside = Path(temporary.name) / "outside-model.json"
        outside.write_bytes(artifact.read_bytes())
        artifact.unlink()
        artifact.symlink_to(outside)

        with self.assertRaisesRegex(OfflineModelRuntimeError, "symlinks"):
            load_pinned_offline_test_model(
                manifest_path=manifest,
                allowed_model_root=root,
            )

    def test_tampered_fixture_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture_root = Path(temp_dir) / "fixtures"
            shutil.copytree(self.fixture_root, fixture_root)
            fixture_manifest = fixture_root / self.fixture_manifest.name
            manifest_payload = json.loads(
                fixture_manifest.read_text(encoding="utf-8")
            )
            fixture_input = fixture_root / manifest_payload["inputName"]
            fixture_input.write_text(
                fixture_input.read_text(encoding="utf-8") + "tampered\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                OfflineModelRuntimeError,
                "fixture validation failed closed",
            ):
                run_pinned_offline_test_model(
                    model_manifest_path=self.model_manifest,
                    model_root=self.model_root,
                    fixture_manifest_path=fixture_manifest,
                    fixture_root=fixture_root,
                )


if __name__ == "__main__":
    unittest.main()
