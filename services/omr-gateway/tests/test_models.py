from __future__ import annotations

import sys
from pathlib import Path
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_gateway.models import ModelError, build_job_record


class JobRecordTests(unittest.TestCase):
    def test_three_engine_runs_are_independent(self) -> None:
        record = build_job_record("job_abcdefgh1234")

        self.assertEqual(record.status, "queued")
        self.assertEqual(
            record.requested_engines,
            ("audiveris", "homr", "clarity"),
        )
        self.assertEqual(len({run.run_id for run in record.engine_runs}), 3)
        self.assertEqual(
            {run.candidate_key for run in record.engine_runs},
            {
                "candidates/job_abcdefgh1234/audiveris",
                "candidates/job_abcdefgh1234/homr",
                "candidates/job_abcdefgh1234/clarity",
            },
        )

    def test_subset_preserves_requested_order(self) -> None:
        record = build_job_record(
            "job_abcdefgh1234",
            ("homr", "audiveris"),
        )
        self.assertEqual(record.requested_engines, ("homr", "audiveris"))
        self.assertEqual(
            [run.engine for run in record.engine_runs],
            ["homr", "audiveris"],
        )

    def test_duplicate_engine_is_rejected(self) -> None:
        with self.assertRaisesRegex(ModelError, "must be unique"):
            build_job_record(
                "job_abcdefgh1234",
                ("homr", "homr"),
            )

    def test_invalid_job_id_is_rejected(self) -> None:
        with self.assertRaisesRegex(ModelError, "job_id"):
            build_job_record("unsafe-id")


if __name__ == "__main__":
    unittest.main()
