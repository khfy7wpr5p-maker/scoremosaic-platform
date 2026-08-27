from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts" / "teacher-review-product-workflow-v1.json"
APP = ROOT / "prototypes" / "stage10-ui-application-experience" / "app.js"


def test_contract_locks_production_authority() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    assert contract["contract"] == "SCOREMOSAIC_TEACHER_REVIEW_PRODUCT_WORKFLOW"
    assert contract["version"] == "1.0.0"
    assert contract["flow"] == [
        "teacher-review-workspace",
        "score-view",
        "structured-edit",
        "mark-reviewed",
        "validation",
        "approval-preparation",
        "production-approval-lock",
    ]

    authority = contract["authority"]
    assert authority == {
        "authoritative": False,
        "networkCapable": False,
        "persistent": False,
        "canCreateScoreEditCommand": False,
        "canCreateTeacherScoreRevision": False,
        "canApprove": False,
        "canPublish": False,
        "canActivateProduction": False,
    }

    gate = contract["approvalGate"]
    assert gate["requiresZeroUnresolvedBlockingIssues"] is True
    assert gate["requiresLocalValidationPass"] is True
    assert gate["productionApproveControlVisible"] is True
    assert gate["productionApproveControlEnabled"] is False
    assert gate["unlockRequiresSeparateSecurityGate"] is True


def test_browser_surface_exposes_complete_fail_closed_review_flow() -> None:
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
        assert marker in app

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
        assert token not in app


def test_approval_requires_validation_and_zero_blockers() -> None:
    app = APP.read_text(encoding="utf-8")

    assert "runValidation.disabled = issues.length === 0 || blocking !== 0" in app
    assert "prepareApproval.disabled = workflowState.validation !== 'pass'" in app
    assert "if (workflowState.validation !== 'pass' || unresolvedBlocking() !== 0) return" in app
