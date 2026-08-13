from __future__ import annotations

from pathlib import Path
import sys
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

import test_safe_upload_finalization as helpers
from scoremosaic_gateway.safe_source_job_binding import (
    SafeSourceJobBindingError,
    bind_finalized_source_to_job,
)
from scoremosaic_gateway.safe_source_job_binding_verification import (
    verify_safe_source_job_binding_decision,
)
from scoremosaic_gateway.safe_upload_finalization import finalize_safe_upload_session


class EqualitySpoofingStr(str):
    def __eq__(self, other: object) -> bool:
        return True

    def __ne__(self, other: object) -> bool:
        return False


class GateE4ClosureConvergenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = helpers.SafeUploadFinalizationContractTests(methodName="runTest")
        self.fixture.setUp()
        self.finalization = finalize_safe_upload_session(
            session=self.fixture.session,
            payload=helpers.PNG_1X1,
            original_filename="score.png",
            declared_media_type="image/png",
            observed_at_epoch_s=self.fixture.now + 4,
            finalizer=self.fixture._receipt_for,
        )
        self.binding = bind_finalized_source_to_job(self.finalization)

    def test_exact_e4a_e4b_e4c_replay_converges_to_same_source_job_identity(self) -> None:
        replay = finalize_safe_upload_session(
            session=self.fixture.session,
            payload=helpers.PNG_1X1,
            original_filename="score.png",
            declared_media_type="image/png",
            observed_at_epoch_s=self.fixture.now + 4,
            finalizer=lambda request: self.fixture._receipt_for(
                request,
                outcome="replay",
                finalized_at_epoch_s=self.finalization.finalized_at_epoch_s,
            ),
        )
        replay_binding = bind_finalized_source_to_job(replay)

        self.assertEqual(replay.finalization_id, self.finalization.finalization_id)
        self.assertEqual(replay_binding.job_id, self.binding.job_id)
        self.assertEqual(replay_binding.source_artifact_id, self.binding.source_artifact_id)
        self.assertEqual(replay_binding.source_storage_key, self.binding.source_storage_key)
        self.assertEqual(replay_binding.storage_manifest_sha256, self.binding.storage_manifest_sha256)
        verify_safe_source_job_binding_decision(self.binding, finalization=self.finalization)
        verify_safe_source_job_binding_decision(replay_binding, finalization=replay)

    def test_valid_shape_post_creation_source_substitution_fails_closed(self) -> None:
        forged_artifact_id = "artifact_" + "f" * 24
        object.__setattr__(self.binding, "source_artifact_id", forged_artifact_id)
        object.__setattr__(
            self.binding,
            "source_storage_key",
            f"immutable/jobs/{self.binding.job_id}/source/{forged_artifact_id}",
        )

        with self.assertRaises(SafeSourceJobBindingError) as raised:
            verify_safe_source_job_binding_decision(
                self.binding,
                finalization=self.finalization,
            )
        self.assertEqual(raised.exception.category, "source_binding_invalid")

    def test_equality_spoofing_string_substitutions_fail_closed(self) -> None:
        for field_name, forged_value in (
            ("source_artifact_ref", EqualitySpoofingStr("../../attacker-controlled")),
            ("source_storage_key", EqualitySpoofingStr("attacker-controlled")),
        ):
            with self.subTest(field_name=field_name):
                binding = bind_finalized_source_to_job(self.finalization)
                object.__setattr__(binding, field_name, forged_value)
                with self.assertRaises(SafeSourceJobBindingError) as raised:
                    verify_safe_source_job_binding_decision(
                        binding,
                        finalization=self.finalization,
                    )
                self.assertEqual(raised.exception.category, "source_binding_invalid")

    def test_binding_from_one_finalization_cannot_verify_against_another(self) -> None:
        other = finalize_safe_upload_session(
            session=self.fixture.session,
            payload=helpers.JPEG_1X1,
            original_filename="score.jpg",
            declared_media_type="image/jpeg",
            observed_at_epoch_s=self.fixture.now + 5,
            finalizer=self.fixture._receipt_for,
        )

        with self.assertRaises(SafeSourceJobBindingError) as raised:
            verify_safe_source_job_binding_decision(self.binding, finalization=other)
        self.assertEqual(raised.exception.category, "source_binding_invalid")

    def test_closure_evidence_still_grants_no_runtime_authority(self) -> None:
        verify_safe_source_job_binding_decision(
            self.binding,
            finalization=self.finalization,
        )
        safe = self.binding.as_safe_dict()
        for key in (
            "uploadAllowed",
            "storageWriteAllowed",
            "persistenceEnabled",
            "jobExecutionAllowed",
            "networkDispatchAllowed",
            "orchestrationAllowed",
        ):
            self.assertIs(safe[key], False)


if __name__ == "__main__":
    unittest.main()
