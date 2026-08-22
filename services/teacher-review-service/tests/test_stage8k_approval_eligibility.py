from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import MappingProxyType
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
    issue_authorization_grant,
    materialize_canonical_state,
)
from scoremosaic_teacher_review.approval_eligibility import (  # noqa: E402
    APPROVAL_ELIGIBILITY_VERSION,
    ApprovalEligibilityEvidence,
    Stage8ApprovalEligibilityError,
    build_approval_eligibility_evidence,
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

STORE_KEY = b"stage8k-durable-store-purpose-key-32bytes!!"


class Stage8KApprovalEligibilityTests(unittest.TestCase):
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
            command_id="cmd_stage8k_clean",
        )
        self._persist(revision)
        artifact = build_corrected_musicxml_artifact(
            scope=self.scope,
            revision=revision,
            state=state,
        )
        return state, revision, artifact

    def test_exact_current_clean_revision_is_candidate_eligible_but_has_no_authority(self):
        state, revision, artifact = self._clean_current()
        evidences = [
            build_approval_eligibility_evidence(
                scope=self.scope,
                store=self.store,
                revision=revision,
                state=state,
                artifact=artifact,
            )
            for _ in range(10)
        ]
        self.assertEqual(1, len({item.evidence_sha256 for item in evidences}))
        data = evidences[0].to_dict()
        self.assertEqual(APPROVAL_ELIGIBILITY_VERSION, data["schemaVersion"])
        self.assertTrue(data["eligibility"]["candidateEligible"])
        self.assertEqual([], data["eligibility"]["reasons"])
        self.assertEqual(1, data["currentHead"]["sequence"])
        self.assertEqual(revision.to_dict()["revisionSha256"], data["currentHead"]["revisionSha256"])
        self.assertEqual(artifact.to_dict()["musicXmlSha256"], data["correctedArtifact"]["musicXmlSha256"])
        self.assertTrue(all(data["checks"].values()))
        self.assertTrue(all(value is False for value in data["authority"].values()))
        self.assertFalse(artifact.to_dict()["approvalEligible"])
        self.assertFalse(artifact.to_dict()["publicationEligible"])

    def test_validation_issues_produce_ineligible_evidence_without_granting_authority(self):
        state, revision = revision_for(
            self.base,
            self.base_state,
            {"type": "remove_event", "value": None},
            target=loc("P1:M1:E2", 1),
            command_id="cmd_stage8k_underfill",
        )
        record = revision.to_dict()
        self.assertGreater(record["blockingIssueCount"] + record["unresolvedIssueCount"], 0)
        self._persist(revision)
        artifact = build_corrected_musicxml_artifact(scope=self.scope, revision=revision, state=state)
        data = build_approval_eligibility_evidence(
            scope=self.scope,
            store=self.store,
            revision=revision,
            state=state,
            artifact=artifact,
        ).to_dict()
        self.assertFalse(data["eligibility"]["candidateEligible"])
        expected = []
        if record["blockingIssueCount"]:
            expected.append("BLOCKING_ISSUES_PRESENT")
        if record["unresolvedIssueCount"]:
            expected.append("UNRESOLVED_ISSUES_PRESENT")
        self.assertEqual(expected, data["eligibility"]["reasons"])
        self.assertTrue(all(value is False for value in data["authority"].values()))

    def test_historical_revision_is_rejected_after_new_exact_head_is_appended(self):
        state1, revision1, artifact1 = self._clean_current()
        revision1_record = revision1.to_dict()
        target = loc("P1:M1:E2", 1)
        operation = {"type": "set_pitch", "value": {"step": "G", "alter": q(0), "octave": 4}}
        command = build_score_edit_command(
            {
                "schemaVersion": COMMAND_VERSION,
                "commandId": "cmd_stage8k_second",
                "jobId": "job_stage8f_0001",
                "reviewerId": "teacher_stage8f",
                "authorizationDecisionId": "authz_cmd_stage8k_second",
                "reviewReportId": "report_stage8f_0001",
                "reviewReportSha256": H_REPORT,
                "baseCanonicalSha256": self.base["canonicalSha256"],
                "baseRevisionId": revision1_record["revisionId"],
                "baseRevisionSha256": revision1_record["revisionSha256"],
                "issueId": "issue_stage8k_second",
                "location": target,
                "operation": operation,
                "oldValueSha256": expected_old_value_sha256(
                    state1,
                    location=target,
                    operation_type=operation["type"],
                ),
                "reason": "Advance head for stale eligibility regression.",
            }
        )
        applied = apply_score_edit_command(state1, command)
        grant = issue_authorization_grant(
            decision_id="authz_cmd_stage8k_second",
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
            created_at="2026-08-22T14:30:00Z",
            previous_audit_event_sha256=revision1_record["auditEventSha256"],
        )
        self._persist(revision2)

        with self.assertRaisesRegex(
            Stage8ApprovalEligibilityError,
            "APPROVAL_ELIGIBILITY_STALE_REVISION",
        ):
            build_approval_eligibility_evidence(
                scope=self.scope,
                store=self.store,
                revision=revision1,
                state=state1,
                artifact=artifact1,
            )

    def test_artifact_document_and_record_substitution_fail_closed(self):
        state, revision, artifact = self._clean_current()
        forged_document = CorrectedMusicXmlArtifact(
            document=artifact.document + b"\n",
            _record=artifact._record,
        )
        with self.assertRaisesRegex(
            Stage8ApprovalEligibilityError,
            "APPROVAL_ELIGIBILITY_ARTIFACT_DOCUMENT_MISMATCH",
        ):
            build_approval_eligibility_evidence(
                scope=self.scope,
                store=self.store,
                revision=revision,
                state=state,
                artifact=forged_document,
            )

        record = artifact.to_dict()
        record.pop("artifactRecordSha256")
        record["musicXmlSha256"] = "0" * 64
        forged_record = CorrectedMusicXmlArtifact(
            document=artifact.document,
            _record=MappingProxyType(record),
        )
        with self.assertRaisesRegex(
            Stage8ApprovalEligibilityError,
            "APPROVAL_ELIGIBILITY_ARTIFACT_RECORD_MISMATCH",
        ):
            build_approval_eligibility_evidence(
                scope=self.scope,
                store=self.store,
                revision=revision,
                state=state,
                artifact=forged_record,
            )

    def test_evidence_constructor_is_sealed(self):
        with self.assertRaisesRegex(
            Stage8ApprovalEligibilityError,
            "APPROVAL_ELIGIBILITY_CONSTRUCTION_FORBIDDEN",
        ):
            ApprovalEligibilityEvidence(MappingProxyType({}))

    def test_module_has_no_route_network_clock_audio_or_process_runtime(self):
        source = (
            SRC / "scoremosaic_teacher_review" / "approval_eligibility.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            "fastapi", "flask", "django", "starlette", "aiohttp",
            "requests.", "urllib.", "http.server", "socket.", "websocket",
            "subprocess", "os.system", "midi", "soundfont", "pyaudio",
            "sounddevice", "time.sleep", "perf_counter", "monotonic(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
