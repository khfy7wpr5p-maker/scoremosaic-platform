from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import sys
import tempfile
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

import test_safe_upload_finalization as helpers
from scoremosaic_gateway.config import EngineEndpoint
from scoremosaic_gateway.controlled_staging_dispatch_intent import (
    persist_controlled_staging_dispatch_intent,
)
from scoremosaic_gateway.controlled_staging_dispatching_transition import (
    ControlledStagingDispatchingTransitionError,
    recover_controlled_staging_dispatching_run,
    transition_controlled_staging_queued_to_dispatching,
)
from scoremosaic_gateway.controlled_staging_job_lifecycle import (
    run_controlled_staging_job_lifecycle,
)
from scoremosaic_gateway.controlled_staging_queued_transition import (
    queue_controlled_staging_run,
)
from scoremosaic_gateway.controlled_staging_terminal_cancellation import (
    ControlledStagingTerminalCancellationError,
    cancel_controlled_staging_queued_run,
    recover_controlled_staging_cancelled_run,
)
from scoremosaic_gateway.controlled_staging_transition_state import transition_record_path
from scoremosaic_gateway.dispatch_target import APPROVED_ENGINE_ORIGINS
from scoremosaic_gateway.minimum_staging_vertical_slice import (
    StagingUploadProvider,
    run_minimum_staging_vertical_slice,
)


class ControlledStagingDispatchingTransitionTests(unittest.TestCase):
    def setUp(self) -> None:
        fixture = helpers.SafeUploadFinalizationContractTests(methodName="runTest")
        fixture.setUp()
        self.admission = fixture._admission()
        self.session_policy = fixture.session_policy
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.key = b"D" * 32
        self.provider = StagingUploadProvider(
            self.root,
            state_integrity_key=self.key,
        )
        self.minimum_slice = run_minimum_staging_vertical_slice(
            admission=self.admission,
            session_policy=self.session_policy,
            payload=helpers.PNG_1X1,
            original_filename="scan.png",
            declared_media_type="image/png",
            observed_at_epoch_s=self.admission.evaluated_at_epoch_s,
            provider=self.provider,
        )
        run_controlled_staging_job_lifecycle(
            minimum_slice=self.minimum_slice,
            provider=self.provider,
        )
        self.endpoint = EngineEndpoint(
            "audiveris",
            APPROVED_ENGINE_ORIGINS["staging"]["audiveris"],
        )
        self.queued = queue_controlled_staging_run(
            minimum_slice=self.minimum_slice,
            provider=self.provider,
            engine=self.endpoint.name,
        )
        self.intent = persist_controlled_staging_dispatch_intent(
            minimum_slice=self.minimum_slice,
            provider=self.provider,
            endpoint=self.endpoint,
        )

    def _dispatch(self, *, provider=None, endpoint=None):
        return transition_controlled_staging_queued_to_dispatching(
            minimum_slice=self.minimum_slice,
            provider=self.provider if provider is None else provider,
            endpoint=self.endpoint if endpoint is None else endpoint,
        )

    def _cancel(self, *, provider=None):
        return cancel_controlled_staging_queued_run(
            minimum_slice=self.minimum_slice,
            provider=self.provider if provider is None else provider,
            engine=self.endpoint.name,
        )

    def _rev2_path(self) -> Path:
        return transition_record_path(
            self.provider,
            job_id=self.queued.job_id,
            run_id=self.queued.run_id,
            revision=2,
        )

    def test_dispatching_claim_is_exact_create_once_and_non_executable(self) -> None:
        first = self._dispatch()
        path = self._rev2_path()
        expected_bytes = path.read_bytes()
        replay = self._dispatch()

        self.assertEqual((first.state, first.revision), ("dispatching", 2))
        self.assertEqual(first.persistence_state, "written")
        self.assertEqual(replay.persistence_state, "replay")
        self.assertEqual(first.dispatch_identity_sha256, self.queued.dispatch_identity_sha256)
        self.assertEqual(first.dispatch_intent_sha256, replay.dispatch_intent_sha256)
        self.assertEqual(path.read_bytes(), expected_bytes)
        self.assertTrue(first.reconciliation_required)
        self.assertEqual(first.recovery_disposition, "reconciliation_required")

        for attribute in (
            "credential_resolution_allowed",
            "request_signing_allowed",
            "network_dispatch_allowed",
            "automatic_retry_allowed",
            "automatic_execution_allowed",
            "engine_execution_allowed",
            "further_state_mutation_allowed",
            "source_mutation_allowed",
        ):
            self.assertIs(getattr(first, attribute), False)

    def test_restart_recovery_is_reconciliation_only_and_never_auto_retries(self) -> None:
        self._dispatch()
        expected_bytes = self._rev2_path().read_bytes()
        restarted = StagingUploadProvider(
            self.root,
            state_integrity_key=self.key,
        )

        for attempt in range(10):
            with self.subTest(attempt=attempt + 1):
                decision = recover_controlled_staging_dispatching_run(
                    minimum_slice=self.minimum_slice,
                    provider=restarted,
                    endpoint=self.endpoint,
                )
                self.assertEqual((decision.state, decision.revision), ("dispatching", 2))
                self.assertEqual(decision.disposition, "reconciliation_required")
                self.assertTrue(decision.reconciliation_required)
                self.assertFalse(decision.automatic_execution_allowed)
                self.assertFalse(decision.retry_allowed)
                self.assertFalse(decision.network_dispatch_allowed)
                self.assertFalse(decision.state_mutation_allowed)
                self.assertEqual(self._rev2_path().read_bytes(), expected_bytes)

    def test_missing_dispatch_intent_fails_without_revision_two_publication(self) -> None:
        intent_path = (
            self.root
            / "state"
            / "dispatch_intents"
            / self.queued.job_id
            / f"{self.queued.run_id}.json"
        )
        intent_path.chmod(0o600)
        intent_path.unlink()

        with self.assertRaisesRegex(
            ControlledStagingDispatchingTransitionError,
            "staging_dispatching_intent_invalid",
        ):
            self._dispatch()
        self.assertFalse(self._rev2_path().exists())

    def test_existing_terminal_cancellation_wins_and_is_never_rewritten(self) -> None:
        cancelled = self._cancel()
        self.assertEqual((cancelled.state, cancelled.revision), ("cancelled", 2))
        path = self._rev2_path()
        expected_bytes = path.read_bytes()

        for attempt in range(5):
            with self.subTest(attempt=attempt + 1):
                with self.assertRaisesRegex(
                    ControlledStagingDispatchingTransitionError,
                    "staging_dispatching_revision_conflict",
                ):
                    self._dispatch()
                self.assertTrue(path.exists())
                self.assertEqual(path.read_bytes(), expected_bytes)

        decision = recover_controlled_staging_cancelled_run(
            minimum_slice=self.minimum_slice,
            provider=self.provider,
            engine=self.endpoint.name,
        )
        self.assertEqual((decision.state, decision.revision), ("cancelled", 2))
        self.assertTrue(decision.terminal)
        self.assertFalse(decision.retry_allowed)

    def test_existing_dispatching_claim_wins_and_cancellation_cannot_overwrite_it(self) -> None:
        dispatching = self._dispatch()
        self.assertEqual((dispatching.state, dispatching.revision), ("dispatching", 2))
        path = self._rev2_path()
        expected_bytes = path.read_bytes()

        for attempt in range(5):
            with self.subTest(attempt=attempt + 1):
                with self.assertRaises(ControlledStagingTerminalCancellationError):
                    self._cancel()
                self.assertTrue(path.exists())
                self.assertEqual(path.read_bytes(), expected_bytes)

        decision = recover_controlled_staging_dispatching_run(
            minimum_slice=self.minimum_slice,
            provider=self.provider,
            endpoint=self.endpoint,
        )
        self.assertEqual(decision.disposition, "reconciliation_required")

    def test_concurrent_cancel_and_dispatch_have_exactly_one_revision_two_winner(self) -> None:
        def dispatch_attempt():
            try:
                result = self._dispatch()
                return ("dispatching", True, result.persistence_state)
            except ControlledStagingDispatchingTransitionError as exc:
                return ("dispatching", False, exc.category)

        def cancel_attempt():
            try:
                result = self._cancel()
                return ("cancelled", True, result.persistence_state)
            except ControlledStagingTerminalCancellationError as exc:
                return ("cancelled", False, exc.category)

        with ThreadPoolExecutor(max_workers=2) as pool:
            dispatch_future = pool.submit(dispatch_attempt)
            cancel_future = pool.submit(cancel_attempt)
            observed = (dispatch_future.result(), cancel_future.result())

        winners = tuple(item for item in observed if item[1])
        losers = tuple(item for item in observed if not item[1])
        self.assertEqual(len(winners), 1, observed)
        self.assertEqual(len(losers), 1, observed)
        self.assertEqual(winners[0][2], "written")

        path = self._rev2_path()
        self.assertTrue(path.exists())
        expected_bytes = path.read_bytes()

        if winners[0][0] == "dispatching":
            decision = recover_controlled_staging_dispatching_run(
                minimum_slice=self.minimum_slice,
                provider=self.provider,
                endpoint=self.endpoint,
            )
            self.assertEqual(decision.state, "dispatching")
            for _ in range(5):
                with self.assertRaises(ControlledStagingTerminalCancellationError):
                    self._cancel()
                self.assertEqual(path.read_bytes(), expected_bytes)
        else:
            decision = recover_controlled_staging_cancelled_run(
                minimum_slice=self.minimum_slice,
                provider=self.provider,
                engine=self.endpoint.name,
            )
            self.assertEqual(decision.state, "cancelled")
            for _ in range(5):
                with self.assertRaisesRegex(
                    ControlledStagingDispatchingTransitionError,
                    "staging_dispatching_revision_conflict",
                ):
                    self._dispatch()
                self.assertEqual(path.read_bytes(), expected_bytes)

    def test_tampered_dispatching_record_fails_closed_on_recovery(self) -> None:
        self._dispatch()
        path = self._rev2_path()
        payload = bytearray(path.read_bytes())
        payload[-2] ^= 1
        os.chmod(path, 0o600)
        path.write_bytes(bytes(payload))

        with self.assertRaises(ControlledStagingDispatchingTransitionError):
            recover_controlled_staging_dispatching_run(
                minimum_slice=self.minimum_slice,
                provider=self.provider,
                endpoint=self.endpoint,
            )

    def test_symlink_revision_two_record_fails_closed_without_following_target(self) -> None:
        self._dispatch()
        path = self._rev2_path()
        original = path.read_bytes()
        outside = self.root / "outside-revision-two.json"
        outside.write_bytes(original)
        os.chmod(path, 0o600)
        path.unlink()
        path.symlink_to(outside)

        with self.assertRaises(ControlledStagingDispatchingTransitionError):
            recover_controlled_staging_dispatching_run(
                minimum_slice=self.minimum_slice,
                provider=self.provider,
                endpoint=self.endpoint,
            )
        self.assertEqual(outside.read_bytes(), original)

    def test_source_substitution_fails_before_revision_two_publication(self) -> None:
        source_path = self.provider._source_path(self.minimum_slice.binding)
        source_path.chmod(0o600)
        source_path.write_bytes(b"tampered")

        with self.assertRaisesRegex(
            ControlledStagingDispatchingTransitionError,
            "staging_dispatching_source_invalid",
        ):
            self._dispatch()
        self.assertFalse(self._rev2_path().exists())

    def test_wrong_engine_endpoint_cannot_claim_an_unqueued_run(self) -> None:
        clarity = EngineEndpoint(
            "clarity",
            APPROVED_ENGINE_ORIGINS["staging"]["clarity"],
        )
        with self.assertRaises(ControlledStagingDispatchingTransitionError):
            self._dispatch(endpoint=clarity)
        self.assertFalse(
            transition_record_path(
                self.provider,
                job_id=self.queued.job_id,
                run_id=self.queued.run_id,
                revision=2,
            ).exists()
        )


if __name__ == "__main__":
    unittest.main()
