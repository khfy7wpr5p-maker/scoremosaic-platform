from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
import threading
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "services" / "teacher-review-service" / "src"
sys.path.insert(0, str(SRC))

from scoremosaic_teacher_review import (  # noqa: E402
    COMMAND_VERSION,
    DurableRevisionStore,
    RevisionScope,
    ReviewMusicalState,
    build_score_edit_command,
    canonical_payload_sha256,
    expected_old_value_sha256,
    issue_authorization_grant,
    materialize_canonical_state,
)
from scoremosaic_teacher_review.write_boundary import (  # noqa: E402
    Stage8WriteBoundaryError,
    WriteIdempotencyReservationReceipt,
    WriteIdempotencyReservationRequest,
    build_write_request,
    submit_score_edit_request,
)

AUTHZ_KEY = b"stage8g-authz-purpose-separated-key-32bytes!!"
STORE_KEY = b"stage8g-store-purpose-separated-key-32bytes!!"
H_A, H_C = "a" * 64, "c" * 64


def q(n: int, d: int = 1) -> dict[str, int]:
    return {"numerator": n, "denominator": d}


def ev(eid: str, order: int, onset: int, duration: int, *, kind="note", step="C") -> dict:
    return {
        "eventId": eid,
        "xmlOrder": order,
        "kind": kind,
        "onset": q(onset),
        "effectiveDuration": q(duration),
        "writtenDuration": q(duration),
        "writtenType": "quarter" if duration == 1 else "half",
        "dots": 0,
        "tuplet": None,
        "voice": "1",
        "staff": 1,
        "pitch": None if kind == "rest" else {"step": step, "alter": q(0), "octave": 4},
        "tab": None if kind == "rest" else {"string": 2, "fret": 1},
        "grace": False,
        "chordGroup": None,
        "chordIndex": None,
        "ties": [],
        "provenance": {
            "xmlPath": f"/score/part/measure/note[{order + 1}]",
            "sourceEventIndex": order,
        },
    }


def fixture() -> dict:
    data = {
        "schemaVersion": "1.0",
        "source": {
            "engine": "audiveris",
            "engineVersion": "5.5",
            "modelVersion": None,
            "artifactRef": "artifact://stage8g/base.musicxml",
            "artifactSha256": H_C,
        },
        "rootType": "score-partwise",
        "movementTitle": "Stage8G",
        "parts": [
            {
                "partId": "P1",
                "name": "Guitar",
                "ordinal": 1,
                "measures": [
                    {
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
                            ev("P1:M1:E1", 0, 0, 1, step="C"),
                            ev("P1:M1:E2", 1, 1, 1, step="D"),
                            ev("P1:M1:E3", 2, 2, 2, kind="rest"),
                        ],
                    }
                ],
            }
        ],
        "diagnostics": [],
        "canonicalSha256": "0" * 64,
    }
    data["canonicalSha256"] = canonical_payload_sha256(data)
    return data


def scope_for(data: dict, *, tenant="school_stage8g") -> RevisionScope:
    return RevisionScope.create(
        tenant_id=tenant,
        job_id="job_stage8g_0001",
        review_report_id="report_stage8g_0001",
        review_report_sha256=H_A,
        base_canonical_sha256=data["canonicalSha256"],
    )


def loc(eid="P1:M1:E1", onset=0, staff=1, voice="1") -> dict:
    return {
        "partId": "P1",
        "measureId": "P1:M1",
        "eventId": eid,
        "staff": staff,
        "voice": voice,
        "onset": q(onset),
    }


def grant(canonical_sha: str, *, aid="authz_stage8g_01", tenant="school_stage8g", parent_id=None, parent_sha=None):
    return issue_authorization_grant(
        decision_id=aid,
        reviewer_id="teacher_stage8g",
        tenant_id=tenant,
        job_id="job_stage8g_0001",
        review_report_id="report_stage8g_0001",
        review_report_sha256=H_A,
        canonical_score_sha256=canonical_sha,
        parent_revision_id=parent_id,
        parent_revision_sha256=parent_sha,
        allowed_actions=("revision:read", "revision:propose"),
        signing_key=AUTHZ_KEY,
    )


def command(state, *, op=None, cid="cmd_stage8g_01", aid="authz_stage8g_01", parent_id=None, parent_sha=None, target=None):
    op = op or {"type": "set_dots", "value": 1}
    target = target or loc()
    old_hash = expected_old_value_sha256(
        state,
        location=target,
        operation_type=op["type"],
    )
    return build_score_edit_command(
        {
            "schemaVersion": COMMAND_VERSION,
            "commandId": cid,
            "jobId": "job_stage8g_0001",
            "reviewerId": "teacher_stage8g",
            "authorizationDecisionId": aid,
            "reviewReportId": "report_stage8g_0001",
            "reviewReportSha256": H_A,
            "baseCanonicalSha256": state.to_dict()["baseCanonicalSha256"],
            "baseRevisionId": parent_id,
            "baseRevisionSha256": parent_sha,
            "issueId": "issue_stage8g_01",
            "location": target,
            "operation": op,
            "oldValueSha256": old_hash,
            "reason": "Bounded teacher correction.",
        }
    )


class MemoryIdempotency:
    def __init__(self):
        self._lock = threading.Lock()
        self._slots: dict[str, tuple[str, str, str]] = {}
        self.calls = 0

    def __call__(self, request: WriteIdempotencyReservationRequest) -> WriteIdempotencyReservationReceipt:
        with self._lock:
            self.calls += 1
            current = self._slots.get(request.slot_id)
            if current is None:
                created = "2026-08-22T12:45:00Z"
                self._slots[request.slot_id] = (
                    request.request_sha256,
                    request.command_sha256,
                    created,
                )
                return WriteIdempotencyReservationReceipt(
                    request.slot_id,
                    request.request_sha256,
                    request.command_sha256,
                    "reserved",
                    created,
                )
            request_sha, command_sha, created = current
            if request_sha != request.request_sha256 or command_sha != request.command_sha256:
                return WriteIdempotencyReservationReceipt(
                    request.slot_id,
                    request.request_sha256,
                    request.command_sha256,
                    "conflict",
                    None,
                )
            return WriteIdempotencyReservationReceipt(
                request.slot_id,
                request.request_sha256,
                request.command_sha256,
                "replay",
                created,
            )


class BarrierStore(DurableRevisionStore):
    def __init__(self, *args, barrier: threading.Barrier, **kwargs):
        self._test_barrier = barrier
        super().__init__(*args, **kwargs)

    def load_head(self, scope):
        result = super().load_head(scope)
        self._test_barrier.wait(timeout=5)
        return result


class Stage8GServerWriteBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.base = fixture()
        self.scope = scope_for(self.base)
        self.base_state = materialize_canonical_state(self.scope, self.base)

    def _submit(self, store, provider, *, state=None, request=None, auth=None, base=None):
        state = state or self.base_state
        auth = auth or grant(self.base["canonicalSha256"])
        request = request or build_write_request(command(state))
        return submit_score_edit_request(
            request_payload=request,
            grant=auth,
            signing_key=AUTHZ_KEY,
            scope=self.scope,
            reviewer_id="teacher_stage8g",
            current_state=state,
            base_canonical_payload=self.base if base is None else base,
            store=store,
            idempotency_reserver=provider,
        )

    def test_authorization_precedes_request_parsing_and_provider(self):
        with tempfile.TemporaryDirectory() as temp:
            store = DurableRevisionStore(Path(temp) / "store", signing_key=STORE_KEY)
            provider = MemoryIdempotency()
            bad_auth = grant(self.base["canonicalSha256"], tenant="school_other")
            hostile = {"rawXml": "<!ENTITY x SYSTEM 'file:///etc/passwd'>"}
            with self.assertRaisesRegex(Stage8WriteBoundaryError, "WRITE_AUTHORIZATION_DENIED"):
                self._submit(store, provider, request=hostile, auth=bad_auth)
            self.assertEqual(0, provider.calls)
            self.assertEqual((), store.load_history(self.scope))

    def test_closed_request_rejects_raw_xml_and_extra_fields_before_provider(self):
        with tempfile.TemporaryDirectory() as temp:
            store = DurableRevisionStore(Path(temp) / "store", signing_key=STORE_KEY)
            provider = MemoryIdempotency()
            request = build_write_request(command(self.base_state))
            request["rawXml"] = "<score-partwise/>"
            with self.assertRaisesRegex(Stage8WriteBoundaryError, "WRITE_REQUEST_SCHEMA_CLOSED"):
                self._submit(store, provider, request=request)
            self.assertEqual(0, provider.calls)
            self.assertEqual((), store.load_history(self.scope))

    def test_valid_write_creates_one_draft_revision_and_surfaces_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            store = DurableRevisionStore(Path(temp) / "store", signing_key=STORE_KEY)
            provider = MemoryIdempotency()
            result = self._submit(store, provider)
            safe = result.to_safe_dict()
            self.assertTrue(result.append_applied)
            self.assertFalse(result.idempotent_replay)
            self.assertEqual("reserved", result.idempotency_state)
            self.assertEqual("draft", safe["status"])
            self.assertFalse(safe["approvalEligible"])
            self.assertFalse(safe["publicationEligible"])
            self.assertFalse(safe["publicApiEnabled"])
            self.assertFalse(safe["browserWriteEnabled"])
            self.assertEqual(result.state.state_sha256, safe["stateSha256"])
            history = store.load_history(self.scope)
            self.assertEqual(1, len(history))
            self.assertEqual(safe["revisionSha256"], history[0]["revisionSha256"])

    def test_blocking_validator_evidence_is_persisted_not_hidden_or_repaired(self):
        with tempfile.TemporaryDirectory() as temp:
            store = DurableRevisionStore(Path(temp) / "store", signing_key=STORE_KEY)
            provider = MemoryIdempotency()
            op = {"type": "set_effective_duration", "value": q(5)}
            cmd = command(self.base_state, op=op)
            result = self._submit(store, provider, request=build_write_request(cmd))
            safe = result.to_safe_dict()
            self.assertGreater(safe["validationReport"]["blockingIssueCount"], 0)
            self.assertIn(
                "MEASURE_OVERFLOW",
                {item["code"] for item in safe["validationReport"]["issues"]},
            )
            self.assertEqual(q(5), result.state.to_dict()["parts"][0]["measures"][0]["events"][0]["effectiveDuration"])
            self.assertFalse(safe["approvalEligible"])

    def test_stale_parent_fails_before_request_or_idempotency_reuse(self):
        with tempfile.TemporaryDirectory() as temp:
            store = DurableRevisionStore(Path(temp) / "store", signing_key=STORE_KEY)
            provider = MemoryIdempotency()
            old_request = build_write_request(command(self.base_state))
            old_grant = grant(self.base["canonicalSha256"])
            self._submit(store, provider, request=old_request, auth=old_grant)
            calls = provider.calls
            with self.assertRaisesRegex(Stage8WriteBoundaryError, "WRITE_STALE_PARENT"):
                self._submit(store, provider, request={"not": "parsed"}, auth=old_grant)
            self.assertEqual(calls, provider.calls)
            self.assertEqual(1, len(store.load_history(self.scope)))

    def test_stale_old_value_and_location_do_not_reserve_or_append(self):
        with tempfile.TemporaryDirectory() as temp:
            store = DurableRevisionStore(Path(temp) / "store", signing_key=STORE_KEY)
            provider = MemoryIdempotency()
            original = command(self.base_state)
            forged = original.to_dict()
            forged["oldValueSha256"] = "f" * 64
            forged.pop("commandSha256")
            stale = build_score_edit_command(forged)
            with self.assertRaisesRegex(Stage8WriteBoundaryError, "WRITE_STALE_TARGET"):
                self._submit(store, provider, request=build_write_request(stale))
            self.assertEqual(0, provider.calls)
            self.assertEqual((), store.load_history(self.scope))

    def test_current_state_must_match_fresh_base_or_exact_persisted_head(self):
        with tempfile.TemporaryDirectory() as temp:
            store = DurableRevisionStore(Path(temp) / "store", signing_key=STORE_KEY)
            provider = MemoryIdempotency()
            forged_payload = self.base_state.to_dict()
            forged_payload.pop("stateSha256")
            forged_payload["parts"][0]["measures"][0]["events"][0]["dots"] = 7
            forged_state = ReviewMusicalState(forged_payload)
            with self.assertRaisesRegex(Stage8WriteBoundaryError, "WRITE_CURRENT_STATE_MISMATCH"):
                self._submit(
                    store,
                    provider,
                    state=forged_state,
                    request=build_write_request(command(forged_state)),
                )
            self.assertEqual(0, provider.calls)

    def test_idempotency_provider_failure_and_conflict_cannot_append(self):
        with tempfile.TemporaryDirectory() as temp1, tempfile.TemporaryDirectory() as temp2:
            store1 = DurableRevisionStore(Path(temp1) / "store", signing_key=STORE_KEY)
            store2 = DurableRevisionStore(Path(temp2) / "store", signing_key=STORE_KEY)
            provider = MemoryIdempotency()
            first = command(self.base_state, op={"type": "set_dots", "value": 1})
            self._submit(store1, provider, request=build_write_request(first))

            second = command(self.base_state, op={"type": "set_dots", "value": 2})
            with self.assertRaisesRegex(Stage8WriteBoundaryError, "WRITE_IDEMPOTENCY_CONFLICT"):
                self._submit(store2, provider, request=build_write_request(second))
            self.assertEqual((), store2.load_history(self.scope))

            def broken(_request):
                raise RuntimeError("provider detail must not cross the boundary")

            with tempfile.TemporaryDirectory() as temp3:
                store3 = DurableRevisionStore(Path(temp3) / "store", signing_key=STORE_KEY)
                with self.assertRaisesRegex(Stage8WriteBoundaryError, "WRITE_IDEMPOTENCY_UNAVAILABLE"):
                    self._submit(store3, broken)
                self.assertEqual((), store3.load_history(self.scope))

    def test_two_concurrent_exact_duplicates_converge_to_one_revision(self):
        with tempfile.TemporaryDirectory() as temp:
            barrier = threading.Barrier(2)
            store = BarrierStore(
                Path(temp) / "store",
                signing_key=STORE_KEY,
                barrier=barrier,
            )
            provider = MemoryIdempotency()
            cmd = command(self.base_state)
            request = build_write_request(cmd)
            auth = grant(self.base["canonicalSha256"])
            outcomes = []
            failures = []
            lock = threading.Lock()

            def worker():
                try:
                    result = self._submit(store, provider, request=deepcopy(request), auth=auth)
                    with lock:
                        outcomes.append(result)
                except Exception as exc:  # test harness captures unexpected boundary failure
                    with lock:
                        failures.append(exc)

            threads = [threading.Thread(target=worker), threading.Thread(target=worker)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)
            self.assertFalse(failures)
            self.assertEqual(2, len(outcomes))
            self.assertEqual(1, sum(1 for result in outcomes if result.append_applied))
            self.assertEqual(1, sum(1 for result in outcomes if result.idempotent_replay))
            self.assertEqual(1, len({result.revision.to_dict()["revisionSha256"] for result in outcomes}))
            self.assertEqual(1, len(store.load_history(self.scope)))

    def test_second_revision_requires_exact_fresh_parent_and_state(self):
        with tempfile.TemporaryDirectory() as temp:
            store = DurableRevisionStore(Path(temp) / "store", signing_key=STORE_KEY)
            provider = MemoryIdempotency()
            first = self._submit(store, provider)
            head = store.load_head(self.scope)
            self.assertIsNotNone(head)
            assert head is not None
            second_auth = grant(
                self.base["canonicalSha256"],
                aid="authz_stage8g_02",
                parent_id=head.revision_id,
                parent_sha=head.revision_sha256,
            )
            second_cmd = command(
                first.state,
                op={"type": "set_pitch", "value": {"step": "G", "alter": q(0), "octave": 4}},
                cid="cmd_stage8g_02",
                aid="authz_stage8g_02",
                parent_id=head.revision_id,
                parent_sha=head.revision_sha256,
            )
            second = self._submit(
                store,
                provider,
                state=first.state,
                request=build_write_request(second_cmd),
                auth=second_auth,
            )
            self.assertTrue(second.append_applied)
            self.assertEqual(2, len(store.load_history(self.scope)))


if __name__ == "__main__":
    unittest.main()
