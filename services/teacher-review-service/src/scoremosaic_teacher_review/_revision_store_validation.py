from __future__ import annotations

from hashlib import sha256
from typing import Any, Mapping

from .contracts import REVISION_VERSION, TeacherScoreRevision
from ._revision_store_common import (
    RevisionScope,
    canonical_json,
    fail,
    require_hash,
    require_id,
    require_job,
    require_nullable_hash,
    require_parent_pair,
    require_timestamp,
)

REVISION_KEYS = frozenset({
    "schemaVersion", "revisionId", "revisionSha256", "jobId", "reviewerId",
    "tenantId", "authorizationDecisionId", "authorizationGrantSha256",
    "reviewReportId", "reviewReportSha256", "baseCanonicalSha256",
    "parentRevisionId", "parentRevisionSha256", "commandId", "commandSha256",
    "resultingMusicalStateSha256", "validationReportSha256",
    "blockingIssueCount", "unresolvedIssueCount", "createdAt",
    "previousAuditEventSha256", "auditEventSha256", "status", "immutable",
    "approvalEligible", "publicationEligible",
})


def validate_revision_for_store(
    scope: RevisionScope,
    revision: TeacherScoreRevision,
    *,
    expected_parent_revision_id: str | None,
    expected_parent_revision_sha256: str | None,
    expected_previous_audit_event_sha256: str | None,
) -> tuple[dict[str, Any], bytes]:
    if not isinstance(revision, TeacherScoreRevision):
        fail("revision_store_revision_type_invalid")
    record = revision.to_dict()
    if not isinstance(record, Mapping) or set(record) != set(REVISION_KEYS):
        fail("revision_store_revision_schema_invalid")
    record = dict(record)
    if record["schemaVersion"] != REVISION_VERSION:
        fail("revision_store_revision_schema_invalid")
    if (
        record["status"] != "draft"
        or record["immutable"] is not True
        or record["approvalEligible"] is not False
        or record["publicationEligible"] is not False
    ):
        fail("revision_store_revision_authority_invalid")

    revision_sha256 = require_hash(
        record["revisionSha256"], "revision_store_revision_identity_invalid"
    )
    if record["revisionId"] != f"rev_{revision_sha256[:32]}":
        fail("revision_store_revision_identity_invalid")

    for key in (
        "authorizationGrantSha256", "reviewReportSha256", "baseCanonicalSha256",
        "commandSha256", "resultingMusicalStateSha256", "validationReportSha256",
        "auditEventSha256",
    ):
        require_hash(record[key], "revision_store_revision_schema_invalid")
    for key in (
        "reviewerId", "authorizationDecisionId", "reviewReportId", "commandId", "tenantId"
    ):
        require_id(record[key], "revision_store_revision_schema_invalid")
    require_job(record["jobId"], "revision_store_revision_schema_invalid")
    require_timestamp(record["createdAt"], "revision_store_revision_schema_invalid")

    for key in ("blockingIssueCount", "unresolvedIssueCount"):
        value = record[key]
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 1_000_000:
            fail("revision_store_revision_schema_invalid")

    parent_id, parent_sha = require_parent_pair(
        record["parentRevisionId"],
        record["parentRevisionSha256"],
        "revision_store_revision_parent_invalid",
    )
    if parent_id != expected_parent_revision_id or parent_sha != expected_parent_revision_sha256:
        fail("revision_store_stale_parent")
    previous_audit = require_nullable_hash(
        record["previousAuditEventSha256"], "revision_store_revision_audit_invalid"
    )
    if previous_audit != expected_previous_audit_event_sha256:
        fail("revision_store_audit_chain_mismatch")

    if (
        record["tenantId"] != scope.tenant_id
        or record["jobId"] != scope.job_id
        or record["reviewReportId"] != scope.review_report_id
        or record["reviewReportSha256"] != scope.review_report_sha256
        or record["baseCanonicalSha256"] != scope.base_canonical_sha256
    ):
        fail("revision_store_scope_mismatch")

    audit_body = {
        "actorId": record["reviewerId"],
        "authorizationDecisionId": record["authorizationDecisionId"],
        "commandSha256": record["commandSha256"],
        "resultingMusicalStateSha256": record["resultingMusicalStateSha256"],
        "previousAuditEventSha256": record["previousAuditEventSha256"],
        "createdAt": record["createdAt"],
    }
    if sha256(canonical_json(audit_body)).hexdigest() != record["auditEventSha256"]:
        fail("revision_store_revision_audit_invalid")

    revision_body = {
        key: value
        for key, value in record.items()
        if key not in {"revisionId", "revisionSha256"}
    }
    if sha256(canonical_json(revision_body)).hexdigest() != revision_sha256:
        fail("revision_store_revision_hash_mismatch")
    return record, canonical_json(record)
