from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import hmac
import json
from types import MappingProxyType
from typing import Any, Mapping

from .contracts import TeacherScoreRevision
from .corrected_musicxml import CorrectedMusicXmlArtifact, build_corrected_musicxml_artifact
from .durable_revision_store import DurableRevisionStore, DurableRevisionStoreError, RevisionScope
from .musical_state import ReviewMusicalState


APPROVAL_ELIGIBILITY_VERSION = "scoremosaic-approval-eligibility-v1"
_CONSTRUCTION_SEAL = object()


class Stage8ApprovalEligibilityError(ValueError):
    """Stable fail-closed Stage 8-K eligibility error."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> None:
    raise Stage8ApprovalEligibilityError(code)


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
        _fail("APPROVAL_ELIGIBILITY_NON_CANONICAL_VALUE")


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


@dataclass(frozen=True, slots=True, repr=False, init=False)
class ApprovalEligibilityEvidence:
    _payload: Mapping[str, Any]

    def __init__(
        self,
        payload: Mapping[str, Any],
        *,
        _construction_seal: object | None = None,
    ) -> None:
        if _construction_seal is not _CONSTRUCTION_SEAL:
            _fail("APPROVAL_ELIGIBILITY_CONSTRUCTION_FORBIDDEN")
        object.__setattr__(self, "_payload", payload)

    @property
    def evidence_sha256(self) -> str:
        return _digest(_thaw(self._payload))

    def to_dict(self) -> dict[str, Any]:
        payload = _thaw(self._payload)
        payload["eligibilityEvidenceSha256"] = self.evidence_sha256
        return payload


def _require_exact_current_revision(
    *,
    scope: RevisionScope,
    store: DurableRevisionStore,
    revision: TeacherScoreRevision,
) -> tuple[dict[str, Any], int]:
    if type(scope) is not RevisionScope:
        _fail("APPROVAL_ELIGIBILITY_SCOPE_INVALID")
    if type(store) is not DurableRevisionStore:
        _fail("APPROVAL_ELIGIBILITY_STORE_INVALID")
    if type(revision) is not TeacherScoreRevision:
        _fail("APPROVAL_ELIGIBILITY_REVISION_INVALID")

    revision_record = revision.to_dict()
    try:
        head = store.load_head(scope)
    except DurableRevisionStoreError as exc:
        raise Stage8ApprovalEligibilityError("APPROVAL_ELIGIBILITY_STORE_REJECTED") from exc
    if head is None:
        _fail("APPROVAL_ELIGIBILITY_HEAD_MISSING")

    if (
        revision_record.get("revisionId") != head.revision_id
        or revision_record.get("revisionSha256") != head.revision_sha256
    ):
        _fail("APPROVAL_ELIGIBILITY_STALE_REVISION")

    try:
        persisted = store.load_revision(scope, head.revision_sha256)
    except DurableRevisionStoreError as exc:
        raise Stage8ApprovalEligibilityError("APPROVAL_ELIGIBILITY_STORE_REJECTED") from exc

    if persisted != revision_record:
        _fail("APPROVAL_ELIGIBILITY_REVISION_PERSISTENCE_MISMATCH")
    return persisted, head.sequence


def _require_exact_rebuilt_artifact(
    *,
    scope: RevisionScope,
    revision: TeacherScoreRevision,
    state: ReviewMusicalState,
    artifact: CorrectedMusicXmlArtifact,
) -> dict[str, Any]:
    if type(state) is not ReviewMusicalState:
        _fail("APPROVAL_ELIGIBILITY_STATE_INVALID")
    if type(artifact) is not CorrectedMusicXmlArtifact:
        _fail("APPROVAL_ELIGIBILITY_ARTIFACT_INVALID")

    try:
        rebuilt = build_corrected_musicxml_artifact(
            scope=scope,
            revision=revision,
            state=state,
        )
    except ValueError as exc:
        raise Stage8ApprovalEligibilityError("APPROVAL_ELIGIBILITY_ARTIFACT_REBUILD_FAILED") from exc

    supplied_record = artifact.to_dict()
    rebuilt_record = rebuilt.to_dict()
    supplied_document_sha = sha256(artifact.document).hexdigest()
    rebuilt_document_sha = sha256(rebuilt.document).hexdigest()

    if not hmac.compare_digest(supplied_document_sha, rebuilt_document_sha):
        _fail("APPROVAL_ELIGIBILITY_ARTIFACT_DOCUMENT_MISMATCH")
    if supplied_record != rebuilt_record:
        _fail("APPROVAL_ELIGIBILITY_ARTIFACT_RECORD_MISMATCH")

    required_locked = {
        "roundTripMatch": True,
        "status": "draft",
        "immutable": True,
        "approvalEligible": False,
        "publicationEligible": False,
    }
    for key, expected in required_locked.items():
        if rebuilt_record.get(key) is not expected and rebuilt_record.get(key) != expected:
            _fail("APPROVAL_ELIGIBILITY_ARTIFACT_CAPABILITY_INVALID")

    return rebuilt_record


def build_approval_eligibility_evidence(
    *,
    scope: RevisionScope,
    store: DurableRevisionStore,
    revision: TeacherScoreRevision,
    state: ReviewMusicalState,
    artifact: CorrectedMusicXmlArtifact,
) -> ApprovalEligibilityEvidence:
    """Derive non-authoritative approval-candidate evidence for the exact current revision.

    This function grants no approval or publication authority. It accepts only an exact
    durable head revision and an exact deterministic Stage 8-F artifact rebuilt from the
    same revision/state pair. Musical validation issues make the candidate ineligible;
    identity, persistence, or artifact substitutions fail closed instead.
    """

    persisted, head_sequence = _require_exact_current_revision(
        scope=scope,
        store=store,
        revision=revision,
    )
    artifact_record = _require_exact_rebuilt_artifact(
        scope=scope,
        revision=revision,
        state=state,
        artifact=artifact,
    )

    exact_bindings = (
        ("tenantId", scope.tenant_id),
        ("jobId", scope.job_id),
        ("reviewReportId", scope.review_report_id),
        ("reviewReportSha256", scope.review_report_sha256),
        ("baseCanonicalSha256", scope.base_canonical_sha256),
        ("revisionId", persisted["revisionId"]),
        ("revisionSha256", persisted["revisionSha256"]),
        ("stateSha256", persisted["resultingMusicalStateSha256"]),
        ("validationReportSha256", persisted["validationReportSha256"]),
    )
    for key, expected in exact_bindings:
        if artifact_record.get(key) != expected:
            _fail("APPROVAL_ELIGIBILITY_ARTIFACT_SCOPE_MISMATCH")

    if artifact_record["blockingIssueCount"] != persisted["blockingIssueCount"]:
        _fail("APPROVAL_ELIGIBILITY_BLOCKING_COUNT_MISMATCH")
    if artifact_record["unresolvedIssueCount"] != persisted["unresolvedIssueCount"]:
        _fail("APPROVAL_ELIGIBILITY_UNRESOLVED_COUNT_MISMATCH")

    reasons: list[str] = []
    if persisted["blockingIssueCount"] != 0:
        reasons.append("BLOCKING_ISSUES_PRESENT")
    if persisted["unresolvedIssueCount"] != 0:
        reasons.append("UNRESOLVED_ISSUES_PRESENT")
    candidate_eligible = not reasons

    body = {
        "schemaVersion": APPROVAL_ELIGIBILITY_VERSION,
        "scope": {
            "tenantId": scope.tenant_id,
            "jobId": scope.job_id,
            "reviewReportId": scope.review_report_id,
            "reviewReportSha256": scope.review_report_sha256,
            "baseCanonicalSha256": scope.base_canonical_sha256,
        },
        "currentHead": {
            "revisionId": persisted["revisionId"],
            "revisionSha256": persisted["revisionSha256"],
            "sequence": head_sequence,
        },
        "revision": {
            "reviewerId": persisted["reviewerId"],
            "stateSha256": persisted["resultingMusicalStateSha256"],
            "validationReportSha256": persisted["validationReportSha256"],
            "blockingIssueCount": persisted["blockingIssueCount"],
            "unresolvedIssueCount": persisted["unresolvedIssueCount"],
        },
        "correctedArtifact": {
            "artifactId": artifact_record["artifactId"],
            "artifactRecordSha256": artifact_record["artifactRecordSha256"],
            "musicXmlSha256": artifact_record["musicXmlSha256"],
            "byteSize": artifact_record["byteSize"],
            "mediaType": artifact_record["mediaType"],
            "safetyReportSha256": artifact_record["safetyReportSha256"],
            "regeneratedCanonicalSha256": artifact_record["regeneratedCanonicalSha256"],
            "expectedSemanticSha256": artifact_record["expectedSemanticSha256"],
            "regeneratedSemanticSha256": artifact_record["regeneratedSemanticSha256"],
        },
        "checks": {
            "exactCurrentHead": True,
            "exactPersistedRevision": True,
            "exactRebuiltArtifact": True,
            "generatedMusicXmlSafe": True,
            "semanticRoundTripMatch": True,
        },
        "eligibility": {
            "candidateEligible": candidate_eligible,
            "reasons": reasons,
        },
        "authority": {
            "approvalGranted": False,
            "publicationGranted": False,
            "mutationGranted": False,
            "writeGranted": False,
            "authoritativeTruth": False,
        },
    }
    return ApprovalEligibilityEvidence(
        _freeze(body),
        _construction_seal=_CONSTRUCTION_SEAL,
    )


__all__ = [
    "APPROVAL_ELIGIBILITY_VERSION",
    "ApprovalEligibilityEvidence",
    "Stage8ApprovalEligibilityError",
    "build_approval_eligibility_evidence",
]
