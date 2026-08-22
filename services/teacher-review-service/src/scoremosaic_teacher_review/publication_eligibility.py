from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import hmac
import json
from types import MappingProxyType
from typing import Any, Mapping

from .approval_handoff import ApprovalHandoffGrant, HumanApprovalHandoffRequest
from .approval_record import (
    HUMAN_APPROVAL_RECORD_VERSION,
    HumanApprovalDecisionGrant,
    ImmutableHumanApprovalRecord,
    Stage8HumanApprovalRecordError,
    build_immutable_human_approval_record,
)
from .contracts import TeacherScoreRevision
from .corrected_musicxml import CorrectedMusicXmlArtifact
from .durable_revision_store import DurableRevisionStore, RevisionScope
from .musical_state import ReviewMusicalState


PUBLICATION_ELIGIBILITY_VERSION = "scoremosaic-publication-eligibility-v1"
_CONSTRUCTION_SEAL = object()


class Stage8PublicationEligibilityError(ValueError):
    """Fail-closed Stage 8-N publication-eligibility error."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> None:
    raise Stage8PublicationEligibilityError(code)


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
        _fail("PUBLICATION_ELIGIBILITY_NON_CANONICAL_VALUE")


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


def _require_approval_record(record: ImmutableHumanApprovalRecord) -> dict[str, Any]:
    if type(record) is not ImmutableHumanApprovalRecord:
        _fail("PUBLICATION_ELIGIBILITY_APPROVAL_RECORD_TYPE_INVALID")
    payload = record.to_dict()
    if payload.get("schemaVersion") != HUMAN_APPROVAL_RECORD_VERSION:
        _fail("PUBLICATION_ELIGIBILITY_APPROVAL_RECORD_VERSION_INVALID")
    if payload.get("approvalRecordSha256") != record.record_sha256:
        _fail("PUBLICATION_ELIGIBILITY_APPROVAL_RECORD_HASH_INVALID")
    if payload.get("approval") != {
        "status": "approved",
        "immutable": True,
        "exactHumanDecision": True,
        "freshHandoffRevalidated": True,
        "productionPersistenceActivated": False,
    }:
        _fail("PUBLICATION_ELIGIBILITY_APPROVAL_STATE_INVALID")
    if payload.get("publication") != {
        "eligible": False,
        "granted": False,
        "publicationRecordId": None,
    }:
        _fail("PUBLICATION_ELIGIBILITY_UPSTREAM_PUBLICATION_INVALID")
    if payload.get("capabilities") != {
        "humanApprovalCaptured": True,
        "canPublish": False,
        "canMutate": False,
        "canWrite": False,
        "productionPersistence": False,
        "authoritativeMusicalTruth": False,
    }:
        _fail("PUBLICATION_ELIGIBILITY_UPSTREAM_CAPABILITY_INVALID")
    return payload


@dataclass(frozen=True, slots=True, repr=False, init=False)
class PublicationEligibilityEvidence:
    _payload: Mapping[str, Any]

    def __init__(
        self,
        payload: Mapping[str, Any],
        *,
        _construction_seal: object | None = None,
    ) -> None:
        if _construction_seal is not _CONSTRUCTION_SEAL:
            _fail("PUBLICATION_ELIGIBILITY_CONSTRUCTION_FORBIDDEN")
        object.__setattr__(self, "_payload", payload)

    @property
    def evidence_sha256(self) -> str:
        return _digest(_thaw(self._payload))

    def to_dict(self) -> dict[str, Any]:
        payload = _thaw(self._payload)
        payload["publicationEligibilityEvidenceSha256"] = self.evidence_sha256
        return payload


def build_publication_eligibility_evidence(
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
    approval_record: ImmutableHumanApprovalRecord,
) -> PublicationEligibilityEvidence:
    """Derive non-authoritative publication-handoff eligibility from exact approval.

    The complete Stage 8-M record is freshly rebuilt from current durable inputs before
    evidence is emitted. This function never authorizes publication, storage, mutation,
    networking, or a publisher. It only proves that an exact human-approved artifact
    may proceed to a later publication-authorization handoff contract.
    """

    supplied = _require_approval_record(approval_record)
    try:
        rebuilt = build_immutable_human_approval_record(
            scope=scope,
            store=store,
            revision=revision,
            state=state,
            artifact=artifact,
            handoff_grant=handoff_grant,
            handoff_signing_key=handoff_signing_key,
            handoff=handoff,
            decision_grant=decision_grant,
            decision_signing_key=decision_signing_key,
            expected_approver_id=expected_approver_id,
        )
    except Stage8HumanApprovalRecordError as exc:
        raise Stage8PublicationEligibilityError(
            "PUBLICATION_ELIGIBILITY_APPROVAL_REVALIDATION_REJECTED"
        ) from exc

    rebuilt_payload = _require_approval_record(rebuilt)
    if not hmac.compare_digest(approval_record.record_sha256, rebuilt.record_sha256):
        _fail("PUBLICATION_ELIGIBILITY_APPROVAL_RECORD_SUBSTITUTED")
    if supplied != rebuilt_payload:
        _fail("PUBLICATION_ELIGIBILITY_APPROVAL_RECORD_MISMATCH")

    scope_payload = rebuilt_payload["scope"]
    head = rebuilt_payload["currentHead"]
    corrected = rebuilt_payload["correctedArtifact"]
    human_decision = rebuilt_payload["humanDecision"]
    body = {
        "schemaVersion": PUBLICATION_ELIGIBILITY_VERSION,
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
        "humanApproval": {
            "approvalRecordId": rebuilt_payload["approvalRecordId"],
            "approvalRecordSha256": rebuilt_payload["approvalRecordSha256"],
            "decisionId": human_decision["decisionId"],
            "approverId": human_decision["approverId"],
            "decisionProvenanceSha256": human_decision["decisionProvenanceSha256"],
        },
        "checks": {
            "exactCurrentApprovalRecord": True,
            "exactCurrentHead": True,
            "exactApprovedArtifact": True,
            "explicitHumanApproval": True,
            "freshApprovalRevalidated": True,
        },
        "eligibility": {
            "candidateEligibleForPublicationHandoff": True,
            "productionPublicationEligible": False,
            "productionBlockers": [
                "PRODUCTION_PUBLICATION_AUTHORIZATION_REQUIRED",
                "PRODUCTION_PERSISTENCE_REQUIRED",
            ],
        },
        "authority": {
            "publicationGranted": False,
            "publisherAuthority": False,
            "writeGranted": False,
            "mutationGranted": False,
            "productionPersistence": False,
            "authoritativeMusicalTruth": False,
        },
    }
    return PublicationEligibilityEvidence(
        _freeze(body),
        _construction_seal=_CONSTRUCTION_SEAL,
    )


__all__ = [
    "PUBLICATION_ELIGIBILITY_VERSION",
    "PublicationEligibilityEvidence",
    "Stage8PublicationEligibilityError",
    "build_publication_eligibility_evidence",
]
