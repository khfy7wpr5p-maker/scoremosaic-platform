from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import hmac
import json
import re
from types import MappingProxyType
from typing import Any, Mapping

from .approval_handoff import ApprovalHandoffGrant, HumanApprovalHandoffRequest
from .approval_record import HumanApprovalDecisionGrant, ImmutableHumanApprovalRecord
from .contracts import TeacherScoreRevision
from .corrected_musicxml import CorrectedMusicXmlArtifact
from .durable_revision_store import DurableRevisionStore, RevisionScope
from .musical_state import ReviewMusicalState
from .publication_eligibility import (
    PUBLICATION_ELIGIBILITY_VERSION,
    PublicationEligibilityEvidence,
    Stage8PublicationEligibilityError,
    build_publication_eligibility_evidence,
)


PUBLICATION_HANDOFF_AUTHZ_VERSION = "scoremosaic-publication-handoff-authz-v1"
PUBLICATION_HANDOFF_VERSION = "scoremosaic-publication-handoff-v1"
PUBLICATION_HANDOFF_PURPOSE = b"scoremosaic/teacher-review/publication-handoff/v1\x00"
_ALLOWED_ACTION = "present_for_publication_execution"
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_CONSTRUCTION_SEAL = object()


class Stage8PublicationHandoffError(ValueError):
    """Fail-closed Stage 8-O publication-handoff error."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> None:
    raise Stage8PublicationHandoffError(code)


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
        _fail("PUBLICATION_HANDOFF_NON_CANONICAL_VALUE")


def _digest(value: Any) -> str:
    return sha256(_canonical_json(value)).hexdigest()


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


def _require_id(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 200 or _ID_RE.fullmatch(value) is None:
        _fail(code)
    return value


def _require_hash(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HASH_RE.fullmatch(value) is None:
        _fail(code)
    return value


def _require_eligibility(evidence: PublicationEligibilityEvidence) -> dict[str, Any]:
    if type(evidence) is not PublicationEligibilityEvidence:
        _fail("PUBLICATION_HANDOFF_ELIGIBILITY_TYPE_INVALID")
    payload = evidence.to_dict()
    if payload.get("schemaVersion") != PUBLICATION_ELIGIBILITY_VERSION:
        _fail("PUBLICATION_HANDOFF_ELIGIBILITY_VERSION_INVALID")
    if payload.get("publicationEligibilityEvidenceSha256") != evidence.evidence_sha256:
        _fail("PUBLICATION_HANDOFF_ELIGIBILITY_HASH_INVALID")
    if payload.get("eligibility") != {
        "candidateEligibleForPublicationHandoff": True,
        "productionPublicationEligible": False,
        "productionBlockers": [
            "PRODUCTION_PUBLICATION_AUTHORIZATION_REQUIRED",
            "PRODUCTION_PERSISTENCE_REQUIRED",
        ],
    }:
        _fail("PUBLICATION_HANDOFF_ELIGIBILITY_STATE_INVALID")
    if payload.get("authority") != {
        "publicationGranted": False,
        "publisherAuthority": False,
        "writeGranted": False,
        "mutationGranted": False,
        "productionPersistence": False,
        "authoritativeMusicalTruth": False,
    }:
        _fail("PUBLICATION_HANDOFF_ELIGIBILITY_AUTHORITY_INVALID")
    return payload


def _grant_body(
    *,
    request_id: str,
    publisher_id: str,
    eligibility: dict[str, Any],
) -> dict[str, Any]:
    scope = eligibility["scope"]
    head = eligibility["currentHead"]
    artifact = eligibility["correctedArtifact"]
    approval = eligibility["humanApproval"]
    return {
        "schemaVersion": PUBLICATION_HANDOFF_AUTHZ_VERSION,
        "requestId": request_id,
        "publisherId": publisher_id,
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
        "approvalRecordId": approval["approvalRecordId"],
        "approvalRecordSha256": approval["approvalRecordSha256"],
        "publicationEligibilityEvidenceSha256": eligibility["publicationEligibilityEvidenceSha256"],
        "allowedAction": _ALLOWED_ACTION,
    }


@dataclass(frozen=True, slots=True)
class PublicationHandoffGrant:
    request_id: str
    publisher_id: str
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
    approval_record_id: str
    approval_record_sha256: str
    publication_eligibility_evidence_sha256: str
    grant_sha256: str
    signature_hex: str = field(repr=False)

    def safe_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": PUBLICATION_HANDOFF_AUTHZ_VERSION,
            "requestId": self.request_id,
            "publisherId": self.publisher_id,
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
            "approvalRecordId": self.approval_record_id,
            "approvalRecordSha256": self.approval_record_sha256,
            "publicationEligibilityEvidenceSha256": self.publication_eligibility_evidence_sha256,
            "allowedAction": _ALLOWED_ACTION,
            "grantSha256": self.grant_sha256,
            "signature": "<redacted>",
        }


@dataclass(frozen=True, slots=True, repr=False, init=False)
class PublicationHandoffRequest:
    _payload: Mapping[str, Any]

    def __init__(
        self,
        payload: Mapping[str, Any],
        *,
        _construction_seal: object | None = None,
    ) -> None:
        if _construction_seal is not _CONSTRUCTION_SEAL:
            _fail("PUBLICATION_HANDOFF_CONSTRUCTION_FORBIDDEN")
        object.__setattr__(self, "_payload", payload)

    @property
    def request_sha256(self) -> str:
        return _digest(_thaw(self._payload))

    def to_dict(self) -> dict[str, Any]:
        payload = _thaw(self._payload)
        payload["publicationHandoffRequestSha256"] = self.request_sha256
        return payload


def issue_publication_handoff_grant(
    *,
    request_id: str,
    publisher_id: str,
    eligibility: PublicationEligibilityEvidence,
    signing_key: bytes,
) -> PublicationHandoffGrant:
    """Authorize presentation to one publisher identity, never publication execution."""

    if not isinstance(signing_key, bytes) or len(signing_key) < 32:
        _fail("PUBLICATION_HANDOFF_KEY_INVALID")
    request_id = _require_id(request_id, "PUBLICATION_HANDOFF_REQUEST_ID_INVALID")
    publisher_id = _require_id(publisher_id, "PUBLICATION_HANDOFF_PUBLISHER_ID_INVALID")
    payload = _require_eligibility(eligibility)
    body = _grant_body(request_id=request_id, publisher_id=publisher_id, eligibility=payload)
    grant_sha256 = _digest(body)
    signature_hex = hmac.new(
        signing_key,
        PUBLICATION_HANDOFF_PURPOSE + _canonical_json(body),
        sha256,
    ).hexdigest()
    return PublicationHandoffGrant(
        request_id=request_id,
        publisher_id=publisher_id,
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
        approval_record_id=body["approvalRecordId"],
        approval_record_sha256=body["approvalRecordSha256"],
        publication_eligibility_evidence_sha256=body["publicationEligibilityEvidenceSha256"],
        grant_sha256=grant_sha256,
        signature_hex=signature_hex,
    )


def _verify_grant(
    *,
    grant: PublicationHandoffGrant,
    eligibility: dict[str, Any],
    expected_publisher_id: str,
    signing_key: bytes,
) -> None:
    if type(grant) is not PublicationHandoffGrant:
        _fail("PUBLICATION_HANDOFF_GRANT_TYPE_INVALID")
    if not isinstance(signing_key, bytes) or len(signing_key) < 32:
        _fail("PUBLICATION_HANDOFF_KEY_INVALID")
    expected_publisher_id = _require_id(
        expected_publisher_id,
        "PUBLICATION_HANDOFF_EXPECTED_PUBLISHER_INVALID",
    )
    expected = _grant_body(
        request_id=grant.request_id,
        publisher_id=expected_publisher_id,
        eligibility=eligibility,
    )
    actual = {
        "schemaVersion": PUBLICATION_HANDOFF_AUTHZ_VERSION,
        "requestId": grant.request_id,
        "publisherId": grant.publisher_id,
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
        "approvalRecordId": grant.approval_record_id,
        "approvalRecordSha256": grant.approval_record_sha256,
        "publicationEligibilityEvidenceSha256": grant.publication_eligibility_evidence_sha256,
        "allowedAction": _ALLOWED_ACTION,
    }
    if actual != expected:
        _fail("PUBLICATION_HANDOFF_GRANT_SCOPE_MISMATCH")
    if not hmac.compare_digest(grant.grant_sha256, _digest(actual)):
        _fail("PUBLICATION_HANDOFF_GRANT_HASH_MISMATCH")
    expected_signature = hmac.new(
        signing_key,
        PUBLICATION_HANDOFF_PURPOSE + _canonical_json(actual),
        sha256,
    ).hexdigest()
    if not hmac.compare_digest(grant.signature_hex, expected_signature):
        _fail("PUBLICATION_HANDOFF_SIGNATURE_INVALID")


def build_publication_handoff_request(
    *,
    scope: RevisionScope,
    store: DurableRevisionStore,
    revision: TeacherScoreRevision,
    state: ReviewMusicalState,
    artifact: CorrectedMusicXmlArtifact,
    approval_handoff_grant: ApprovalHandoffGrant,
    approval_handoff_signing_key: bytes,
    approval_handoff: HumanApprovalHandoffRequest,
    decision_grant: HumanApprovalDecisionGrant,
    decision_signing_key: bytes,
    expected_approver_id: str,
    approval_record: ImmutableHumanApprovalRecord,
    grant: PublicationHandoffGrant,
    expected_publisher_id: str,
    signing_key: bytes,
) -> PublicationHandoffRequest:
    """Build the final non-executing request before external publication execution."""

    try:
        eligibility = build_publication_eligibility_evidence(
            scope=scope,
            store=store,
            revision=revision,
            state=state,
            artifact=artifact,
            handoff_grant=approval_handoff_grant,
            handoff_signing_key=approval_handoff_signing_key,
            handoff=approval_handoff,
            decision_grant=decision_grant,
            decision_signing_key=decision_signing_key,
            expected_approver_id=expected_approver_id,
            approval_record=approval_record,
        )
    except Stage8PublicationEligibilityError as exc:
        raise Stage8PublicationHandoffError(
            "PUBLICATION_HANDOFF_ELIGIBILITY_REVALIDATION_REJECTED"
        ) from exc

    eligibility_payload = _require_eligibility(eligibility)
    _verify_grant(
        grant=grant,
        eligibility=eligibility_payload,
        expected_publisher_id=expected_publisher_id,
        signing_key=signing_key,
    )
    scope_payload = eligibility_payload["scope"]
    head = eligibility_payload["currentHead"]
    corrected = eligibility_payload["correctedArtifact"]
    approval = eligibility_payload["humanApproval"]
    body = {
        "schemaVersion": PUBLICATION_HANDOFF_VERSION,
        "requestId": grant.request_id,
        "publisherId": grant.publisher_id,
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
        },
        "humanApproval": {
            "approvalRecordId": approval["approvalRecordId"],
            "approvalRecordSha256": approval["approvalRecordSha256"],
            "approverId": approval["approverId"],
        },
        "publicationEligibilityEvidenceSha256": eligibility.evidence_sha256,
        "authorization": {
            "grantSha256": grant.grant_sha256,
            "allowedAction": _ALLOWED_ACTION,
            "productionPublicationAuthority": False,
        },
        "state": {
            "status": "awaiting_external_publication_execution",
            "publicationRecordId": None,
            "publishedArtifactId": None,
        },
        "requirements": {
            "externalPublicationExecutionRequired": True,
            "productionPersistenceRequired": True,
        },
        "capabilities": {
            "canPresentForPublicationExecution": True,
            "canExecutePublication": False,
            "canWriteExternal": False,
            "canPersistProduction": False,
            "canMutate": False,
            "publicationGranted": False,
            "authoritativeMusicalTruth": False,
        },
    }
    return PublicationHandoffRequest(
        _freeze(body),
        _construction_seal=_CONSTRUCTION_SEAL,
    )


__all__ = [
    "PUBLICATION_HANDOFF_AUTHZ_VERSION",
    "PUBLICATION_HANDOFF_VERSION",
    "PublicationHandoffGrant",
    "PublicationHandoffRequest",
    "Stage8PublicationHandoffError",
    "build_publication_handoff_request",
    "issue_publication_handoff_grant",
]
