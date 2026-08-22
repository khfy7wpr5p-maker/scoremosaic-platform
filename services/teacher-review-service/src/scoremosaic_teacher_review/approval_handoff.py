from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import hmac
import json
import re
from types import MappingProxyType
from typing import Any, Mapping

from .approval_eligibility import (
    APPROVAL_ELIGIBILITY_VERSION,
    ApprovalEligibilityEvidence,
    Stage8ApprovalEligibilityError,
    build_approval_eligibility_evidence,
)
from .contracts import TeacherScoreRevision
from .corrected_musicxml import CorrectedMusicXmlArtifact
from .durable_revision_store import DurableRevisionStore, RevisionScope
from .musical_state import ReviewMusicalState


APPROVAL_HANDOFF_AUTHZ_VERSION = "scoremosaic-approval-handoff-authz-v1"
APPROVAL_HANDOFF_VERSION = "scoremosaic-human-approval-handoff-v1"
APPROVAL_HANDOFF_PURPOSE = b"scoremosaic/teacher-review/approval-handoff/v1\x00"
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_CONSTRUCTION_SEAL = object()


class Stage8ApprovalHandoffError(ValueError):
    """Fail-closed Stage 8-L handoff error with stable public code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> None:
    raise Stage8ApprovalHandoffError(code)


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError):
        _fail("APPROVAL_HANDOFF_NON_CANONICAL_VALUE")


def _digest(value: Any) -> str:
    return sha256(_canonical_json(value)).hexdigest()


def _require_id(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 200 or _ID_RE.fullmatch(value) is None:
        _fail(code)
    return value


def _require_hash(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HASH_RE.fullmatch(value) is None:
        _fail(code)
    return value


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _eligible_payload(evidence: ApprovalEligibilityEvidence) -> dict[str, Any]:
    if type(evidence) is not ApprovalEligibilityEvidence:
        _fail("APPROVAL_HANDOFF_ELIGIBILITY_TYPE_INVALID")
    payload = evidence.to_dict()
    if payload.get("schemaVersion") != APPROVAL_ELIGIBILITY_VERSION:
        _fail("APPROVAL_HANDOFF_ELIGIBILITY_VERSION_INVALID")
    if payload.get("eligibility") != {"candidateEligible": True, "reasons": []}:
        _fail("APPROVAL_HANDOFF_CANDIDATE_INELIGIBLE")
    checks = payload.get("checks")
    if not isinstance(checks, dict) or not checks or any(value is not True for value in checks.values()):
        _fail("APPROVAL_HANDOFF_ELIGIBILITY_CHECK_INVALID")
    authority = payload.get("authority")
    if not isinstance(authority, dict) or not authority or any(value is not False for value in authority.values()):
        _fail("APPROVAL_HANDOFF_UPSTREAM_AUTHORITY_INVALID")
    if payload.get("eligibilityEvidenceSha256") != evidence.evidence_sha256:
        _fail("APPROVAL_HANDOFF_ELIGIBILITY_HASH_INVALID")
    return payload


def _grant_body(
    *,
    request_id: str,
    approver_id: str,
    eligibility: dict[str, Any],
) -> dict[str, Any]:
    scope = eligibility["scope"]
    head = eligibility["currentHead"]
    artifact = eligibility["correctedArtifact"]
    return {
        "schemaVersion": APPROVAL_HANDOFF_AUTHZ_VERSION,
        "requestId": request_id,
        "approverId": approver_id,
        "tenantId": scope["tenantId"],
        "jobId": scope["jobId"],
        "reviewReportId": scope["reviewReportId"],
        "reviewReportSha256": scope["reviewReportSha256"],
        "baseCanonicalSha256": scope["baseCanonicalSha256"],
        "revisionId": head["revisionId"],
        "revisionSha256": head["revisionSha256"],
        "artifactId": artifact["artifactId"],
        "artifactRecordSha256": artifact["artifactRecordSha256"],
        "musicXmlSha256": artifact["musicXmlSha256"],
        "eligibilityEvidenceSha256": eligibility["eligibilityEvidenceSha256"],
        "allowedAction": "present_for_human_approval",
    }


@dataclass(frozen=True, slots=True)
class ApprovalHandoffGrant:
    request_id: str
    approver_id: str
    tenant_id: str
    job_id: str
    review_report_id: str
    review_report_sha256: str
    base_canonical_sha256: str
    revision_id: str
    revision_sha256: str
    artifact_id: str
    artifact_record_sha256: str
    music_xml_sha256: str
    eligibility_evidence_sha256: str
    grant_sha256: str
    signature_hex: str = field(repr=False)

    def safe_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": APPROVAL_HANDOFF_AUTHZ_VERSION,
            "requestId": self.request_id,
            "approverId": self.approver_id,
            "tenantId": self.tenant_id,
            "jobId": self.job_id,
            "reviewReportId": self.review_report_id,
            "reviewReportSha256": self.review_report_sha256,
            "baseCanonicalSha256": self.base_canonical_sha256,
            "revisionId": self.revision_id,
            "revisionSha256": self.revision_sha256,
            "artifactId": self.artifact_id,
            "artifactRecordSha256": self.artifact_record_sha256,
            "musicXmlSha256": self.music_xml_sha256,
            "eligibilityEvidenceSha256": self.eligibility_evidence_sha256,
            "allowedAction": "present_for_human_approval",
            "grantSha256": self.grant_sha256,
            "signature": "<redacted>",
        }


@dataclass(frozen=True, slots=True, repr=False, init=False)
class HumanApprovalHandoffRequest:
    _payload: Mapping[str, Any]

    def __init__(
        self,
        payload: Mapping[str, Any],
        *,
        _construction_seal: object | None = None,
    ) -> None:
        if _construction_seal is not _CONSTRUCTION_SEAL:
            _fail("APPROVAL_HANDOFF_CONSTRUCTION_FORBIDDEN")
        object.__setattr__(self, "_payload", payload)

    @property
    def request_sha256(self) -> str:
        return _digest(_thaw(self._payload))

    def to_dict(self) -> dict[str, Any]:
        payload = _thaw(self._payload)
        payload["handoffRequestSha256"] = self.request_sha256
        return payload


def issue_approval_handoff_grant(
    *,
    request_id: str,
    approver_id: str,
    eligibility: ApprovalEligibilityEvidence,
    signing_key: bytes,
) -> ApprovalHandoffGrant:
    """Authorize presentation of one exact eligible candidate to one human approver.

    This grant does not authorize recording an approval decision. It only binds one
    Stage 8-K evidence object to one intended human approval handoff.
    """

    if not isinstance(signing_key, bytes) or len(signing_key) < 32:
        _fail("APPROVAL_HANDOFF_KEY_INVALID")
    request_id = _require_id(request_id, "APPROVAL_HANDOFF_REQUEST_ID_INVALID")
    approver_id = _require_id(approver_id, "APPROVAL_HANDOFF_APPROVER_ID_INVALID")
    payload = _eligible_payload(eligibility)
    body = _grant_body(request_id=request_id, approver_id=approver_id, eligibility=payload)
    grant_sha256 = _digest(body)
    signature_hex = hmac.new(
        signing_key,
        APPROVAL_HANDOFF_PURPOSE + _canonical_json(body),
        sha256,
    ).hexdigest()
    return ApprovalHandoffGrant(
        request_id=request_id,
        approver_id=approver_id,
        tenant_id=body["tenantId"],
        job_id=body["jobId"],
        review_report_id=body["reviewReportId"],
        review_report_sha256=body["reviewReportSha256"],
        base_canonical_sha256=body["baseCanonicalSha256"],
        revision_id=body["revisionId"],
        revision_sha256=body["revisionSha256"],
        artifact_id=body["artifactId"],
        artifact_record_sha256=body["artifactRecordSha256"],
        music_xml_sha256=body["musicXmlSha256"],
        eligibility_evidence_sha256=body["eligibilityEvidenceSha256"],
        grant_sha256=grant_sha256,
        signature_hex=signature_hex,
    )


def _verify_grant(
    *,
    grant: ApprovalHandoffGrant,
    eligibility: ApprovalEligibilityEvidence,
    expected_approver_id: str,
    signing_key: bytes,
) -> None:
    if type(grant) is not ApprovalHandoffGrant:
        _fail("APPROVAL_HANDOFF_GRANT_TYPE_INVALID")
    if not isinstance(signing_key, bytes) or len(signing_key) < 32:
        _fail("APPROVAL_HANDOFF_KEY_INVALID")
    expected_approver_id = _require_id(
        expected_approver_id,
        "APPROVAL_HANDOFF_EXPECTED_APPROVER_INVALID",
    )
    payload = _eligible_payload(eligibility)
    expected_body = _grant_body(
        request_id=grant.request_id,
        approver_id=expected_approver_id,
        eligibility=payload,
    )
    actual_body = {
        "schemaVersion": APPROVAL_HANDOFF_AUTHZ_VERSION,
        "requestId": grant.request_id,
        "approverId": grant.approver_id,
        "tenantId": grant.tenant_id,
        "jobId": grant.job_id,
        "reviewReportId": grant.review_report_id,
        "reviewReportSha256": grant.review_report_sha256,
        "baseCanonicalSha256": grant.base_canonical_sha256,
        "revisionId": grant.revision_id,
        "revisionSha256": grant.revision_sha256,
        "artifactId": grant.artifact_id,
        "artifactRecordSha256": grant.artifact_record_sha256,
        "musicXmlSha256": grant.music_xml_sha256,
        "eligibilityEvidenceSha256": grant.eligibility_evidence_sha256,
        "allowedAction": "present_for_human_approval",
    }
    if actual_body != expected_body:
        _fail("APPROVAL_HANDOFF_GRANT_SCOPE_MISMATCH")
    if not hmac.compare_digest(grant.grant_sha256, _digest(actual_body)):
        _fail("APPROVAL_HANDOFF_GRANT_HASH_MISMATCH")
    expected_signature = hmac.new(
        signing_key,
        APPROVAL_HANDOFF_PURPOSE + _canonical_json(actual_body),
        sha256,
    ).hexdigest()
    if not hmac.compare_digest(grant.signature_hex, expected_signature):
        _fail("APPROVAL_HANDOFF_SIGNATURE_INVALID")


def build_human_approval_handoff_request(
    *,
    scope: RevisionScope,
    store: DurableRevisionStore,
    revision: TeacherScoreRevision,
    state: ReviewMusicalState,
    artifact: CorrectedMusicXmlArtifact,
    grant: ApprovalHandoffGrant,
    expected_approver_id: str,
    signing_key: bytes,
) -> HumanApprovalHandoffRequest:
    """Build the last non-authoritative packet before a human approval decision.

    Stage 8-K is recomputed first so stale revisions and substituted artifacts fail
    closed. The result can be presented to a human, but it contains no approval
    decision, cannot record approval, and cannot publish or mutate score state.
    """

    try:
        eligibility = build_approval_eligibility_evidence(
            scope=scope,
            store=store,
            revision=revision,
            state=state,
            artifact=artifact,
        )
    except Stage8ApprovalEligibilityError as exc:
        raise Stage8ApprovalHandoffError("APPROVAL_HANDOFF_ELIGIBILITY_REJECTED") from exc

    payload = _eligible_payload(eligibility)
    _verify_grant(
        grant=grant,
        eligibility=eligibility,
        expected_approver_id=expected_approver_id,
        signing_key=signing_key,
    )

    scope_payload = payload["scope"]
    head = payload["currentHead"]
    corrected = payload["correctedArtifact"]
    body = {
        "schemaVersion": APPROVAL_HANDOFF_VERSION,
        "requestId": grant.request_id,
        "approverId": grant.approver_id,
        "scope": {
            "tenantId": scope_payload["tenantId"],
            "jobId": scope_payload["jobId"],
            "reviewReportId": scope_payload["reviewReportId"],
            "reviewReportSha256": scope_payload["reviewReportSha256"],
            "baseCanonicalSha256": scope_payload["baseCanonicalSha256"],
        },
        "currentHead": {
            "revisionId": head["revisionId"],
            "revisionSha256": head["revisionSha256"],
            "sequence": head["sequence"],
        },
        "correctedArtifact": {
            "artifactId": corrected["artifactId"],
            "artifactRecordSha256": corrected["artifactRecordSha256"],
            "musicXmlSha256": corrected["musicXmlSha256"],
            "safetyReportSha256": corrected["safetyReportSha256"],
            "expectedSemanticSha256": corrected["expectedSemanticSha256"],
            "regeneratedSemanticSha256": corrected["regeneratedSemanticSha256"],
        },
        "eligibilityEvidenceSha256": payload["eligibilityEvidenceSha256"],
        "authorization": {
            "grantSha256": grant.grant_sha256,
            "allowedAction": "present_for_human_approval",
        },
        "requirements": {
            "exactCurrentHead": True,
            "exactEligibleArtifact": True,
            "humanDecisionRequired": True,
            "freshEligibilityRecomputed": True,
        },
        "capabilities": {
            "canPresentForHumanApproval": True,
            "canRecordApproval": False,
            "canPublish": False,
            "canMutate": False,
            "canWrite": False,
            "authoritativeTruth": False,
        },
        "state": {
            "status": "awaiting_human_decision",
            "approvalDecision": None,
            "approvalRecordId": None,
            "publicationRecordId": None,
        },
    }
    return HumanApprovalHandoffRequest(
        _freeze(body),
        _construction_seal=_CONSTRUCTION_SEAL,
    )


__all__ = [
    "APPROVAL_HANDOFF_AUTHZ_VERSION",
    "APPROVAL_HANDOFF_VERSION",
    "ApprovalHandoffGrant",
    "HumanApprovalHandoffRequest",
    "Stage8ApprovalHandoffError",
    "build_human_approval_handoff_request",
    "issue_approval_handoff_grant",
]
