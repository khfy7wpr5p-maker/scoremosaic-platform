from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path
import sys
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_gateway.artifact_lifecycle import build_artifact_lifecycle
from scoremosaic_gateway.dispatch_identity import build_dispatch_identity
from scoremosaic_gateway.durable_artifact_storage import (
    build_durable_artifact_storage_manifest,
)
from scoremosaic_gateway.durable_idempotency import (
    DurableIdempotencyLedger,
    apply_durable_transition_idempotently,
    build_durable_idempotency_ledger,
)
from scoremosaic_gateway.durable_job_state import build_durable_job_state
from scoremosaic_gateway.durable_provenance import (
    DurableProvenanceChain,
    append_durable_provenance_record_idempotently,
    build_durable_provenance_chain,
)
from scoremosaic_gateway.durable_restart_recovery import (
    DURABLE_RESTART_RECOVERY_CONTRACT_VERSION,
    DurableRestartRecoveryError,
    evaluate_durable_restart_recovery,
)
from scoremosaic_gateway.orchestration import build_orchestration_plan


SOURCE_SHA = "a" * 64


class DurableRestartRecoveryContractTests(unittest.TestCase):
    def _context(self, job_id: str = "job_recovery_12345678"):
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

    def _advance(
        self,
        snapshot,
        ledger: DurableIdempotencyLedger,
        lifecycle,
        manifest,
        provenance: DurableProvenanceChain,
        next_state: str,
    ):
        applied = apply_durable_transition_idempotently(
            ledger,
            snapshot,
            next_state,
        )
        provenance_result = append_durable_provenance_record_idempotently(
            provenance,
            applied.snapshot,
            manifest,
            lifecycle=lifecycle,
        )
        return applied.snapshot, applied.ledger, provenance_result.chain

    def _decision_for_state(self, state: str):
        snapshot, ledger, lifecycle, manifest, provenance = self._context()
        path = {
            "planned": (),
            "queued": ("queued",),
            "dispatching": ("queued", "dispatching"),
            "running": ("queued", "dispatching", "running"),
            "completed": ("queued", "dispatching", "running", "completed"),
            "failed": ("queued", "dispatching", "failed"),
            "cancelled": ("cancelled",),
            "timed_out": ("queued", "timed_out"),
        }[state]
        for next_state in path:
            snapshot, ledger, provenance = self._advance(
                snapshot,
                ledger,
                lifecycle,
                manifest,
                provenance,
                next_state,
            )
        decision = evaluate_durable_restart_recovery(
            snapshot,
            ledger,
            manifest,
            lifecycle=lifecycle,
            provenance=provenance,
        )
        return decision

    def test_planned_and_queued_are_pre_dispatch_candidates_without_execution_authority(self) -> None:
        for state in ("planned", "queued"):
            with self.subTest(state=state):
                decision = self._decision_for_state(state)
                self.assertEqual(
                    decision.version,
                    DURABLE_RESTART_RECOVERY_CONTRACT_VERSION,
                )
                self.assertEqual(decision.state, state)
                self.assertEqual(decision.disposition, "pre_dispatch_candidate")
                self.assertFalse(decision.terminal)
                self.assertFalse(decision.reconciliation_required)
                self.assertFalse(decision.automatic_execution_allowed)
                self.assertFalse(decision.retry_allowed)
                self.assertFalse(decision.network_dispatch_allowed)
                self.assertFalse(decision.state_mutation_allowed)

    def test_dispatching_and_running_require_reconciliation_and_never_resume_automatically(self) -> None:
        for state in ("dispatching", "running"):
            with self.subTest(state=state):
                decision = self._decision_for_state(state)
                self.assertEqual(decision.state, state)
                self.assertEqual(decision.disposition, "reconciliation_required")
                self.assertFalse(decision.terminal)
                self.assertTrue(decision.reconciliation_required)
                self.assertFalse(decision.automatic_execution_allowed)
                self.assertFalse(decision.retry_allowed)
                self.assertFalse(decision.network_dispatch_allowed)
                self.assertFalse(decision.state_mutation_allowed)

    def test_all_terminal_states_are_preserved_and_cannot_reopen(self) -> None:
        for state in ("completed", "failed", "cancelled", "timed_out"):
            with self.subTest(state=state):
                decision = self._decision_for_state(state)
                self.assertEqual(decision.state, state)
                self.assertEqual(decision.disposition, "terminal_preserved")
                self.assertTrue(decision.terminal)
                self.assertFalse(decision.reconciliation_required)
                self.assertFalse(decision.automatic_execution_allowed)
                self.assertFalse(decision.retry_allowed)
                self.assertFalse(decision.network_dispatch_allowed)
                self.assertFalse(decision.state_mutation_allowed)

    def test_exact_restore_is_read_only_and_does_not_append_state_or_provenance(self) -> None:
        snapshot, ledger, lifecycle, manifest, provenance = self._context()
        snapshot, ledger, provenance = self._advance(
            snapshot,
            ledger,
            lifecycle,
            manifest,
            provenance,
            "queued",
        )
        state_revision = snapshot.revision
        ledger_records = ledger.records
        provenance_records = provenance.records

        first = evaluate_durable_restart_recovery(
            snapshot,
            ledger,
            manifest,
            lifecycle=lifecycle,
            provenance=provenance,
        )
        second = evaluate_durable_restart_recovery(
            snapshot,
            ledger,
            manifest,
            lifecycle=lifecycle,
            provenance=provenance,
        )

        self.assertEqual(first, second)
        self.assertEqual(snapshot.revision, state_revision)
        self.assertEqual(ledger.records, ledger_records)
        self.assertEqual(provenance.records, provenance_records)

    def test_ledger_tip_must_match_exact_restored_snapshot(self) -> None:
        snapshot, ledger, lifecycle, manifest, provenance = self._context()
        applied = apply_durable_transition_idempotently(ledger, snapshot, "queued")
        queued = applied.snapshot
        queued_provenance = append_durable_provenance_record_idempotently(
            provenance,
            queued,
            manifest,
            lifecycle=lifecycle,
        ).chain

        with self.assertRaises(DurableRestartRecoveryError) as caught:
            evaluate_durable_restart_recovery(
                queued,
                ledger,
                manifest,
                lifecycle=lifecycle,
                provenance=queued_provenance,
            )
        self.assertEqual(caught.exception.category, "idempotency_state_mismatch")

    def test_provenance_tip_must_match_exact_restored_snapshot_and_manifest(self) -> None:
        snapshot, ledger, lifecycle, manifest, provenance = self._context()
        applied = apply_durable_transition_idempotently(ledger, snapshot, "queued")

        with self.assertRaises(DurableRestartRecoveryError) as caught:
            evaluate_durable_restart_recovery(
                applied.snapshot,
                applied.ledger,
                manifest,
                lifecycle=lifecycle,
                provenance=provenance,
            )
        self.assertEqual(caught.exception.category, "provenance_mismatch")

    def test_cross_job_recovery_evidence_fails_closed(self) -> None:
        snapshot, ledger, lifecycle, manifest, provenance = self._context()
        _, other_ledger, _, _, _ = self._context("job_recovery_87654321")

        with self.assertRaises(DurableRestartRecoveryError) as caught:
            evaluate_durable_restart_recovery(
                snapshot,
                other_ledger,
                manifest,
                lifecycle=lifecycle,
                provenance=provenance,
            )
        self.assertEqual(caught.exception.category, "identity_mismatch")

    def test_decision_is_immutable_and_safe_evidence_has_no_runtime_authority(self) -> None:
        decision = self._decision_for_state("running")
        with self.assertRaises(FrozenInstanceError):
            decision.disposition = "pre_dispatch_candidate"  # type: ignore[misc]

        safe = decision.as_safe_dict()
        self.assertEqual(safe["state"], "running")
        self.assertEqual(safe["disposition"], "reconciliation_required")
        self.assertFalse(safe["automaticExecutionAllowed"])
        self.assertFalse(safe["retryAllowed"])
        self.assertFalse(safe["networkDispatchAllowed"])
        self.assertFalse(safe["stateMutationAllowed"])
        self.assertNotIn("payload", safe)
        self.assertNotIn("credential", safe)
        self.assertNotIn("storageKey", safe)
        self.assertNotIn("provider", safe)


if __name__ == "__main__":
    unittest.main()
