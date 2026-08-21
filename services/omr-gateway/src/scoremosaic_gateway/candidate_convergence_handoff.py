"""Stage 7 verified candidate handoff from durable Stage 6 persistence.

This module is the Gateway-side trust boundary for Canonical/Ensemble admission.
It never accepts caller-controlled filesystem paths and never exports persistence
keys, HMAC material, credentials, or mutable storage authority. Candidate bytes
are loaded only through the Stage 6 HMAC-sealed, read-after-hash-verified store.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
import re
from typing import Any, Mapping

from .dispatch_identity import DispatchIdentityBinding, DispatchIdentityError, build_dispatch_identity
from .engine_result_ingestion import (
    ENGINE_RESULT_INGESTION_VERSION,
    EngineIngestionOutcome,
    EngineResultIngestionError,
    load_persisted_candidate_musicxml,
    load_persisted_candidate_record,
    summarize_partial_success,
)
from .minimum_staging_vertical_slice import StagingUploadProvider
from .orchestration import ENGINE_NAMES, OrchestrationContractError, verify_orchestration_plan

CANDIDATE_CONVERGENCE_HANDOFF_VERSION = "scoremosaic-candidate-convergence-handoff-v1"
MAX_CONVERGENCE_MUSICXML_BYTES = 16 * 1024 * 1024

_JOB_RE = re.compile(r"job_[A-Za-z0-9_-]{8,80}\Z")
_PLAN_RE = re.compile(r"plan_[0-9a-f]{24}\Z")
_RUN_RE = re.compile(r"run_[0-9a-f]{24}\Z")
_ARTIFACT_RE = re.compile(r"artifact_[0-9a-f]{24}\Z")
_CANDIDATE_RE = re.compile(r"candidate_[0-9a-f]{24}\Z")
_SHA_RE = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_REF_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,499}\Z")
_SAFE_VERSION_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+:-]{0,127}\Z")
_ARTIFACT_KINDS = ("raw_engine_result", "musicxml", "diagnostic")


class CandidateConvergenceHandoffError(ValueError):
    """Stable fail-closed Stage 7 handoff category."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


def _matches(pattern: re.Pattern[str], value: object) -> bool:
    return type(value) is str and pattern.fullmatch(value) is not None


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    except (TypeError, ValueError, OverflowError, UnicodeEncodeError):
        raise CandidateConvergenceHandoffError("stage7_handoff_state_invalid") from None


def _safe_ref(value: object) -> bool:
    if not _matches(_SAFE_REF_RE, value):
        return False
    assert isinstance(value, str)
    if value.startswith("/") or "\\" in value or "//" in value:
        return False
    return all(part not in {"", ".", ".."} for part in value.split("/"))


def _safe_optional_version(value: object) -> bool:
    return value is None or _matches(_SAFE_VERSION_RE, value)


@dataclass(frozen=True, slots=True, repr=False)
class VerifiedCandidateHandoff:
    version: str
    job_id: str
    plan_id: str
    plan_sha256: str
    source_artifact_id: str
    source_sha256: str
    engine: str
    run_id: str
    candidate_id: str
    candidate_sha256: str
    persistence_record_sha256: str
    musicxml_artifact_id: str
    musicxml_artifact_ref: str
    musicxml_sha256: str
    engine_version: str | None
    model_version: str | None
    document: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if (
            self.version != CANDIDATE_CONVERGENCE_HANDOFF_VERSION
            or not _matches(_JOB_RE, self.job_id)
            or not _matches(_PLAN_RE, self.plan_id)
            or not _matches(_SHA_RE, self.plan_sha256)
            or not _matches(_ARTIFACT_RE, self.source_artifact_id)
            or not _matches(_SHA_RE, self.source_sha256)
            or self.engine not in ENGINE_NAMES
            or not _matches(_RUN_RE, self.run_id)
            or not _matches(_CANDIDATE_RE, self.candidate_id)
            or not _matches(_SHA_RE, self.candidate_sha256)
            or not _matches(_SHA_RE, self.persistence_record_sha256)
            or not _matches(_ARTIFACT_RE, self.musicxml_artifact_id)
            or not _safe_ref(self.musicxml_artifact_ref)
            or not _matches(_SHA_RE, self.musicxml_sha256)
            or not _safe_optional_version(self.engine_version)
            or not _safe_optional_version(self.model_version)
            or type(self.document) is not bytes
            or not 1 <= len(self.document) <= MAX_CONVERGENCE_MUSICXML_BYTES
            or sha256(self.document).hexdigest() != self.musicxml_sha256
        ):
            raise CandidateConvergenceHandoffError("stage7_handoff_invalid")

    def _core(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "jobId": self.job_id,
            "planId": self.plan_id,
            "planSha256": self.plan_sha256,
            "sourceArtifactId": self.source_artifact_id,
            "sourceSha256": self.source_sha256,
            "engine": self.engine,
            "runId": self.run_id,
            "candidateId": self.candidate_id,
            "candidateSha256": self.candidate_sha256,
            "persistenceRecordSha256": self.persistence_record_sha256,
            "musicxmlArtifactId": self.musicxml_artifact_id,
            "musicxmlArtifactRef": self.musicxml_artifact_ref,
            "musicxmlSha256": self.musicxml_sha256,
            "musicxmlBytes": len(self.document),
            "engineVersion": self.engine_version,
            "modelVersion": self.model_version,
            "provenanceAuthenticated": True,
            "persistedArtifactVerified": True,
            "candidateOnly": True,
            "authoritativeScore": False,
        }

    @property
    def handoff_sha256(self) -> str:
        return sha256(_canonical_json(self._core())).hexdigest()

    def as_safe_dict(self) -> dict[str, Any]:
        payload = self._core()
        payload.update(
            {
                "handoffSha256": self.handoff_sha256,
                "documentExported": False,
                "transportAuthorizationGranted": False,
            }
        )
        return payload

    def to_ensemble_payload(self) -> dict[str, Any]:
        """Return exact in-memory content plus independently verifiable metadata.

        This object is not a network authorization. Any future cross-service
        transport must authenticate this payload separately.
        """

        payload = self._core()
        payload["handoffSha256"] = self.handoff_sha256
        payload["document"] = self.document
        return payload


def _musicxml_artifact_ref(plan: Mapping[str, Any], engine: str) -> str:
    try:
        verify_orchestration_plan(plan)
        runs = [item for item in plan["engineRuns"] if item["engine"] == engine]
        if len(runs) != 1:
            raise CandidateConvergenceHandoffError("stage7_handoff_plan_invalid")
        artifacts = [
            item for item in runs[0]["expectedArtifacts"] if item["kind"] == "musicxml"
        ]
        if len(artifacts) != 1:
            raise CandidateConvergenceHandoffError("stage7_handoff_plan_invalid")
        artifact_ref = artifacts[0]["artifactRef"]
        if not _safe_ref(artifact_ref):
            raise CandidateConvergenceHandoffError("stage7_handoff_plan_invalid")
        return artifact_ref
    except CandidateConvergenceHandoffError:
        raise
    except (OrchestrationContractError, KeyError, TypeError, ValueError):
        raise CandidateConvergenceHandoffError("stage7_handoff_plan_invalid") from None


def _artifact_metadata(record: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    artifacts = record.get("artifacts")
    if type(artifacts) is not list or len(artifacts) != 3:
        raise CandidateConvergenceHandoffError("stage7_handoff_persistence_invalid")
    result: dict[str, Mapping[str, Any]] = {}
    for item in artifacts:
        if type(item) is not dict:
            raise CandidateConvergenceHandoffError("stage7_handoff_persistence_invalid")
        kind = item.get("kind")
        if kind not in _ARTIFACT_KINDS or kind in result:
            raise CandidateConvergenceHandoffError("stage7_handoff_persistence_invalid")
        if (
            not _matches(_ARTIFACT_RE, item.get("artifactId"))
            or not _matches(_SHA_RE, item.get("sha256"))
            or type(item.get("sizeBytes")) is not int
            or item["sizeBytes"] <= 0
        ):
            raise CandidateConvergenceHandoffError("stage7_handoff_persistence_invalid")
        result[kind] = item
    if set(result) != set(_ARTIFACT_KINDS):
        raise CandidateConvergenceHandoffError("stage7_handoff_persistence_invalid")
    return result


def _recompute_candidate_sha256(
    record: Mapping[str, Any],
    identity: DispatchIdentityBinding,
    artifacts: Mapping[str, Mapping[str, Any]],
) -> str:
    raw = artifacts["raw_engine_result"]
    musicxml = artifacts["musicxml"]
    diagnostic = artifacts["diagnostic"]
    if (
        musicxml.get("artifactId") != identity.musicxml_artifact_id
        or diagnostic.get("artifactId") != identity.diagnostic_artifact_id
    ):
        raise CandidateConvergenceHandoffError("stage7_handoff_persistence_invalid")
    payload = {
        "version": ENGINE_RESULT_INGESTION_VERSION,
        "engine": identity.engine,
        "jobId": identity.job_id,
        "runId": identity.run_id,
        "planId": identity.plan_id,
        "planSha256": identity.plan_sha256,
        "sourceArtifactId": identity.source_artifact_id,
        "sourceSha256": identity.source_sha256,
        "candidateId": identity.candidate_id,
        "candidateNamespace": identity.candidate_namespace,
        "musicxmlArtifactId": identity.musicxml_artifact_id,
        "diagnosticArtifactId": identity.diagnostic_artifact_id,
        "dispatchIdentitySha256": identity.identity_sha256,
        "authenticatedResultSha256": record.get("authenticatedResultSha256"),
        "rawSha256": raw.get("sha256"),
        "rawBytes": raw.get("sizeBytes"),
        "musicxmlSha256": musicxml.get("sha256"),
        "musicxmlBytes": musicxml.get("sizeBytes"),
        "diagnosticSha256": diagnostic.get("sha256"),
        "diagnosticBytes": diagnostic.get("sizeBytes"),
        "engineVersion": record.get("engineVersion"),
        "modelVersion": record.get("modelVersion"),
    }
    if not _matches(_SHA_RE, payload["authenticatedResultSha256"]):
        raise CandidateConvergenceHandoffError("stage7_handoff_persistence_invalid")
    return sha256(_canonical_json(payload)).hexdigest()


def load_verified_candidate_handoff(
    *,
    provider: StagingUploadProvider,
    orchestration_plan: Mapping[str, Any],
    engine: str,
) -> VerifiedCandidateHandoff:
    """Load one Stage 6 candidate only after durable record and bytes re-verify."""

    if type(provider) is not StagingUploadProvider or engine not in ENGINE_NAMES:
        raise CandidateConvergenceHandoffError("stage7_handoff_input_invalid")
    try:
        identity = build_dispatch_identity(orchestration_plan, engine)
        record = load_persisted_candidate_record(
            provider=provider,
            orchestration_plan=orchestration_plan,
            engine=engine,
        )
        document = load_persisted_candidate_musicxml(
            provider=provider,
            orchestration_plan=orchestration_plan,
            engine=engine,
        )
    except (DispatchIdentityError, EngineResultIngestionError):
        raise CandidateConvergenceHandoffError("stage7_handoff_persistence_invalid") from None

    if len(document) > MAX_CONVERGENCE_MUSICXML_BYTES:
        raise CandidateConvergenceHandoffError("stage7_handoff_musicxml_oversized")
    artifacts = _artifact_metadata(record)
    metadata = artifacts["musicxml"]
    artifact_ref = _musicxml_artifact_ref(orchestration_plan, engine)
    record_sha = sha256(_canonical_json(record)).hexdigest()
    expected_candidate_sha = _recompute_candidate_sha256(record, identity, artifacts)
    if (
        record.get("candidateId") != identity.candidate_id
        or record.get("candidateSha256") != expected_candidate_sha
        or metadata.get("artifactId") != identity.musicxml_artifact_id
        or metadata.get("sha256") != sha256(document).hexdigest()
        or metadata.get("sizeBytes") != len(document)
    ):
        raise CandidateConvergenceHandoffError("stage7_handoff_persistence_invalid")

    return VerifiedCandidateHandoff(
        version=CANDIDATE_CONVERGENCE_HANDOFF_VERSION,
        job_id=identity.job_id,
        plan_id=identity.plan_id,
        plan_sha256=identity.plan_sha256,
        source_artifact_id=identity.source_artifact_id,
        source_sha256=identity.source_sha256,
        engine=identity.engine,
        run_id=identity.run_id,
        candidate_id=identity.candidate_id,
        candidate_sha256=expected_candidate_sha,
        persistence_record_sha256=record_sha,
        musicxml_artifact_id=identity.musicxml_artifact_id,
        musicxml_artifact_ref=artifact_ref,
        musicxml_sha256=metadata["sha256"],
        engine_version=record.get("engineVersion"),
        model_version=record.get("modelVersion"),
        document=document,
    )


def load_verified_candidate_handoffs(
    *,
    provider: StagingUploadProvider,
    orchestration_plan: Mapping[str, Any],
    outcomes: tuple[EngineIngestionOutcome, ...],
) -> tuple[VerifiedCandidateHandoff, ...]:
    """Load exactly the successful Stage 6 candidates eligible for comparison."""

    try:
        summary = summarize_partial_success(orchestration_plan, outcomes)
    except EngineResultIngestionError:
        raise CandidateConvergenceHandoffError("stage7_handoff_outcomes_invalid") from None
    if not summary.comparison_eligible:
        raise CandidateConvergenceHandoffError("stage7_handoff_insufficient_candidates")

    handoffs = tuple(
        load_verified_candidate_handoff(
            provider=provider,
            orchestration_plan=orchestration_plan,
            engine=outcome.engine,
        )
        for outcome in summary.outcomes
        if outcome.status == "success"
    )
    if len(handoffs) < 2:
        raise CandidateConvergenceHandoffError("stage7_handoff_insufficient_candidates")
    return handoffs
