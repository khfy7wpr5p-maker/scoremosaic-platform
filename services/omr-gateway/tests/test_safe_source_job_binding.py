from __future__ import annotations

from hashlib import sha256
import inspect
from pathlib import Path
import re
import sys
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

import test_safe_upload_finalization as helpers
from scoremosaic_gateway.safe_upload_finalization import finalize_safe_upload_session
from scoremosaic_gateway.safe_source_job_binding import (
    SAFE_SOURCE_JOB_BINDING_CONTRACT_VERSION,
    SafeSourceJobBindingError,
    bind_finalized_source_to_job,
)


_JOB_ID_RE = re.compile(r"job_[0-9a-f]{32}\Z")
_ARTIFACT_ID_RE = re.compile(r"artifact_[0-9a-f]{24}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")


class SafeSourceJobBindingContractTests(unittest.TestCase):
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

    def test_public_api_accepts_only_exact_e4b_finalization_authority(self) -> None:
        signature = inspect.signature(bind_finalized_source_to_job)
        self.assertEqual(tuple(signature.parameters), ("finalization",))

        with self.assertRaises(SafeSourceJobBindingError) as raised:
            bind_finalized_source_to_job(object())  # type: ignore[arg-type]
        self.assertEqual(raised.exception.category, "source_finalization_invalid")

    def test_valid_finalization_derives_server_owned_job_and_gate_d_source_binding(self) -> None:
        decision = bind_finalized_source_to_job(self.finalization)

        self.assertEqual(decision.version, SAFE_SOURCE_JOB_BINDING_CONTRACT_VERSION)
        self.assertEqual(decision.environment, self.finalization.environment)
        self.assertEqual(decision.principal_id, self.finalization.principal_id)
        self.assertEqual(decision.operation_id, self.finalization.operation_id)
        self.assertEqual(decision.session_id, self.finalization.session_id)
        self.assertEqual(decision.finalization_id, self.finalization.finalization_id)
        self.assertEqual(decision.document_sha256, sha256(helpers.PNG_1X1).hexdigest())
        self.assertEqual(decision.source_size_bytes, len(helpers.PNG_1X1))
        self.assertEqual(decision.source_media_type, "image/png")
        self.assertIsNotNone(_JOB_ID_RE.fullmatch(decision.job_id))
        self.assertIsNotNone(_ARTIFACT_ID_RE.fullmatch(decision.source_artifact_id))
        self.assertEqual(decision.source_artifact_ref, f"sources/{decision.job_id}/original")
        self.assertEqual(
            decision.source_storage_key,
            f"immutable/jobs/{decision.job_id}/source/{decision.source_artifact_id}",
        )
        for value in (
            decision.source_binding_sha256,
            decision.orchestration_plan_sha256,
            decision.lifecycle_sha256,
            decision.storage_manifest_sha256,
        ):
            self.assertIsNotNone(_SHA256_RE.fullmatch(value))

        safe = decision.as_safe_dict()
        for key in (
            "uploadAllowed",
            "storageWriteAllowed",
            "persistenceEnabled",
            "jobExecutionAllowed",
            "networkDispatchAllowed",
            "orchestrationAllowed",
        ):
            self.assertIs(safe[key], False)
        self.assertFalse(hasattr(decision, "payload"))
        self.assertFalse(hasattr(decision, "original_filename"))

    def test_exact_replay_is_deterministic_and_does_not_create_second_job_identity(self) -> None:
        first = bind_finalized_source_to_job(self.finalization)
        second = bind_finalized_source_to_job(self.finalization)
        self.assertEqual(first, second)
        self.assertEqual(first.job_id, second.job_id)
        self.assertEqual(first.source_storage_key, second.source_storage_key)

    def test_distinct_finalized_source_identity_changes_job_identity(self) -> None:
        other = finalize_safe_upload_session(
            session=self.fixture.session,
            payload=helpers.JPEG_1X1,
            original_filename="score.jpg",
            declared_media_type="image/jpeg",
            observed_at_epoch_s=self.fixture.now + 5,
            finalizer=self.fixture._receipt_for,
        )
        self.assertNotEqual(
            bind_finalized_source_to_job(self.finalization).job_id,
            bind_finalized_source_to_job(other).job_id,
        )

    def test_pre_tampered_document_identity_fails_closed(self) -> None:
        object.__setattr__(self.finalization, "document_sha256", "f" * 64)
        with self.assertRaises(SafeSourceJobBindingError) as raised:
            bind_finalized_source_to_job(self.finalization)
        self.assertEqual(raised.exception.category, "source_finalization_invalid")

    def test_pre_tampered_safe_intake_evidence_fails_closed(self) -> None:
        object.__setattr__(self.finalization, "image_width", 2)
        object.__setattr__(self.finalization, "image_height", 2)
        object.__setattr__(self.finalization, "image_pixel_count", 4)
        with self.assertRaises(SafeSourceJobBindingError) as raised:
            bind_finalized_source_to_job(self.finalization)
        self.assertEqual(raised.exception.category, "source_finalization_invalid")

    def test_source_job_binding_cannot_be_forged_or_used_as_runtime_authority(self) -> None:
        decision = bind_finalized_source_to_job(self.finalization)
        safe = decision.as_safe_dict()
        self.assertNotIn("credential", repr(decision).lower())
        self.assertNotIn("subject", repr(decision).lower())
        self.assertNotIn("payload", repr(decision).lower())
        self.assertEqual(safe["documentSha256"], self.finalization.document_sha256)
        self.assertEqual(safe["safeIntakePolicyVersion"], self.finalization.intake_policy_version)


if __name__ == "__main__":
    unittest.main()
