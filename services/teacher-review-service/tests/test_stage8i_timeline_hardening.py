from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "services" / "teacher-review-service" / "src"
TESTS = ROOT / "services" / "teacher-review-service" / "tests"
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(TESTS))

from scoremosaic_teacher_review import (  # noqa: E402
    COMMAND_VERSION,
    DurableRevisionStore,
    apply_score_edit_command,
    build_score_edit_command,
    build_teacher_score_revision,
    expected_old_value_sha256,
    materialize_canonical_state,
)
from scoremosaic_teacher_review.review_timeline import (  # noqa: E402
    Stage8TimelineError,
    build_review_timeline_projection,
)
from test_stage8i_rational_timeline import (  # noqa: E402
    AUTHZ_KEY,
    H_A,
    STORE_KEY,
    fixture,
    grant,
    q,
    scope_for,
)


class Stage8ITimelineHardeningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base = fixture()
        self.scope = scope_for(self.base)
        self.state = materialize_canonical_state(self.scope, self.base)

    def _duration_command(self, *, value: dict[str, int]):
        location = {
            "partId": "P1",
            "measureId": "P1:M1",
            "eventId": "P1:M1:E1",
            "staff": 1,
            "voice": "1",
            "onset": q(0),
        }
        return build_score_edit_command({
            "schemaVersion": COMMAND_VERSION,
            "commandId": "cmd_stage8i_duration_hardening",
            "jobId": "job_stage8i_0001",
            "reviewerId": "teacher_stage8i",
            "authorizationDecisionId": "authz_stage8i_write_hardening",
            "reviewReportId": "report_stage8i_0001",
            "reviewReportSha256": H_A,
            "baseCanonicalSha256": self.base["canonicalSha256"],
            "baseRevisionId": None,
            "baseRevisionSha256": None,
            "issueId": "issue_stage8i_duration",
            "location": location,
            "operation": {"type": "set_effective_duration", "value": value},
            "oldValueSha256": expected_old_value_sha256(
                self.state,
                location=location,
                operation_type="set_effective_duration",
            ),
            "reason": "Verify derived cursor timing is recomputed from current events.",
        })

    def _append_revision(
        self,
        store: DurableRevisionStore,
        *,
        command,
        applied,
        validation_sha: str,
        blocking_count: int,
        unresolved_count: int,
    ):
        write_auth = grant(
            self.base["canonicalSha256"],
            aid="authz_stage8i_write_hardening",
        )
        revision = build_teacher_score_revision(
            grant=write_auth,
            signing_key=AUTHZ_KEY,
            expected_tenant_id="school_stage8i",
            expected_job_id="job_stage8i_0001",
            expected_reviewer_id="teacher_stage8i",
            expected_review_report_id="report_stage8i_0001",
            expected_review_report_sha256=H_A,
            expected_canonical_score_sha256=self.base["canonicalSha256"],
            command=command,
            current_parent_revision_id=None,
            current_parent_revision_sha256=None,
            resulting_musical_state_sha256=applied.state.state_sha256,
            validation_report_sha256=validation_sha,
            blocking_issue_count=blocking_count,
            unresolved_issue_count=unresolved_count,
            created_at="2026-08-22T13:30:00Z",
            previous_audit_event_sha256=None,
        )
        store.append_revision(
            self.scope,
            revision,
            expected_parent_revision_id=None,
            expected_parent_revision_sha256=None,
        )
        return revision

    def test_stale_observed_duration_is_not_projected_and_extent_is_recomputed(self):
        command = self._duration_command(value=q(5))
        applied = apply_score_edit_command(self.state, command)
        # Stage 8-C intentionally preserves some derived Canonical metadata. The
        # timeline must never expose that stale metadata as cursor truth.
        self.assertEqual(q(4), applied.state.to_dict()["parts"][0]["measures"][0]["observedDuration"])

        with tempfile.TemporaryDirectory() as temp:
            store = DurableRevisionStore(Path(temp) / "store", signing_key=STORE_KEY)
            revision = self._append_revision(
                store,
                command=command,
                applied=applied,
                validation_sha=applied.validation.report_sha256,
                blocking_count=applied.validation.blocking_issue_count,
                unresolved_count=applied.validation.unresolved_issue_count,
            )
            record = revision.to_dict()
            read_auth = grant(
                self.base["canonicalSha256"],
                aid="authz_stage8i_read_hardening",
                parent_id=record["revisionId"],
                parent_sha=record["revisionSha256"],
            )
            result = build_review_timeline_projection(
                grant=read_auth,
                signing_key=AUTHZ_KEY,
                expected_reviewer_id="teacher_stage8i",
                scope=self.scope,
                store=store,
                state=applied.state,
                base_canonical_payload=self.base,
            ).to_dict()

        measure = result["parts"][0]["measures"][0]
        self.assertNotIn("observedDuration", measure)
        self.assertEqual(q(5), measure["eventExtentEnd"])
        self.assertEqual(q(5), measure["loopBounds"]["eventExtentEnd"])
        self.assertFalse(measure["loopBounds"]["safeWithinExpectedDuration"])
        self.assertGreater(result["validation"]["blockingIssueCount"], 0)
        self.assertFalse(result["capabilities"]["canPlay"])
        self.assertFalse(result["capabilities"]["canLoop"])

    def test_revision_validation_evidence_must_match_independent_recompute(self):
        command = self._duration_command(value=q(2))
        applied = apply_score_edit_command(self.state, command)
        with tempfile.TemporaryDirectory() as temp:
            store = DurableRevisionStore(Path(temp) / "store", signing_key=STORE_KEY)
            revision = self._append_revision(
                store,
                command=command,
                applied=applied,
                validation_sha="f" * 64,
                blocking_count=0,
                unresolved_count=0,
            )
            record = revision.to_dict()
            read_auth = grant(
                self.base["canonicalSha256"],
                aid="authz_stage8i_read_bad_validation",
                parent_id=record["revisionId"],
                parent_sha=record["revisionSha256"],
            )
            with self.assertRaisesRegex(
                Stage8TimelineError,
                "TIMELINE_REVISION_VALIDATION_MISMATCH",
            ):
                build_review_timeline_projection(
                    grant=read_auth,
                    signing_key=AUTHZ_KEY,
                    expected_reviewer_id="teacher_stage8i",
                    scope=self.scope,
                    store=store,
                    state=applied.state,
                    base_canonical_payload=self.base,
                )

    def test_timeline_module_has_no_generic_exception_catch(self):
        source = (
            SRC / "scoremosaic_teacher_review" / "review_timeline.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("except Exception", source)
        self.assertNotIn("except BaseException", source)
        self.assertNotIn('"observedDuration"', source)


if __name__ == "__main__":
    unittest.main()
