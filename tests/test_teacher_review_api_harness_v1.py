from __future__ import annotations

import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / "contracts" / "teacher-review-api-harness-v1.json").read_text(encoding="utf-8"))
API = json.loads((ROOT / "contracts" / "teacher-review-api-v1.json").read_text(encoding="utf-8"))
CURRENT = json.loads((ROOT / "contracts" / "architecture-current-state-v1.json").read_text(encoding="utf-8"))
DOC = (ROOT / "docs" / "teacher-review-api-harness-v1.md").read_text(encoding="utf-8")
MODULE = (ROOT / "services" / "teacher-review-service" / "src" / "scoremosaic_teacher_review" / "api_harness.py").read_text(encoding="utf-8")
PYPROJECT = (ROOT / "services" / "teacher-review-service" / "pyproject.toml").read_text(encoding="utf-8")


class TeacherReviewApiHarnessV1RepositoryTests(unittest.TestCase):
    def test_identity_and_parent_contracts(self) -> None:
        self.assertEqual("scoremosaic-teacher-review-api-harness-v1", CONTRACT["version"])
        self.assertIs(CONTRACT["stageNumberAssigned"], False)
        self.assertIn("scoremosaic-teacher-review-api-v1", CONTRACT["parents"])
        self.assertIn("scoremosaic-live-ui-api-security-architecture-v1", CONTRACT["parents"])
        self.assertEqual(
            "services/teacher-review-service/src/scoremosaic_teacher_review/api_harness.py",
            CONTRACT["implementation"]["module"],
        )
        self.assertEqual("handle_revision_proposal", CONTRACT["implementation"]["entryPoint"])

    def test_security_order_preserves_authorize_before_parse_and_server_command_construction(self) -> None:
        order = CONTRACT["securityOrder"]
        self.assertLess(order.index("authenticate_session_test_double"), order.index("parse_and_validate_bounded_api_intent"))
        self.assertLess(order.index("validate_csrf"), order.index("parse_and_validate_bounded_api_intent"))
        self.assertLess(order.index("validate_exact_origin"), order.index("parse_and_validate_bounded_api_intent"))
        self.assertLess(order.index("authorize_revision_propose_and_document_scope"), order.index("parse_and_validate_bounded_api_intent"))
        self.assertLess(order.index("resolve_current_staff_voice_onset_and_old_value_sha256"), order.index("construct_and_validate_score_edit_command"))
        self.assertLess(order.index("construct_and_validate_score_edit_command"), order.index("invoke_stage8g_authorized_write_boundary"))
        self.assertLess(order.index("invoke_stage8g_authorized_write_boundary"), order.index("append_security_audit_evidence"))

    def test_public_operation_surface_does_not_expand_api_v1(self) -> None:
        self.assertEqual(API["initialBrowserOperationSurface"], CONTRACT["publicOperationSurface"])
        self.assertEqual(
            ["set_pitch", "set_effective_duration", "set_dots", "remove_event"],
            CONTRACT["publicOperationSurface"],
        )

    def test_browser_authority_and_activation_locks_are_closed(self) -> None:
        for key, value in CONTRACT["browserAuthority"].items():
            with self.subTest(browser_authority=key):
                self.assertIs(value, False)
        for key, value in CONTRACT["activationLocks"].items():
            with self.subTest(lock=key):
                self.assertIs(value, False)

    def test_idempotency_and_ambiguous_outcome_fail_closed(self) -> None:
        idem = CONTRACT["idempotency"]
        self.assertIs(idem["rawKeyLogged"], False)
        self.assertTrue(idem["exactCommittedReplayReturnsSameRevision"])
        self.assertTrue(idem["sameKeyDifferentBindingConflicts"])
        self.assertFalse(idem["ambiguousOutcomeAutoRetried"])
        self.assertTrue(idem["pendingOutcomeRequiresAuthorizedReconciliation"])
        ambiguous = CONTRACT["ambiguousMutationPolicy"]
        self.assertTrue(ambiguous["writeExceptionAfterReservationIsAmbiguous"])
        self.assertTrue(ambiguous["auditFailureAfterAppendIsAmbiguous"])
        self.assertFalse(ambiguous["sameExactRequestWhilePendingInvokesStage8Again"])

    def test_module_has_no_http_listener_or_network_framework(self) -> None:
        for forbidden in (
            r"\bimport\s+socket\b",
            r"\bfrom\s+socket\s+import\b",
            r"\bhttp\.server\b",
            r"\bfastapi\b",
            r"\bflask\b",
            r"\buvicorn\b",
            r"\baiohttp\b",
            r"\brequests\b",
            r"\burllib\.request\b",
        ):
            self.assertIsNone(re.search(forbidden, MODULE, flags=re.IGNORECASE), forbidden)
        self.assertNotIn("@app.", MODULE)
        self.assertNotIn("listen(", MODULE)
        self.assertIs(CONTRACT["implementation"]["httpListenerImplemented"], False)
        self.assertIs(CONTRACT["implementation"]["routeRegistered"], False)

    def test_service_metadata_registers_foundation_without_live_api(self) -> None:
        self.assertIn("api-security-harness-foundation-enabled = true", PYPROJECT)
        for marker in (
            "write-api-enabled = false",
            "public-api-enabled = false",
            "http-routes-registered = false",
            "browser-network-enabled = false",
            "production-identity-enabled = false",
            "production-durable-store-enabled = false",
        ):
            self.assertIn(marker, PYPROJECT)

    def test_document_declares_exact_external_coolify_stop_boundary(self) -> None:
        self.assertIn("contracts/architecture-current-state-v1.json", DOC)
        self.assertIn("does not consume Stage 12", DOC)
        self.assertIn("Coolify", DOC)
        self.assertIn("real credentials", DOC)
        self.assertIn("real PDF/JPG/PNG upload", DOC)

    def test_current_state_registers_repo_only_harness(self) -> None:
        harness = CURRENT["approvedWorkstreams"]["teacherReviewApiHarness"]
        self.assertIs(harness["stageNumberAssigned"], False)
        self.assertEqual("contracts/teacher-review-api-harness-v1.json", harness["contract"])
        self.assertIs(harness["repositoryHarnessReady"], True)
        for key in (
            "httpRoutesRegistered",
            "liveNetworkActivated",
            "productionPersistenceActivated",
            "productionIdentityActivated",
        ):
            self.assertIs(harness[key], False, key)


if __name__ == "__main__":
    unittest.main()
