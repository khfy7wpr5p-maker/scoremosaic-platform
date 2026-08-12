from dataclasses import FrozenInstanceError
import unittest

from scoremosaic_gateway.dispatch_identity import build_dispatch_identity
from scoremosaic_gateway.orchestration import build_orchestration_plan
from scoremosaic_gateway.durable_job_state import (
    DURABLE_JOB_STATE_CONTRACT_VERSION,
    JOB_RUN_STATES,
    TERMINAL_JOB_RUN_STATES,
    DurableJobStateError,
    DurableJobStateSnapshot,
    build_durable_job_state,
    transition_durable_job_state,
)


class _StringSubclass(str):
    pass


class DurableJobStateTests(unittest.TestCase):
    def setUp(self) -> None:
        plan = build_orchestration_plan(
            "job_durable001",
            source_artifact_ref="sources/job_durable001/source.pdf",
            source_sha256="1" * 64,
            source_size_bytes=4096,
            source_media_type="application/pdf",
        )
        self.binding = build_dispatch_identity(plan.as_dict(), "homr")

    def test_closed_state_vocabulary_matches_existing_engine_run_lifecycle(self) -> None:
        self.assertEqual(
            JOB_RUN_STATES,
            (
                "planned",
                "queued",
                "dispatching",
                "running",
                "completed",
                "failed",
                "cancelled",
                "timed_out",
            ),
        )
        self.assertEqual(
            TERMINAL_JOB_RUN_STATES,
            ("completed", "failed", "cancelled", "timed_out"),
        )

    def test_initial_snapshot_is_immutable_and_bound_to_exact_dispatch_identity(self) -> None:
        snapshot = build_durable_job_state(self.binding)

        self.assertEqual(snapshot.version, DURABLE_JOB_STATE_CONTRACT_VERSION)
        self.assertIs(snapshot.binding, self.binding)
        self.assertEqual(snapshot.state, "planned")
        self.assertEqual(snapshot.revision, 0)
        self.assertEqual(snapshot.dispatch_identity_sha256, self.binding.identity_sha256)
        self.assertEqual(snapshot.job_id, self.binding.job_id)
        self.assertEqual(snapshot.source_artifact_id, self.binding.source_artifact_id)
        self.assertEqual(snapshot.source_sha256, self.binding.source_sha256)
        self.assertEqual(snapshot.run_id, self.binding.run_id)
        self.assertEqual(snapshot.engine, self.binding.engine)

        with self.assertRaises(FrozenInstanceError):
            snapshot.state = "queued"  # type: ignore[misc]

    def test_allowed_path_preserves_identity_and_advances_revision(self) -> None:
        state = build_durable_job_state(self.binding)
        for expected_revision, next_state in enumerate(
            ("queued", "dispatching", "running", "completed"),
            start=1,
        ):
            previous = state
            state = transition_durable_job_state(state, next_state)
            self.assertIs(state.binding, self.binding)
            self.assertEqual(state.dispatch_identity_sha256, self.binding.identity_sha256)
            self.assertEqual(state.state, next_state)
            self.assertEqual(state.revision, expected_revision)
            self.assertEqual(previous.revision + 1, state.revision)

    def test_invalid_skip_and_same_state_transitions_fail_closed(self) -> None:
        state = build_durable_job_state(self.binding)

        with self.assertRaises(DurableJobStateError) as skipped:
            transition_durable_job_state(state, "running")
        self.assertEqual(skipped.exception.category, "state_transition_invalid")

        with self.assertRaises(DurableJobStateError) as repeated:
            transition_durable_job_state(state, "planned")
        self.assertEqual(repeated.exception.category, "state_transition_invalid")

    def test_terminal_states_cannot_reopen(self) -> None:
        terminal_snapshots = []

        completed = build_durable_job_state(self.binding)
        for next_state in ("queued", "dispatching", "running", "completed"):
            completed = transition_durable_job_state(completed, next_state)
        terminal_snapshots.append(completed)

        failed = build_durable_job_state(self.binding)
        for next_state in ("queued", "dispatching", "failed"):
            failed = transition_durable_job_state(failed, next_state)
        terminal_snapshots.append(failed)

        cancelled = transition_durable_job_state(
            build_durable_job_state(self.binding), "cancelled"
        )
        terminal_snapshots.append(cancelled)

        timed_out = build_durable_job_state(self.binding)
        timed_out = transition_durable_job_state(timed_out, "queued")
        timed_out = transition_durable_job_state(timed_out, "timed_out")
        terminal_snapshots.append(timed_out)

        for terminal in terminal_snapshots:
            with self.subTest(state=terminal.state):
                with self.assertRaises(DurableJobStateError) as caught:
                    transition_durable_job_state(terminal, "queued")
                self.assertEqual(caught.exception.category, "state_transition_invalid")

    def test_unknown_or_extensible_string_states_are_rejected(self) -> None:
        state = build_durable_job_state(self.binding)

        for next_state in ("unknown", _StringSubclass("queued")):
            with self.subTest(next_state=repr(next_state)):
                with self.assertRaises(DurableJobStateError) as caught:
                    transition_durable_job_state(state, next_state)
                self.assertEqual(caught.exception.category, "state_invalid")

        with self.assertRaises(DurableJobStateError) as caught:
            DurableJobStateSnapshot(
                version=DURABLE_JOB_STATE_CONTRACT_VERSION,
                binding=self.binding,
                state=_StringSubclass("planned"),
                revision=0,
            )
        self.assertEqual(caught.exception.category, "state_invalid")

    def test_invalid_binding_and_revision_shapes_are_rejected(self) -> None:
        with self.assertRaises(DurableJobStateError) as caught:
            build_durable_job_state(object())  # type: ignore[arg-type]
        self.assertEqual(caught.exception.category, "dispatch_identity_invalid")

        for revision in (-1, True, 1.5):
            with self.subTest(revision=revision):
                with self.assertRaises(DurableJobStateError) as caught:
                    DurableJobStateSnapshot(
                        version=DURABLE_JOB_STATE_CONTRACT_VERSION,
                        binding=self.binding,
                        state="planned",
                        revision=revision,  # type: ignore[arg-type]
                    )
                self.assertEqual(caught.exception.category, "revision_invalid")

    def test_safe_dict_is_bounded_and_contains_no_storage_or_transport_authority(self) -> None:
        snapshot = build_durable_job_state(self.binding)
        self.assertEqual(
            snapshot.as_safe_dict(),
            {
                "version": DURABLE_JOB_STATE_CONTRACT_VERSION,
                "dispatchIdentitySha256": self.binding.identity_sha256,
                "planId": self.binding.plan_id,
                "planSha256": self.binding.plan_sha256,
                "jobId": self.binding.job_id,
                "sourceArtifactId": self.binding.source_artifact_id,
                "sourceSha256": self.binding.source_sha256,
                "runId": self.binding.run_id,
                "engine": self.binding.engine,
                "state": "planned",
                "revision": 0,
            },
        )


if __name__ == "__main__":
    unittest.main()
