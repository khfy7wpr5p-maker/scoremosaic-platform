from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import os
import sqlite3
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "services" / "teacher-review-service" / "src"
sys.path.insert(0, str(SRC))

from scoremosaic_teacher_review import (  # noqa: E402
    COMMAND_VERSION,
    DurableRevisionStore,
    DurableRevisionStoreError,
    RevisionScope,
    TeacherScoreRevision,
    build_score_edit_command,
    build_teacher_score_revision,
    issue_authorization_grant,
)

AUTHZ_KEY = b"stage8b-authz-purpose-separated-key-32bytes!!"
STORE_KEY = b"stage8b-store-purpose-separated-key-32bytes!!"
OTHER_STORE_KEY = b"stage8b-other-store-purpose-key-32bytes!!"
H_A = "a" * 64
H_B = "b" * 64
H_C = "c" * 64
H_D = "d" * 64


def scope(tenant: str = "school_001") -> RevisionScope:
    return RevisionScope.create(
        tenant_id=tenant,
        job_id="job_stage8b_0001",
        review_report_id="report_stage8b_0001",
        review_report_sha256=H_A,
        base_canonical_sha256=H_B,
    )


def command_payload(
    *,
    command_id: str,
    decision_id: str,
    parent_id: str | None,
    parent_sha: str | None,
    operation: dict | None = None,
) -> dict:
    return {
        "schemaVersion": COMMAND_VERSION,
        "commandId": command_id,
        "jobId": "job_stage8b_0001",
        "reviewerId": "teacher_001",
        "authorizationDecisionId": decision_id,
        "reviewReportId": "report_stage8b_0001",
        "reviewReportSha256": H_A,
        "baseCanonicalSha256": H_B,
        "baseRevisionId": parent_id,
        "baseRevisionSha256": parent_sha,
        "issueId": "issue_stage8b_01",
        "location": {
            "partId": "P1",
            "measureId": "P1:M1",
            "eventId": "P1:M1:E1",
            "staff": 1,
            "voice": "1",
            "onset": {"numerator": 0, "denominator": 1},
        },
        "operation": operation or {"type": "set_dots", "value": 1},
        "oldValueSha256": H_C,
        "reason": "Teacher correction from immutable source evidence.",
    }


def make_revision(
    *,
    ordinal: int,
    parent_id: str | None = None,
    parent_sha: str | None = None,
    previous_audit: str | None = None,
    tenant: str = "school_001",
) -> TeacherScoreRevision:
    decision_id = f"authz_stage8b_{ordinal:04d}"
    grant = issue_authorization_grant(
        decision_id=decision_id,
        reviewer_id="teacher_001",
        tenant_id=tenant,
        job_id="job_stage8b_0001",
        review_report_id="report_stage8b_0001",
        review_report_sha256=H_A,
        canonical_score_sha256=H_B,
        parent_revision_id=parent_id,
        parent_revision_sha256=parent_sha,
        allowed_actions=("revision:read", "revision:propose"),
        signing_key=AUTHZ_KEY,
    )
    command = build_score_edit_command(
        command_payload(
            command_id=f"cmd_stage8b_{ordinal:04d}",
            decision_id=decision_id,
            parent_id=parent_id,
            parent_sha=parent_sha,
            operation={"type": "set_dots", "value": ordinal % 8},
        )
    )
    result_hash = f"{(ordinal % 15) + 1:x}" * 64
    validation_hash = f"{((ordinal + 5) % 15) + 1:x}" * 64
    return build_teacher_score_revision(
        grant=grant,
        signing_key=AUTHZ_KEY,
        expected_tenant_id=tenant,
        expected_job_id="job_stage8b_0001",
        expected_reviewer_id="teacher_001",
        expected_review_report_id="report_stage8b_0001",
        expected_review_report_sha256=H_A,
        expected_canonical_score_sha256=H_B,
        command=command,
        current_parent_revision_id=parent_id,
        current_parent_revision_sha256=parent_sha,
        resulting_musical_state_sha256=result_hash,
        validation_report_sha256=validation_hash,
        blocking_issue_count=0,
        unresolved_issue_count=ordinal % 3,
        created_at=f"2026-08-22T05:00:{ordinal % 60:02d}Z",
        previous_audit_event_sha256=previous_audit,
    )


class Stage8BDurableRevisionStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "private-store"
        self.scope = scope()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def store(self, **kwargs) -> DurableRevisionStore:
        return DurableRevisionStore(self.root, signing_key=STORE_KEY, **kwargs)

    def test_append_exact_idempotent_replay_restart_and_history(self):
        store = self.store()
        first = make_revision(ordinal=1)
        result = store.append_revision(
            self.scope,
            first,
            expected_parent_revision_id=None,
            expected_parent_revision_sha256=None,
        )
        self.assertTrue(result.applied)
        self.assertFalse(result.idempotent_replay)
        self.assertEqual(1, result.head.sequence)

        replay = store.append_revision(
            self.scope,
            first,
            expected_parent_revision_id=None,
            expected_parent_revision_sha256=None,
        )
        self.assertFalse(replay.applied)
        self.assertTrue(replay.idempotent_replay)
        self.assertEqual(result.head, replay.head)

        reopened = self.store()
        self.assertEqual(result.head, reopened.load_head(self.scope))
        loaded = reopened.load_revision(self.scope, first.record["revisionSha256"])
        self.assertEqual(first.to_dict(), loaded)
        self.assertEqual((first.to_dict(),), reopened.load_history(self.scope))

    def test_second_revision_binds_exact_parent_and_audit_chain(self):
        store = self.store()
        first = make_revision(ordinal=1)
        store.append_revision(
            self.scope,
            first,
            expected_parent_revision_id=None,
            expected_parent_revision_sha256=None,
        )
        second = make_revision(
            ordinal=2,
            parent_id=first.record["revisionId"],
            parent_sha=first.record["revisionSha256"],
            previous_audit=first.record["auditEventSha256"],
        )
        result = store.append_revision(
            self.scope,
            second,
            expected_parent_revision_id=first.record["revisionId"],
            expected_parent_revision_sha256=first.record["revisionSha256"],
        )
        self.assertEqual(2, result.head.sequence)
        history = self.store().load_history(self.scope)
        self.assertEqual(2, len(history))
        self.assertEqual(first.record["revisionSha256"], history[1]["parentRevisionSha256"])
        self.assertEqual(first.record["auditEventSha256"], history[1]["previousAuditEventSha256"])

    def test_stale_parent_rejected_without_mutation(self):
        store = self.store()
        first = make_revision(ordinal=1)
        store.append_revision(
            self.scope,
            first,
            expected_parent_revision_id=None,
            expected_parent_revision_sha256=None,
        )
        stale = make_revision(ordinal=2)
        with self.assertRaisesRegex(DurableRevisionStoreError, "revision_store_stale_parent"):
            store.append_revision(
                self.scope,
                stale,
                expected_parent_revision_id=None,
                expected_parent_revision_sha256=None,
            )
        self.assertEqual(1, len(store.load_history(self.scope)))

    def test_concurrent_same_parent_has_exactly_one_winner(self):
        store = self.store()
        revisions = [make_revision(ordinal=i) for i in range(1, 13)]
        barrier = threading.Barrier(len(revisions))
        lock = threading.Lock()
        outcomes: list[str] = []

        def worker(revision: TeacherScoreRevision) -> None:
            barrier.wait()
            try:
                result = store.append_revision(
                    self.scope,
                    revision,
                    expected_parent_revision_id=None,
                    expected_parent_revision_sha256=None,
                )
                outcome = "applied" if result.applied else "replay"
            except DurableRevisionStoreError as exc:
                outcome = exc.category
            with lock:
                outcomes.append(outcome)

        threads = [threading.Thread(target=worker, args=(revision,)) for revision in revisions]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(1, outcomes.count("applied"))
        self.assertEqual(11, outcomes.count("revision_store_stale_parent"))
        self.assertEqual(1, len(store.load_history(self.scope)))

    def test_crash_windows_roll_back_and_restart_cleanly(self):
        for point in (
            "after_record_insert_before_head",
            "after_head_update_before_commit",
        ):
            with self.subTest(point=point):
                case_root = self.root / point

                def injector(actual: str) -> None:
                    if actual == point:
                        raise RuntimeError(f"simulated-crash:{point}")

                store = DurableRevisionStore(
                    case_root,
                    signing_key=STORE_KEY,
                    _fault_injector=injector,
                )
                with self.assertRaisesRegex(RuntimeError, "simulated-crash"):
                    store.append_revision(
                        self.scope,
                        make_revision(ordinal=20),
                        expected_parent_revision_id=None,
                        expected_parent_revision_sha256=None,
                    )
                reopened = DurableRevisionStore(case_root, signing_key=STORE_KEY)
                self.assertIsNone(reopened.load_head(self.scope))
                self.assertEqual((), reopened.load_history(self.scope))

    def test_head_hmac_tamper_is_detected(self):
        store = self.store()
        revision = make_revision(ordinal=1)
        store.append_revision(
            self.scope,
            revision,
            expected_parent_revision_id=None,
            expected_parent_revision_sha256=None,
        )
        connection = sqlite3.connect(self.root / "teacher-review-revisions.sqlite3")
        connection.execute("UPDATE revision_heads SET head_hmac=?", ("0" * 64,))
        connection.commit()
        connection.close()
        with self.assertRaisesRegex(DurableRevisionStoreError, "revision_store_head_tampered"):
            store.load_head(self.scope)

    def test_record_tamper_is_detected(self):
        store = self.store()
        revision = make_revision(ordinal=1)
        store.append_revision(
            self.scope,
            revision,
            expected_parent_revision_id=None,
            expected_parent_revision_sha256=None,
        )
        connection = sqlite3.connect(self.root / "teacher-review-revisions.sqlite3")
        connection.execute("UPDATE revision_records SET record_json=?", (b"{}",))
        connection.commit()
        connection.close()
        with self.assertRaisesRegex(DurableRevisionStoreError, "revision_store_record_tampered"):
            store.load_revision(self.scope, revision.record["revisionSha256"])

    def test_cross_tenant_revision_is_rejected_and_rolled_back(self):
        store = self.store()
        revision = make_revision(ordinal=1, tenant="school_001")
        wrong_scope = scope("school_002")
        with self.assertRaisesRegex(DurableRevisionStoreError, "revision_store_scope_mismatch"):
            store.append_revision(
                wrong_scope,
                revision,
                expected_parent_revision_id=None,
                expected_parent_revision_sha256=None,
            )
        self.assertIsNone(store.load_head(wrong_scope))

    def test_wrong_store_key_cannot_reopen_sealed_scope(self):
        store = self.store()
        revision = make_revision(ordinal=1)
        store.append_revision(
            self.scope,
            revision,
            expected_parent_revision_id=None,
            expected_parent_revision_sha256=None,
        )
        reopened = DurableRevisionStore(self.root, signing_key=OTHER_STORE_KEY)
        with self.assertRaisesRegex(DurableRevisionStoreError, "revision_store_scope_tampered"):
            reopened.load_head(self.scope)

    def test_database_symlink_is_rejected(self):
        self.root.mkdir(parents=True)
        target = Path(self.temp.name) / "attacker.sqlite3"
        target.write_bytes(b"")
        os.symlink(target, self.root / "teacher-review-revisions.sqlite3")
        with self.assertRaisesRegex(DurableRevisionStoreError, "revision_store_database_invalid"):
            self.store()

    def test_caller_constructed_revision_cannot_bypass_integrity(self):
        store = self.store()
        revision = make_revision(ordinal=1)
        forged = revision.to_dict()
        forged["tenantId"] = "school_002"
        forged_revision = TeacherScoreRevision(forged)
        with self.assertRaisesRegex(
            DurableRevisionStoreError,
            "revision_store_scope_mismatch|revision_store_revision_hash_mismatch",
        ):
            store.append_revision(
                self.scope,
                forged_revision,
                expected_parent_revision_id=None,
                expected_parent_revision_sha256=None,
            )

    def test_repr_redacts_store_key(self):
        representation = repr(self.store())
        self.assertIn("<redacted>", representation)
        self.assertNotIn(STORE_KEY.decode("ascii"), representation)


if __name__ == "__main__":
    unittest.main()
