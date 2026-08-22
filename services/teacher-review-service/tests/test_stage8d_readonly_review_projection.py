from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
TEACHER_SRC = ROOT / "services" / "teacher-review-service" / "src"
ENSEMBLE_SRC = ROOT / "services" / "ensemble-service" / "src"
sys.path.insert(0, str(TEACHER_SRC))
sys.path.insert(0, str(ENSEMBLE_SRC))

from scoremosaic_ensemble.comparator import compare_candidates  # noqa: E402
from scoremosaic_ensemble.musicxml import normalize_musicxml  # noqa: E402
from scoremosaic_ensemble.report import build_comparison_report  # noqa: E402
from scoremosaic_teacher_review import (  # noqa: E402
    COMMAND_VERSION,
    RevisionScope,
    apply_score_edit_command,
    build_score_edit_command,
    build_teacher_score_revision,
    expected_old_value_sha256,
    issue_authorization_grant,
    materialize_canonical_state,
)
from scoremosaic_teacher_review.review_projection import (  # noqa: E402
    Stage8ProjectionError,
    build_review_projection_page,
    validate_review_report_for_projection,
)

FIXTURE = ROOT / "services" / "ensemble-service" / "tests" / "fixtures" / "canonical-smoke.musicxml"
AUTHZ_KEY = b"stage8d-authz-purpose-separated-key-32bytes!!"


def evidence():
    raw = FIXTURE.read_bytes()
    changed = raw.replace(b"<step>C</step>", b"<step>F</step>", 1)
    base = normalize_musicxml(
        raw,
        engine="homr",
        engine_version="0.7.0",
        model_version="fixture-model",
        artifact_ref="candidates/homr/stage8d-base.musicxml",
    )
    alternate = normalize_musicxml(
        changed,
        engine="audiveris",
        engine_version="5.5.0",
        model_version=None,
        artifact_ref="candidates/audiveris/stage8d-alternate.musicxml",
    )
    report = build_comparison_report(compare_candidates((base, alternate))).as_dict()
    return base, alternate, report


def make_scope(base, report):
    return RevisionScope.create(
        tenant_id="school_stage8d",
        job_id="job_stage8d_0001",
        review_report_id=report["reportId"],
        review_report_sha256=report["reportSha256"],
        base_canonical_sha256=base.canonical_sha256,
    )


def read_grant(scope, *, parent_id=None, parent_sha=None, tenant=None, actions=("revision:read",)):
    return issue_authorization_grant(
        decision_id=("authz_stage8d_read_base" if parent_id is None else "authz_stage8d_read_revision"),
        reviewer_id="teacher_stage8d",
        tenant_id=tenant or scope.tenant_id,
        job_id=scope.job_id,
        review_report_id=scope.review_report_id,
        review_report_sha256=scope.review_report_sha256,
        canonical_score_sha256=scope.base_canonical_sha256,
        parent_revision_id=parent_id,
        parent_revision_sha256=parent_sha,
        allowed_actions=actions,
        signing_key=AUTHZ_KEY,
    )


def projection(scope, base, report, state, *, revision=None, grant=None, offset=0, limit=100):
    return build_review_projection_page(
        grant=grant or read_grant(
            scope,
            parent_id=(revision.record["revisionId"] if revision is not None else None),
            parent_sha=(revision.record["revisionSha256"] if revision is not None else None),
        ),
        signing_key=AUTHZ_KEY,
        expected_reviewer_id="teacher_stage8d",
        scope=scope,
        comparison_report=report,
        base_canonical_payload=base.as_dict(),
        state=state,
        revision=revision,
        offset=offset,
        limit=limit,
    )


def first_location(state):
    payload = state.to_dict()
    part = payload["parts"][0]
    measure = part["measures"][0]
    event = measure["events"][0]
    return event, {
        "partId": part["partId"],
        "measureId": measure["measureId"],
        "eventId": event["eventId"],
        "staff": event["staff"],
        "voice": event["voice"],
        "onset": event["onset"],
    }


class Stage8DReadOnlyProjectionTests(unittest.TestCase):
    def setUp(self):
        self.base, self.alternate, self.report = evidence()
        self.scope = make_scope(self.base, self.report)
        self.state = materialize_canonical_state(self.scope, self.base.as_dict())

    def test_real_stage7_report_projects_deterministically(self):
        outputs = [projection(self.scope, self.base, self.report, self.state).to_dict() for _ in range(10)]
        self.assertTrue(outputs[0]["differences"])
        self.assertEqual(1, len({item["projectionSha256"] for item in outputs}))
        self.assertTrue(outputs[0]["capabilities"]["readOnly"])
        self.assertFalse(outputs[0]["capabilities"]["canEdit"])
        self.assertFalse(outputs[0]["capabilities"]["canApprove"])
        self.assertFalse(outputs[0]["capabilities"]["canPublish"])
        self.assertFalse(outputs[0]["capabilities"]["authoritativeTruth"])
        self.assertEqual("base", outputs[0]["snapshot"]["kind"])
        self.assertEqual(self.state.state_sha256, outputs[0]["snapshot"]["stateSha256"])

    def test_projection_strips_raw_source_and_xml_path_authority(self):
        payload = projection(self.scope, self.base, self.report, self.state).to_dict()
        forbidden_keys = {
            "source",
            "artifactRef",
            "artifactSha256",
            "xmlPath",
            "sourceEventIndex",
            "signature",
            "allowedActions",
        }

        def walk(value):
            if isinstance(value, dict):
                self.assertTrue(forbidden_keys.isdisjoint(value))
                for item in value.values():
                    walk(item)
            elif isinstance(value, list):
                for item in value:
                    walk(item)

        walk(payload)

    def test_tampered_stage7_report_fails_closed(self):
        tampered = deepcopy(self.report)
        tampered["comparison"]["differences"][0]["description"] = "forged"
        with self.assertRaisesRegex(Stage8ProjectionError, "PROJECTION_REPORT_DIFFERENCE_INVALID"):
            validate_review_report_for_projection(
                tampered,
                expected_report_id=self.scope.review_report_id,
                expected_report_sha256=self.scope.review_report_sha256,
            )

    def test_cross_tenant_and_missing_read_authority_fail_closed(self):
        wrong_tenant = read_grant(self.scope, tenant="school_other")
        with self.assertRaisesRegex(Stage8ProjectionError, "PROJECTION_AUTHORIZATION_DENIED"):
            projection(self.scope, self.base, self.report, self.state, grant=wrong_tenant)
        propose_only = read_grant(self.scope, actions=("revision:propose",))
        with self.assertRaisesRegex(Stage8ProjectionError, "PROJECTION_AUTHORIZATION_DENIED"):
            projection(self.scope, self.base, self.report, self.state, grant=propose_only)

    def test_pagination_is_bounded_and_explicit(self):
        payload = projection(self.scope, self.base, self.report, self.state, limit=1).to_dict()
        self.assertEqual(1, payload["page"]["limit"])
        self.assertEqual(1, payload["page"]["returned"])
        self.assertEqual(len(self.report["comparison"]["differences"]), payload["page"]["totalDifferences"])
        self.assertEqual(payload["page"]["totalDifferences"] > 1, payload["page"]["hasMore"])
        with self.assertRaisesRegex(Stage8ProjectionError, "PROJECTION_PAGE_INVALID"):
            projection(self.scope, self.base, self.report, self.state, limit=201)

    def test_unpersisted_edited_state_cannot_masquerade_as_base_snapshot(self):
        _, location = first_location(self.state)
        command = build_score_edit_command(
            {
                "schemaVersion": COMMAND_VERSION,
                "commandId": "cmd_stage8d_unpersisted",
                "jobId": self.scope.job_id,
                "reviewerId": "teacher_stage8d",
                "authorizationDecisionId": "authz_stage8d_unpersisted",
                "reviewReportId": self.scope.review_report_id,
                "reviewReportSha256": self.scope.review_report_sha256,
                "baseCanonicalSha256": self.scope.base_canonical_sha256,
                "baseRevisionId": None,
                "baseRevisionSha256": None,
                "issueId": self.report["comparison"]["differences"][0]["differenceId"],
                "location": location,
                "operation": {"type": "set_dots", "value": 1},
                "oldValueSha256": expected_old_value_sha256(
                    self.state, location=location, operation_type="set_dots"
                ),
                "reason": "Stage 8-D base-snapshot binding test.",
            }
        )
        edited = apply_score_edit_command(self.state, command).state
        with self.assertRaisesRegex(Stage8ProjectionError, "PROJECTION_BASE_STATE_MISMATCH"):
            projection(self.scope, self.base, self.report, edited)

    def test_exact_revision_snapshot_binds_revision_hash_to_state_and_focus(self):
        event, location = first_location(self.state)
        decision_id = "authz_stage8d_remove"
        command = build_score_edit_command(
            {
                "schemaVersion": COMMAND_VERSION,
                "commandId": "cmd_stage8d_remove",
                "jobId": self.scope.job_id,
                "reviewerId": "teacher_stage8d",
                "authorizationDecisionId": decision_id,
                "reviewReportId": self.scope.review_report_id,
                "reviewReportSha256": self.scope.review_report_sha256,
                "baseCanonicalSha256": self.scope.base_canonical_sha256,
                "baseRevisionId": None,
                "baseRevisionSha256": None,
                "issueId": self.report["comparison"]["differences"][0]["differenceId"],
                "location": location,
                "operation": {"type": "remove_event", "value": None},
                "oldValueSha256": expected_old_value_sha256(
                    self.state, location=location, operation_type="remove_event"
                ),
                "reason": "Remove one exact event for projection focus evidence.",
            }
        )
        applied = apply_score_edit_command(self.state, command)
        propose_grant = issue_authorization_grant(
            decision_id=decision_id,
            reviewer_id="teacher_stage8d",
            tenant_id=self.scope.tenant_id,
            job_id=self.scope.job_id,
            review_report_id=self.scope.review_report_id,
            review_report_sha256=self.scope.review_report_sha256,
            canonical_score_sha256=self.scope.base_canonical_sha256,
            parent_revision_id=None,
            parent_revision_sha256=None,
            allowed_actions=("revision:read", "revision:propose"),
            signing_key=AUTHZ_KEY,
        )
        revision = build_teacher_score_revision(
            grant=propose_grant,
            signing_key=AUTHZ_KEY,
            expected_tenant_id=self.scope.tenant_id,
            expected_job_id=self.scope.job_id,
            expected_reviewer_id="teacher_stage8d",
            expected_review_report_id=self.scope.review_report_id,
            expected_review_report_sha256=self.scope.review_report_sha256,
            expected_canonical_score_sha256=self.scope.base_canonical_sha256,
            command=command,
            current_parent_revision_id=None,
            current_parent_revision_sha256=None,
            resulting_musical_state_sha256=applied.state.state_sha256,
            validation_report_sha256=applied.validation.report_sha256,
            blocking_issue_count=applied.validation.blocking_issue_count,
            unresolved_issue_count=applied.validation.unresolved_issue_count,
            created_at="2026-08-22T08:30:00Z",
            previous_audit_event_sha256=None,
        )
        payload = projection(
            self.scope,
            self.base,
            self.report,
            applied.state,
            revision=revision,
        ).to_dict()
        self.assertEqual("revision", payload["snapshot"]["kind"])
        self.assertEqual(revision.record["revisionId"], payload["snapshot"]["revisionId"])
        selected = [
            item for item in payload["differences"] if item["focus"]["eventId"] == event["eventId"]
        ]
        self.assertTrue(selected)
        self.assertFalse(selected[0]["focus"]["eventPresentInSnapshot"])

        with self.assertRaisesRegex(Stage8ProjectionError, "PROJECTION_REVISION_STATE_MISMATCH"):
            projection(self.scope, self.base, self.report, self.state, revision=revision)


if __name__ == "__main__":
    unittest.main()
