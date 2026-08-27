from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts" / "teacher-review-product-workflow-v1.json"
APP = ROOT / "prototypes" / "stage10-ui-application-experience" / "app.js"


class TeacherReviewProductWorkflowV1Tests(unittest.TestCase):
    def test_contract_locks_production_authority(self) -> None:
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

        self.assertEqual(contract["contract"], "SCOREMOSAIC_TEACHER_REVIEW_PRODUCT_WORKFLOW")
        self.assertEqual(contract["version"], "1.0.0")
        self.assertEqual(contract["flow"], [
            "teacher-review-workspace",
            "score-view",
            "structured-edit",
            "mark-reviewed",
            "validation",
            "approval-preparation",
            "production-approval-lock",
        ])

        authority = contract["authority"]
        self.assertEqual(authority, {
            "authoritative": False,
            "networkCapable": False,
            "persistent": False,
            "canCreateScoreEditCommand": False,
            "canCreateTeacherScoreRevision": False,
            "canApprove": False,
            "canPublish": False,
            "canActivateProduction": False,
        })

        gate = contract["approvalGate"]
        self.assertIs(gate["requiresZeroUnresolvedBlockingIssues"], True)
        self.assertIs(gate["requiresLocalValidationPass"], True)
        self.assertIs(gate["productionApproveControlVisible"], True)
        self.assertIs(gate["productionApproveControlEnabled"], False)
        self.assertIs(gate["unlockRequiresSeparateSecurityGate"], True)

    def test_browser_surface_exposes_complete_fail_closed_review_flow(self) -> None:
        app = APP.read_text(encoding="utf-8")

        required_markers = (
            "Validation & approval",
            "Mark selected reviewed",
            "Run validation",
            "Prepare approval",
            "Approve score",
            "reviewedIssueIds: new Set()",
            "workflowState.validation = 'pass'",
            "workflowState.approval = 'ready-preview'",
            "approveScore.disabled = true",
            "Production approval authority is not activated",
            "authenticated server revision, validation evidence, RBAC, persistence, and approval authority",
        )
        for marker in required_markers:
            self.assertIn(marker, app)

        forbidden = (
            "fetch(",
            "XMLHttpRequest",
            "WebSocket",
            "EventSource",
            "navigator.sendBeacon",
            "localStorage",
            "sessionStorage",
            "indexedDB",
            "document.cookie",
            "innerHTML",
        )
        for token in forbidden:
            self.assertNotIn(token, app)

    def test_approval_requires_validation_and_zero_blockers(self) -> None:
        app = APP.read_text(encoding="utf-8")

        self.assertIn("runValidation.disabled = issues.length === 0 || blocking !== 0", app)
        self.assertIn("prepareApproval.disabled = workflowState.validation !== 'pass'", app)
        self.assertIn("if (workflowState.validation !== 'pass' || unresolvedBlocking() !== 0) return", app)


if __name__ == "__main__":
    unittest.main()
