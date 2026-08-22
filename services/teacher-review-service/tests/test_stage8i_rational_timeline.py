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
    COMMAND_VERSION,
    DurableRevisionStore,
    RevisionScope,
    apply_score_edit_command,
    build_score_edit_command,
    build_teacher_score_revision,
    canonical_payload_sha256,
    expected_old_value_sha256,
    issue_authorization_grant,
    materialize_canonical_state,
)
from scoremosaic_teacher_review.review_timeline import (  # noqa: E402
    Stage8TimelineError,
    build_review_timeline_projection,
)

AUTHZ_KEY = b"stage8i-authz-purpose-separated-key-32bytes!!"
STORE_KEY = b"stage8i-store-purpose-separated-key-32bytes!!"
H_A, H_C = "a" * 64, "c" * 64


def q(n: int, d: int = 1) -> dict[str, int]:
    return {"numerator": n, "denominator": d}


def ev(eid: str, order: int, onset: dict, duration: dict, *, step="C", chord_group=None, chord_index=None) -> dict:
    return {
        "eventId": eid,
        "xmlOrder": order,
        "kind": "note",
        "onset": onset,
        "effectiveDuration": duration,
        "writtenDuration": duration,
        "writtenType": "quarter",
        "dots": 0,
        "tuplet": None,
        "voice": "1",
        "staff": 1,
        "pitch": {"step": step, "alter": q(0), "octave": 4},
        "tab": {"string": 2, "fret": 1},
        "grace": False,
        "chordGroup": chord_group,
        "chordIndex": chord_index,
        "ties": [],
        "provenance": {"xmlPath": f"/score/part/measure/note[{order + 1}]", "sourceEventIndex": order},
    }


def fixture() -> dict:
    data = {
        "schemaVersion": "1.0",
        "source": {
            "engine": "audiveris",
            "engineVersion": "5.5",
            "modelVersion": None,
            "artifactRef": "artifact://stage8i/base.musicxml",
            "artifactSha256": H_C,
        },
        "rootType": "score-partwise",
        "movementTitle": "Stage8I",
        "parts": [{
            "partId": "P1",
            "name": "Guitar",
            "ordinal": 1,
            "measures": [{
                "measureId": "P1:M1",
                "number": "1",
                "ordinal": 1,
                "implicit": False,
                "divisionsAtStart": 1,
                "timeSignatureAtStart": {"beats": "4", "beatType": 4},
                "expectedDuration": q(4),
                "observedDuration": q(4),
                "divisionsChanges": [],
                "timeSignatureChanges": [],
                "timingMovements": [],
                "events": [
                    ev("P1:M1:E1", 0, q(0), q(1), step="C"),
                    ev("P1:M1:E2", 1, q(1), q(1), step="D"),
                    ev("P1:M1:E3", 2, q(2), q(2), step="E"),
                ],
            }],
        }],
        "diagnostics": [],
        "canonicalSha256": "0" * 64,
    }
    data["canonicalSha256"] = canonical_payload_sha256(data)
    return data


def scope_for(data: dict, *, tenant="school_stage8i") -> RevisionScope:
    return RevisionScope.create(
        tenant_id=tenant,
        job_id="job_stage8i_0001",
        review_report_id="report_stage8i_0001",
        review_report_sha256=H_A,
        base_canonical_sha256=data["canonicalSha256"],
    )


def grant(canonical_sha: str, *, aid="authz_stage8i_read", tenant="school_stage8i", parent_id=None, parent_sha=None):
    return issue_authorization_grant(
        decision_id=aid,
        reviewer_id="teacher_stage8i",
        tenant_id=tenant,
        job_id="job_stage8i_0001",
        review_report_id="report_stage8i_0001",
        review_report_sha256=H_A,
        canonical_score_sha256=canonical_sha,
        parent_revision_id=parent_id,
        parent_revision_sha256=parent_sha,
        allowed_actions=("revision:read", "revision:propose"),
        signing_key=AUTHZ_KEY,
    )


def edit_command(state, *, aid="authz_stage8i_write", parent_id=None, parent_sha=None):
    location = {
        "partId": "P1",
        "measureId": "P1:M1",
        "eventId": "P1:M1:E1",
        "staff": 1,
        "voice": "1",
        "onset": q(0),
    }
    operation = {"type": "set_dots", "value": 1}
    return build_score_edit_command({
        "schemaVersion": COMMAND_VERSION,
        "commandId": "cmd_stage8i_01",
        "jobId": "job_stage8i_0001",
        "reviewerId": "teacher_stage8i",
        "authorizationDecisionId": aid,
        "reviewReportId": "report_stage8i_0001",
        "reviewReportSha256": H_A,
        "baseCanonicalSha256": state.to_dict()["baseCanonicalSha256"],
        "baseRevisionId": parent_id,
        "baseRevisionSha256": parent_sha,
        "issueId": "issue_stage8i_01",
        "location": location,
        "operation": operation,
        "oldValueSha256": expected_old_value_sha256(state, location=location, operation_type="set_dots"),
        "reason": "Timeline revision fixture.",
    })


class Stage8IRationalTimelineTests(unittest.TestCase):
    def setUp(self):
        self.base = fixture()
        self.scope = scope_for(self.base)
        self.state = materialize_canonical_state(self.scope, self.base)

    def _build(self, store, *, state=None, auth=None, base=None):
        return build_review_timeline_projection(
            grant=auth or grant(self.base["canonicalSha256"]),
            signing_key=AUTHZ_KEY,
            expected_reviewer_id="teacher_stage8i",
            scope=self.scope,
            store=store,
            state=self.state if state is None else state,
            base_canonical_payload=self.base if base is None else base,
        )

    def test_base_timeline_is_deterministic_exact_and_read_only(self):
        with tempfile.TemporaryDirectory() as temp:
            store = DurableRevisionStore(Path(temp) / "store", signing_key=STORE_KEY)
            outputs = [self._build(store).to_dict() for _ in range(5)]
            self.assertEqual(1, len({item["timelineSha256"] for item in outputs}))
            result = outputs[0]
            self.assertEqual("base", result["snapshot"]["kind"])
            self.assertEqual(self.state.state_sha256, result["snapshot"]["stateSha256"])
            self.assertEqual(
                {
                    "readOnly": True,
                    "cursorNavigation": True,
                    "canSeek": True,
                    "canLoop": False,
                    "canPlay": False,
                    "canMutate": False,
                    "canApprove": False,
                    "canPublish": False,
                    "authoritativeTruth": False,
                },
                result["capabilities"],
            )
            self.assertEqual(q(0), result["parts"][0]["measures"][0]["loopBounds"]["start"])
            self.assertFalse(result["parts"][0]["measures"][0]["loopBounds"]["playbackAuthority"])

    def test_beat_mapping_uses_exact_rationals_without_floats(self):
        with tempfile.TemporaryDirectory() as temp:
            store = DurableRevisionStore(Path(temp) / "store", signing_key=STORE_KEY)
            result = self._build(store).to_dict()
            events = result["parts"][0]["measures"][0]["events"]
            self.assertEqual([1, 2, 3], [event["beat"]["beatIndex"] for event in events])
            self.assertEqual([q(0), q(0), q(0)], [event["beat"]["offsetWithinBeat"] for event in events])
            self.assertTrue(all(event["beat"]["insideDeclaredMeter"] for event in events))

            def assert_no_float(value):
                self.assertNotIsInstance(value, float)
                if isinstance(value, dict):
                    for child in value.values():
                        assert_no_float(child)
                elif isinstance(value, list):
                    for child in value:
                        assert_no_float(child)

            assert_no_float(result)

    def test_additive_meter_and_fractional_beat_offsets_are_exact(self):
        data = deepcopy(self.base)
        measure = data["parts"][0]["measures"][0]
        measure["timeSignatureAtStart"] = {"beats": "3+2", "beatType": 8}
        measure["expectedDuration"] = q(5, 2)
        measure["observedDuration"] = q(5, 2)
        events = measure["events"]
        events[0]["onset"], events[0]["effectiveDuration"] = q(0), q(1, 2)
        events[1]["onset"], events[1]["effectiveDuration"] = q(3, 4), q(1, 2)
        events[2]["onset"], events[2]["effectiveDuration"] = q(2), q(1, 2)
        for event in events:
            event["writtenDuration"] = event["effectiveDuration"]
        data["canonicalSha256"] = canonical_payload_sha256(data)
        scope = scope_for(data)
        state = materialize_canonical_state(scope, data)
        with tempfile.TemporaryDirectory() as temp:
            store = DurableRevisionStore(Path(temp) / "store", signing_key=STORE_KEY)
            result = build_review_timeline_projection(
                grant=grant(data["canonicalSha256"]), signing_key=AUTHZ_KEY,
                expected_reviewer_id="teacher_stage8i", scope=scope, store=store,
                state=state, base_canonical_payload=data,
            ).to_dict()
        projected = result["parts"][0]["measures"][0]["events"]
        self.assertEqual(q(1, 2), projected[0]["beat"]["beatUnit"])
        self.assertEqual(2, projected[1]["beat"]["beatIndex"])
        self.assertEqual(q(1, 4), projected[1]["beat"]["offsetWithinBeat"])
        self.assertEqual(5, projected[2]["beat"]["beatIndex"])

    def test_simultaneous_events_share_one_deterministic_group(self):
        data = deepcopy(self.base)
        events = data["parts"][0]["measures"][0]["events"]
        events[0]["chordGroup"], events[0]["chordIndex"] = "chord_a", 0
        events[1]["onset"] = q(0)
        events[1]["chordGroup"], events[1]["chordIndex"] = "chord_a", 1
        data["canonicalSha256"] = canonical_payload_sha256(data)
        scope = scope_for(data)
        state = materialize_canonical_state(scope, data)
        with tempfile.TemporaryDirectory() as temp:
            store = DurableRevisionStore(Path(temp) / "store", signing_key=STORE_KEY)
            result = build_review_timeline_projection(
                grant=grant(data["canonicalSha256"]), signing_key=AUTHZ_KEY,
                expected_reviewer_id="teacher_stage8i", scope=scope, store=store,
                state=state, base_canonical_payload=data,
            ).to_dict()
        first, second = result["parts"][0]["measures"][0]["events"][:2]
        self.assertEqual(first["simultaneityId"], second["simultaneityId"])
        self.assertEqual(["P1:M1:E1", "P1:M1:E2"], first["simultaneousEventIds"])
        self.assertEqual(first["simultaneousEventIds"], second["simultaneousEventIds"])

    def test_overflow_is_visible_and_never_grants_playback_or_loop_authority(self):
        data = deepcopy(self.base)
        data["parts"][0]["measures"][0]["events"][0]["effectiveDuration"] = q(5)
        data["canonicalSha256"] = canonical_payload_sha256(data)
        scope = scope_for(data)
        state = materialize_canonical_state(scope, data)
        with tempfile.TemporaryDirectory() as temp:
            store = DurableRevisionStore(Path(temp) / "store", signing_key=STORE_KEY)
            result = build_review_timeline_projection(
                grant=grant(data["canonicalSha256"]), signing_key=AUTHZ_KEY,
                expected_reviewer_id="teacher_stage8i", scope=scope, store=store,
                state=state, base_canonical_payload=data,
            ).to_dict()
        measure = result["parts"][0]["measures"][0]
        self.assertGreater(result["validation"]["blockingIssueCount"], 0)
        self.assertFalse(measure["loopBounds"]["safeWithinExpectedDuration"])
        self.assertFalse(measure["loopBounds"]["playbackAuthority"])
        self.assertFalse(result["capabilities"]["canPlay"])
        self.assertFalse(result["capabilities"]["canLoop"])

    def test_cross_tenant_authorization_fails_before_state_processing(self):
        with tempfile.TemporaryDirectory() as temp:
            store = DurableRevisionStore(Path(temp) / "store", signing_key=STORE_KEY)
            wrong = grant(self.base["canonicalSha256"], tenant="school_other")
            with self.assertRaisesRegex(Stage8TimelineError, "TIMELINE_AUTHORIZATION_DENIED"):
                self._build(store, state="not-a-state", auth=wrong, base={"hostile": object()})

    def test_current_head_revision_is_required_and_exactly_bound(self):
        with tempfile.TemporaryDirectory() as temp:
            store = DurableRevisionStore(Path(temp) / "store", signing_key=STORE_KEY)
            write_auth = grant(self.base["canonicalSha256"], aid="authz_stage8i_write")
            command = edit_command(self.state)
            applied = apply_score_edit_command(self.state, command)
            revision = build_teacher_score_revision(
                grant=write_auth, signing_key=AUTHZ_KEY,
                expected_tenant_id="school_stage8i", expected_job_id="job_stage8i_0001",
                expected_reviewer_id="teacher_stage8i", expected_review_report_id="report_stage8i_0001",
                expected_review_report_sha256=H_A, expected_canonical_score_sha256=self.base["canonicalSha256"],
                command=command, current_parent_revision_id=None, current_parent_revision_sha256=None,
                resulting_musical_state_sha256=applied.state.state_sha256,
                validation_report_sha256=applied.validation.report_sha256,
                blocking_issue_count=applied.validation.blocking_issue_count,
                unresolved_issue_count=applied.validation.unresolved_issue_count,
                created_at="2026-08-22T13:10:00Z", previous_audit_event_sha256=None,
            )
            store.append_revision(self.scope, revision, expected_parent_revision_id=None, expected_parent_revision_sha256=None)
            record = revision.to_dict()
            read_auth = grant(
                self.base["canonicalSha256"], aid="authz_stage8i_current",
                parent_id=record["revisionId"], parent_sha=record["revisionSha256"],
            )
            result = self._build(store, state=applied.state, auth=read_auth).to_dict()
            self.assertEqual("revision", result["snapshot"]["kind"])
            self.assertEqual(record["revisionId"], result["snapshot"]["revisionId"])
            self.assertEqual(record["revisionSha256"], result["snapshot"]["revisionSha256"])
            self.assertEqual(applied.state.state_sha256, result["snapshot"]["stateSha256"])

            with self.assertRaisesRegex(Stage8TimelineError, "TIMELINE_STATE_MISMATCH"):
                self._build(store, state=self.state, auth=read_auth)

    def test_stale_read_grant_is_rejected_before_state_processing(self):
        with tempfile.TemporaryDirectory() as temp:
            store = DurableRevisionStore(Path(temp) / "store", signing_key=STORE_KEY)
            old_read = grant(self.base["canonicalSha256"])
            write_auth = grant(self.base["canonicalSha256"], aid="authz_stage8i_write")
            command = edit_command(self.state)
            applied = apply_score_edit_command(self.state, command)
            revision = build_teacher_score_revision(
                grant=write_auth, signing_key=AUTHZ_KEY,
                expected_tenant_id="school_stage8i", expected_job_id="job_stage8i_0001",
                expected_reviewer_id="teacher_stage8i", expected_review_report_id="report_stage8i_0001",
                expected_review_report_sha256=H_A, expected_canonical_score_sha256=self.base["canonicalSha256"],
                command=command, current_parent_revision_id=None, current_parent_revision_sha256=None,
                resulting_musical_state_sha256=applied.state.state_sha256,
                validation_report_sha256=applied.validation.report_sha256,
                blocking_issue_count=applied.validation.blocking_issue_count,
                unresolved_issue_count=applied.validation.unresolved_issue_count,
                created_at="2026-08-22T13:10:01Z", previous_audit_event_sha256=None,
            )
            store.append_revision(self.scope, revision, expected_parent_revision_id=None, expected_parent_revision_sha256=None)
            with self.assertRaisesRegex(Stage8TimelineError, "TIMELINE_STALE_SNAPSHOT"):
                self._build(store, state="hostile", auth=old_read, base={"hostile": object()})

    def test_projection_minimizes_musical_data_for_cursor_only(self):
        with tempfile.TemporaryDirectory() as temp:
            store = DurableRevisionStore(Path(temp) / "store", signing_key=STORE_KEY)
            result = self._build(store).to_dict()
        banned = {"pitch", "tab", "provenance", "xmlPath", "sourceEventIndex", "artifactRef", "artifactSha256"}

        def walk(value):
            if isinstance(value, dict):
                self.assertTrue(banned.isdisjoint(value))
                for item in value.values():
                    walk(item)
            elif isinstance(value, list):
                for item in value:
                    walk(item)

        walk(result)


if __name__ == "__main__":
    unittest.main()
