from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256
import hmac
import json
import re
from types import MappingProxyType
from typing import Any, Mapping

from .approval_handoff import (
    APPROVAL_HANDOFF_VERSION,
    ApprovalHandoffGrant,
    HumanApprovalHandoffRequest,
    Stage8ApprovalHandoffError,
    build_human_approval_handoff_request,
)
from .contracts import TeacherScoreRevision
from .corrected_musicxml import CorrectedMusicXmlArtifact
from .durable_revision_store import DurableRevisionStore, RevisionScope
from .musical_state import ReviewMusicalState


HUMAN_APPROVAL_DECISION_AUTHZ_VERSION = "scoremosaic-human-approval-decision-authz-v1"
HUMAN_APPROVAL_RECORD_VERSION = "scoremosaic-human-approval-record-v1"
HUMAN_APPROVAL_DECISION_PURPOSE = b"scoremosaic/teacher-review/human-approval-decision/v1\x00"
_ALLOWED_ACTION = "record_explicit_human_approval"
_ALLOWED_DECISION = "approved"
_ALLOWED_SOURCE = "explicit_human_action"
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_UTC_SECONDS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_CONSTRUCTION_SEAL = object()


class Stage8HumanApprovalRecordError(ValueError):
    """Fail-closed Stage 8-M explicit-human approval record error."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> None:
    raise Stage8HumanApprovalRecordError(code)


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
        _fail("HUMAN_APPROVAL_NON_CANONICAL_VALUE")


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


def _require_decided_at(value: Any) -> str:
    if not isinstance(value, str) or _UTC_SECONDS_RE.fullmatch(value) is None:
        _fail("HUMAN_APPROVAL_DECIDED_AT_INVALID")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        _fail("HUMAN_APPROVAL_DECIDED_AT_INVALID")
    if parsed.year < 2000:
        _fail("HUMAN_APPROVAL_DECIDED_AT_INVALID")
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


def _require_handoff_payload(handoff: HumanApprovalHandoffRequest) -> dict[str, Any]:
    if type(handoff) is not HumanApprovalHandoffRequest:
        _fail("HUMAN_APPROVAL_HANDOFF_TYPE_INVALID")
    payload = handoff.to_dict()
    if payload.get("schemaVersion") != APPROVAL_HANDOFF_VERSION:
        _fail("HUMAN_APPROVAL_HANDOFF_VERSION_INVALID")
    if payload.get("handoffRequestSha256") != handoff.request_sha256:
        _fail("HUMAN_APPROVAL_HANDOFF_HASH_INVALID")
    if payload.get("state") != {
        "status": "awaiting_human_decision",
        "approvalDecision": None,
        "approvalRecordId": None,
        "publicationRecordId": None,
    }:
        _fail("HUMAN_APPROVAL_HANDOFF_STATE_INVALID")
    requirements = payload.get("requirements")
    if not isinstance(requirements, dict) or requirements.get("humanDecisionRequired") is not True:
        _fail("HUMAN_APPROVAL_HANDOFF_REQUIREMENTS_INVALID")
    capabilities = payload.get("capabilities")
    expected_capabilities = {
        "canPresentForHumanApproval": True,
        "canRecordApproval": False,
        "canPublish": False,
        "canMutate": False,
        "canWrite": False,
        "authoritativeTruth": False,
    }
    if capabilities != expected_capabilities:
        _fail("HUMAN_APPROVAL_HANDOFF_CAPABILITY_INVALID")
    return payload


def _decision_body(
    *,
    decision_id: str,
    handoff: dict[str, Any],
    approver_id: str,
    decided_at: str,
    decision_provenance_sha256: str,
) -> dict[str, Any]:
    scope = handoff["scope"]
    head = handoff["currentHead"]
    artifact = handoff["correctedArtifact"]
    return {
        "schemaVersion": HUMAN_APPROVAL_DECISION_AUTHZ_VERSION,
        "decisionId": decision_id,
        "requestId": handoff["requestId"],
        "handoffRequestSha256": handoff["handoffRequestSha256"],
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
        "eligibilityEvidenceSha256": handoff["eligibilityEvidenceSha256"],
        "decision": _ALLOWED_DECISION,
        "decisionSource": _ALLOWED_SOURCE,
        "decidedAt": decided_at,
        "decisionProvenanceSha256": decision_provenance_sha256,
        "allowedAction": _ALLOWED_ACTION,
    }


@dataclass(frozen=True, slots=True)
class HumanApprovalDecisionGrant:
    decision_id: str
    request_id: str
    handoff_request_sha256: str
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
    decided_at: str
    decision_provenance_sha256: str
    grant_sha256: str
    signature_hex: str = field(repr=False)

    def safe_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": HUMAN_APPROVAL_DECISION_AUTHZ_VERSION,
            "decisionId": self.decision_id,
            "requestId": self.request_id,
            "handoffRequestSha256": self.handoff_request_sha256,
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
            "decision": _ALLOWED_DECISION,
            "decisionSource": _ALLOWED_SOURCE,
            "decidedAt": self.decided_at,
            "decisionProvenanceSha256": self.decision_provenance_sha256,
            "allowedAction": _ALLOWED_ACTION,
            "grantSha256": self.grant_sha256,
            "signature": "<redacted>",
        }


@dataclass(frozen=True, slots=True, repr=False, init=False)
class ImmutableHumanApprovalRecord:
    _payload: Mapping[str, Any]

    def __init__(
        self,
        payload: Mapping[str, Any],
        *,
        _construction_seal: object | None = None,
    ) -> None:
        if _construction_seal is not _CONSTRUCTION_SEAL:
            _fail("HUMAN_APPROVAL_RECORD_CONSTRUCTION_FORBIDDEN")
        object.__setattr__(self, "_payload", payload)

    @property
    def record_sha256(self) -> str:
        return _digest(_thaw(self._payload))

    def to_dict(self) -> dict[str, Any]:
        payload = _thaw(self._payload)
        payload["approvalRecordSha256"] = self.record_sha256
        return payload


def issue_explicit_human_approval_decision_grant(
    *,
    decision_id: str,
    handoff: HumanApprovalHandoffRequest,
    approver_id: str,
    decision: str,
    decided_at: str,
    decision_provenance_sha256: str,
    signing_key: bytes,
) -> HumanApprovalDecisionGrant:
    """Seal an externally supplied explicit human approval decision.

    This helper is a contract seam for a future trusted human-action adapter. It does
    not infer a decision and has no route/provider/runtime authority. The caller must
    explicitly supply decision="approved" plus provenance for the human action.
    """

    if decision != _ALLOWED_DECISION:
        _fail("HUMAN_APPROVAL_DECISION_INVALID")
    if not isinstance(signing_key, bytes) or len(signing_key) < 32:
        _fail("HUMAN_APPROVAL_DECISION_KEY_INVALID")
    decision_id = _require_id(decision_id, "HUMAN_APPROVAL_DECISION_ID_INVALID")
    approver_id = _require_id(approver_id, "HUMAN_APPROVAL_APPROVER_ID_INVALID")
    decided_at = _require_decided_at(decided_at)
    decision_provenance_sha256 = _require_hash(
        decision_provenance_sha256,
        "HUMAN_APPROVAL_PROVENANCE_HASH_INVALID",
    )
    handoff_payload = _require_handoff_payload(handoff)
    if approver_id != handoff_payload["approverId"]:
        _fail("HUMAN_APPROVAL_APPROVER_MISMATCH")

    body = _decision_body(
        decision_id=decision_id,
        handoff=handoff_payload,
        approver_id=approver_id,
        decided_at=decided_at,
        decision_provenance_sha256=decision_provenance_sha256,
    )
    grant_sha256 = _digest(body)
    signature_hex = hmac.new(
        signing_key,
        HUMAN_APPROVAL_DECISION_PURPOSE + _canonical_json(body),
        sha256,
    ).hexdigest()
    return HumanApprovalDecisionGrant(
        decision_id=decision_id,
        request_id=body["requestId"],
        handoff_request_sha256=body["handoffRequestSha256"],
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
        decided_at=decided_at,
        decision_provenance_sha256=decision_provenance_sha256,
        grant_sha256=grant_sha256,
        signature_hex=signature_hex,
    )


def _verify_decision_grant(
    *,
    grant: HumanApprovalDecisionGrant,
    handoff: dict[str, Any],
    expected_approver_id: str,
    signing_key: bytes,
) -> None:
    if type(grant) is not HumanApprovalDecisionGrant:
        _fail("HUMAN_APPROVAL_DECISION_GRANT_TYPE_INVALID")
    if not isinstance(signing_key, bytes) or len(signing_key) < 32:
        _fail("HUMAN_APPROVAL_DECISION_KEY_INVALID")
    expected_approver_id = _require_id(
        expected_approver_id,
        "HUMAN_APPROVAL_EXPECTED_APPROVER_INVALID",
    )
    decided_at = _require_decided_at(grant.decided_at)
    provenance = _require_hash(
        grant.decision_provenance_sha256,
        "HUMAN_APPROVAL_PROVENANCE_HASH_INVALID",
    )
    expected_body = _decision_body(
        decision_id=grant.decision_id,
        handoff=handoff,
        approver_id=expected_approver_id,
        decided_at=decided_at,
        decision_provenance_sha256=provenance,
    )
    actual_body = {
        "schemaVersion": HUMAN_APPROVAL_DECISION_AUTHZ_VERSION,
        "decisionId": grant.decision_id,
        "requestId": grant.request_id,
        "handoffRequestSha256": grant.handoff_request_sha256,
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
        "decision": _ALLOWED_DECISION,
        "decisionSource": _ALLOWED_SOURCE,
        "decidedAt": grant.decided_at,
        "decisionProvenanceSha256": grant.decision_provenance_sha256,
        "allowedAction": _ALLOWED_ACTION,
    }
    if actual_body != expected_body:
        _fail("HUMAN_APPROVAL_DECISION_SCOPE_MISMATCH")
    if not hmac.compare_digest(grant.grant_sha256, _digest(actual_body)):
        _fail("HUMAN_APPROVAL_DECISION_GRANT_HASH_MISMATCH")
    expected_signature = hmac.new(
        signing_key,
        HUMAN_APPROVAL_DECISION_PURPOSE + _canonical_json(actual_body),
        sha256,
    ).hexdigest()
    if not hmac.compare_digest(grant.signature_hex, expected_signature):
        _fail("HUMAN_APPROVAL_DECISION_SIGNATURE_INVALID")


def build_immutable_human_approval_record(
    *,
    scope: RevisionScope,
    store: DurableRevisionStore,
    revision: TeacherScoreRevision,
    state: ReviewMusicalState,
    artifact: CorrectedMusicXmlArtifact,
    handoff_grant: ApprovalHandoffGrant,
    handoff_signing_key: bytes,
    handoff: HumanApprovalHandoffRequest,
    decision_grant: HumanApprovalDecisionGrant,
    decision_signing_key: bytes,
    expected_approver_id: str,
) -> ImmutableHumanApprovalRecord:
    """Capture one explicit human approval without granting publication authority.

    The Stage 8-L handoff is freshly rebuilt first. A stale revision, changed artifact,
    wrong approver, changed handoff, or forged decision grant fails closed. The output
    is immutable approval evidence only; no production persistence or publication is
    activated.
    """

    supplied_handoff = _require_handoff_payload(handoff)
    try:
        rebuilt_handoff = build_human_approval_handoff_request(
            scope=scope,
            store=store,
            revision=revision,
            state=state,
            artifact=artifact,
            grant=handoff_grant,
            expected_approver_id=expected_approver_id,
            signing_key=handoff_signing_key,
        )
    except Stage8ApprovalHandoffError as exc:
        raise Stage8HumanApprovalRecordError("HUMAN_APPROVAL_HANDOFF_REVALIDATION_REJECTED") from exc

    rebuilt_payload = _require_handoff_payload(rebuilt_handoff)
    if not hmac.compare_digest(handoff.request_sha256, rebuilt_handoff.request_sha256):
        _fail("HUMAN_APPROVAL_HANDOFF_STALE_OR_SUBSTITUTED")
    if supplied_handoff != rebuilt_payload:
        _fail("HUMAN_APPROVAL_HANDOFF_RECORD_MISMATCH")

    _verify_decision_grant(
        grant=decision_grant,
        handoff=rebuilt_payload,
        expected_approver_id=expected_approver_id,
        signing_key=decision_signing_key,
    )

    scope_payload = rebuilt_payload["scope"]
    head = rebuilt_payload["currentHead"]
    corrected = rebuilt_payload["correctedArtifact"]
    record_seed = {
        "handoffRequestSha256": rebuilt_payload["handoffRequestSha256"],
        "decisionGrantSha256": decision_grant.grant_sha256,
    }
    approval_record_id = "approval_" + _digest(record_seed)[:32]
    body = {
        "schemaVersion": HUMAN_APPROVAL_RECORD_VERSION,
        "approvalRecordId": approval_record_id,
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
        "eligibilityEvidenceSha256": rebuilt_payload["eligibilityEvidenceSha256"],
        "handoff": {
            "requestId": rebuilt_payload["requestId"],
            "handoffRequestSha256": rebuilt_payload["handoffRequestSha256"],
        },
        "humanDecision": {
            "decisionId": decision_grant.decision_id,
            "approverId": decision_grant.approver_id,
            "decision": _ALLOWED_DECISION,
            "decisionSource": _ALLOWED_SOURCE,
            "decidedAt": decision_grant.decided_at,
            "decisionProvenanceSha256": decision_grant.decision_provenance_sha256,
        },
        "authorization": {
            "decisionGrantSha256": decision_grant.grant_sha256,
            "allowedAction": _ALLOWED_ACTION,
        },
        "approval": {
            "status": "approved",
            "immutable": True,
            "exactHumanDecision": True,
            "freshHandoffRevalidated": True,
            "productionPersistenceActivated": False,
        },
        "publication": {
            "eligible": False,
            "granted": False,
            "publicationRecordId": None,
        },
        "capabilities": {
            "humanApprovalCaptured": True,
            "canPublish": False,
            "canMutate": False,
            "canWrite": False,
            "productionPersistence": False,
            "authoritativeMusicalTruth": False,
        },
    }
    return ImmutableHumanApprovalRecord(
        _freeze(body),
        _construction_seal=_CONSTRUCTION_SEAL,
    )


__all__ = [
    "HUMAN_APPROVAL_DECISION_AUTHZ_VERSION",
    "HUMAN_APPROVAL_RECORD_VERSION",
    "HumanApprovalDecisionGrant",
    "ImmutableHumanApprovalRecord",
    "Stage8HumanApprovalRecordError",
    "build_immutable_human_approval_record",
    "issue_explicit_human_approval_decision_grant",
]
