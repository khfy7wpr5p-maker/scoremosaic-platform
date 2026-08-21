from __future__ import annotations
import os
from pathlib import Path
import sys
import tempfile
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

if SERVICE_ROOT.name == "audiveris-service":
    from scoremosaic_audiveris.dispatch_acceptance import (
        DispatchAcceptanceStoreError,
        EngineDispatchAcceptanceStore,
    )
elif SERVICE_ROOT.name == "homr-service":
    from scoremosaic_homr.dispatch_acceptance import (
        DispatchAcceptanceStoreError,
        EngineDispatchAcceptanceStore,
    )
elif SERVICE_ROOT.name == "clarity-service":
    from scoremosaic_clarity.dispatch_acceptance import (
        DispatchAcceptanceStoreError,
        EngineDispatchAcceptanceStore,
    )
else:
    raise RuntimeError("unexpected engine service root")


class Stage5DispatchAcceptanceHardeningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "acceptance"
        self.store = EngineDispatchAcceptanceStore(
            root=self.root,
            integrity_key=b"i" * 32,
        )
        self.job_id = "job_stage5a2hardening01"
        self.run_id = "run_" + "a" * 24
        self.dispatch_sha = "b" * 64

    def _record_path(self) -> Path:
        return (
            self.root
            / "accepted-dispatches"
            / f"{self.job_id}.{self.run_id}.json"
        )

    def test_symlink_record_is_never_followed_or_overwritten(self) -> None:
        outside = Path(self.temp.name) / "outside.json"
        outside.write_text("outside-must-remain-unchanged", encoding="utf-8")
        os.symlink(outside, self._record_path())

        with self.assertRaises(DispatchAcceptanceStoreError) as context:
            self.store.publish(
                job_id=self.job_id,
                run_id=self.run_id,
                dispatch_identity_sha256=self.dispatch_sha,
            )
        self.assertEqual(context.exception.category, "dispatch_acceptance_state_invalid")
        self.assertEqual(
            outside.read_text(encoding="utf-8"),
            "outside-must-remain-unchanged",
        )

    def test_root_symlink_is_rejected_fail_closed(self) -> None:
        real_root = Path(self.temp.name) / "real-root"
        real_root.mkdir()
        symlink_root = Path(self.temp.name) / "symlink-root"
        os.symlink(real_root, symlink_root)
        with self.assertRaises(DispatchAcceptanceStoreError) as context:
            EngineDispatchAcceptanceStore(
                root=symlink_root,
                integrity_key=b"k" * 32,
            )
        self.assertEqual(context.exception.category, "dispatch_acceptance_state_invalid")

    def test_safe_receipt_contains_no_integrity_key_or_retry_execution_authority(self) -> None:
        receipt = self.store.publish(
            job_id=self.job_id,
            run_id=self.run_id,
            dispatch_identity_sha256=self.dispatch_sha,
        )
        rendered = repr(receipt.as_safe_dict())
        self.assertNotIn((b"i" * 32).hex(), rendered)
        self.assertTrue(receipt.source_delivery_authorized)
        self.assertFalse(receipt.engine_execution_allowed)
        self.assertFalse(receipt.retry_allowed)


if __name__ == "__main__":
    unittest.main()
