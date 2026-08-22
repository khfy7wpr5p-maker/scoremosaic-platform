from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "services" / "teacher-review-service" / "src"
sys.path.insert(0, str(SRC))

from scoremosaic_teacher_review import (  # noqa: E402
    COMMAND_VERSION, DurableRevisionStore, RevisionScope,
    Stage8MaterializationError, apply_score_edit_command,
    build_score_edit_command, build_teacher_score_revision,
    canonical_payload_sha256, expected_old_value_sha256,
    issue_authorization_grant, materialize_canonical_state,
    validate_musical_state,
)

AUTHZ_KEY = b"stage8c-authz-purpose-separated-key-32bytes!!"
STORE_KEY = b"stage8c-store-purpose-separated-key-32bytes!!"
H_A, H_B, H_C = "a" * 64, "b" * 64, "c" * 64


def q(n: int, d: int = 1) -> dict[str, int]:
    return {"numerator": n, "denominator": d}


def ev(eid: str, order: int, onset: int, duration: int, *, kind="note", step="C") -> dict:
    return {
        "eventId": eid, "xmlOrder": order, "kind": kind, "onset": q(onset),
        "effectiveDuration": q(duration), "writtenDuration": q(duration),
        "writtenType": "quarter" if duration == 1 else "half", "dots": 0,
        "tuplet": None, "voice": "1", "staff": 1,
        "pitch": None if kind == "rest" else {"step": step, "alter": q(0), "octave": 4},
        "tab": None if kind == "rest" else {"string": 2, "fret": 1},
        "grace": False, "chordGroup": None, "chordIndex": None, "ties": [],
        "provenance": {"xmlPath": f"/score/part/measure/note[{order + 1}]", "sourceEventIndex": order},
    }


def fixture() -> dict:
    data = {
        "schemaVersion": "1.0",
        "source": {"engine": "audiveris", "engineVersion": "5.5", "modelVersion": None,
                   "artifactRef": "artifact://stage8c/base.musicxml", "artifactSha256": H_C},
        "rootType": "score-partwise", "movementTitle": "Stage8C",
        "parts": [{"partId": "P1", "name": "Guitar", "ordinal": 1, "measures": [{
            "measureId": "P1:M1", "number": "1", "ordinal": 1, "implicit": False,
            "divisionsAtStart": 1, "timeSignatureAtStart": {"beats": "4", "beatType": 4},
            "expectedDuration": q(4), "observedDuration": q(4), "divisionsChanges": [],
            "timeSignatureChanges": [], "timingMovements": [],
            "events": [ev("P1:M1:E1", 0, 0, 1, step="C"), ev("P1:M1:E2", 1, 1, 1, step="D"),
                       ev("P1:M1:E3", 2, 2, 2, kind="rest")],
        }]}], "diagnostics": [], "canonicalSha256": "0" * 64,
    }
    data["canonicalSha256"] = canonical_payload_sha256(data)
    return data


def scope_for(data: dict) -> RevisionScope:
    return RevisionScope.create(
        tenant_id="school_stage8c", job_id="job_stage8c_0001",
        review_report_id="report_stage8c_0001", review_report_sha256=H_A,
        base_canonical_sha256=data["canonicalSha256"],
    )


def loc(eid="P1:M1:E1", onset=0, staff=1, voice="1") -> dict:
    return {"partId": "P1", "measureId": "P1:M1", "eventId": eid,
            "staff": staff, "voice": voice, "onset": q(onset)}


def cmd(state, op: dict, *, target=None, cid="cmd_stage8c_01", aid="authz_stage8c_01",
        parent_id=None, parent_sha=None, old_hash=None):
    target = target or loc()
    old_hash = old_hash or expected_old_value_sha256(
        state, location=target, operation_type=op["type"]
    )
    return build_score_edit_command({
        "schemaVersion": COMMAND_VERSION, "commandId": cid, "jobId": "job_stage8c_0001",
        "reviewerId": "teacher_stage8c", "authorizationDecisionId": aid,
        "reviewReportId": "report_stage8c_0001", "reviewReportSha256": H_A,
        "baseCanonicalSha256": state.to_dict()["baseCanonicalSha256"],
        "baseRevisionId": parent_id, "baseRevisionSha256": parent_sha,
        "issueId": "issue_stage8c_01", "location": target, "operation": op,
        "oldValueSha256": old_hash, "reason": "Bounded deterministic correction.",
    })


def grant(canonical_sha: str, aid: str, parent_id=None, parent_sha=None):
    return issue_authorization_grant(
        decision_id=aid, reviewer_id="teacher_stage8c", tenant_id="school_stage8c",
        job_id="job_stage8c_0001", review_report_id="report_stage8c_0001",
        review_report_sha256=H_A, canonical_score_sha256=canonical_sha,
        parent_revision_id=parent_id, parent_revision_sha256=parent_sha,
        allowed_actions=("revision:read", "revision:propose"), signing_key=AUTHZ_KEY,
    )


class Stage8CMaterializationTests(unittest.TestCase):
    def setUp(self):
        self.base = fixture()
        self.scope = scope_for(self.base)
        self.state = materialize_canonical_state(self.scope, self.base)

    def test_hash_scope_determinism_and_immutability(self):
        self.assertEqual(1, len({materialize_canonical_state(self.scope, deepcopy(self.base)).state_sha256 for _ in range(10)}))
        copy = self.state.to_dict(); copy["parts"][0]["measures"][0]["events"][0]["dots"] = 8
        self.assertEqual(0, self.state.to_dict()["parts"][0]["measures"][0]["events"][0]["dots"])
        tampered = deepcopy(self.base); tampered["movementTitle"] = "tampered"
        with self.assertRaisesRegex(Stage8MaterializationError, "CANONICAL_HASH_MISMATCH"):
            materialize_canonical_state(self.scope, tampered)
        wrong = RevisionScope.create(tenant_id="school_stage8c", job_id="job_stage8c_0001",
            review_report_id="report_stage8c_0001", review_report_sha256=H_A, base_canonical_sha256=H_B)
        with self.assertRaisesRegex(Stage8MaterializationError, "CANONICAL_SCOPE_MISMATCH"):
            materialize_canonical_state(wrong, self.base)

    def test_all_allowlisted_operations_are_deterministic_and_locked(self):
        cases = [
            {"type": "set_pitch", "value": {"step": "F", "alter": q(1), "octave": 5}},
            {"type": "set_effective_duration", "value": q(2)},
            {"type": "set_written_type", "value": "eighth"},
            {"type": "set_dots", "value": 1},
            {"type": "set_staff_voice", "value": {"staff": 2, "voice": "2"}},
            {"type": "set_time_signature", "value": {"beats": "3", "beatType": 4}},
            {"type": "set_tab", "value": {"string": 3, "fret": 5}},
            {"type": "remove_event", "value": None},
        ]
        for i, op in enumerate(cases, 1):
            with self.subTest(op=op["type"]):
                command = cmd(self.state, op, cid=f"cmd_stage8c_{i:02d}", aid=f"authz_stage8c_{i:02d}")
                results = [apply_score_edit_command(self.state, command) for _ in range(10)]
                self.assertEqual(1, len({r.state.state_sha256 for r in results}))
                self.assertEqual(1, len({r.validation.report_sha256 for r in results}))
                report = results[0].validation.to_dict()
                self.assertFalse(report["authoritativeCorrection"])
                self.assertFalse(report["approvalEligible"])
                self.assertFalse(report["publicationEligible"])

    def test_old_value_location_and_value_domains_fail_closed(self):
        stale = cmd(self.state, {"type": "set_dots", "value": 1}, old_hash="f" * 64)
        with self.assertRaisesRegex(Stage8MaterializationError, "EDIT_OLD_VALUE_PRECONDITION_FAILED"):
            apply_score_edit_command(self.state, stale)
        original = cmd(self.state, {"type": "set_dots", "value": 1})
        forged = original.to_dict(); forged["location"] = loc(onset=1); forged.pop("commandSha256")
        with self.assertRaisesRegex(Stage8MaterializationError, "EDIT_TARGET_LOCATION_STALE"):
            apply_score_edit_command(self.state, build_score_edit_command(forged))
        rest = loc("P1:M1:E3", onset=2)
        for op, code in [
            ({"type": "set_pitch", "value": {"step": "C", "alter": q(0), "octave": 4}}, "EDIT_PITCH_REQUIRES_NOTE"),
            ({"type": "set_tab", "value": {"string": 1, "fret": 0}}, "EDIT_TAB_REQUIRES_NOTE"),
        ]:
            with self.assertRaisesRegex(Stage8MaterializationError, code):
                apply_score_edit_command(self.state, cmd(self.state, op, target=rest))
        with self.assertRaisesRegex(Stage8MaterializationError, "EDIT_DURATION_INVALID"):
            apply_score_edit_command(self.state, cmd(self.state, {"type": "set_effective_duration", "value": q(0)}))

    def test_mid_measure_meter_change_is_not_rewritten(self):
        data = deepcopy(self.base)
        data["parts"][0]["measures"][0]["timeSignatureChanges"] = [
            {"xmlOrder": 1, "onset": q(2), "timeSignature": {"beats": "3", "beatType": 4}}
        ]
        data["canonicalSha256"] = canonical_payload_sha256(data)
        state = materialize_canonical_state(scope_for(data), data)
        with self.assertRaisesRegex(Stage8MaterializationError, "EDIT_MID_MEASURE_TIME_SIGNATURE_UNSUPPORTED"):
            apply_score_edit_command(state, cmd(state, {"type": "set_time_signature", "value": {"beats": "2", "beatType": 4}}))

    def test_validator_reports_without_auto_correction(self):
        overflow = apply_score_edit_command(self.state, cmd(self.state, {"type": "set_effective_duration", "value": q(5)}))
        report = overflow.validation.to_dict()
        self.assertIn("MEASURE_OVERFLOW", {i["code"] for i in report["issues"]})
        self.assertGreater(report["blockingIssueCount"], 0)
        self.assertEqual(q(5), overflow.state.to_dict()["parts"][0]["measures"][0]["events"][0]["effectiveDuration"])
        data = deepcopy(self.base); data["parts"][0]["measures"][0]["events"][1]["onset"] = q(0)
        data["canonicalSha256"] = canonical_payload_sha256(data)
        state = materialize_canonical_state(scope_for(data), data)
        self.assertIn("VOICE_OVERLAP", {i["code"] for i in validate_musical_state(state).to_dict()["issues"]})

    def test_chord_alignment_is_blocking(self):
        data = deepcopy(self.base); events = data["parts"][0]["measures"][0]["events"]
        for index in (0, 1): events[index]["chordGroup"], events[index]["chordIndex"] = "chord_1", index
        data["canonicalSha256"] = canonical_payload_sha256(data)
        state = materialize_canonical_state(scope_for(data), data)
        self.assertIn("CHORD_ALIGNMENT_INVALID", {i["code"] for i in validate_musical_state(state).to_dict()["issues"]})

    def test_extra_and_excessive_inputs_fail_closed(self):
        extra = deepcopy(self.base); extra["parts"][0]["measures"][0]["events"][0]["rendererMutation"] = "x"
        extra["canonicalSha256"] = canonical_payload_sha256(extra)
        with self.assertRaisesRegex(Stage8MaterializationError, "CANONICAL_EVENT_INVALID"):
            materialize_canonical_state(scope_for(extra), extra)
        huge = deepcopy(self.base); huge["diagnostics"] = ["x"] * 500_001
        with self.assertRaisesRegex(Stage8MaterializationError, "CANONICAL_INPUT_TOO_COMPLEX"):
            canonical_payload_sha256(huge)

    def test_two_revision_chain_integrates_with_durable_store(self):
        with tempfile.TemporaryDirectory() as temp:
            store = DurableRevisionStore(Path(temp) / "store", signing_key=STORE_KEY)
            c1 = cmd(self.state, {"type": "set_dots", "value": 1}, cid="cmd_chain_01", aid="authz_chain_01")
            a1 = apply_score_edit_command(self.state, c1)
            r1 = build_teacher_score_revision(
                grant=grant(self.base["canonicalSha256"], "authz_chain_01"), signing_key=AUTHZ_KEY,
                expected_tenant_id="school_stage8c", expected_job_id="job_stage8c_0001",
                expected_reviewer_id="teacher_stage8c", expected_review_report_id="report_stage8c_0001",
                expected_review_report_sha256=H_A, expected_canonical_score_sha256=self.base["canonicalSha256"],
                command=c1, current_parent_revision_id=None, current_parent_revision_sha256=None,
                resulting_musical_state_sha256=a1.state.state_sha256,
                validation_report_sha256=a1.validation.report_sha256,
                blocking_issue_count=a1.validation.blocking_issue_count,
                unresolved_issue_count=a1.validation.unresolved_issue_count,
                created_at="2026-08-22T06:00:01Z", previous_audit_event_sha256=None)
            store.append_revision(self.scope, r1, expected_parent_revision_id=None, expected_parent_revision_sha256=None)
            pid, psha = r1.record["revisionId"], r1.record["revisionSha256"]
            c2 = cmd(a1.state, {"type": "set_pitch", "value": {"step": "G", "alter": q(0), "octave": 4}},
                     cid="cmd_chain_02", aid="authz_chain_02", parent_id=pid, parent_sha=psha)
            a2 = apply_score_edit_command(a1.state, c2)
            r2 = build_teacher_score_revision(
                grant=grant(self.base["canonicalSha256"], "authz_chain_02", pid, psha), signing_key=AUTHZ_KEY,
                expected_tenant_id="school_stage8c", expected_job_id="job_stage8c_0001",
                expected_reviewer_id="teacher_stage8c", expected_review_report_id="report_stage8c_0001",
                expected_review_report_sha256=H_A, expected_canonical_score_sha256=self.base["canonicalSha256"],
                command=c2, current_parent_revision_id=pid, current_parent_revision_sha256=psha,
                resulting_musical_state_sha256=a2.state.state_sha256,
                validation_report_sha256=a2.validation.report_sha256,
                blocking_issue_count=a2.validation.blocking_issue_count,
                unresolved_issue_count=a2.validation.unresolved_issue_count,
                created_at="2026-08-22T06:00:02Z", previous_audit_event_sha256=r1.record["auditEventSha256"])
            store.append_revision(self.scope, r2, expected_parent_revision_id=pid, expected_parent_revision_sha256=psha)
            history = DurableRevisionStore(Path(temp) / "store", signing_key=STORE_KEY).load_history(self.scope)
            self.assertEqual(2, len(history))
            self.assertEqual(a2.state.state_sha256, history[-1]["resultingMusicalStateSha256"])
            self.assertEqual(a2.validation.report_sha256, history[-1]["validationReportSha256"])


if __name__ == "__main__": unittest.main()
