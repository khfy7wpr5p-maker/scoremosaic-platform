from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "services" / "teacher-review-service" / "src"
sys.path.insert(0, str(SRC))

from scoremosaic_teacher_review import DurableRevisionStore  # noqa: E402
from scoremosaic_teacher_review.api_harness import (  # noqa: E402
    ApiHarnessDependencies,
    ApiHarnessRequest,
    ApiPrincipal,
    MemoryApiIdempotencyLedger,
    MemoryStage8IdempotencyReserver,
    handle_revision_proposal,
)


AUTHZ_KEY = b"api-harness-malformed-authz-key-32bytes!!"
ORIGIN = "https://preview.invalid"
SESSION = "session-test-only"
CSRF = "csrf-test-only"
IDEMPOTENCY = "idem-key-malformed-0001"


class TeacherReviewApiHarnessMalformedInputTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.principal = ApiPrincipal(
            principal_id="principal_api_harness",
            reviewer_id="teacher_api_harness",
            tenant_id="school_api_harness",
        )
        self.store = DurableRevisionStore(
            Path(self.temp.name) / "store",
            signing_key=b"api-harness-malformed-store-key-32bytes!!",
        )
        self.operation_calls = 0
        self.resolve_calls = 0
        self.write_calls = 0

    def _deps(self) -> ApiHarnessDependencies:
        def authenticate(token):
            return self.principal if token == SESSION else None

        def csrf(principal, session_token, csrf_token):
            return (
                principal == self.principal
                and session_token == SESSION
                and csrf_token == CSRF
            )

        def operation_authorizer(*_args):
            self.operation_calls += 1
            return True

        def resolver(*_args):
            self.resolve_calls += 1
            raise AssertionError("malformed input must not reach document resolution")

        def write_invoker(**_kwargs):
            self.write_calls += 1
            raise AssertionError("malformed input must not reach Stage 8-G")

        return ApiHarnessDependencies(
            store=self.store,
            signing_key=AUTHZ_KEY,
            allowed_origin=ORIGIN,
            session_authenticator=authenticate,
            csrf_validator=csrf,
            coarse_authorizer=lambda *_args: "allow",
            operation_authorizer=operation_authorizer,
            document_resolver=resolver,
            stage8_idempotency_reserver=MemoryStage8IdempotencyReserver(),
            outer_idempotency=MemoryApiIdempotencyLedger(),
            audit_sink=lambda _event: None,
            correlation_id_factory=lambda: "corr_malformed_0001",
            command_id_factory=lambda: "cmd_malformed_0001",
            decision_id_factory=lambda: "authz_malformed_0001",
            write_invoker=write_invoker,
        )

    def _request(self, *, content_type="application/json", raw_body=b"{}") -> ApiHarnessRequest:
        return ApiHarnessRequest(
            document_id="doc_api_harness_0001",
            raw_body=raw_body,
            content_type=content_type,
            origin=ORIGIN,
            session_token=SESSION,
            csrf_token=CSRF,
            idempotency_key=IDEMPOTENCY,
        )

    def test_missing_or_non_string_content_type_returns_bounded_400(self) -> None:
        for value in (None, 123):
            with self.subTest(content_type=value):
                response = handle_revision_proposal(
                    self._request(content_type=value),
                    self._deps(),
                )
                self.assertEqual(400, response.http_status)
                self.assertEqual("API_REQUEST_INVALID", response.body["error"]["code"])
                self.assertEqual("rejected", response.body["state"])
        self.assertEqual(0, self.operation_calls)
        self.assertEqual(0, self.resolve_calls)
        self.assertEqual(0, self.write_calls)

    def test_huge_json_integer_cannot_escape_public_error_boundary(self) -> None:
        hostile = b'{"value":' + (b"9" * 5000) + b"}"
        response = handle_revision_proposal(
            self._request(raw_body=hostile),
            self._deps(),
        )
        self.assertEqual(400, response.http_status)
        self.assertEqual("API_REQUEST_INVALID", response.body["error"]["code"])
        self.assertEqual("rejected", response.body["state"])
        self.assertEqual(0, self.operation_calls)
        self.assertEqual(0, self.resolve_calls)
        self.assertEqual(0, self.write_calls)


if __name__ == "__main__":
    unittest.main()
