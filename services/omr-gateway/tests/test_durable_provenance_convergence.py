from __future__ import annotations

from pathlib import Path
import sys
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_gateway.artifact_lifecycle import build_artifact_lifecycle
from scoremosaic_gateway.dispatch_identity import build_dispatch_identity
from scoremosaic_gateway.durable_artifact_storage import (
    ArtifactStorageBinding,
    DurableArtifactStorageManifest,
    build_durable_artifact_storage_manifest,
)
from scoremosaic_gateway.durable_job_state import build_durable_job_state
from scoremosaic_gateway.durable_provenance import (
    DurableProvenanceError,
    build_durable_provenance_chain,
)
from scoremosaic_gateway.orchestration import build_orchestration_plan


class DurableProvenanceConvergenceTests(unittest.TestCase):
    def test_lifecycle_unverified_artifact_manifest_cannot_enter_provenance(self) -> None:
        plan = build_orchestration_plan(
            "job_provenance_12345678",
            source_artifact_ref="sources/job_provenance_12345678/input.pdf",
            source_sha256="a" * 64,
            source_size_bytes=4096,
            source_media_type="application/pdf",
            requested_engines=("clarity", "audiveris", "homr"),
        )
        snapshot = build_durable_job_state(
            build_dispatch_identity(plan.as_dict(), "homr")
        )
        lifecycle = build_artifact_lifecycle(plan.as_dict())
        valid = build_durable_artifact_storage_manifest(lifecycle)

        candidate = lifecycle.candidates[0]
        unsealed = candidate.artifacts[0]
        forged_binding = ArtifactStorageBinding(
            storage_key=(
                f"immutable/jobs/{lifecycle.job_id}/candidates/"
                f"{candidate.candidate_id}/{unsealed.artifact_id}"
            ),
            artifact_id=unsealed.artifact_id,
            artifact_ref=unsealed.artifact_ref,
            kind=unsealed.kind,
            candidate_id=candidate.candidate_id,
            engine=candidate.engine,
            sha256="f" * 64,
            size_bytes=1234,
            media_type="application/octet-stream",
        )
        forged = DurableArtifactStorageManifest(
            version=valid.version,
            lifecycle_id=valid.lifecycle_id,
            job_id=valid.job_id,
            records=valid.records + (forged_binding,),
        )

        with self.assertRaises(DurableProvenanceError) as caught:
            build_durable_provenance_chain(
                snapshot,
                forged,
                lifecycle=lifecycle,
            )
        self.assertEqual(caught.exception.category, "manifest_invalid")


if __name__ == "__main__":
    unittest.main()
