from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import MappingProxyType
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "services" / "teacher-review-service" / "src"
ENSEMBLE_SRC = ROOT / "services" / "ensemble-service" / "src"
TESTS = ROOT / "services" / "teacher-review-service" / "tests"
sys.path.insert(0, str(ENSEMBLE_SRC))
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(TESTS))

from scoremosaic_teacher_review import (  # noqa: E402
    COMMAND_VERSION,
    apply_score_edit_command,
    build_score_edit_command,
    build_teacher_score_revision,
    expected_old_value_sha256,
    issue_authorization_grant,
)
from scoremosaic_teacher_review.approval_record import ImmutableHumanApprovalRecord  # noqa: E402
from scoremosaic_teacher_review.corrected_musicxml import CorrectedMusicXmlArtifact  # noqa: E402
from scoremosaic_teacher_review.publication_eligibility import (  # noqa: E402
    PUBLICATION_ELIGIBILITY_VERSION,
    PublicationEligibilityEvidence,
    Stage8PublicationEligibilityError,
    build_publication_eligibility_evidence,
)
from test_stage8m_human_approval_record import (  # noqa: E402
    AUTHZ_KEY,
    DECISION_KEY,
    HANDOFF_KEY,
    H_REPORT,
    Stage8MHumanApprovalRecordTests,
    loc,
    q,
)


class Stage8NPublicationEligibilityTests(unittest.TestCase):
    def _approved_fixture(self):
        helper = Stage8MHumanApprovalRecordTests(
            methodName="test_explicit_human_approval_builds_deterministic_record_without_publication"
        )
        helper.setUp()
        self.addCleanup(helper.doCleanups)
        state, revision, artifact, handoff_grant, handoff, decision_grant = helper._current_handoff()
        approval_record = helper._build_record(
            state=state,
            revision=revision,
            artifact=artifact,
            handoff_grant=handoff_grant,
            handoff=handoff,
            decision_grant=decision_grant,
        )
        return helper, state, revision, artifact, handoff_grant, handoff, decision_grant, approval_record

    def _build(self, values, *, artifact=None, decision_grant=None, approval_record=None):
        helper, state, revision, original_artifact, handoff_grant, handoff, original_decision, original_record = values
        return build_publication_eligibility_evidence(
            scope=helper.scope,
            store=helper.store,
            revision=revision,
            state=state,
            artifact=original_artifact if artifact is None else artifact,
            handoff_grant=handoff_grant,
            handoff_signing_key=HANDOFF_KEY,
            handoff=handoff,
            decision_grant=original_decision if decision_grant is None else decision_grant,
            decision_signing_key=DECISION_KEY,
            expected_approver_id="teacher_stage8f",
            approval_record=original_record if approval_record is None else approval_record,
        )

    def test_exact_approval_record_is_deterministic_publication_handoff_candidate_only(self):
        values = self._approved_fixture()
        evidences = [self._build(values) for _ in range(10)]
        self.assertEqual(1, len({item.evidence_sha256 for item in evidences}))
        data = evidences[0].to_dict()
        self.assertEqual(PUBLICATION_ELIGIBILITY_VERSION, data["schemaVersion"])
        self.assertTrue(all(data["checks"].values()))
        self.assertTrue(data["eligibility"]["candidateEligibleForPublicationHandoff"])
        self.assertFalse(data["eligibility"]["productionPublicationEligible"])
        self.assertEqual(
            ["PRODUCTION_PUBLICATION_AUTHORIZATION_REQUIRED", "PRODUCTION_PERSISTENCE_REQUIRED"],
            data["eligibility"]["productionBlockers"],
        )
        self.assertTrue(all(value is False for value in data["authority"].values()))
        approval = values[-1].to_dict()
        self.assertEqual(approval["approvalRecordSha256"], data["humanApproval"]["approvalRecordSha256"])
        self.assertEqual(approval["correctedArtifact"]["musicXmlSha256"], data["correctedArtifact"]["musicXmlSha256"])

    def test_stale_head_fails_via_fresh_stage8m_revalidation(self):
        values = self._approved_fixture()
        helper, state, revision, _, _, _, _, _ = values
        r1 = revision.to_dict()
        target = loc("P1:M1:E2", 1)
        operation = {"type": "set_pitch", "value": {"step": "G", "alter": q(0), "octave": 4}}
        command = build_score_edit_command({
            "schemaVersion": COMMAND_VERSION,
            "commandId": "cmd_stage8n_second",
            "jobId": "job_stage8f_0001",
            "reviewerId": "teacher_stage8f",
            "authorizationDecisionId": "authz_cmd_stage8n_second",
            "reviewReportId": "report_stage8f_0001",
            "reviewReportSha256": H_REPORT,
            "baseCanonicalSha256": helper.base["canonicalSha256"],
            "baseRevisionId": r1["revisionId"],
            "baseRevisionSha256": r1["revisionSha256"],
            "issueId": "issue_stage8n_second",
            "location": target,
            "operation": operation,
            "oldValueSha256": expected_old_value_sha256(state, location=target, operation_type=operation["type"]),
            "reason": "Advance head before publication eligibility.",
        })
        applied = apply_score_edit_command(state, command)
        grant = issue_authorization_grant(
            decision_id="authz_cmd_stage8n_second",
            reviewer_id="teacher_stage8f",
            tenant_id="school_stage8f",
            job_id="job_stage8f_0001",
            review_report_id="report_stage8f_0001",
            review_report_sha256=H_REPORT,
            canonical_score_sha256=helper.base["canonicalSha256"],
            parent_revision_id=r1["revisionId"],
            parent_revision_sha256=r1["revisionSha256"],
            allowed_actions=("revision:read", "revision:propose"),
            signing_key=AUTHZ_KEY,
        )
        revision2 = build_teacher_score_revision(
            grant=grant,
            signing_key=AUTHZ_KEY,
            expected_tenant_id="school_stage8f",
            expected_job_id="job_stage8f_0001",
            expected_reviewer_id="teacher_stage8f",
            expected_review_report_id="report_stage8f_0001",
            expected_review_report_sha256=H_REPORT,
            expected_canonical_score_sha256=helper.base["canonicalSha256"],
            command=command,
            current_parent_revision_id=r1["revisionId"],
            current_parent_revision_sha256=r1["revisionSha256"],
            resulting_musical_state_sha256=applied.state.state_sha256,
            validation_report_sha256=applied.validation.report_sha256,
            blocking_issue_count=applied.validation.blocking_issue_count,
            unresolved_issue_count=applied.validation.unresolved_issue_count,
            created_at="2026-08-22T16:45:00Z",
            previous_audit_event_sha256=r1["auditEventSha256"],
        )
        helper._persist(revision2)
        with self.assertRaisesRegex(
            Stage8PublicationEligibilityError,
            "PUBLICATION_ELIGIBILITY_APPROVAL_REVALIDATION_REJECTED",
        ):
            self._build(values)

    def test_artifact_and_decision_substitution_fail_closed(self):
        values = self._approved_fixture()
        artifact = values[3]
        forged_artifact = CorrectedMusicXmlArtifact(document=artifact.document + b"\n", _record=artifact._record)
        with self.assertRaisesRegex(
            Stage8PublicationEligibilityError,
            "PUBLICATION_ELIGIBILITY_APPROVAL_REVALIDATION_REJECTED",
        ):
            self._build(values, artifact=forged_artifact)

        tampered_decision = replace(values[6], music_xml_sha256="0" * 64)
        with self.assertRaisesRegex(
            Stage8PublicationEligibilityError,
            "PUBLICATION_ELIGIBILITY_APPROVAL_REVALIDATION_REJECTED",
        ):
            self._build(values, decision_grant=tampered_decision)

    def test_substituted_approval_record_fails_closed(self):
        values = self._approved_fixture()
        payload = values[-1].to_dict()
        payload.pop("approvalRecordSha256")
        payload["approvalRecordId"] = "approval_" + "0" * 32
        forged = object.__new__(ImmutableHumanApprovalRecord)
        object.__setattr__(forged, "_payload", MappingProxyType(payload))
        with self.assertRaises(Stage8PublicationEligibilityError):
            self._build(values, approval_record=forged)

    def test_evidence_constructor_is_sealed(self):
        with self.assertRaisesRegex(
            Stage8PublicationEligibilityError,
            "PUBLICATION_ELIGIBILITY_CONSTRUCTION_FORBIDDEN",
        ):
            PublicationEligibilityEvidence(MappingProxyType({}))

    def test_module_has_no_publisher_route_network_storage_or_process_runtime(self):
        source = (SRC / "scoremosaic_teacher_review" / "publication_eligibility.py").read_text(encoding="utf-8").lower()
        for forbidden in (
            "fastapi", "flask", "django", "starlette", "requests.", "urllib.", "socket.",
            "subprocess", "os.system", "sqlite3", "psycopg", "boto3", "redis", "publish(",
            "put_object", "upload_file", "http.server", "websocket",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
