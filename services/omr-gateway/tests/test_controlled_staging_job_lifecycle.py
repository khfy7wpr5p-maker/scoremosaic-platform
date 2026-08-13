from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

import test_safe_upload_finalization as helpers
from scoremosaic_gateway.controlled_staging_job_lifecycle import (
    ControlledStagingJobLifecycleError,
    recover_controlled_staging_job_lifecycle,
    run_controlled_staging_job_lifecycle,
)
from scoremosaic_gateway.minimum_staging_vertical_slice import (
    StagingUploadProvider,
    run_minimum_staging_vertical_slice,
)
from scoremosaic_gateway.orchestration import ENGINE_NAMES


class ControlledStagingJobLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = helpers.SafeUploadFinalizationContractTests(methodName="runTest")
        self.fixture.setUp()
        self.admission = self.fixture._admission()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.integrity_key = b"S" * 32
        self.provider = StagingUploadProvider(
            Path(self.temp_dir.name),
            state_integrity_key=self.integrity_key,
        )
        self.minimum_slice = run_minimum_staging_vertical_slice(
            admission=self.admission,
            session_policy=self.fixture.session_policy,
            payload=helpers.PNG_1X1,
            original_filename="scan.png",
            declared_media_type="image/png",
            observed_at_epoch_s=self.admission.evaluated_at_epoch_s,
            provider=self.provider,
        )

    def run_lifecycle(self, *, provider=None, minimum_slice=None):
        return run_controlled_staging_job_lifecycle(
            minimum_slice=self.minimum_slice if minimum_slice is None else minimum_slice,
            provider=self.provider if provider is None else provider,
        )

    def test_persists_initial_gate_d_state_ledger_and_provenance_only(self) -> None:
        result = self.run_lifecycle()

        self.assertEqual(result.persistence_state, "written")
        self.assertEqual(result.job_id, self.minimum_slice.job_id)
        self.assertEqual(tuple(run.engine for run in result.runs), ENGINE_NAMES)
        self.assertTrue(all(run.state == "planned" for run in result.runs))
        self.assertTrue(all(run.revision == 0 for run in result.runs))
        self.assertTrue(all(run.idempotency_record_count == 0 for run in result.runs))
        self.assertTrue(all(run.provenance_record_count == 1 for run in result.runs))
        self.assertFalse(result.queue_allowed)
        self.assertFalse(result.worker_allowed)
        self.assertFalse(result.network_dispatch_allowed)
        self.assertFalse(result.orchestration_allowed)
        self.assertFalse(result.engine_execution_allowed)

        stored = json.loads(
            (
                Path(self.temp_dir.name)
                / "state"
                / "jobs"
                / f"{result.job_id}.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(stored["job_id"], result.job_id)
        self.assertEqual(
            tuple(run["engine"] for run in stored["runs"]),
            ENGINE_NAMES,
        )
        self.assertTrue(
            all(
                run["job_state"]["state"] == "planned"
                and run["job_state"]["revision"] == 0
                and run["idempotency"]["recordCount"] == 0
                and len(run["provenance"]["records"]) == 1
                for run in stored["runs"]
            )
        )
        self.assertEqual(set(stored["boundaries"].values()), {False})
        self.assertNotIn("source_bytes", stored)

    def test_exact_replay_and_provider_restart_reuse_one_record(self) -> None:
        first = self.run_lifecycle()
        replay = self.run_lifecycle()
        restarted = StagingUploadProvider(
            Path(self.temp_dir.name),
            state_integrity_key=self.integrity_key,
        )
        after_restart = self.run_lifecycle(provider=restarted)

        self.assertEqual(first.persistence_state, "written")
        self.assertEqual(replay.persistence_state, "replay")
        self.assertEqual(after_restart.persistence_state, "replay")
        self.assertEqual(replay.runs, first.runs)
        self.assertEqual(after_restart.runs, first.runs)

    def test_provider_restart_restores_read_only_gate_d5_decisions(self) -> None:
        created = self.run_lifecycle()
        job_path = (
            Path(self.temp_dir.name)
            / "state"
            / "jobs"
            / f"{created.job_id}.json"
        )
        source_path = (
            Path(self.temp_dir.name)
            / "objects"
            / self.minimum_slice.binding.source_storage_key
        )
        original_job_bytes = job_path.read_bytes()
        original_source_bytes = source_path.read_bytes()
        restarted = StagingUploadProvider(
            Path(self.temp_dir.name),
            state_integrity_key=self.integrity_key,
        )

        recovered = recover_controlled_staging_job_lifecycle(
            minimum_slice=self.minimum_slice,
            provider=restarted,
        )
        replayed = recover_controlled_staging_job_lifecycle(
            minimum_slice=self.minimum_slice,
            provider=restarted,
        )

        self.assertEqual(recovered, replayed)
        self.assertEqual(recovered.job_id, created.job_id)
        self.assertEqual(tuple(run.engine for run in recovered.runs), ENGINE_NAMES)
        self.assertTrue(all(run.state == "planned" for run in recovered.runs))
        self.assertTrue(all(run.revision == 0 for run in recovered.runs))
        self.assertTrue(
            all(
                run.disposition == "pre_dispatch_candidate"
                for run in recovered.runs
            )
        )
        self.assertTrue(all(not run.terminal for run in recovered.runs))
        self.assertTrue(
            all(not run.reconciliation_required for run in recovered.runs)
        )
        self.assertFalse(recovered.automatic_execution_allowed)
        self.assertFalse(recovered.retry_allowed)
        self.assertFalse(recovered.state_mutation_allowed)
        self.assertFalse(recovered.queue_allowed)
        self.assertFalse(recovered.worker_allowed)
        self.assertFalse(recovered.network_dispatch_allowed)
        self.assertFalse(recovered.orchestration_allowed)
        self.assertFalse(recovered.engine_execution_allowed)
        self.assertEqual(job_path.read_bytes(), original_job_bytes)
        self.assertEqual(source_path.read_bytes(), original_source_bytes)

    def test_recovery_requires_existing_authenticated_exact_job_record(self) -> None:
        missing_path = (
            Path(self.temp_dir.name)
            / "state"
            / "jobs"
            / f"{self.minimum_slice.job_id}.json"
        )

        with self.assertRaises(ControlledStagingJobLifecycleError) as raised:
            recover_controlled_staging_job_lifecycle(
                minimum_slice=self.minimum_slice,
                provider=self.provider,
            )

        self.assertEqual(
            raised.exception.category,
            "staging_job_lifecycle_state_invalid",
        )
        self.assertFalse(missing_path.exists())

    def test_recovery_rejects_valid_but_different_authenticated_record(self) -> None:
        created = self.run_lifecycle()
        path = (
            Path(self.temp_dir.name)
            / "state"
            / "jobs"
            / f"{created.job_id}.json"
        )
        stored = json.loads(path.read_text(encoding="utf-8"))
        stored["boundaries"]["networkDispatchAllowed"] = True
        stored.pop("state_integrity_mac")
        resealed = self.provider._seal_state_record(
            kind="job_lifecycle",
            record=stored,
        )
        path.chmod(0o600)
        path.write_text(
            json.dumps(resealed, separators=(",", ":"), sort_keys=True),
            encoding="utf-8",
        )

        with self.assertRaises(ControlledStagingJobLifecycleError) as raised:
            recover_controlled_staging_job_lifecycle(
                minimum_slice=self.minimum_slice,
                provider=self.provider,
            )

        self.assertEqual(
            raised.exception.category,
            "staging_job_lifecycle_state_invalid",
        )

    def test_recovery_rejects_wrong_key_or_modified_source(self) -> None:
        self.run_lifecycle()
        wrong_key_provider = StagingUploadProvider(
            Path(self.temp_dir.name),
            state_integrity_key=b"W" * 32,
        )

        with self.assertRaises(ControlledStagingJobLifecycleError) as wrong_key:
            recover_controlled_staging_job_lifecycle(
                minimum_slice=self.minimum_slice,
                provider=wrong_key_provider,
            )
        self.assertEqual(
            wrong_key.exception.category,
            "staging_job_lifecycle_state_invalid",
        )

        source_path = (
            Path(self.temp_dir.name)
            / "objects"
            / self.minimum_slice.binding.source_storage_key
        )
        source_path.chmod(0o600)
        source_path.write_bytes(
            b"X" * self.minimum_slice.binding.source_size_bytes
        )
        with self.assertRaises(ControlledStagingJobLifecycleError) as modified:
            recover_controlled_staging_job_lifecycle(
                minimum_slice=self.minimum_slice,
                provider=self.provider,
            )
        self.assertEqual(
            modified.exception.category,
            "staging_job_lifecycle_state_invalid",
        )

    def test_tampered_job_lifecycle_record_fails_closed(self) -> None:
        self.run_lifecycle()
        path = (
            Path(self.temp_dir.name)
            / "state"
            / "jobs"
            / f"{self.minimum_slice.job_id}.json"
        )
        stored = json.loads(path.read_text(encoding="utf-8"))
        stored["job_id"] = "job_" + "0" * 32
        path.chmod(0o600)
        path.write_text(json.dumps(stored), encoding="utf-8")

        with self.assertRaises(ControlledStagingJobLifecycleError) as raised:
            self.run_lifecycle()

        self.assertEqual(raised.exception.category, "staging_job_lifecycle_state_invalid")

    def test_job_state_symlink_cannot_escape_staging_root(self) -> None:
        outside = Path(self.temp_dir.name) / "outside"
        outside.mkdir()
        state = Path(self.temp_dir.name) / "state"
        state.mkdir(exist_ok=True)
        os.symlink(outside, state / "jobs")

        with self.assertRaises(ControlledStagingJobLifecycleError) as raised:
            self.run_lifecycle()

        self.assertEqual(raised.exception.category, "staging_job_lifecycle_state_invalid")
        self.assertEqual(list(outside.iterdir()), [])

    def test_restart_with_wrong_integrity_key_fails_closed(self) -> None:
        self.run_lifecycle()
        wrong_key_provider = StagingUploadProvider(
            Path(self.temp_dir.name),
            state_integrity_key=b"W" * 32,
        )

        with self.assertRaises(ControlledStagingJobLifecycleError) as raised:
            self.run_lifecycle(provider=wrong_key_provider)

        self.assertEqual(raised.exception.category, "staging_job_lifecycle_state_invalid")

    def test_missing_or_modified_immutable_source_fails_before_job_persistence(self) -> None:
        source_path = (
            Path(self.temp_dir.name)
            / "objects"
            / self.minimum_slice.binding.source_storage_key
        )
        source_path.unlink()

        with self.assertRaises(ControlledStagingJobLifecycleError) as raised:
            self.run_lifecycle()

        self.assertEqual(raised.exception.category, "staging_job_source_invalid")
        self.assertFalse(
            (
                Path(self.temp_dir.name)
                / "state"
                / "jobs"
                / f"{self.minimum_slice.job_id}.json"
            ).exists()
        )

    def test_source_replacement_after_initial_verification_cannot_publish_job(self) -> None:
        source_path = (
            Path(self.temp_dir.name)
            / "objects"
            / self.minimum_slice.binding.source_storage_key
        )
        job_path = (
            Path(self.temp_dir.name)
            / "state"
            / "jobs"
            / f"{self.minimum_slice.job_id}.json"
        )
        real_read_source = self.provider.read_source

        def replace_after_read(binding):
            payload = real_read_source(binding)
            source_path.chmod(0o600)
            source_path.write_bytes(b"X" * len(payload))
            return payload

        with patch.object(
            self.provider,
            "read_source",
            side_effect=replace_after_read,
        ):
            with self.assertRaises(ControlledStagingJobLifecycleError) as raised:
                self.run_lifecycle()

        self.assertEqual(raised.exception.category, "staging_job_lifecycle_state_invalid")
        self.assertFalse(job_path.exists())

    def test_source_replacement_during_record_build_fails_before_link(self) -> None:
        source_path = (
            Path(self.temp_dir.name)
            / "objects"
            / self.minimum_slice.binding.source_storage_key
        )
        job_path = (
            Path(self.temp_dir.name)
            / "state"
            / "jobs"
            / f"{self.minimum_slice.job_id}.json"
        )
        real_write_all = self.provider._write_all

        def replace_while_building_record(fd, payload):
            real_write_all(fd, payload)
            if b'"job_id"' in payload:
                source_path.chmod(0o600)
                source_path.write_bytes(b"X" * self.minimum_slice.binding.source_size_bytes)

        with patch.object(
            self.provider,
            "_write_all",
            side_effect=replace_while_building_record,
        ):
            with self.assertRaises(ControlledStagingJobLifecycleError) as raised:
                self.run_lifecycle()

        self.assertEqual(raised.exception.category, "staging_job_lifecycle_state_invalid")
        self.assertFalse(job_path.exists())

    def test_source_replacement_between_final_check_and_link_rolls_back_job(self) -> None:
        source_path = (
            Path(self.temp_dir.name)
            / "objects"
            / self.minimum_slice.binding.source_storage_key
        )
        job_path = (
            Path(self.temp_dir.name)
            / "state"
            / "jobs"
            / f"{self.minimum_slice.job_id}.json"
        )
        real_link = self.provider._link_unnamed_file

        def replace_immediately_before_link(temp_fd, parent_fd, final_leaf):
            if final_leaf.endswith(".json"):
                source_path.chmod(0o600)
                source_path.write_bytes(
                    b"X" * self.minimum_slice.binding.source_size_bytes
                )
            real_link(temp_fd, parent_fd, final_leaf)

        with patch.object(
            self.provider,
            "_link_unnamed_file",
            side_effect=replace_immediately_before_link,
        ):
            with self.assertRaises(ControlledStagingJobLifecycleError) as raised:
                self.run_lifecycle()

        self.assertEqual(raised.exception.category, "staging_job_lifecycle_state_invalid")
        self.assertFalse(job_path.exists())

    def test_wrong_input_types_fail_before_provider_use(self) -> None:
        with self.assertRaises(ControlledStagingJobLifecycleError) as raised:
            run_controlled_staging_job_lifecycle(
                minimum_slice=object(),
                provider=self.provider,
            )

        self.assertEqual(raised.exception.category, "staging_job_lifecycle_input_invalid")


if __name__ == "__main__":
    unittest.main()
