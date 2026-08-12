from __future__ import annotations

from pathlib import Path
import sys
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_gateway.durable_restart_recovery import (
    DURABLE_RESTART_RECOVERY_CONTRACT_VERSION,
    DurableRestartRecoveryDecision,
    DurableRestartRecoveryError,
)


class DurableRestartRecoveryConvergenceTests(unittest.TestCase):
    def _kwargs(self) -> dict[str, object]:
        return {
            "version": DURABLE_RESTART_RECOVERY_CONTRACT_VERSION,
            "dispatch_identity_sha256": "a" * 64,
            "job_id": "job_recovery_12345678",
            "run_id": "run_" + "b" * 24,
            "engine": "homr",
            "state": "planned",
            "revision": 0,
            "storage_manifest_sha256": "c" * 64,
            "provenance_chain_sha256": "d" * 64,
            "disposition": "pre_dispatch_candidate",
            "terminal": False,
            "reconciliation_required": False,
            "automatic_execution_allowed": False,
            "retry_allowed": False,
            "network_dispatch_allowed": False,
            "state_mutation_allowed": False,
        }

    def test_direct_decision_rejects_unbounded_or_noncanonical_identity_fields(self) -> None:
        for field, value in (
            ("job_id", "x" * 4096),
            ("run_id", "run_invalid"),
            ("engine", "future-engine"),
        ):
            with self.subTest(field=field):
                kwargs = self._kwargs()
                kwargs[field] = value
                with self.assertRaises(DurableRestartRecoveryError):
                    DurableRestartRecoveryDecision(**kwargs)

    def test_direct_decision_rejects_impossible_state_revision_pair(self) -> None:
        kwargs = self._kwargs()
        kwargs.update(
            {
                "state": "running",
                "revision": 0,
                "disposition": "reconciliation_required",
                "reconciliation_required": True,
            }
        )
        with self.assertRaises(DurableRestartRecoveryError) as caught:
            DurableRestartRecoveryDecision(**kwargs)
        self.assertEqual(caught.exception.category, "decision_invalid")


if __name__ == "__main__":
    unittest.main()
