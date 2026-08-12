from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import sys
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_gateway.artifact_lifecycle import (
    build_artifact_lifecycle,
    transition_artifact,
    transition_candidate,
)
from scoremosaic_gateway.orchestration import build_orchestration_plan
from scoremosaic_gateway.durable_artifact_storage import (
    DURABLE_ARTIFACT_STORAGE_CONTRACT_VERSION,
    ArtifactStorageBinding,
    DurableArtifactStorageError,
    DurableArtifactStorageManifest,
    bind_sealed_artifact_idempotently,
    build_durable_artifact_storage_manifest,
    verify_durable_artifact_storage_manifest,
)


SOURCE_SHA = "a" * 64
OUTPUT_SHA = "b" * 64


class _StringSubclass(str):
    pass


class DurableArtifactStorageContractTests(unittest.TestCase):
    def _plan(self):
        return build_orchestration_plan(
            "job_storage_12345678",
            source_artifact_ref="sources/job_storage_12345678/input.pdf",
            source_sha256=SOURCE_SHA,
            source_size_bytes=4096,
            source_media_type="application/pdf",
            requested_engines=("clarity", "audiveris", "homr"),
        ).as_dict()

    def _initial(self):
        return build_artifact_lifecycle(self._plan())

    def _sealed_first_output(self):
        lifecycle = self._initial()
        candidate = lifecycle.candidates[0]
        artifact = candidate.artifacts[0]
        lifecycle = transition_candidate(
            lifecycle,
            candidate.candidate_id,
            "collecting",
        )
        lifecycle = transition_artifact(
            lifecycle,
            artifact.artifact_id,
            "writing",
        )
        lifecycle = transition_artifact(
            lifecycle,
            artifact.artifact_id,
            "sealed",
            sha256=OUTPUT_SHA,
            size_bytes=1234,
            media_type="application/octet-stream",
        )
        return lifecycle, candidate.candidate_id, artifact.artifact_id

    def test_initial_manifest_binds_source_to_server_derived_key(self) -> None:
        lifecycle = self._initial()
        manifest = build_durable_artifact_storage_manifest(lifecycle)
        payload = manifest.as_safe_dict()

        self.assertEqual(
            payload["version"],
            DURABLE_ARTIFACT_STORAGE_CONTRACT_VERSION,
        )
        self.assertEqual(payload["lifecycleId"], lifecycle.lifecycle_id)
        self.assertEqual(payload["jobId"], lifecycle.job_id)
        self.assertEqual(len(payload["records"]), 1)
        source = payload["records"][0]
        self.assertEqual(source["artifactId"], lifecycle.source_artifact.artifact_id)
        self.assertEqual(source["sha256"], SOURCE_SHA)
        self.assertEqual(
            source["storageKey"],
            f"immutable/jobs/{lifecycle.job_id}/source/"
            f"{lifecycle.source_artifact.artifact_id}",
        )
        self.assertNotEqual(source["storageKey"], source["artifactRef"])
        self.assertTrue(source["immutable"])
        self.assertFalse(source["overwriteAllowed"])
        verify_durable_artifact_storage_manifest(manifest, lifecycle)

    def test_sealed_candidate_artifact_gets_candidate_scoped_key(self) -> None:
        lifecycle, candidate_id, artifact_id = self._sealed_first_output()
        manifest = build_durable_artifact_storage_manifest(self._initial())

        result = bind_sealed_artifact_idempotently(
            manifest,
            lifecycle,
            artifact_id,
        )
        record = result.manifest.records[-1]

        self.assertFalse(result.replayed)
        self.assertEqual(record.candidate_id, candidate_id)
        self.assertEqual(record.sha256, OUTPUT_SHA)
        self.assertEqual(
            record.storage_key,
            f"immutable/jobs/{lifecycle.job_id}/candidates/"
            f"{candidate_id}/{artifact_id}",
        )
        verify_durable_artifact_storage_manifest(result.manifest, lifecycle)

    def test_exact_replay_returns_same_manifest_without_duplicate_record(self) -> None:
        lifecycle, _, artifact_id = self._sealed_first_output()
        initial = build_durable_artifact_storage_manifest(self._initial())
        first = bind_sealed_artifact_idempotently(initial, lifecycle, artifact_id)
        second = bind_sealed_artifact_idempotently(
            first.manifest,
            lifecycle,
            artifact_id,
        )

        self.assertTrue(second.replayed)
        self.assertEqual(second.manifest, first.manifest)
        self.assertEqual(len(second.manifest.records), 2)

    def test_unsealed_candidate_artifact_cannot_receive_storage_authority(self) -> None:
        lifecycle = self._initial()
        manifest = build_durable_artifact_storage_manifest(lifecycle)
        artifact_id = lifecycle.candidates[0].artifacts[0].artifact_id

        with self.assertRaises(DurableArtifactStorageError) as caught:
            bind_sealed_artifact_idempotently(manifest, lifecycle, artifact_id)
        self.assertEqual(caught.exception.category, "artifact_not_sealed")

    def test_restored_manifest_rejects_same_key_with_different_content(self) -> None:
        lifecycle, _, artifact_id = self._sealed_first_output()
        initial = build_durable_artifact_storage_manifest(self._initial())
        valid = bind_sealed_artifact_idempotently(
            initial,
            lifecycle,
            artifact_id,
        ).manifest
        forged_record = replace(valid.records[-1], sha256="c" * 64)
        forged = DurableArtifactStorageManifest(
            version=valid.version,
            lifecycle_id=valid.lifecycle_id,
            job_id=valid.job_id,
            records=valid.records[:-1] + (forged_record,),
        )

        with self.assertRaises(DurableArtifactStorageError) as caught:
            verify_durable_artifact_storage_manifest(forged, lifecycle)
        self.assertEqual(caught.exception.category, "storage_conflict")

    def test_restored_manifest_rejects_cross_candidate_identity_tamper(self) -> None:
        lifecycle, _, artifact_id = self._sealed_first_output()
        initial = build_durable_artifact_storage_manifest(self._initial())
        valid = bind_sealed_artifact_idempotently(
            initial,
            lifecycle,
            artifact_id,
        ).manifest
        other_candidate = lifecycle.candidates[1]
        forged_record = replace(
            valid.records[-1],
            candidate_id=other_candidate.candidate_id,
            engine=other_candidate.engine,
        )

        with self.assertRaises(DurableArtifactStorageError) as caught:
            DurableArtifactStorageManifest(
                version=valid.version,
                lifecycle_id=valid.lifecycle_id,
                job_id=valid.job_id,
                records=valid.records[:-1] + (forged_record,),
            )
        self.assertEqual(caught.exception.category, "manifest_invalid")

    def test_restored_manifest_rejects_non_server_derived_storage_key(self) -> None:
        lifecycle, _, artifact_id = self._sealed_first_output()
        initial = build_durable_artifact_storage_manifest(self._initial())
        valid = bind_sealed_artifact_idempotently(
            initial,
            lifecycle,
            artifact_id,
        ).manifest
        forged_record = replace(
            valid.records[-1],
            storage_key="immutable/jobs/job_storage_12345678/foreign/key",
        )

        with self.assertRaises(DurableArtifactStorageError) as caught:
            DurableArtifactStorageManifest(
                version=valid.version,
                lifecycle_id=valid.lifecycle_id,
                job_id=valid.job_id,
                records=valid.records[:-1] + (forged_record,),
            )
        self.assertEqual(caught.exception.category, "manifest_invalid")

    def test_valid_manifest_can_be_reconstructed_and_verified(self) -> None:
        lifecycle, _, artifact_id = self._sealed_first_output()
        initial = build_durable_artifact_storage_manifest(self._initial())
        valid = bind_sealed_artifact_idempotently(
            initial,
            lifecycle,
            artifact_id,
        ).manifest
        restored = DurableArtifactStorageManifest(
            version=valid.version,
            lifecycle_id=valid.lifecycle_id,
            job_id=valid.job_id,
            records=valid.records,
        )

        verify_durable_artifact_storage_manifest(restored, lifecycle)
        self.assertEqual(restored, valid)

    def test_manifest_and_records_are_immutable(self) -> None:
        manifest = build_durable_artifact_storage_manifest(self._initial())

        with self.assertRaises(FrozenInstanceError):
            manifest.records = ()  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            manifest.records[0].sha256 = "c" * 64  # type: ignore[misc]

    def test_extensible_artifact_id_fails_closed(self) -> None:
        lifecycle, _, artifact_id = self._sealed_first_output()
        manifest = build_durable_artifact_storage_manifest(self._initial())

        with self.assertRaises(DurableArtifactStorageError) as caught:
            bind_sealed_artifact_idempotently(
                manifest,
                lifecycle,
                _StringSubclass(artifact_id),
            )
        self.assertEqual(caught.exception.category, "artifact_id_invalid")

    def test_safe_evidence_is_bounded_and_has_no_runtime_authority(self) -> None:
        payload = build_durable_artifact_storage_manifest(
            self._initial()
        ).as_safe_dict()

        self.assertEqual(
            payload["policies"],
            {
                "serverDerivedKeys": True,
                "immutableObjects": True,
                "overwriteAllowed": False,
                "exactReplayAllowed": True,
                "crossCandidateWriteAllowed": False,
                "crossEngineWriteAllowed": False,
                "hashRequired": True,
            },
        )
        self.assertEqual(
            payload["boundaries"],
            {
                "providerSelected": False,
                "persistenceEnabled": False,
                "storageWritesEnabled": False,
                "queueEnabled": False,
                "networkDispatchEnabled": False,
                "orchestrationEnabled": False,
                "uploadEnabled": False,
                "teacherApproval": False,
                "publication": False,
            },
        )
        self.assertLessEqual(len(payload["records"]), 16)
        serialized = str(payload).lower()
        for raw_byte_field in (
            "contentbytes",
            "payloadbytes",
            "bodybytes",
            "rawbytes",
            "objectbytes",
        ):
            self.assertNotIn(raw_byte_field, serialized)

    def test_structural_manifest_rejects_duplicate_storage_keys(self) -> None:
        manifest = build_durable_artifact_storage_manifest(self._initial())
        duplicate = ArtifactStorageBinding(
            storage_key=manifest.records[0].storage_key,
            artifact_id="artifact_" + "d" * 24,
            artifact_ref="sources/job_storage_12345678/duplicate.pdf",
            kind="source",
            candidate_id=None,
            engine=None,
            sha256="d" * 64,
            size_bytes=1024,
            media_type="application/pdf",
        )

        with self.assertRaises(DurableArtifactStorageError) as caught:
            DurableArtifactStorageManifest(
                version=manifest.version,
                lifecycle_id=manifest.lifecycle_id,
                job_id=manifest.job_id,
                records=manifest.records + (duplicate,),
            )
        self.assertEqual(caught.exception.category, "manifest_invalid")


if __name__ == "__main__":
    unittest.main()
