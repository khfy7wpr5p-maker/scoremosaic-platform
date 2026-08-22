from __future__ import annotations

from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[3]
TEACHER_SRC = ROOT / "services" / "teacher-review-service" / "src"
ENSEMBLE_SRC = ROOT / "services" / "ensemble-service" / "src"
sys.path.insert(0, str(TEACHER_SRC))
sys.path.insert(0, str(ENSEMBLE_SRC))

from scoremosaic_ensemble.musicxml import normalize_musicxml  # noqa: E402
from scoremosaic_teacher_review import (  # noqa: E402
    Stage8ContractError,
    build_score_edit_command,
    build_teacher_score_revision,
    issue_authorization_grant,
)
from scoremosaic_teacher_review._materialization import (  # noqa: E402
    canonical_base_state,
    materialize_score_edit,
    musical_value_sha256,
)
from scoremosaic_teacher_review._revision_store import SqliteRevisionStore  # noqa: E402


KEY = b"stage8-runtime-purpose-separated-test-key!!"
REPORT_SHA = "a" * 64
FIXTURE = ROOT / "services" / "ensemble-service" / "tests" / "fixtures" / "canonical-smoke.musicxml"


def base_score():
    return normalize_musicxml(
        FIXTURE.read_bytes(),
        engine="homr",
        engine_version="0.7.0",
        model_version="fixture-model",
        artifact_ref="candidates/homr/original.musicxml",
    ).as_dict()


def first_event(score):
    return score["parts"][0]["measures"][0]["events"][0]


def location_for(event):
    return {
        "partId": "P1",
        "measureId": "P1:M1",
        "eventId": event["eventId"],
        "staff": event["staff"],
        "voice": event["voice"],
        "onset": event["onset"],
    }


def command_for(state, *, command_id, operation, old_value, event=None, old_hash=None):
    score = state.score_dict()
    event = first_event(score) if event is None else event
    return build_score_edit_command(
        {
            "schemaVersion": "scoremosaic-score-edit-command-v1",
            "commandId": command_id,
            "jobId": "job_stage8_runtime_0001",
            "reviewerId": "teacher_001",
            "authorizationDecisionId": f"authz_{command_id}",
            "reviewReportId": "report_stage8_runtime_0001",
            "reviewReportSha256": REPORT_SHA,
            "baseCanonicalSha256": state.base_canonical_sha256,
            "baseRevisionId": state.current_revision_id,
            "baseRevisionSha256": state.current_revision_sha256,
            "issueId": "issue_stage8_runtime_01",
            "location": location_for(event),
            "operation": operation,
            "oldValueSha256": old_hash or musical_value_sha256(old_value),
            "reason": "Bounded teacher correction from immutable source evidence.",
        }
    )


def grant_for(state, command):
    return issue_authorization_grant(
        decision_id=command.authorization_decision_id,
        reviewer_id="teacher_001",
        tenant_id="school_001",
        job_id="job_stage8_runtime_0001",
        review_report_id="report_stage8_runtime_0001",
        review_report_sha256=REPORT_SHA,
        canonical_score_sha256=state.base_canonical_sha256,
        parent_revision_id=state.current_revision_id,
        parent_revision_sha256=state.current_revision_sha256,
        allowed_actions=("revision:read", "revision:propose"),
        signing_key=KEY,
    )


def revision_for(state, command, materialized, *, created_at, previous_audit):
    return build_teacher_score_revision(
        grant=grant_for(state, command),
        signing_key=KEY,
        expected_tenant_id="school_001",
        expected_job_id="job_stage8_runtime_0001",
        expected_reviewer_id="teacher_001",
        expected_review_report_id="report_stage8_runtime_0001",
        expected_review_report_sha256=REPORT_SHA,
        expected_canonical_score_sha256=state.base_canonical_sha256,
        command=command,
        current_parent_revision_id=state.current_revision_id,
        current_parent_revision_sha256=state.current_revision_sha256,
        resulting_musical_state_sha256=materialized.musical_state_sha256,
        validation_report_sha256=materialized.validation.report_sha256,
        blocking_issue_count=materialized.validation.blocking_issue_count,
        unresolved_issue_count=materialized.validation.unresolved_issue_count,
        created_at=created_at,
        previous_audit_event_sha256=previous_audit,
    )


def pitch_command(state, *, command_id, step):
    event = first_event(state.score_dict())
    return command_for(
        state,
        command_id=command_id,
        operation={
            "type": "set_pitch",
            "value": {
                "step": step,
                "alter": {"numerator": 0, "denominator": 1},
                "octave": event["pitch"]["octave"],
            },
        },
        old_value=event["pitch"],
        event=event,
    )


class Stage8MaterializationTests(unittest.TestCase):
    def setUp(self):
        self.canonical = base_score()
        self.state = canonical_base_state(self.canonical)

    def test_base_is_verified_and_never_mutated_in_place(self):
        original_pitch = first_event(self.canonical)["pitch"].copy()
        command = pitch_command(self.state, command_id="cmd_stage8_runtime_0001", step="D")
        left = materialize_score_edit(self.state, command)
        right = materialize_score_edit(self.state, command)

        self.assertEqual(left.musical_state_sha256, right.musical_state_sha256)
        self.assertEqual(left.validation.to_dict(), right.validation.to_dict())
        self.assertEqual(original_pitch, first_event(self.canonical)["pitch"])
        self.assertEqual("D", first_event(left.score_dict())["pitch"]["step"])
        self.assertNotEqual(self.state.musical_state_sha256, left.musical_state_sha256)

    def test_old_value_precondition_is_semantic_and_fail_closed(self):
        command = command_for(
            self.state,
            command_id="cmd_stage8_runtime_0002",
            operation={"type": "set_dots", "value": 1},
            old_value=first_event(self.state.score_dict())["dots"],
            old_hash="0" * 64,
        )
        with self.assertRaisesRegex(Stage8ContractError, "MATERIALIZATION_OLD_VALUE_MISMATCH"):
            materialize_score_edit(self.state, command)

    def test_parent_identity_is_rechecked_at_materialization_boundary(self):
        command = pitch_command(self.state, command_id="cmd_stage8_runtime_0003", step="E")
        forged_state = type(self.state)(
            base_canonical_sha256=self.state.base_canonical_sha256,
            current_revision_id="rev_" + "1" * 32,
            current_revision_sha256="1" * 64,
            score=self.state.score,
            musical_state_sha256=self.state.musical_state_sha256,
        )
        with self.assertRaisesRegex(Stage8ContractError, "MATERIALIZATION_STALE_PARENT"):
            materialize_score_edit(forged_state, command)

    def test_invalid_edit_becomes_visible_validation_evidence_not_hidden_repair(self):
        event = first_event(self.state.score_dict())
        command = command_for(
            self.state,
            command_id="cmd_stage8_runtime_0004",
            operation={
                "type": "set_effective_duration",
                "value": {"numerator": 0, "denominator": 1},
            },
            old_value=event["effectiveDuration"],
            event=event,
        )
        materialized = materialize_score_edit(self.state, command)
        codes = {item["code"] for item in materialized.validation.to_dict()["issues"]}

        self.assertIn("INVALID_EFFECTIVE_DURATION", codes)
        self.assertGreater(materialized.validation.blocking_issue_count, 0)
        self.assertEqual(
            {"numerator": 0, "denominator": 1},
            first_event(materialized.score_dict())["effectiveDuration"],
        )

    def test_derived_written_duration_updates_deterministically(self):
        event = first_event(self.state.score_dict())
        command = command_for(
            self.state,
            command_id="cmd_stage8_runtime_0005",
            operation={"type": "set_dots", "value": event["dots"] + 1},
            old_value=event["dots"],
            event=event,
        )
        materialized = materialize_score_edit(self.state, command)
        changed = first_event(materialized.score_dict())
        self.assertNotEqual(event["writtenDuration"], changed["writtenDuration"])


class Stage8DurableRevisionStoreTests(unittest.TestCase):
    def _first_revision(self):
        state = canonical_base_state(base_score())
        command = pitch_command(state, command_id="cmd_stage8_store_0001", step="D")
        materialized = materialize_score_edit(state, command)
        revision = revision_for(
            state,
            command,
            materialized,
            created_at="2026-08-22T08:00:00Z",
            previous_audit=None,
        )
        return state, command, materialized, revision

    def test_restart_recovery_exact_replay_and_second_append(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "teacher-revisions.sqlite3"
            _, _, materialized, revision = self._first_revision()
            first_store = SqliteRevisionStore(db)
            result = first_store.append(
                revision=revision,
                materialized=materialized,
                expected_parent_revision_id=None,
                expected_parent_revision_sha256=None,
            )
            self.assertFalse(result.already_present)

            restarted = SqliteRevisionStore(db)
            replay = restarted.append(
                revision=revision,
                materialized=materialized,
                expected_parent_revision_id=None,
                expected_parent_revision_sha256=None,
            )
            self.assertTrue(replay.already_present)

            head = restarted.load_head("job_stage8_runtime_0001")
            self.assertIsNotNone(head)
            restored = head.restore_state()
            self.assertEqual(revision.record["revisionId"], restored.current_revision_id)
            self.assertEqual(materialized.musical_state_sha256, restored.musical_state_sha256)

            event = first_event(restored.score_dict())
            command2 = command_for(
                restored,
                command_id="cmd_stage8_store_0002",
                operation={"type": "set_dots", "value": event["dots"] + 1},
                old_value=event["dots"],
                event=event,
            )
            materialized2 = materialize_score_edit(restored, command2)
            revision2 = revision_for(
                restored,
                command2,
                materialized2,
                created_at="2026-08-22T08:00:01Z",
                previous_audit=head.revision["auditEventSha256"],
            )
            second = restarted.append(
                revision=revision2,
                materialized=materialized2,
                expected_parent_revision_id=restored.current_revision_id,
                expected_parent_revision_sha256=restored.current_revision_sha256,
            )
            self.assertFalse(second.already_present)
            self.assertEqual(
                revision2.record["revisionId"],
                restarted.load_head("job_stage8_runtime_0001").revision["revisionId"],
            )

    def test_concurrent_same_parent_writers_allow_exactly_one_winner(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "teacher-revisions.sqlite3"
            state = canonical_base_state(base_score())
            candidates = []
            for suffix, step in (("a", "D"), ("b", "E")):
                command = pitch_command(state, command_id=f"cmd_stage8_race_{suffix}", step=step)
                materialized = materialize_score_edit(state, command)
                revision = revision_for(
                    state,
                    command,
                    materialized,
                    created_at="2026-08-22T08:01:00Z",
                    previous_audit=None,
                )
                candidates.append((materialized, revision))

            stores = [SqliteRevisionStore(db), SqliteRevisionStore(db)]
            barrier = threading.Barrier(2)
            outcomes = []
            lock = threading.Lock()

            def writer(index, candidate):
                materialized, revision = candidate
                barrier.wait()
                try:
                    stores[index].append(
                        revision=revision,
                        materialized=materialized,
                        expected_parent_revision_id=None,
                        expected_parent_revision_sha256=None,
                    )
                except Stage8ContractError as exc:
                    outcome = str(exc)
                else:
                    outcome = "PASS"
                with lock:
                    outcomes.append(outcome)

            threads = [
                threading.Thread(target=writer, args=(index, candidate))
                for index, candidate in enumerate(candidates)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            self.assertEqual(1, outcomes.count("PASS"))
            self.assertEqual(1, outcomes.count("REVISION_STORE_STALE_PARENT"))

    def test_persisted_state_corruption_is_detected_after_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "teacher-revisions.sqlite3"
            _, _, materialized, revision = self._first_revision()
            store = SqliteRevisionStore(db)
            store.append(
                revision=revision,
                materialized=materialized,
                expected_parent_revision_id=None,
                expected_parent_revision_sha256=None,
            )
            connection = sqlite3.connect(db)
            try:
                connection.execute(
                    "UPDATE teacher_revisions SET state_json = ? WHERE revision_id = ?",
                    (b"{}", revision.record["revisionId"]),
                )
                connection.commit()
            finally:
                connection.close()

            with self.assertRaisesRegex(Stage8ContractError, "REVISION_STORE_STATE_CORRUPTION_DETECTED"):
                SqliteRevisionStore(db).load_head("job_stage8_runtime_0001")

    def test_wrong_audit_predecessor_is_rejected_even_with_exact_parent(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "teacher-revisions.sqlite3"
            _, _, materialized, revision = self._first_revision()
            store = SqliteRevisionStore(db)
            store.append(
                revision=revision,
                materialized=materialized,
                expected_parent_revision_id=None,
                expected_parent_revision_sha256=None,
            )
            head = store.load_head("job_stage8_runtime_0001")
            restored = head.restore_state()
            event = first_event(restored.score_dict())
            command2 = command_for(
                restored,
                command_id="cmd_stage8_store_bad_audit",
                operation={"type": "set_dots", "value": event["dots"] + 1},
                old_value=event["dots"],
                event=event,
            )
            materialized2 = materialize_score_edit(restored, command2)
            revision2 = revision_for(
                restored,
                command2,
                materialized2,
                created_at="2026-08-22T08:02:00Z",
                previous_audit="f" * 64,
            )
            with self.assertRaisesRegex(Stage8ContractError, "REVISION_STORE_AUDIT_PARENT_MISMATCH"):
                store.append(
                    revision=revision2,
                    materialized=materialized2,
                    expected_parent_revision_id=restored.current_revision_id,
                    expected_parent_revision_sha256=restored.current_revision_sha256,
                )


if __name__ == "__main__":
    unittest.main()
