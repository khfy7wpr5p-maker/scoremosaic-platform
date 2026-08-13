from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

import test_safe_upload_finalization as helpers
from scoremosaic_gateway.minimum_staging_vertical_slice import (
    MinimumStagingVerticalSliceError,
    StagingUploadProvider,
    run_minimum_staging_vertical_slice,
)


class MinimumStagingVerticalSliceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = helpers.SafeUploadFinalizationContractTests(methodName="runTest")
        self.fixture.setUp()
        self.admission = self.fixture._admission()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.state_integrity_key = b"S" * 32
        self.provider = StagingUploadProvider(
            Path(self.temp_dir.name),
            state_integrity_key=self.state_integrity_key,
        )

    def run_slice(self, *, payload=helpers.PNG_1X1, filename="scan.png", media_type="image/png"):
        return run_minimum_staging_vertical_slice(
            admission=self.admission,
            session_policy=self.fixture.session_policy,
            payload=payload,
            original_filename=filename,
            declared_media_type=media_type,
            observed_at_epoch_s=self.admission.evaluated_at_epoch_s,
            provider=self.provider,
        )

    def test_exact_document_runs_e4a_e4b_e4c_and_writes_one_immutable_source(self) -> None:
        result = self.run_slice()

        self.assertFalse(result.session.replayed)
        self.assertFalse(result.finalization.replayed)
        self.assertEqual(result.source_write_state, "written")
        self.assertEqual(result.binding.document_sha256, result.finalization.document_sha256)
        self.assertEqual(result.binding.job_id, result.job_id)
        self.assertEqual(result.binding.source_artifact_id, result.source_artifact_id)
        self.assertEqual(
            self.provider.read_source(result.binding),
            helpers.PNG_1X1,
        )
        self.assertFalse(result.network_dispatch_allowed)
        self.assertFalse(result.orchestration_allowed)

    def test_exact_replay_reuses_session_finalization_job_and_source_without_overwrite(self) -> None:
        first = self.run_slice()
        replay = self.run_slice()

        self.assertTrue(replay.session.replayed)
        self.assertTrue(replay.finalization.replayed)
        self.assertEqual(replay.source_write_state, "replay")
        self.assertEqual(replay.job_id, first.job_id)
        self.assertEqual(replay.source_artifact_id, first.source_artifact_id)
        self.assertEqual(
            self.provider.read_source(replay.binding),
            helpers.PNG_1X1,
        )

    def test_provider_restart_with_same_integrity_key_preserves_exact_replay(self) -> None:
        first = self.run_slice()
        restarted_provider = StagingUploadProvider(
            Path(self.temp_dir.name),
            state_integrity_key=self.state_integrity_key,
        )
        replay = run_minimum_staging_vertical_slice(
            admission=self.admission,
            session_policy=self.fixture.session_policy,
            payload=helpers.PNG_1X1,
            original_filename="scan.png",
            declared_media_type="image/png",
            observed_at_epoch_s=self.admission.evaluated_at_epoch_s,
            provider=restarted_provider,
        )

        self.assertTrue(replay.session.replayed)
        self.assertTrue(replay.finalization.replayed)
        self.assertEqual(replay.source_write_state, "replay")
        self.assertEqual(replay.job_id, first.job_id)
        self.assertEqual(replay.source_artifact_id, first.source_artifact_id)

    def test_same_session_with_different_document_fails_closed_and_preserves_original(self) -> None:
        first = self.run_slice()

        with self.assertRaises(MinimumStagingVerticalSliceError) as raised:
            self.run_slice(
                payload=helpers.JPEG_1X1,
                filename="scan.jpg",
                media_type="image/jpeg",
            )
        self.assertEqual(raised.exception.category, "staging_upload_finalization_conflict")
        self.assertEqual(self.provider.read_source(first.binding), helpers.PNG_1X1)

    def test_provider_rejects_payload_that_does_not_match_verified_binding(self) -> None:
        result = self.run_slice()

        with self.assertRaises(MinimumStagingVerticalSliceError) as raised:
            self.provider.write_source(
                binding=result.binding,
                finalization=result.finalization,
                payload=helpers.JPEG_1X1,
            )
        self.assertEqual(raised.exception.category, "staging_source_payload_mismatch")
        self.assertEqual(self.provider.read_source(result.binding), helpers.PNG_1X1)

    def test_source_writer_rejects_nonstaging_evidence_before_binding_use(self) -> None:
        result = self.run_slice()
        object.__setattr__(result.binding, "environment", "production")
        object.__setattr__(result.finalization, "environment", "production")

        with self.assertRaises(MinimumStagingVerticalSliceError) as raised:
            self.provider.write_source(
                binding=result.binding,
                finalization=result.finalization,
                payload=helpers.PNG_1X1,
            )
        self.assertEqual(raised.exception.category, "staging_environment_required")

    def test_corrupt_persisted_session_fails_closed_without_touching_source(self) -> None:
        first = self.run_slice()
        session_path = (
            Path(self.temp_dir.name)
            / "state"
            / "sessions"
            / f"{first.session.session_id}.json"
        )
        session_path.write_text("{}", encoding="utf-8")

        with self.assertRaises(MinimumStagingVerticalSliceError) as raised:
            self.run_slice()
        self.assertEqual(raised.exception.category, "staging_upload_session_failed")
        self.assertEqual(self.provider.read_source(first.binding), helpers.PNG_1X1)

    def test_persisted_session_version_mismatch_fails_closed(self) -> None:
        first = self.run_slice()
        session_path = (
            Path(self.temp_dir.name)
            / "state"
            / "sessions"
            / f"{first.session.session_id}.json"
        )
        record = json.loads(session_path.read_text(encoding="utf-8"))
        record["version"] = "0.0"
        session_path.write_text(
            json.dumps(record, separators=(",", ":"), sort_keys=True),
            encoding="utf-8",
        )

        with self.assertRaises(MinimumStagingVerticalSliceError) as raised:
            self.run_slice()
        self.assertEqual(raised.exception.category, "staging_upload_session_failed")
        self.assertEqual(self.provider.read_source(first.binding), helpers.PNG_1X1)

    def test_coherently_shifted_session_timestamps_fail_closed(self) -> None:
        first = self.run_slice()
        session_path = (
            Path(self.temp_dir.name)
            / "state"
            / "sessions"
            / f"{first.session.session_id}.json"
        )
        record = json.loads(session_path.read_text(encoding="utf-8"))
        record["created_at_epoch_s"] -= 1
        record["expires_at_epoch_s"] -= 1
        session_path.write_text(
            json.dumps(record, separators=(",", ":"), sort_keys=True),
            encoding="utf-8",
        )

        with self.assertRaises(MinimumStagingVerticalSliceError) as raised:
            self.run_slice()
        self.assertEqual(raised.exception.category, "staging_upload_session_failed")
        self.assertEqual(self.provider.read_source(first.binding), helpers.PNG_1X1)

    def test_oversized_persisted_session_record_fails_closed(self) -> None:
        first = self.run_slice()
        session_path = (
            Path(self.temp_dir.name)
            / "state"
            / "sessions"
            / f"{first.session.session_id}.json"
        )
        session_path.write_bytes(session_path.read_bytes() + (b" " * 70_000))

        with self.assertRaises(MinimumStagingVerticalSliceError) as raised:
            self.run_slice()
        self.assertEqual(raised.exception.category, "staging_upload_session_failed")
        self.assertEqual(self.provider.read_source(first.binding), helpers.PNG_1X1)

    def test_preexisting_symlink_state_directory_cannot_escape_staging_root(self) -> None:
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        root = Path(self.temp_dir.name)
        (root / "state").symlink_to(Path(outside.name), target_is_directory=True)

        with self.assertRaises(MinimumStagingVerticalSliceError) as raised:
            self.run_slice()
        self.assertEqual(raised.exception.category, "staging_upload_session_failed")
        self.assertEqual(list(Path(outside.name).rglob("*")), [])

    def test_read_source_rejects_intermediate_symlink_escape(self) -> None:
        first = self.run_slice()
        root = Path(self.temp_dir.name)
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        outside_root = Path(outside.name)
        external_source = outside_root / Path(first.binding.source_storage_key)
        external_source.parent.mkdir(parents=True)
        external_source.write_bytes(helpers.PNG_1X1)

        shutil.rmtree(root / "objects")
        (root / "objects").symlink_to(outside_root, target_is_directory=True)

        with self.assertRaises(MinimumStagingVerticalSliceError) as raised:
            self.provider.read_source(first.binding)
        self.assertEqual(raised.exception.category, "staging_path_invalid")
        self.assertEqual(external_source.read_bytes(), helpers.PNG_1X1)

    def test_read_source_parent_swap_cannot_redirect_open_outside_root(self) -> None:
        first = self.run_slice()
        root = Path(self.temp_dir.name)
        objects = root / "objects"
        original_objects = root / "objects-original"
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        outside_root = Path(outside.name)
        external_source = outside_root / Path(first.binding.source_storage_key)
        external_source.parent.mkdir(parents=True)
        external_source.write_bytes(b"X" * len(helpers.PNG_1X1))
        real_open = os.open
        swapped = False
        source_path = objects / Path(first.binding.source_storage_key)

        def racing_open(path, flags, *args, **kwargs):
            nonlocal swapped
            candidate = Path(path) if isinstance(path, (str, os.PathLike)) else None
            is_final_source_open = (
                candidate == source_path
                or (
                    candidate is not None
                    and candidate.name == source_path.name
                    and kwargs.get("dir_fd") is not None
                )
            )
            if is_final_source_open and not swapped:
                objects.rename(original_objects)
                objects.symlink_to(outside_root, target_is_directory=True)
                swapped = True
            return real_open(path, flags, *args, **kwargs)

        with patch(
            "scoremosaic_gateway.minimum_staging_vertical_slice.os.open",
            side_effect=racing_open,
        ):
            self.assertEqual(self.provider.read_source(first.binding), helpers.PNG_1X1)
        self.assertTrue(swapped)
        self.assertEqual(external_source.read_bytes(), b"X" * len(helpers.PNG_1X1))

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires FIFO support")
    def test_special_source_is_opened_nonblocking_and_rejected_as_nonregular(self) -> None:
        first = self.run_slice()
        source_path = (
            Path(self.temp_dir.name)
            / "objects"
            / Path(first.binding.source_storage_key)
        )
        source_path.unlink()
        os.mkfifo(source_path, 0o600)
        real_open = os.open

        def guarded_open(path, flags, *args, **kwargs):
            candidate = Path(path) if isinstance(path, (str, os.PathLike)) else None
            if candidate is not None and (
                candidate == source_path or candidate.name == source_path.name
            ):
                if hasattr(os, "O_NONBLOCK") and not flags & os.O_NONBLOCK:
                    raise AssertionError("source open must be nonblocking")
            return real_open(path, flags, *args, **kwargs)

        with patch(
            "scoremosaic_gateway.minimum_staging_vertical_slice.os.open",
            side_effect=guarded_open,
        ):
            with self.assertRaises(MinimumStagingVerticalSliceError) as raised:
                self.provider.read_source(first.binding)
        self.assertEqual(raised.exception.category, "staging_path_invalid")

    def test_existing_tampered_source_is_never_overwritten_on_replay(self) -> None:
        first = self.run_slice()
        source_path = (
            Path(self.temp_dir.name)
            / "objects"
            / Path(first.binding.source_storage_key)
        )
        tampered = b"X" * len(helpers.PNG_1X1)
        source_path.write_bytes(tampered)

        with self.assertRaises(MinimumStagingVerticalSliceError) as raised:
            self.run_slice()
        self.assertEqual(raised.exception.category, "staging_source_collision")
        self.assertEqual(source_path.read_bytes(), tampered)

    def test_existing_source_read_stops_at_expected_size_plus_one(self) -> None:
        first = self.run_slice()
        source_path = (
            Path(self.temp_dir.name)
            / "objects"
            / Path(first.binding.source_storage_key)
        )
        source_path.write_bytes(b"X" * (1024 * 1024))
        real_read = os.read
        observed_bytes = 0

        def tracking_read(fd, size):
            nonlocal observed_bytes
            chunk = real_read(fd, size)
            observed_bytes += len(chunk)
            return chunk

        with patch(
            "scoremosaic_gateway.minimum_staging_vertical_slice.os.read",
            side_effect=tracking_read,
        ):
            with self.assertRaises(MinimumStagingVerticalSliceError) as raised:
                self.provider.write_source(
                    binding=first.binding,
                    finalization=first.finalization,
                    payload=helpers.PNG_1X1,
                )
        self.assertEqual(raised.exception.category, "staging_source_collision")
        self.assertLessEqual(observed_bytes, len(helpers.PNG_1X1) + 1)

    def test_source_write_oserror_maps_to_stable_slice_error(self) -> None:
        first = self.run_slice()
        source_path = (
            Path(self.temp_dir.name)
            / "objects"
            / Path(first.binding.source_storage_key)
        )
        source_path.unlink()

        with patch.object(
            self.provider,
            "_create_temp_file",
            side_effect=OSError("sensitive filesystem detail"),
        ):
            with self.assertRaises(MinimumStagingVerticalSliceError) as raised:
                self.provider.write_source(
                    binding=first.binding,
                    finalization=first.finalization,
                    payload=helpers.PNG_1X1,
                )
        self.assertEqual(raised.exception.category, "staging_state_unavailable")
        self.assertEqual(str(raised.exception), "staging_state_unavailable")

    def test_atomic_create_closes_descriptor_when_fchmod_fails(self) -> None:
        first = self.run_slice()
        source_path = (
            Path(self.temp_dir.name)
            / "objects"
            / Path(first.binding.source_storage_key)
        )
        source_path.unlink()
        real_create = self.provider._create_temp_file
        captured_fds: list[int] = []

        def tracking_create(parent_fd):
            fd, leaf = real_create(parent_fd)
            captured_fds.append(fd)
            return fd, leaf

        with patch.object(
            self.provider,
            "_create_temp_file",
            side_effect=tracking_create,
        ), patch(
            "scoremosaic_gateway.minimum_staging_vertical_slice.os.fchmod",
            side_effect=OSError("sensitive filesystem detail"),
        ):
            with self.assertRaises(MinimumStagingVerticalSliceError) as raised:
                self.provider.write_source(
                    binding=first.binding,
                    finalization=first.finalization,
                    payload=helpers.PNG_1X1,
                )
        self.assertEqual(raised.exception.category, "staging_state_unavailable")
        self.assertEqual(len(captured_fds), 1)
        fd = captured_fds[0]
        try:
            with self.assertRaises(OSError):
                os.fstat(fd)
        finally:
            try:
                os.close(fd)
            except OSError:
                pass

    def test_slice_is_staging_only_and_does_not_activate_http_or_dispatch_authority(self) -> None:
        object.__setattr__(self.admission, "environment", "production")

        with self.assertRaises(MinimumStagingVerticalSliceError) as raised:
            self.run_slice()
        self.assertEqual(raised.exception.category, "staging_environment_required")
        self.assertEqual(list(Path(self.temp_dir.name).rglob("*")), [])


if __name__ == "__main__":
    unittest.main()
