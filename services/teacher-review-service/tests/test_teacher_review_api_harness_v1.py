from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "services" / "teacher-review-service" / "src"
sys.path.insert(0, str(SRC))

from scoremosaic_teacher_review import (  # noqa: E402
    DurableRevisionStore,
    RevisionScope,
    canonical_payload_sha256,
    materialize_canonical_state,
)
from scoremosaic_teacher_review.api_harness import (  # noqa: E402
    API_EDIT_INTENT_VERSION,
    API_HARNESS_VERSION,
    API_REVISION_RESULT_VERSION,
    ApiDocumentContext,
    ApiHarnessDependencies,
    ApiHarnessRequest,
    ApiPrincipal,
    MemoryApiIdempotencyLedger,
    MemoryStage8IdempotencyReserver,
    handle_revision_proposal,
)
from scoremosaic_teacher_review.write_boundary import submit_score_edit_request  # noqa: E402


AUTHZ_KEY = b"api-harness-authz-purpose-separated-key-32bytes!!"
STORE_KEY = b"api-harness-store-purpose-separated-key-32bytes!!"
H_A, H_C = "a" * 64, "c" * 64
ORIGIN = "https://preview.invalid"
SESSION = "session-test-only"
CSRF = "csrf-test-only"
IDEMPOTENCY = "idem-key-00000001"


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
            "artifactRef": "artifact://api-harness/base.musicxml",
            "artifactSha256": H_C,
        },
        "rootType": "score-partwise",
        "movementTitle": "API Harness",
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


def make_scope(data: dict, *, tenant: str = "school_api_harness") -> RevisionScope:
    return RevisionScope.create(
        tenant_id=tenant,
        job_id="job_api_harness_0001",
        review_report_id="report_api_harness_0001",
        review_report_sha256=H_A,
        base_canonical_sha256=data["canonicalSha256"],
    )


def intent(
    state_sha: str,
    *,
    projection_sha: str = "b" * 64,
    request_id: str = "req_api_harness_0001",
    operation: dict | None = None,
    event_id: str = "P1:M1:E1",
) -> dict:
    return {
        "schemaVersion": API_EDIT_INTENT_VERSION,
        "requestId": request_id,
        "projectionSha256": projection_sha,
        "snapshot": {
            "kind": "base",
            "revisionId": None,
            "revisionSha256": None,
            "stateSha256": state_sha,
        },
        "evidenceContext": {
            "issueId": "issue_api_harness_01",
            "differenceId": None,
        },
        "target": {
            "partId": "P1",
            "measureId": "P1:M1",
            "eventId": event_id,
        },
        "operation": operation or {"type": "set_dots", "value": 1},
        "reason": "Teacher correction.",
    }


def encode(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


class Counters:
    def __init__(self) -> None:
        self.coarse = 0
        self.operation = 0
        self.resolve = 0
        self.audit = 0
        self.write = 0
        self.audit_events: list[dict] = []


class TeacherReviewApiHarnessV1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.base = fixture()
        self.scope = make_scope(self.base)
        self.state = materialize_canonical_state(self.scope, self.base)
        self.principal = ApiPrincipal(
            principal_id="principal_api_harness",
            reviewer_id="teacher_api_harness",
            tenant_id=self.scope.tenant_id,
        )
        self.projection_sha = "b" * 64
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = DurableRevisionStore(Path(self.temp.name) / "store", signing_key=STORE_KEY)
        self.counters = Counters()
        self.outer = MemoryApiIdempotencyLedger()
        self.inner = MemoryStage8IdempotencyReserver(created_at="2026-08-24T08:30:00Z")
        self.context = ApiDocumentContext(
            document_id="doc_api_harness_0001",
            scope=self.scope,
            projection_sha256=self.projection_sha,
            current_state=self.state,
            base_canonical_payload=self.base,
        )
        self._correlation = 0
        self._command = 0
        self._decision = 0

    def _deps(
        self,
        *,
        coarse=None,
        operation=None,
        resolver=None,
        audit=None,
        write=None,
    ) -> ApiHarnessDependencies:
        def authenticate(token):
            return self.principal if token == SESSION else None

        def csrf(principal, session_token, csrf_token):
            return (
                principal == self.principal
                and session_token == SESSION
                and csrf_token == CSRF
            )

        def coarse_default(principal, document_id, action):
            self.counters.coarse += 1
            return (
                "allow"
                if principal == self.principal
                and document_id == self.context.document_id
                and action == "revision.propose"
                else "not_visible"
            )

        def operation_default(principal, document_id, op):
            self.counters.operation += 1
            return principal == self.principal and document_id == self.context.document_id and op in {
                "set_pitch", "set_effective_duration", "set_dots", "remove_event"
            }

        def resolver_default(principal, document_id):
            self.counters.resolve += 1
            return self.context if principal == self.principal and document_id == self.context.document_id else None

        def audit_default(event):
            self.counters.audit += 1
            self.counters.audit_events.append(dict(event))

        def write_default(**kwargs):
            self.counters.write += 1
            return submit_score_edit_request(**kwargs)

        def corr():
            self._correlation += 1
            return f"corr_api_harness_{self._correlation:04d}"

        def command_id():
            self._command += 1
            return f"cmd_api_harness_{self._command:04d}"

        def decision_id():
            self._decision += 1
            return f"authz_api_harness_{self._decision:04d}"

        return ApiHarnessDependencies(
            store=self.store,
            signing_key=AUTHZ_KEY,
            allowed_origin=ORIGIN,
            session_authenticator=authenticate,
            csrf_validator=csrf,
            coarse_authorizer=coarse or coarse_default,
            operation_authorizer=operation or operation_default,
            document_resolver=resolver or resolver_default,
            stage8_idempotency_reserver=self.inner,
            outer_idempotency=self.outer,
            audit_sink=audit or audit_default,
            correlation_id_factory=corr,
            command_id_factory=command_id,
            decision_id_factory=decision_id,
            write_invoker=write or write_default,
        )

    def _request(
        self,
        payload: dict | None = None,
        *,
        session=SESSION,
        csrf=CSRF,
        origin=ORIGIN,
        idempotency=IDEMPOTENCY,
        content_type="application/json",
        document_id="doc_api_harness_0001",
        raw_body: bytes | None = None,
    ) -> ApiHarnessRequest:
        payload = payload or intent(self.state.state_sha256, projection_sha=self.projection_sha)
        return ApiHarnessRequest(
            document_id=document_id,
            raw_body=encode(payload) if raw_body is None else raw_body,
            content_type=content_type,
            origin=origin,
            session_token=session,
            csrf_token=csrf,
            idempotency_key=idempotency,
        )

    def test_success_builds_server_authority_and_one_draft_revision(self):
        response = handle_revision_proposal(self._request(), self._deps())
        self.assertEqual(201, response.http_status)
        body = response.body
        self.assertEqual(API_REVISION_RESULT_VERSION, body["schemaVersion"])
        self.assertEqual("created", body["state"])
        self.assertEqual("doc_api_harness_0001", body["documentId"])
        self.assertEqual("draft", body["revision"]["status"])
        self.assertTrue(body["revision"]["immutable"])
        self.assertFalse(body["revision"]["approvalEligible"])
        self.assertFalse(body["revision"]["publicationEligible"])
        self.assertEqual(
            {
                "canCreateAnotherRevision": False,
                "canApprove": False,
                "canPublish": False,
                "canPersistCorrectedMusicXmlToProduction": False,
            },
            body["authority"],
        )
        self.assertEqual(1, len(self.store.load_history(self.scope)))
        self.assertEqual(1, self.counters.write)
        self.assertEqual(1, self.counters.audit)
        audit = self.counters.audit_events[0]
        self.assertEqual(API_HARNESS_VERSION, audit["schemaVersion"])
        self.assertNotIn(IDEMPOTENCY, json.dumps(audit))
        self.assertNotIn(SESSION, json.dumps(audit))
        self.assertNotIn(CSRF, json.dumps(audit))

    def test_authentication_csrf_and_origin_precede_body_parsing(self):
        hostile = b"{ definitely-not-json"

        response = handle_revision_proposal(
            self._request(raw_body=hostile, session="wrong"), self._deps()
        )
        self.assertEqual(401, response.http_status)
        self.assertEqual(0, self.counters.coarse)

        self.counters = Counters()
        response = handle_revision_proposal(
            self._request(raw_body=hostile, csrf="wrong"), self._deps()
        )
        self.assertEqual(403, response.http_status)
        self.assertEqual("API_CSRF_INVALID", response.body["error"]["code"])
        self.assertEqual(0, self.counters.coarse)

        self.counters = Counters()
        response = handle_revision_proposal(
            self._request(raw_body=hostile, origin="https://evil.invalid"), self._deps()
        )
        self.assertEqual(403, response.http_status)
        self.assertEqual("API_ORIGIN_INVALID", response.body["error"]["code"])
        self.assertEqual(0, self.counters.coarse)
        self.assertEqual((), self.store.load_history(self.scope))

    def test_coarse_resource_authorization_precedes_bounded_body_oracle(self):
        def not_visible(*_args):
            self.counters.coarse += 1
            return "not_visible"

        response = handle_revision_proposal(
            self._request(raw_body=b"not-json"), self._deps(coarse=not_visible)
        )
        self.assertEqual(404, response.http_status)
        self.assertEqual("API_RESOURCE_NOT_VISIBLE", response.body["error"]["code"])
        self.assertEqual(0, self.counters.operation)
        self.assertEqual(0, self.counters.resolve)
        self.assertEqual(0, self.counters.write)

    def test_browser_cannot_smuggle_authority_or_internal_command_fields(self):
        for forbidden_key in (
            "reviewerId",
            "tenantId",
            "authorizationDecisionId",
            "commandId",
            "oldValueSha256",
            "staff",
            "voice",
            "onset",
            "approvalDecision",
            "publicationDecision",
        ):
            with self.subTest(forbidden_key=forbidden_key):
                payload = intent(self.state.state_sha256, projection_sha=self.projection_sha)
                payload[forbidden_key] = "attacker"
                response = handle_revision_proposal(
                    self._request(payload, idempotency=f"idem-{forbidden_key}-000000000000"),
                    self._deps(),
                )
                self.assertEqual(400, response.http_status)
                self.assertEqual("API_REQUEST_INVALID", response.body["error"]["code"])
        self.assertEqual((), self.store.load_history(self.scope))

    def test_cross_tenant_or_hidden_document_is_not_disclosed(self):
        other = ApiDocumentContext(
            document_id=self.context.document_id,
            scope=make_scope(self.base, tenant="school_other"),
            projection_sha256=self.projection_sha,
            current_state=self.state,
            base_canonical_payload=self.base,
        )

        response = handle_revision_proposal(
            self._request(), self._deps(resolver=lambda *_args: other)
        )
        self.assertEqual(404, response.http_status)
        self.assertIsNone(response.body["documentId"])
        self.assertIsNone(response.body["parent"])
        self.assertIsNone(response.body["revision"])
        self.assertIsNone(response.body["requestId"])

    def test_stale_projection_snapshot_and_target_fail_before_write(self):
        stale_projection = intent(self.state.state_sha256, projection_sha="f" * 64)
        response = handle_revision_proposal(
            self._request(stale_projection), self._deps()
        )
        self.assertEqual(409, response.http_status)
        self.assertEqual("stale", response.body["state"])
        self.assertEqual(0, self.counters.write)

        self.counters = Counters()
        stale_state = intent("e" * 64, projection_sha=self.projection_sha)
        response = handle_revision_proposal(
            self._request(stale_state, idempotency="idem-key-00000002"), self._deps()
        )
        self.assertEqual(409, response.http_status)
        self.assertEqual(0, self.counters.write)

        self.counters = Counters()
        missing_target = intent(
            self.state.state_sha256,
            projection_sha=self.projection_sha,
            event_id="P1:M1:E999",
        )
        response = handle_revision_proposal(
            self._request(missing_target, idempotency="idem-key-00000003"), self._deps()
        )
        self.assertEqual(409, response.http_status)
        self.assertEqual(0, self.counters.write)
        self.assertEqual((), self.store.load_history(self.scope))

    def test_exact_idempotent_replay_returns_same_revision_without_second_write(self):
        deps = self._deps()
        first = handle_revision_proposal(self._request(), deps)
        second = handle_revision_proposal(self._request(), deps)
        self.assertEqual(201, first.http_status)
        self.assertEqual(200, second.http_status)
        self.assertEqual("replayed", second.body["state"])
        self.assertEqual(first.body["revision"], second.body["revision"])
        self.assertEqual(1, self.counters.write)
        self.assertEqual(1, len(self.store.load_history(self.scope)))

    def test_same_idempotency_key_with_different_digest_conflicts(self):
        deps = self._deps()
        first = handle_revision_proposal(self._request(), deps)
        self.assertEqual(201, first.http_status)
        changed = intent(
            self.state.state_sha256,
            projection_sha=self.projection_sha,
            operation={"type": "set_dots", "value": 2},
        )
        second = handle_revision_proposal(self._request(changed), deps)
        self.assertEqual(409, second.http_status)
        self.assertEqual("conflict", second.body["state"])
        self.assertEqual("API_IDEMPOTENCY_CONFLICT", second.body["error"]["code"])
        self.assertEqual(1, self.counters.write)
        self.assertEqual(1, len(self.store.load_history(self.scope)))

    def test_ambiguous_write_is_quarantined_until_reconciliation(self):
        def ambiguous_write(**kwargs):
            self.counters.write += 1
            submit_score_edit_request(**kwargs)
            raise RuntimeError("provider detail must never cross the public boundary")

        deps = self._deps(write=ambiguous_write)
        first = handle_revision_proposal(self._request(), deps)
        self.assertEqual(503, first.http_status)
        self.assertEqual("API_RECONCILIATION_REQUIRED", first.body["error"]["code"])
        self.assertTrue(first.body["error"]["reconciliationRequired"])
        self.assertNotIn("provider detail", json.dumps(first.body))
        self.assertEqual(1, len(self.store.load_history(self.scope)))

        second = handle_revision_proposal(self._request(), deps)
        self.assertEqual(503, second.http_status)
        self.assertEqual("API_RECONCILIATION_REQUIRED", second.body["error"]["code"])
        self.assertEqual(1, self.counters.write)
        self.assertEqual(1, len(self.store.load_history(self.scope)))

    def test_audit_failure_after_append_is_ambiguous_and_not_auto_retried(self):
        def broken_audit(_event):
            self.counters.audit += 1
            raise RuntimeError("audit backend secret detail")

        deps = self._deps(audit=broken_audit)
        first = handle_revision_proposal(self._request(), deps)
        self.assertEqual(503, first.http_status)
        self.assertTrue(first.body["error"]["reconciliationRequired"])
        self.assertNotIn("audit backend", json.dumps(first.body))
        self.assertEqual(1, len(self.store.load_history(self.scope)))

        second = handle_revision_proposal(self._request(), deps)
        self.assertEqual(503, second.http_status)
        self.assertEqual(1, self.counters.write)
        self.assertEqual(1, self.counters.audit)
        self.assertEqual(1, len(self.store.load_history(self.scope)))

    def test_unsupported_operation_and_invalid_idempotency_are_closed(self):
        payload = intent(self.state.state_sha256, projection_sha=self.projection_sha)
        payload["operation"] = {"type": "set_tab", "value": {"string": 1, "fret": 3}}
        response = handle_revision_proposal(self._request(payload), self._deps())
        self.assertEqual(422, response.http_status)
        self.assertEqual("API_OPERATION_NOT_SUPPORTED", response.body["error"]["code"])

        response = handle_revision_proposal(
            self._request(idempotency="short"), self._deps()
        )
        self.assertEqual(400, response.http_status)
        self.assertEqual("API_IDEMPOTENCY_KEY_INVALID", response.body["error"]["code"])
        self.assertEqual((), self.store.load_history(self.scope))

    def test_public_error_shape_never_exposes_resolved_identity(self):
        payload = intent(self.state.state_sha256, projection_sha="f" * 64)
        response = handle_revision_proposal(self._request(payload), self._deps())
        body = response.body
        self.assertEqual(
            {
                "schemaVersion", "requestId", "correlationId", "state", "documentId",
                "parent", "revision", "error", "authority",
            },
            set(body),
        )
        self.assertIsNone(body["requestId"])
        self.assertIsNone(body["documentId"])
        self.assertIsNone(body["parent"])
        self.assertIsNone(body["revision"])
        serialized = json.dumps(body)
        for secret in (SESSION, CSRF, IDEMPOTENCY, AUTHZ_KEY.decode("utf-8")):
            self.assertNotIn(secret, serialized)


if __name__ == "__main__":
    unittest.main()
