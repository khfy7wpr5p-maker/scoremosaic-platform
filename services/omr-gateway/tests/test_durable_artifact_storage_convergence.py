from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_gateway.artifact_lifecycle import build_artifact_lifecycle
from scoremosaic_gateway.orchestration import build_orchestration_plan
from scoremosaic_gateway.durable_artifact_storage import (
    DurableArtifactStorageError,
    DurableArtifactStorageManifest,
    build_durable_artifact_storage_manifest,
)


class DurableArtifactStorageConvergenceTests(unittest.TestCase):
    def _lifecycle(self):
        plan = build_orchestration_plan(
            "job_storage_convergence_12345678",
            source_artifact_ref=(
                "sources/job_storage_convergence_12345678/input.pdf"
            ),
            source_sha256="e" * 64,
            source_size_bytes=4096,
            source_media_type="application/pdf",
            requested_engines=("clarity", "audiveris", "homr"),
        ).as_dict()
        return build_artifact_lifecycle(plan)

    def test_manifest_constructor_rejects_non_server_derived_source_key(self) -> None:
        manifest = build_durable_artifact_storage_manifest(self._lifecycle())
        forged_source = replace(
            manifest.records[0],
            storage_key=(
                f"immutable/jobs/{manifest.job_id}/foreign/"
                f"{manifest.records[0].artifact_id}"
            ),
        )

        with self.assertRaises(DurableArtifactStorageError) as caught:
            DurableArtifactStorageManifest(
                version=manifest.version,
                lifecycle_id=manifest.lifecycle_id,
                job_id=manifest.job_id,
                records=(forged_source,),
            )
        self.assertEqual(caught.exception.category, "manifest_invalid")


if __name__ == "__main__":
    unittest.main()
