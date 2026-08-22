from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
TEACHER_SRC = ROOT / "services" / "teacher-review-service" / "src"
ENSEMBLE_SRC = ROOT / "services" / "ensemble-service" / "src"
TESTS = ROOT / "services" / "teacher-review-service" / "tests"
sys.path.insert(0, str(TEACHER_SRC))
sys.path.insert(0, str(ENSEMBLE_SRC))
sys.path.insert(0, str(TESTS))

import scoremosaic_teacher_review.review_projection as projection_module  # noqa: E402
from scoremosaic_teacher_review.review_projection import (  # noqa: E402
    Stage8ProjectionError,
    build_review_projection_page,
)
from test_stage8d_readonly_review_projection import (  # noqa: E402
    AUTHZ_KEY,
    evidence,
    make_scope,
    read_grant,
)


class Stage8DProjectionAuthorizationHardeningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base, _, self.report = evidence()
        self.scope = make_scope(self.base, self.report)

    def test_wrong_tenant_is_rejected_before_state_base_or_report_processing(self):
        wrong_tenant = read_grant(self.scope, tenant="school_other")
        with self.assertRaisesRegex(Stage8ProjectionError, "PROJECTION_AUTHORIZATION_DENIED"):
            build_review_projection_page(
                grant=wrong_tenant,
                signing_key=AUTHZ_KEY,
                expected_reviewer_id="teacher_stage8d",
                scope=self.scope,
                comparison_report={"hostile": object()},
                base_canonical_payload={"hostile": object()},
                state="not-a-review-state",  # type: ignore[arg-type]
            )

    def test_missing_read_action_is_rejected_before_state_processing(self):
        propose_only = read_grant(self.scope, actions=("revision:propose",))
        with self.assertRaisesRegex(Stage8ProjectionError, "PROJECTION_AUTHORIZATION_DENIED"):
            build_review_projection_page(
                grant=propose_only,
                signing_key=AUTHZ_KEY,
                expected_reviewer_id="teacher_stage8d",
                scope=self.scope,
                comparison_report={"hostile": object()},
                base_canonical_payload={"hostile": object()},
                state="not-a-review-state",  # type: ignore[arg-type]
            )

    def test_unexpected_authorization_runtime_error_is_not_masked(self):
        valid_grant = read_grant(self.scope)
        with patch.object(
            projection_module,
            "verify_authorization_grant",
            side_effect=RuntimeError("programming defect"),
        ):
            with self.assertRaisesRegex(RuntimeError, "programming defect"):
                build_review_projection_page(
                    grant=valid_grant,
                    signing_key=AUTHZ_KEY,
                    expected_reviewer_id="teacher_stage8d",
                    scope=self.scope,
                    comparison_report={"hostile": object()},
                    base_canonical_payload={"hostile": object()},
                    state="not-a-review-state",  # type: ignore[arg-type]
                )

    def test_projection_source_has_no_generic_authorization_catch(self):
        source = (
            TEACHER_SRC / "scoremosaic_teacher_review" / "review_projection.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("except Exception", source)
        self.assertNotIn("except BaseException", source)
        self.assertIn("except Stage8ContractError", source)


if __name__ == "__main__":
    unittest.main()
