from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import MappingProxyType
import sys
import tempfile
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
    DurableRevisionStore,
    apply_score_edit_command,
    build_score_edit_command,
    build_teacher_score_revision,
    expected_old_value_sha256,
    issue_authorization_grant,
    materialize_canonical_state,
)
from scoremosaic_teacher_review.approval_eligibility import (  # noqa: E402
    build_approval_eligibility_evidence,
)
from scoremosaic_teacher_review.approval_handoff import (  # noqa: E402
    APPROVAL_HANDOFF_AUTHZ_VERSION,
    APPROVAL_HANDOFF_VERSION,
    HumanApprovalHandoffRequest,
    Stage8ApprovalHandoffError,
    build_human_approval_handoff_request,
    issue_approval_handoff_grant,
)
from scoremosaic_teacher_review.corrected_musicxml import (  # noqa: E402
    CorrectedMusicXmlArtifact,
    build_corrected_musicxml_artifact,
)
from test_stage8f_corrected_musicxml import (  # noqa: E402
    AUTHZ_KEY,
    H_REPORT,
    fixture,
    loc,
    q,
    revision_for,
    scope_for,
)

STORE_KEY = b"stage8l-durable-store-purpose-key-32bytes!!"
HANDOFF_KEY = b"stage8l-approval-handoff-purpose-key-32bytes!!"
WRONG_HANDOFF_KEY = b"stage8l-wrong-handoff-purpose-key-32bytes!!"


class Stage8LHumanApprovalHandoffTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base = fixture()
        self.scope = scope_for(self.base)
        self.base_state = materialize_canonical_state(self.scope, self.base)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = DurableRevisionStore(Path(self.temp.name) / "store", signing_key=STORE_KEY)

    def _persist(self, revision):
        record = revision.to_dict()
        return self.store.append_revision(
            self.scope,
            revision,
            expected_parent_revision_id=record["parentRevisionId"],
            expected_parent_revision_sha256=record["parentRevisionSha256"],
        )

    def _clean_current(self):
        state, revision = revision_for(
            self.base,
            self.base_state,
            {"type": "set_pitch", "value": {"step": "F", "alter": q(1), "octave": 5}},
            command_id="cmd_stage8l_clean",
        )
        self._persist(revision)
        artifact = build_corrected_musicxml_artifact(
            scope=self.scope,
            revision=revision,
            state=state,
        )
        eligibility = build_approval_eligibility_evidence(
            scope=self.scope,
            store=self.store,
            revision=revision,
            state=state,
            artifact=artifact,
        )
        grant = issue_approval_handoff_grant(
            request_id="handoff_stage8l_0001",
            approver_id="teacher_stage8f",
            eligibility=eligibility,
            signing_key=HANDOFF_KEY,
        )
        return state, revision, artifact, eligibility, grant

    def _advance_head(self, state1, revision1):
        revision1_record = revision1.to_dict()
        target = loc("P1:M1:E2", 1)
        operation = {"type": "set_pitch", "value": {"step": "G", "alter": q(0), "octave": 4}}
        command = build_score_edit_command(
            {
                "schemaVersion": COMMAND_VERSION,
                "commandId": "cmd_stage8l_second",
                "jobId": "job_stage8f_0001",
                "reviewerId": "teacher_stage8f",
                "authorizationDecisionId": "authz_cmd_stage8l_second",
                "reviewReportId": "report_stage8f_0001",
                "reviewReportSha256": H_REPORT,
                "baseCanonicalSha256": self.base["canonicalSha256"],
                "baseRevisionId": revision1_record["revisionId"],
                "baseRevisionSha256": revision1_record["revisionSha256"],
                "issueId": "issue_stage8l_second",
                "location": target,
                "operation": operation,
                "oldValueSha256": expected_old_value_sha256(
                    state1,
                    location=target,
                    operation_type=operation["type"],
                ),
                "reason": "Advance exact head before approval handoff replay.",
            }
        )
        applied = apply_score_edit_command(state1, command)
        grant = issue_authorization_grant(
            decision_id="authz_cmd_stage8l_second",
            reviewer_id="teacher_stage8f",
            tenant_id="school_stage8f",
            job_id="job_stage8f_0001",
            review_report_id="report_stage8f_0001",
            review_report_sha256=H_REPORT,
            canonical_score_sha256=self.base["canonicalSha256"],
            parent_revision_id=revision1_record["revisionId"],
            parent_revision_sha256=revision1_record["revisionSha256"],
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
            expected_canonical_score_sha256=self.base["canonicalSha256"],
            command=command,
            current_parent_revision_id=revision1_record["revisionId"],
            current_parent_revision_sha256=revision1_record["revisionSha256"],
            resulting_musical_state_sha256=applied.state.state_sha256,
            validation_report_sha256=applied.validation.report_sha256,
            blocking_issue_count=applied.validation.blocking_issue_count,
            unresolved_issue_count=applied.validation.unresolved_issue_count,
            created_at="2026-08-22T16:30:00Z",
            previous_audit_event_sha256=revision1_record["auditEventSha256"],
        )
        self._persist(revision2)
        return applied.state, revision2

    def test_exact_current_eligible_candidate_builds_deterministic_human_handoff_only(self):
        state, revision, artifact, eligibility, grant = self._clean_current()
        requests = [
            build_human_approval_handoff_request(
                scope=self.scope,
                store=self.store,
                revision=revision,
                state=state,
                artifact=artifact,
                grant=grant,
                expected_approver_id="teacher_stage8f",
                signing_key=HANDOFF_KEY,
            )
            for _ in range(10)
        ]
        self.assertEqual(1, len({item.request_sha256 for item in requests}))
        data = requests[0].to_dict()
        self.assertEqual(APPROVAL_HANDOFF_VERSION, data["schemaVersion"])
        self.assertEqual("awaiting_human_decision", data["state"]["status"])
        self.assertIsNone(data["state"]["approvalDecision"])
        self.assertIsNone(data["state"]["approvalRecordId"])
        self.assertIsNone(data["state"]["publicationRecordId"])
        self.assertTrue(data["requirements"]["humanDecisionRequired"])
        self.assertTrue(data["requirements"]["freshEligibilityRecomputed"])
        self.assertTrue(data["capabilities"]["canPresentForHumanApproval"])
        for key in ("canRecordApproval", "canPublish", "canMutate", "canWrite", "authoritativeTruth"):
            self.assertFalse(data["capabilities"][key])
        self.assertEqual(eligibility.evidence_sha256, data["eligibilityEvidenceSha256"])
        self.assertEqual(revision.to_dict()["revisionSha256"], data["currentHead"]["revisionSha256"])
        self.assertEqual(artifact.to_dict()["musicXmlSha256"], data["correctedArtifact"]["musicXmlSha256"])

    def test_grant_is_purpose_bound_and_repr_redacts_signature(self):
        _, _, _, eligibility, grant = self._clean_current()
        safe = grant.safe_dict()
        self.assertEqual(APPROVAL_HANDOFF_AUTHZ_VERSION, safe["schemaVersion"])
        self.assertEqual("present_for_human_approval", safe["allowedAction"])
        self.assertEqual("<redacted>", safe["signature"])
        self.assertNotIn(grant.signature_hex, repr(grant))
        duplicate = issue_approval_handoff_grant(
            request_id="handoff_stage8l_0001",
            approver_id="teacher_stage8f",
            eligibility=eligibility,
            signing_key=HANDOFF_KEY,
        )
        self.assertEqual(grant.grant_sha256, duplicate.grant_sha256)
        self.assertEqual(grant.signature_hex, duplicate.signature_hex)

    def test_ineligible_candidate_cannot_receive_handoff_authorization(self):
        state, revision = revision_for(
            self.base,
            self.base_state,
            {"type": "set_effective_duration", "value": q(5)},
            command_id="cmd_stage8l_overflow",
        )
        self._persist(revision)
        artifact = build_corrected_musicxml_artifact(scope=self.scope, revision=revision, state=state)
        eligibility = build_approval_eligibility_evidence(
            scope=self.scope,
            store=self.store,
            revision=revision,
            state=state,
            artifact=artifact,
        )
        self.assertFalse(eligibility.to_dict()["eligibility"]["candidateEligible"])
        with self.assertRaisesRegex(Stage8ApprovalHandoffError, "APPROVAL_HANDOFF_CANDIDATE_INELIGIBLE"):
            issue_approval_handoff_grant(
                request_id="handoff_stage8l_bad",
                approver_id="teacher_stage8f",
                eligibility=eligibility,
                signing_key=HANDOFF_KEY,
            )

    def test_wrong_approver_wrong_key_and_tampered_grant_fail_closed(self):
        state, revision, artifact, _, grant = self._clean_current()
        common = dict(
            scope=self.scope,
            store=self.store,
            revision=revision,
            state=state,
            artifact=artifact,
            grant=grant,
        )
        with self.assertRaisesRegex(Stage8ApprovalHandoffError, "APPROVAL_HANDOFF_GRANT_SCOPE_MISMATCH"):
            build_human_approval_handoff_request(
                **common,
                expected_approver_id="other_teacher",
                signing_key=HANDOFF_KEY,
            )
        with self.assertRaisesRegex(Stage8ApprovalHandoffError, "APPROVAL_HANDOFF_SIGNATURE_INVALID"):
            build_human_approval_handoff_request(
                **common,
                expected_approver_id="teacher_stage8f",
                signing_key=WRONG_HANDOFF_KEY,
            )
        forged = replace(grant, revision_sha256="0" * 64)
        with self.assertRaisesRegex(Stage8ApprovalHandoffError, "APPROVAL_HANDOFF_GRANT_SCOPE_MISMATCH"):
            build_human_approval_handoff_request(
                **{**common, "grant": forged},
                expected_approver_id="teacher_stage8f",
                signing_key=HANDOFF_KEY,
            )

    def test_old_handoff_grant_cannot_survive_new_revision_head(self):
        state1, revision1, artifact1, _, grant1 = self._clean_current()
        self._advance_head(state1, revision1)
        with self.assertRaisesRegex(Stage8ApprovalHandoffError, "APPROVAL_HANDOFF_ELIGIBILITY_REJECTED"):
            build_human_approval_handoff_request(
                scope=self.scope,
                store=self.store,
                revision=revision1,
                state=state1,
                artifact=artifact1,
                grant=grant1,
                expected_approver_id="teacher_stage8f",
                signing_key=HANDOFF_KEY,
            )

    def test_artifact_substitution_fails_before_handoff_authority(self):
        state, revision, artifact, _, grant = self._clean_current()
        forged = CorrectedMusicXmlArtifact(
            document=artifact.document + b"\n",
            _record=artifact._record,
        )
        with self.assertRaisesRegex(Stage8ApprovalHandoffError, "APPROVAL_HANDOFF_ELIGIBILITY_REJECTED"):
            build_human_approval_handoff_request(
                scope=self.scope,
                store=self.store,
                revision=revision,
                state=state,
                artifact=forged,
                grant=grant,
                expected_approver_id="teacher_stage8f",
                signing_key=HANDOFF_KEY,
            )

    def test_handoff_request_constructor_is_sealed(self):
        with self.assertRaisesRegex(Stage8ApprovalHandoffError, "APPROVAL_HANDOFF_CONSTRUCTION_FORBIDDEN"):
            HumanApprovalHandoffRequest(MappingProxyType({}))

    def test_module_has_no_live_route_network_clock_audio_process_or_approval_record_runtime(self):
        source = (SRC / "scoremosaic_teacher_review" / "approval_handoff.py").read_text(encoding="utf-8").lower()
        for forbidden in (
            "fastapi", "flask", "django", "starlette", "aiohttp",
            "requests.", "urllib.", "http.server", "socket.", "websocket",
            "subprocess", "os.system", "midi", "soundfont", "pyaudio",
            "sounddevice", "time.sleep", "perf_counter", "monotonic(",
            "publish(", "record_approval(", "approvaldecision=\"approve\"",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
