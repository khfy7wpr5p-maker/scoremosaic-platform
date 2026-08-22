from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
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
    build_human_approval_handoff_request,
    issue_approval_handoff_grant,
)
from scoremosaic_teacher_review.approval_record import (  # noqa: E402
    HUMAN_APPROVAL_DECISION_AUTHZ_VERSION,
    HUMAN_APPROVAL_RECORD_VERSION,
    ImmutableHumanApprovalRecord,
    Stage8HumanApprovalRecordError,
    build_immutable_human_approval_record,
    issue_explicit_human_approval_decision_grant,
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

STORE_KEY = b"stage8m-durable-store-purpose-key-32bytes!!"
HANDOFF_KEY = b"stage8m-approval-handoff-purpose-key-32bytes!!"
DECISION_KEY = b"stage8m-human-decision-purpose-key-32bytes!!"
WRONG_DECISION_KEY = b"stage8m-wrong-decision-purpose-key-32bytes!!"
PROVENANCE = sha256(b"explicit-human-action-fixture-stage8m").hexdigest()


class Stage8MHumanApprovalRecordTests(unittest.TestCase):
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

    def _current_handoff(self):
        state, revision = revision_for(
            self.base,
            self.base_state,
            {"type": "set_pitch", "value": {"step": "F", "alter": q(1), "octave": 5}},
            command_id="cmd_stage8m_clean",
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
        handoff_grant = issue_approval_handoff_grant(
            request_id="handoff_stage8m_0001",
            approver_id="teacher_stage8f",
            eligibility=eligibility,
            signing_key=HANDOFF_KEY,
        )
        handoff = build_human_approval_handoff_request(
            scope=self.scope,
            store=self.store,
            revision=revision,
            state=state,
            artifact=artifact,
            grant=handoff_grant,
            expected_approver_id="teacher_stage8f",
            signing_key=HANDOFF_KEY,
        )
        decision_grant = issue_explicit_human_approval_decision_grant(
            decision_id="decision_stage8m_0001",
            handoff=handoff,
            approver_id="teacher_stage8f",
            decision="approved",
            decided_at="2026-08-22T16:32:00Z",
            decision_provenance_sha256=PROVENANCE,
            signing_key=DECISION_KEY,
        )
        return state, revision, artifact, handoff_grant, handoff, decision_grant

    def _build_record(self, *, state, revision, artifact, handoff_grant, handoff, decision_grant, decision_key=DECISION_KEY, approver="teacher_stage8f"):
        return build_immutable_human_approval_record(
            scope=self.scope,
            store=self.store,
            revision=revision,
            state=state,
            artifact=artifact,
            handoff_grant=handoff_grant,
            handoff_signing_key=HANDOFF_KEY,
            handoff=handoff,
            decision_grant=decision_grant,
            decision_signing_key=decision_key,
            expected_approver_id=approver,
        )

    def test_explicit_human_approval_builds_deterministic_record_without_publication(self):
        state, revision, artifact, handoff_grant, handoff, decision_grant = self._current_handoff()
        records = [
            self._build_record(
                state=state,
                revision=revision,
                artifact=artifact,
                handoff_grant=handoff_grant,
                handoff=handoff,
                decision_grant=decision_grant,
            )
            for _ in range(10)
        ]
        self.assertEqual(1, len({record.record_sha256 for record in records}))
        data = records[0].to_dict()
        self.assertEqual(HUMAN_APPROVAL_RECORD_VERSION, data["schemaVersion"])
        self.assertRegex(data["approvalRecordId"], r"^approval_[0-9a-f]{32}$")
        self.assertEqual("approved", data["approval"]["status"])
        self.assertTrue(data["approval"]["immutable"])
        self.assertTrue(data["approval"]["exactHumanDecision"])
        self.assertTrue(data["approval"]["freshHandoffRevalidated"])
        self.assertFalse(data["approval"]["productionPersistenceActivated"])
        self.assertEqual("explicit_human_action", data["humanDecision"]["decisionSource"])
        self.assertEqual(PROVENANCE, data["humanDecision"]["decisionProvenanceSha256"])
        self.assertEqual(handoff.request_sha256, data["handoff"]["handoffRequestSha256"])
        self.assertEqual(revision.to_dict()["revisionSha256"], data["currentHead"]["revisionSha256"])
        self.assertEqual(artifact.to_dict()["musicXmlSha256"], data["correctedArtifact"]["musicXmlSha256"])
        self.assertEqual({"eligible": False, "granted": False, "publicationRecordId": None}, data["publication"])
        self.assertTrue(data["capabilities"]["humanApprovalCaptured"])
        for key in ("canPublish", "canMutate", "canWrite", "productionPersistence", "authoritativeMusicalTruth"):
            self.assertFalse(data["capabilities"][key])

    def test_decision_grant_is_purpose_bound_and_signature_redacted(self):
        _, _, _, _, handoff, grant = self._current_handoff()
        safe = grant.safe_dict()
        self.assertEqual(HUMAN_APPROVAL_DECISION_AUTHZ_VERSION, safe["schemaVersion"])
        self.assertEqual("approved", safe["decision"])
        self.assertEqual("explicit_human_action", safe["decisionSource"])
        self.assertEqual("record_explicit_human_approval", safe["allowedAction"])
        self.assertEqual("<redacted>", safe["signature"])
        self.assertNotIn(grant.signature_hex, repr(grant))
        duplicate = issue_explicit_human_approval_decision_grant(
            decision_id="decision_stage8m_0001",
            handoff=handoff,
            approver_id="teacher_stage8f",
            decision="approved",
            decided_at="2026-08-22T16:32:00Z",
            decision_provenance_sha256=PROVENANCE,
            signing_key=DECISION_KEY,
        )
        self.assertEqual(grant.grant_sha256, duplicate.grant_sha256)
        self.assertEqual(grant.signature_hex, duplicate.signature_hex)

    def test_decision_must_be_explicit_approved_and_have_valid_human_provenance(self):
        _, _, _, _, handoff, _ = self._current_handoff()
        with self.assertRaisesRegex(Stage8HumanApprovalRecordError, "HUMAN_APPROVAL_DECISION_INVALID"):
            issue_explicit_human_approval_decision_grant(
                decision_id="decision_stage8m_reject",
                handoff=handoff,
                approver_id="teacher_stage8f",
                decision="inferred",
                decided_at="2026-08-22T16:32:00Z",
                decision_provenance_sha256=PROVENANCE,
                signing_key=DECISION_KEY,
            )
        with self.assertRaisesRegex(Stage8HumanApprovalRecordError, "HUMAN_APPROVAL_PROVENANCE_HASH_INVALID"):
            issue_explicit_human_approval_decision_grant(
                decision_id="decision_stage8m_badprov",
                handoff=handoff,
                approver_id="teacher_stage8f",
                decision="approved",
                decided_at="2026-08-22T16:32:00Z",
                decision_provenance_sha256="not-a-hash",
                signing_key=DECISION_KEY,
            )
        with self.assertRaisesRegex(Stage8HumanApprovalRecordError, "HUMAN_APPROVAL_DECIDED_AT_INVALID"):
            issue_explicit_human_approval_decision_grant(
                decision_id="decision_stage8m_badtime",
                handoff=handoff,
                approver_id="teacher_stage8f",
                decision="approved",
                decided_at="now",
                decision_provenance_sha256=PROVENANCE,
                signing_key=DECISION_KEY,
            )

    def test_wrong_approver_wrong_key_and_tampered_grant_fail_closed(self):
        state, revision, artifact, handoff_grant, handoff, decision_grant = self._current_handoff()
        # Wrong expected approver is rejected even earlier by fresh Stage 8-L
        # revalidation, before the decision grant is considered.
        with self.assertRaisesRegex(Stage8HumanApprovalRecordError, "HUMAN_APPROVAL_HANDOFF_REVALIDATION_REJECTED"):
            self._build_record(
                state=state, revision=revision, artifact=artifact, handoff_grant=handoff_grant,
                handoff=handoff, decision_grant=decision_grant, approver="other_teacher",
            )
        with self.assertRaisesRegex(Stage8HumanApprovalRecordError, "HUMAN_APPROVAL_DECISION_SIGNATURE_INVALID"):
            self._build_record(
                state=state, revision=revision, artifact=artifact, handoff_grant=handoff_grant,
                handoff=handoff, decision_grant=decision_grant, decision_key=WRONG_DECISION_KEY,
            )
        tampered = replace(decision_grant, music_xml_sha256="0" * 64)
        with self.assertRaisesRegex(Stage8HumanApprovalRecordError, "HUMAN_APPROVAL_DECISION_SCOPE_MISMATCH"):
            self._build_record(
                state=state, revision=revision, artifact=artifact, handoff_grant=handoff_grant,
                handoff=handoff, decision_grant=tampered,
            )

    def test_stale_head_is_rejected_by_fresh_stage8l_revalidation(self):
        state1, revision1, artifact1, handoff_grant1, handoff1, decision_grant1 = self._current_handoff()
        r1 = revision1.to_dict()
        target = loc("P1:M1:E2", 1)
        operation = {"type": "set_pitch", "value": {"step": "G", "alter": q(0), "octave": 4}}
        command = build_score_edit_command({
            "schemaVersion": COMMAND_VERSION,
            "commandId": "cmd_stage8m_second",
            "jobId": "job_stage8f_0001",
            "reviewerId": "teacher_stage8f",
            "authorizationDecisionId": "authz_cmd_stage8m_second",
            "reviewReportId": "report_stage8f_0001",
            "reviewReportSha256": H_REPORT,
            "baseCanonicalSha256": self.base["canonicalSha256"],
            "baseRevisionId": r1["revisionId"],
            "baseRevisionSha256": r1["revisionSha256"],
            "issueId": "issue_stage8m_second",
            "location": target,
            "operation": operation,
            "oldValueSha256": expected_old_value_sha256(state1, location=target, operation_type=operation["type"]),
            "reason": "Advance head before approval capture.",
        })
        applied = apply_score_edit_command(state1, command)
        edit_grant = issue_authorization_grant(
            decision_id="authz_cmd_stage8m_second",
            reviewer_id="teacher_stage8f",
            tenant_id="school_stage8f",
            job_id="job_stage8f_0001",
            review_report_id="report_stage8f_0001",
            review_report_sha256=H_REPORT,
            canonical_score_sha256=self.base["canonicalSha256"],
            parent_revision_id=r1["revisionId"],
            parent_revision_sha256=r1["revisionSha256"],
            allowed_actions=("revision:read", "revision:propose"),
            signing_key=AUTHZ_KEY,
        )
        revision2 = build_teacher_score_revision(
            grant=edit_grant,
            signing_key=AUTHZ_KEY,
            expected_tenant_id="school_stage8f",
            expected_job_id="job_stage8f_0001",
            expected_reviewer_id="teacher_stage8f",
            expected_review_report_id="report_stage8f_0001",
            expected_review_report_sha256=H_REPORT,
            expected_canonical_score_sha256=self.base["canonicalSha256"],
            command=command,
            current_parent_revision_id=r1["revisionId"],
            current_parent_revision_sha256=r1["revisionSha256"],
            resulting_musical_state_sha256=applied.state.state_sha256,
            validation_report_sha256=applied.validation.report_sha256,
            blocking_issue_count=applied.validation.blocking_issue_count,
            unresolved_issue_count=applied.validation.unresolved_issue_count,
            created_at="2026-08-22T16:33:00Z",
            previous_audit_event_sha256=r1["auditEventSha256"],
        )
        self._persist(revision2)
        with self.assertRaisesRegex(Stage8HumanApprovalRecordError, "HUMAN_APPROVAL_HANDOFF_REVALIDATION_REJECTED"):
            self._build_record(
                state=state1, revision=revision1, artifact=artifact1, handoff_grant=handoff_grant1,
                handoff=handoff1, decision_grant=decision_grant1,
            )

    def test_corrected_artifact_substitution_fails_before_approval_record(self):
        state, revision, artifact, handoff_grant, handoff, decision_grant = self._current_handoff()
        forged = CorrectedMusicXmlArtifact(document=artifact.document + b"\n", _record=artifact._record)
        with self.assertRaisesRegex(Stage8HumanApprovalRecordError, "HUMAN_APPROVAL_HANDOFF_REVALIDATION_REJECTED"):
            self._build_record(
                state=state, revision=revision, artifact=forged, handoff_grant=handoff_grant,
                handoff=handoff, decision_grant=decision_grant,
            )

    def test_approval_record_constructor_is_sealed(self):
        with self.assertRaisesRegex(Stage8HumanApprovalRecordError, "HUMAN_APPROVAL_RECORD_CONSTRUCTION_FORBIDDEN"):
            ImmutableHumanApprovalRecord(MappingProxyType({}))

    def test_module_has_no_route_network_storage_clock_audio_or_process_runtime(self):
        source = (SRC / "scoremosaic_teacher_review" / "approval_record.py").read_text(encoding="utf-8").lower()
        for forbidden in (
            "fastapi", "flask", "django", "starlette", "aiohttp", "requests.", "urllib.",
            "http.server", "socket.", "websocket", "subprocess", "os.system", "sqlite3", "psycopg",
            "boto3", "redis", "pyaudio", "sounddevice", "midi", "soundfont", "time.sleep",
            "datetime.now", "datetime.utcnow", "perf_counter", "monotonic(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
