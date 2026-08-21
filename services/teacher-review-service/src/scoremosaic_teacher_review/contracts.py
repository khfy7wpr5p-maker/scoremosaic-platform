from __future__ import annotations

import re
from typing import Any

from . import _contracts as _internal

AUTHZ_VERSION = _internal.AUTHZ_VERSION
COMMAND_VERSION = _internal.COMMAND_VERSION
REVISION_VERSION = _internal.REVISION_VERSION
ReviewAuthorizationGrant = _internal.ReviewAuthorizationGrant
ScoreEditCommand = _internal.ScoreEditCommand
Stage8ContractError = _internal.Stage8ContractError
TeacherScoreRevision = _internal.TeacherScoreRevision
issue_authorization_grant = _internal.issue_authorization_grant
build_score_edit_command = _internal.build_score_edit_command
validate_score_edit_command = _internal.validate_score_edit_command

_TENANT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")


def _verify_scoped_authorization(
    grant: ReviewAuthorizationGrant,
    *,
    signing_key: bytes,
    required_action: str,
    expected_tenant_id: str,
    expected_job_id: str,
    expected_reviewer_id: str,
    expected_review_report_id: str,
    expected_review_report_sha256: str,
    expected_canonical_score_sha256: str,
    expected_parent_revision_id: str | None,
    expected_parent_revision_sha256: str | None,
) -> _internal.VerifiedReviewAuthorization:
    if (
        not isinstance(expected_tenant_id, str)
        or not expected_tenant_id
        or len(expected_tenant_id) > 200
        or _TENANT_RE.fullmatch(expected_tenant_id) is None
    ):
        raise Stage8ContractError("AUTHZ_EXPECTED_TENANT_INVALID")

    verified = _internal.verify_authorization_grant(
        grant,
        signing_key=signing_key,
        required_action=required_action,
        expected_job_id=expected_job_id,
        expected_reviewer_id=expected_reviewer_id,
        expected_review_report_id=expected_review_report_id,
        expected_review_report_sha256=expected_review_report_sha256,
        expected_canonical_score_sha256=expected_canonical_score_sha256,
        expected_parent_revision_id=expected_parent_revision_id,
        expected_parent_revision_sha256=expected_parent_revision_sha256,
    )
    if verified.tenant_id != expected_tenant_id:
        raise Stage8ContractError("AUTHZ_TENANT_MISMATCH")
    return verified


def verify_authorization_grant(
    grant: ReviewAuthorizationGrant,
    *,
    signing_key: bytes,
    required_action: str,
    expected_tenant_id: str,
    expected_job_id: str,
    expected_reviewer_id: str,
    expected_review_report_id: str,
    expected_review_report_sha256: str,
    expected_canonical_score_sha256: str,
    expected_parent_revision_id: str | None,
    expected_parent_revision_sha256: str | None,
) -> dict[str, Any]:
    """Verify a sealed grant against trusted scope and return non-authoritative evidence.

    The returned mapping is diagnostic evidence only. Mutation authority is never
    delegated to it; `build_teacher_score_revision` re-verifies the sealed grant.
    """

    verified = _verify_scoped_authorization(
        grant,
        signing_key=signing_key,
        required_action=required_action,
        expected_tenant_id=expected_tenant_id,
        expected_job_id=expected_job_id,
        expected_reviewer_id=expected_reviewer_id,
        expected_review_report_id=expected_review_report_id,
        expected_review_report_sha256=expected_review_report_sha256,
        expected_canonical_score_sha256=expected_canonical_score_sha256,
        expected_parent_revision_id=expected_parent_revision_id,
        expected_parent_revision_sha256=expected_parent_revision_sha256,
    )
    return {
        "decisionId": verified.decision_id,
        "reviewerId": verified.reviewer_id,
        "tenantId": verified.tenant_id,
        "jobId": verified.job_id,
        "reviewReportId": verified.review_report_id,
        "reviewReportSha256": verified.review_report_sha256,
        "canonicalScoreSha256": verified.canonical_score_sha256,
        "parentRevisionId": verified.parent_revision_id,
        "parentRevisionSha256": verified.parent_revision_sha256,
        "allowedActions": list(verified.allowed_actions),
        "grantSha256": verified.grant_sha256,
        "authoritativeCapability": False,
    }


def build_teacher_score_revision(
    *,
    grant: ReviewAuthorizationGrant,
    signing_key: bytes,
    expected_tenant_id: str,
    expected_job_id: str,
    expected_reviewer_id: str,
    expected_review_report_id: str,
    expected_review_report_sha256: str,
    expected_canonical_score_sha256: str,
    command: ScoreEditCommand,
    current_parent_revision_id: str | None,
    current_parent_revision_sha256: str | None,
    resulting_musical_state_sha256: str,
    validation_report_sha256: str,
    blocking_issue_count: int,
    unresolved_issue_count: int,
    created_at: str,
    previous_audit_event_sha256: str | None,
) -> TeacherScoreRevision:
    """Create a draft revision only after re-verifying sealed authorization.

    A caller-created "verified" object is never accepted as authority. The exact
    tenant/resource/parent scope is checked again at the mutation boundary.
    """

    if not isinstance(command, ScoreEditCommand):
        raise Stage8ContractError("COMMAND_TYPE_INVALID")

    verified = _verify_scoped_authorization(
        grant,
        signing_key=signing_key,
        required_action="revision:propose",
        expected_tenant_id=expected_tenant_id,
        expected_job_id=expected_job_id,
        expected_reviewer_id=expected_reviewer_id,
        expected_review_report_id=expected_review_report_id,
        expected_review_report_sha256=expected_review_report_sha256,
        expected_canonical_score_sha256=expected_canonical_score_sha256,
        expected_parent_revision_id=current_parent_revision_id,
        expected_parent_revision_sha256=current_parent_revision_sha256,
    )
    return _internal.build_teacher_score_revision(
        authorization=verified,
        command=command,
        current_parent_revision_id=current_parent_revision_id,
        current_parent_revision_sha256=current_parent_revision_sha256,
        resulting_musical_state_sha256=resulting_musical_state_sha256,
        validation_report_sha256=validation_report_sha256,
        blocking_issue_count=blocking_issue_count,
        unresolved_issue_count=unresolved_issue_count,
        created_at=created_at,
        previous_audit_event_sha256=previous_audit_event_sha256,
    )
