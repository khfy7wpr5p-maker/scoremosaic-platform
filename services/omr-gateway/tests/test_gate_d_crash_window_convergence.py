from __future__ import annotations

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
from scoremosaic_gateway.durable_idempotency import (
    apply_durable_transition_idempotently,
    build_durable_idempotency_ledger,
)
from scoremosaic_gateway.durable_job_state import build_durable_job_state
from scoremosaic_gateway.durable_provenance import (
    append_durable_provenance_record_idempotently,
    build_durable_provenance_chain,
)
from scoremosaic_gateway.durable_restart_recovery import (
    DurableRestartRecoveryError,
    evaluate_durable_restart_recovery,
)
from scoremosaic_gateway.orchestration import build_orchestration_plan


SOURCE_SHA = "a" * 64
CONTENT = {
    "raw_engine_result": ("b" * 64, 111, "application/octet-stream"),
    "musicxml": (
        "c" * 64,
        222,
        "application/vnd.recordare.musicxml+xml",
    ),
    "diagnostic": ("d" * 64, 333, "application/json"),
}


class GateDCrashWindowConvergenceTests(unittest.TestCase):
    def _context(self):
        job_id = "job_crash_window_12345678"
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
        ledger = build_durable_idempotency_ledger(snapshot)
        lifecycle = build_artifact_lifecycle(plan.as_dict())
        manifest = build_durable_artifact_storage_manifest(lifecycle)
        provenance = build_durable_provenance_chain(
            snapshot,
            manifest,
            lifecycle=lifecycle,
        )
        return snapshot, ledger, lifecycle, manifest, provenance

    def _advance(self, snapshot, ledger, lifecycle, manifest, provenance, next_state):
        applied = apply_durable_transition_idempotently(
            ledger,
            snapshot,
            next_state,
        )
        appended = append_durable_provenance_record_idempotently(
            provenance,
            applied.snapshot,
            manifest,
            lifecycle=lifecycle,
        )
        return applied.snapshot, applied.ledger, appended.chain

    def _advance_to_running(self, snapshot, ledger, lifecycle, manifest, provenance):
        for next_state in ("queued", "dispatching", "running"):
            snapshot, ledger, provenance = self._advance(
                snapshot,
                ledger,
                lifecycle,
                manifest,
                provenance,
                next_state,
            )
        return snapshot, ledger, provenance

    def _homr_candidate(self, lifecycle):
        return next(candidate for candidate in lifecycle.candidates if candidate.engine == "homr")

    def _seal_homr_candidate(self, lifecycle):
        candidate = self._homr_candidate(lifecycle)
        lifecycle = transition_candidate(lifecycle, candidate.candidate_id, "collecting")
        for original in candidate.artifacts:
            lifecycle = transition_artifact(lifecycle, original.artifact_id, "writing")
            sha256, size_bytes, media_type = CONTENT[original.kind]
            lifecycle = transition_artifact(
                lifecycle,
                original.artifact_id,
                "sealed",
                sha256=sha256,
                size_bytes=size_bytes,
                media_type=media_type,
            )
        lifecycle = transition_candidate(lifecycle, candidate.candidate_id, "sealed")
        return lifecycle

    def _bind_all_homr_artifacts(self, manifest, lifecycle):
        candidate = self._homr_candidate(lifecycle)
        for artifact in candidate.artifacts:
            manifest = bind_sealed_artifact_idempotently(
                manifest,
                lifecycle,
                artifact.artifact_id,
            ).manifest
        return manifest

    def test_completed_run_with_reserved_candidate_fails_closed(self) -> None:
        snapshot, ledger, lifecycle, manifest, provenance = self._context()
        snapshot, ledger, provenance = self._advance_to_running(
            snapshot, ledger, lifecycle, manifest, provenance
        )
        snapshot, ledger, provenance = self._advance(
            snapshot,
            ledger,
            lifecycle,
            manifest,
            provenance,
            "completed",
        )

        with self.assertRaises(DurableRestartRecoveryError) as caught:
            evaluate_durable_restart_recovery(
                snapshot,
                ledger,
                manifest,
                lifecycle=lifecycle,
                provenance=provenance,
            )
        self.assertEqual(caught.exception.category, "crash_window_mismatch")

    def test_completed_run_with_sealed_candidate_but_missing_storage_bindings_fails_closed(self) -> None:
        snapshot, ledger, lifecycle, manifest, provenance = self._context()
        snapshot, ledger, provenance = self._advance_to_running(
            snapshot, ledger, lifecycle, manifest, provenance
        )
        lifecycle = self._seal_homr_candidate(lifecycle)
        snapshot, ledger, provenance = self._advance(
            snapshot,
            ledger,
            lifecycle,
            manifest,
            provenance,
            "completed",
        )

        with self.assertRaises(DurableRestartRecoveryError) as caught:
            evaluate_durable_restart_recovery(
                snapshot,
                ledger,
                manifest,
                lifecycle=lifecycle,
                provenance=provenance,
            )
        self.assertEqual(caught.exception.category, "crash_window_mismatch")

    def test_pre_dispatch_snapshot_with_collecting_candidate_fails_closed(self) -> None:
        snapshot, ledger, lifecycle, manifest, provenance = self._context()
        applied = apply_durable_transition_idempotently(ledger, snapshot, "queued")
        snapshot, ledger = applied.snapshot, applied.ledger
        candidate = self._homr_candidate(lifecycle)
        lifecycle = transition_candidate(lifecycle, candidate.candidate_id, "collecting")
        provenance = append_durable_provenance_record_idempotently(
            provenance,
            snapshot,
            manifest,
            lifecycle=lifecycle,
        ).chain

        with self.assertRaises(DurableRestartRecoveryError) as caught:
            evaluate_durable_restart_recovery(
                snapshot,
                ledger,
                manifest,
                lifecycle=lifecycle,
                provenance=provenance,
            )
        self.assertEqual(caught.exception.category, "crash_window_mismatch")

    def test_failed_run_with_nonterminal_candidate_fails_closed(self) -> None:
        snapshot, ledger, lifecycle, manifest, provenance = self._context()
        for next_state in ("queued", "dispatching", "failed"):
            snapshot, ledger, provenance = self._advance(
                snapshot,
                ledger,
                lifecycle,
                manifest,
                provenance,
                next_state,
            )

        with self.assertRaises(DurableRestartRecoveryError) as caught:
            evaluate_durable_restart_recovery(
                snapshot,
                ledger,
                manifest,
                lifecycle=lifecycle,
                provenance=provenance,
            )
        self.assertEqual(caught.exception.category, "crash_window_mismatch")

    def test_running_partial_output_remains_reconciliation_only(self) -> None:
        snapshot, ledger, lifecycle, manifest, provenance = self._context()
        snapshot, ledger, provenance = self._advance_to_running(
            snapshot, ledger, lifecycle, manifest, provenance
        )
        candidate = self._homr_candidate(lifecycle)
        lifecycle = transition_candidate(lifecycle, candidate.candidate_id, "collecting")
        raw = candidate.artifacts[0]
        lifecycle = transition_artifact(lifecycle, raw.artifact_id, "writing")

        decision = evaluate_durable_restart_recovery(
            snapshot,
            ledger,
            manifest,
            lifecycle=lifecycle,
            provenance=provenance,
        )
        self.assertEqual(decision.disposition, "reconciliation_required")
        self.assertTrue(decision.reconciliation_required)
        self.assertFalse(decision.automatic_execution_allowed)
        self.assertFalse(decision.retry_allowed)
        self.assertFalse(decision.network_dispatch_allowed)
        self.assertFalse(decision.state_mutation_allowed)

    def test_completed_run_with_sealed_candidate_and_complete_manifest_is_preserved(self) -> None:
        snapshot, ledger, lifecycle, manifest, provenance = self._context()
        snapshot, ledger, provenance = self._advance_to_running(
            snapshot, ledger, lifecycle, manifest, provenance
        )
        lifecycle = self._seal_homr_candidate(lifecycle)
        manifest = self._bind_all_homr_artifacts(manifest, lifecycle)
        provenance = append_durable_provenance_record_idempotently(
            provenance,
            snapshot,
            manifest,
            lifecycle=lifecycle,
        ).chain
        snapshot, ledger, provenance = self._advance(
            snapshot,
            ledger,
            lifecycle,
            manifest,
            provenance,
            "completed",
        )

        decision = evaluate_durable_restart_recovery(
            snapshot,
            ledger,
            manifest,
            lifecycle=lifecycle,
            provenance=provenance,
        )
        self.assertEqual(decision.disposition, "terminal_preserved")
        self.assertTrue(decision.terminal)
        self.assertFalse(decision.reconciliation_required)
        self.assertFalse(decision.automatic_execution_allowed)
        self.assertFalse(decision.retry_allowed)
        self.assertFalse(decision.network_dispatch_allowed)
        self.assertFalse(decision.state_mutation_allowed)


if __name__ == "__main__":
    unittest.main()
