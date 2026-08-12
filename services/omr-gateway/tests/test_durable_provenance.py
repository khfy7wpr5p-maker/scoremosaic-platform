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
from scoremosaic_gateway.dispatch_identity import build_dispatch_identity
from scoremosaic_gateway.durable_artifact_storage import (
    bind_sealed_artifact_idempotently,
    build_durable_artifact_storage_manifest,
)
from scoremosaic_gateway.durable_job_state import (
    build_durable_job_state,
    transition_durable_job_state,
)
from scoremosaic_gateway.orchestration import build_orchestration_plan
from scoremosaic_gateway.durable_provenance import (
    DURABLE_PROVENANCE_CONTRACT_VERSION,
    DurableProvenanceChain,
    DurableProvenanceError,
    append_durable_provenance_record_idempotently,
    build_durable_provenance_chain,
    verify_durable_provenance_chain,
)


SOURCE_SHA = "a" * 64
OUTPUT_SHA = "b" * 64


class DurableProvenanceContractTests(unittest.TestCase):
    def _context(self, job_id: str = "job_provenance_12345678"):
        plan = build_orchestration_plan(
            job_id,
            source_artifact_ref=f"sources/{job_id}/input.pdf",
            source_sha256=SOURCE_SHA,
            source_size_bytes=4096,
            source_media_type="application/pdf",
            requested_engines=("clarity", "audiveris", "homr"),
        )
        binding = build_dispatch_identity(plan.as_dict(), "homr")
        snapshot = build_durable_job_state(binding)
        lifecycle = build_artifact_lifecycle(plan.as_dict())
        manifest = build_durable_artifact_storage_manifest(lifecycle)
        self.assertEqual(snapshot.job_id, lifecycle.job_id)
        self.assertEqual(
            snapshot.source_artifact_id,
            lifecycle.source_artifact.artifact_id,
        )
        self.assertEqual(snapshot.source_sha256, lifecycle.source_artifact.sha256)
        return snapshot, lifecycle, manifest

    def _manifest_with_first_output(self):
        snapshot, lifecycle, manifest = self._context()
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
        manifest = bind_sealed_artifact_idempotently(
            manifest,
            lifecycle,
            artifact.artifact_id,
        ).manifest
        return snapshot, lifecycle, manifest

    def test_initial_record_binds_exact_job_run_source_and_storage_hashes(self) -> None:
        snapshot, lifecycle, manifest = self._context()
        chain = build_durable_provenance_chain(
            snapshot,
            manifest,
            lifecycle=lifecycle,
        )

        self.assertEqual(chain.version, DURABLE_PROVENANCE_CONTRACT_VERSION)
        self.assertEqual(len(chain.records), 1)
        record = chain.records[0]
        self.assertEqual(record.sequence, 0)
        self.assertIsNone(record.previous_record_sha256)
        self.assertEqual(
            record.dispatch_identity_sha256,
            snapshot.dispatch_identity_sha256,
        )
        self.assertEqual(record.plan_id, snapshot.plan_id)
        self.assertEqual(record.plan_sha256, snapshot.plan_sha256)
        self.assertEqual(record.job_id, snapshot.job_id)
        self.assertEqual(record.source_artifact_id, snapshot.source_artifact_id)
        self.assertEqual(record.source_sha256, snapshot.source_sha256)
        self.assertEqual(record.run_id, snapshot.run_id)
        self.assertEqual(record.engine, snapshot.engine)
        self.assertEqual(record.state, "planned")
        self.assertEqual(record.state_revision, 0)
        self.assertEqual(record.storage_manifest_sha256, manifest.manifest_sha256)
        self.assertEqual(
            record.storage_binding_sha256s,
            tuple(item.binding_sha256 for item in manifest.records),
        )
        verify_durable_provenance_chain(
            chain,
            snapshot,
            manifest,
            lifecycle=lifecycle,
        )

    def test_exact_replay_returns_same_chain_without_duplicate_record(self) -> None:
        snapshot, lifecycle, manifest = self._context()
        initial = build_durable_provenance_chain(
            snapshot,
            manifest,
            lifecycle=lifecycle,
        )
        replay = append_durable_provenance_record_idempotently(
            initial,
            snapshot,
            manifest,
            lifecycle=lifecycle,
        )

        self.assertTrue(replay.replayed)
        self.assertIs(replay.chain, initial)
        self.assertEqual(len(replay.chain.records), 1)

    def test_state_advance_appends_hash_chained_record(self) -> None:
        snapshot, lifecycle, manifest = self._context()
        initial = build_durable_provenance_chain(
            snapshot,
            manifest,
            lifecycle=lifecycle,
        )
        queued = transition_durable_job_state(snapshot, "queued")
        result = append_durable_provenance_record_idempotently(
            initial,
            queued,
            manifest,
            lifecycle=lifecycle,
        )

        self.assertFalse(result.replayed)
        self.assertEqual(len(result.chain.records), 2)
        previous, current = result.chain.records
        self.assertEqual(current.sequence, 1)
        self.assertEqual(current.previous_record_sha256, previous.record_sha256)
        self.assertEqual(current.state, "queued")
        self.assertEqual(current.state_revision, 1)
        verify_durable_provenance_chain(
            result.chain,
            queued,
            manifest,
            lifecycle=lifecycle,
        )

    def test_storage_manifest_advance_can_append_with_same_job_state_revision(self) -> None:
        snapshot, lifecycle, manifest = self._manifest_with_first_output()
        source_only = build_durable_artifact_storage_manifest(lifecycle)
        initial = build_durable_provenance_chain(
            snapshot,
            source_only,
            lifecycle=lifecycle,
        )
        result = append_durable_provenance_record_idempotently(
            initial,
            snapshot,
            manifest,
            lifecycle=lifecycle,
        )

        self.assertFalse(result.replayed)
        self.assertEqual(result.chain.records[-1].state_revision, 0)
        self.assertEqual(
            result.chain.records[-1].previous_record_sha256,
            result.chain.records[-2].record_sha256,
        )
        self.assertNotEqual(
            result.chain.records[-1].storage_manifest_sha256,
            result.chain.records[-2].storage_manifest_sha256,
        )

    def test_cross_job_or_source_manifest_binding_fails_closed(self) -> None:
        snapshot, _, _ = self._context()
        _, other_lifecycle, other_manifest = self._context(
            "job_provenance_87654321"
        )

        with self.assertRaises(DurableProvenanceError) as caught:
            build_durable_provenance_chain(
                snapshot,
                other_manifest,
                lifecycle=other_lifecycle,
            )
        self.assertEqual(caught.exception.category, "identity_mismatch")

    def test_state_revision_cannot_go_backwards_or_change_state_at_same_revision(self) -> None:
        snapshot, lifecycle, manifest = self._context()
        chain = build_durable_provenance_chain(
            snapshot,
            manifest,
            lifecycle=lifecycle,
        )
        queued = transition_durable_job_state(snapshot, "queued")
        chain = append_durable_provenance_record_idempotently(
            chain,
            queued,
            manifest,
            lifecycle=lifecycle,
        ).chain

        with self.assertRaises(DurableProvenanceError) as caught:
            append_durable_provenance_record_idempotently(
                chain,
                snapshot,
                manifest,
                lifecycle=lifecycle,
            )
        self.assertEqual(caught.exception.category, "state_history_invalid")

        cancelled = transition_durable_job_state(snapshot, "cancelled")
        with self.assertRaises(DurableProvenanceError) as caught:
            append_durable_provenance_record_idempotently(
                chain,
                cancelled,
                manifest,
                lifecycle=lifecycle,
            )
        self.assertEqual(caught.exception.category, "state_history_invalid")

    def test_restored_chain_rejects_sequence_gap(self) -> None:
        snapshot, lifecycle, manifest = self._context()
        chain = build_durable_provenance_chain(
            snapshot,
            manifest,
            lifecycle=lifecycle,
        )
        queued = transition_durable_job_state(snapshot, "queued")
        chain = append_durable_provenance_record_idempotently(
            chain,
            queued,
            manifest,
            lifecycle=lifecycle,
        ).chain
        forged_last = replace(chain.records[-1], sequence=2)

        with self.assertRaises(DurableProvenanceError) as caught:
            DurableProvenanceChain(
                version=chain.version,
                records=(chain.records[0], forged_last),
            )
        self.assertEqual(caught.exception.category, "chain_invalid")

    def test_restored_chain_rejects_previous_hash_tamper(self) -> None:
        snapshot, lifecycle, manifest = self._context()
        chain = build_durable_provenance_chain(
            snapshot,
            manifest,
            lifecycle=lifecycle,
        )
        queued = transition_durable_job_state(snapshot, "queued")
        chain = append_durable_provenance_record_idempotently(
            chain,
            queued,
            manifest,
            lifecycle=lifecycle,
        ).chain
        forged_last = replace(
            chain.records[-1],
            previous_record_sha256="f" * 64,
        )

        with self.assertRaises(DurableProvenanceError) as caught:
            DurableProvenanceChain(
                version=chain.version,
                records=(chain.records[0], forged_last),
            )
        self.assertEqual(caught.exception.category, "chain_invalid")

    def test_restore_verification_rejects_latest_manifest_hash_mismatch(self) -> None:
        snapshot, lifecycle, manifest = self._context()
        chain = build_durable_provenance_chain(
            snapshot,
            manifest,
            lifecycle=lifecycle,
        )
        forged_record = replace(
            chain.records[0],
            storage_manifest_sha256="f" * 64,
        )
        forged_chain = DurableProvenanceChain(
            version=chain.version,
            records=(forged_record,),
        )

        with self.assertRaises(DurableProvenanceError) as caught:
            verify_durable_provenance_chain(
                forged_chain,
                snapshot,
                manifest,
                lifecycle=lifecycle,
            )
        self.assertEqual(caught.exception.category, "provenance_mismatch")

    def test_records_and_chain_are_immutable(self) -> None:
        snapshot, lifecycle, manifest = self._context()
        chain = build_durable_provenance_chain(
            snapshot,
            manifest,
            lifecycle=lifecycle,
        )

        with self.assertRaises(FrozenInstanceError):
            chain.records = ()  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            chain.records[0].state = "queued"  # type: ignore[misc]

    def test_safe_evidence_is_bounded_and_has_no_persistence_or_runtime_authority(self) -> None:
        snapshot, lifecycle, manifest = self._context()
        payload = build_durable_provenance_chain(
            snapshot,
            manifest,
            lifecycle=lifecycle,
        ).as_safe_dict()

        self.assertTrue(payload["policies"]["lifecycleVerificationRequired"])
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
        self.assertLessEqual(len(payload["records"]), 32)
        serialized = str(payload).lower()
        for forbidden in (
            "contentbytes",
            "payloadbytes",
            "bodybytes",
            "rawbytes",
            "objectbytes",
            "credential",
            "authorization",
        ):
            self.assertNotIn(forbidden, serialized)


if __name__ == "__main__":
    unittest.main()
