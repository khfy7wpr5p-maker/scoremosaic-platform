from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scoremosaic_st_omr.model_guard import ModelGuardError, validate_pinned_model


class PinnedModelGuardTests(unittest.TestCase):
    def make_fixture(self, *, checksum: str | None = None) -> tuple[tempfile.TemporaryDirectory[str], Path, Path]:
        temporary = tempfile.TemporaryDirectory()
        models = Path(temporary.name) / "models"
        models.mkdir()
        artifact = models / "st-omr-v1.bin"
        artifact.write_bytes(b"scoremosaic-st-omr-placeholder-artifact")
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        manifest = models / "manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "manifestVersion": "1.0",
                    "modelId": "st-omr-experimental",
                    "modelVersion": "0.0.1",
                    "artifactName": artifact.name,
                    "sha256": checksum or digest,
                }
            ),
            encoding="utf-8",
        )
        return temporary, models, manifest

    def test_valid_artifact_is_verified_but_not_loaded(self) -> None:
        temporary, models, manifest = self.make_fixture()
        self.addCleanup(temporary.cleanup)

        evidence = validate_pinned_model(manifest, allowed_root=models).as_dict()

        self.assertEqual(evidence["status"], "verified_not_loaded")
        self.assertIs(evidence["artifactVerified"], True)
        self.assertIs(evidence["modelLoaded"], False)
        self.assertIs(evidence["inferenceEnabled"], False)

    def test_checksum_mismatch_fails_closed(self) -> None:
        temporary, models, manifest = self.make_fixture(checksum="0" * 64)
        self.addCleanup(temporary.cleanup)

        with self.assertRaisesRegex(ModelGuardError, "checksum mismatch"):
            validate_pinned_model(manifest, allowed_root=models)

    def test_path_escape_fails_closed(self) -> None:
        temporary, models, manifest = self.make_fixture()
        self.addCleanup(temporary.cleanup)
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        payload["artifactName"] = "../outside.bin"
        manifest.write_text(json.dumps(payload), encoding="utf-8")

        with self.assertRaisesRegex(ModelGuardError, "direct child"):
            validate_pinned_model(manifest, allowed_root=models)

    def test_wrong_root_name_fails_closed(self) -> None:
        temporary, models, manifest = self.make_fixture()
        self.addCleanup(temporary.cleanup)
        other = models.parent / "artifacts"
        models.rename(other)

        with self.assertRaisesRegex(ModelGuardError, "named 'models'"):
            validate_pinned_model(other / manifest.name, allowed_root=other)

    def test_invalid_manifest_version_fails_closed(self) -> None:
        temporary, models, manifest = self.make_fixture()
        self.addCleanup(temporary.cleanup)
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        payload["manifestVersion"] = "2.0"
        manifest.write_text(json.dumps(payload), encoding="utf-8")

        with self.assertRaisesRegex(ModelGuardError, "unsupported manifest"):
            validate_pinned_model(manifest, allowed_root=models)


if __name__ == "__main__":
    unittest.main()
