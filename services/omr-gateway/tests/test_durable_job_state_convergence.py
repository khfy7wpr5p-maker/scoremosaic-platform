import unittest

from scoremosaic_gateway.dispatch_identity import build_dispatch_identity
from scoremosaic_gateway.durable_job_state import (
    DURABLE_JOB_STATE_CONTRACT_VERSION,
    JOB_RUN_STATES,
    DurableJobStateError,
    DurableJobStateSnapshot,
    build_durable_job_state,
    transition_durable_job_state,
)
from scoremosaic_gateway.orchestration import build_orchestration_plan


class DurableJobStateConvergenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = build_orchestration_plan(
            "job_durable002",
            source_artifact_ref="sources/job_durable002/source.pdf",
            source_sha256="2" * 64,
            source_size_bytes=8192,
            source_media_type="application/pdf",
        )
        self.binding = build_dispatch_identity(self.plan.as_dict(), "homr")

    def _snapshot_for(self, state: str):
        snapshot = build_durable_job_state(self.binding)
        paths = {
            "planned": (),
            "queued": ("queued",),
            "dispatching": ("queued", "dispatching"),
            "running": ("queued", "dispatching", "running"),
            "completed": ("queued", "dispatching", "running", "completed"),
            "failed": ("queued", "dispatching", "failed"),
            "cancelled": ("cancelled",),
            "timed_out": ("queued", "timed_out"),
        }
        for next_state in paths[state]:
            snapshot = transition_durable_job_state(snapshot, next_state)
        return snapshot

    def test_transition_graph_matches_existing_orchestration_contract(self) -> None:
        lifecycle = self.plan.as_dict()["lifecyclePolicy"]
        expected = {
            state: tuple(lifecycle["allowedEngineRunTransitions"][state])
            for state in JOB_RUN_STATES
        }

        for current_state in JOB_RUN_STATES:
            current = self._snapshot_for(current_state)
            for next_state in JOB_RUN_STATES:
                with self.subTest(current=current_state, next=next_state):
                    if next_state in expected[current_state]:
                        transitioned = transition_durable_job_state(current, next_state)
                        self.assertEqual(transitioned.state, next_state)
                    else:
                        with self.assertRaises(DurableJobStateError) as caught:
                            transition_durable_job_state(current, next_state)
                        self.assertEqual(
                            caught.exception.category, "state_transition_invalid"
                        )

    def test_impossible_restored_state_revision_pairs_fail_closed(self) -> None:
        impossible = (
            ("queued", 2),
            ("dispatching", 1),
            ("running", 2),
            ("completed", 1),
            ("failed", 1),
            ("timed_out", 1),
        )
        for state, revision in impossible:
            with self.subTest(state=state, revision=revision):
                with self.assertRaises(DurableJobStateError) as caught:
                    DurableJobStateSnapshot(
                        version=DURABLE_JOB_STATE_CONTRACT_VERSION,
                        binding=self.binding,
                        state=state,
                        revision=revision,
                    )
                self.assertEqual(caught.exception.category, "revision_state_mismatch")


if __name__ == "__main__":
    unittest.main()
