"""Stage 7 deterministic Candidate Safety -> Canonical -> Comparator convergence.

The Ensemble side trusts no Gateway Python type. It independently validates the
versioned handoff mapping, exact bytes/hash/identity convergence, then reuses the
existing Canonical admission and neutral comparator. No winner, merged score,
automatic correction, teacher approval, or publication authority is granted.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
import re
from typing import Any, Iterable, Mapping

from .admission import (
    CandidateAdmissionError,
    CanonicalCandidateInput,
    EnsembleAdmissionResult,
    admit_and_compare_candidates,
)
from .report import (
    ComparisonReportError,
    EnsembleComparisonReport,
    build_comparison_report,
)

CONVERGENCE_FORMAT_VERSION = "scoremosaic-stage7-convergence-v1"
CANDIDATE_CONVERGENCE_HANDOFF_VERSION = "scoremosaic-candidate-convergence-handoff-v1"
MAX_CONVERGENCE_MUSICXML_BYTES = 16 * 1024 * 1024
MAX_CONVERGENCE_CANDIDATES = 3

_ENGINE_ORDER = {"audiveris": 0, "homr": 1, "clarity": 2}
_JOB_RE = re.compile(r"job_[A-Za-z0-9_-]{8,80}\Z")
_PLAN_RE = re.compile(r"plan_[0-9a-f]{24}\Z")
_RUN_RE = re.compile(r"run_[0-9a-f]{24}\Z")
_ARTIFACT_RE = re.compile(r"artifact_[0-9a-f]{24}\Z")
_CANDIDATE_RE = re.compile(r"candidate_[0-9a-f]{24}\Z")
_SHA_RE = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_REF_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,499}\Z")
_SAFE_VERSION_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+:-]{0,127}\Z")

_HANDOFF_KEYS = {
    "version",
    "jobId",
    "planId",
    "planSha256",
    "sourceArtifactId",
    "sourceSha256",
    "engine",
    "runId",
    "candidateId",
    "candidateSha256",
    "persistenceRecordSha256",
    "musicxmlArtifactId",
    "musicxmlArtifactRef",
    "musicxmlSha256",
    "musicxmlBytes",
    "engineVersion",
    "modelVersion",
    "provenanceAuthenticated",
    "persistedArtifactVerified",
    "candidateOnly",
    "authoritativeScore",
    "handoffSha256",
    "document",
}

_STRUCTURAL_CATEGORIES = frozenset({"measure", "event_time", "voice", "staff"})
_MUSICAL_CATEGORIES = frozenset(
    {"pitch", "duration", "rest", "chord", "tie", "dot", "tuplet", "tab"}
)


class CandidateConvergenceError(ValueError):
    """Stable fail-closed Stage 7 convergence category."""

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
        raise CandidateConvergenceError("stage7_convergence_state_invalid") from None


def _safe_ref(value: object) -> bool:
    if not _matches(_SAFE_REF_RE, value):
        return False
    assert isinstance(value, str)
    if value.startswith("/") or "\\" in value or "//" in value:
        return False
    return all(part not in {"", ".", ".."} for part in value.split("/"))


def _safe_optional_version(value: object) -> bool:
    return value is None or _matches(_SAFE_VERSION_RE, value)


def _handoff_core(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "version": payload["version"],
        "jobId": payload["jobId"],
        "planId": payload["planId"],
        "planSha256": payload["planSha256"],
        "sourceArtifactId": payload["sourceArtifactId"],
        "sourceSha256": payload["sourceSha256"],
        "engine": payload["engine"],
        "runId": payload["runId"],
        "candidateId": payload["candidateId"],
        "candidateSha256": payload["candidateSha256"],
        "persistenceRecordSha256": payload["persistenceRecordSha256"],
        "musicxmlArtifactId": payload["musicxmlArtifactId"],
        "musicxmlArtifactRef": payload["musicxmlArtifactRef"],
        "musicxmlSha256": payload["musicxmlSha256"],
        "musicxmlBytes": payload["musicxmlBytes"],
        "engineVersion": payload["engineVersion"],
        "modelVersion": payload["modelVersion"],
        "provenanceAuthenticated": payload["provenanceAuthenticated"],
        "persistedArtifactVerified": payload["persistedArtifactVerified"],
        "candidateOnly": payload["candidateOnly"],
        "authoritativeScore": payload["authoritativeScore"],
    }


@dataclass(frozen=True, slots=True, repr=False)
class ConvergenceCandidateInput:
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
    handoff_sha256: str
    engine_version: str | None
    model_version: str | None
    document: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if (
            not _matches(_JOB_RE, self.job_id)
            or not _matches(_PLAN_RE, self.plan_id)
            or not _matches(_SHA_RE, self.plan_sha256)
            or not _matches(_ARTIFACT_RE, self.source_artifact_id)
            or not _matches(_SHA_RE, self.source_sha256)
            or self.engine not in _ENGINE_ORDER
            or not _matches(_RUN_RE, self.run_id)
            or not _matches(_CANDIDATE_RE, self.candidate_id)
            or not _matches(_SHA_RE, self.candidate_sha256)
            or not _matches(_SHA_RE, self.persistence_record_sha256)
            or not _matches(_ARTIFACT_RE, self.musicxml_artifact_id)
            or not _safe_ref(self.musicxml_artifact_ref)
            or not _matches(_SHA_RE, self.musicxml_sha256)
            or not _matches(_SHA_RE, self.handoff_sha256)
            or not _safe_optional_version(self.engine_version)
            or not _safe_optional_version(self.model_version)
            or type(self.document) is not bytes
            or not 1 <= len(self.document) <= MAX_CONVERGENCE_MUSICXML_BYTES
            or sha256(self.document).hexdigest() != self.musicxml_sha256
        ):
            raise CandidateConvergenceError("stage7_candidate_input_invalid")

    def as_safe_dict(self) -> dict[str, Any]:
        return {
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
            "handoffSha256": self.handoff_sha256,
            "engineVersion": self.engine_version,
            "modelVersion": self.model_version,
            "candidateOnly": True,
            "authoritativeScore": False,
        }


def parse_verified_candidate_handoff(payload: Mapping[str, Any]) -> ConvergenceCandidateInput:
    """Independently verify the exact Gateway handoff contract and content hash."""

    if type(payload) is not dict or set(payload) != _HANDOFF_KEYS:
        raise CandidateConvergenceError("stage7_handoff_schema_invalid")
    document = payload.get("document")
    if (
        payload.get("version") != CANDIDATE_CONVERGENCE_HANDOFF_VERSION
        or payload.get("provenanceAuthenticated") is not True
        or payload.get("persistedArtifactVerified") is not True
        or payload.get("candidateOnly") is not True
        or payload.get("authoritativeScore") is not False
        or type(payload.get("musicxmlBytes")) is not int
        or type(document) is not bytes
        or payload["musicxmlBytes"] != len(document)
        or not 1 <= len(document) <= MAX_CONVERGENCE_MUSICXML_BYTES
        or payload.get("musicxmlSha256") != sha256(document).hexdigest()
    ):
        raise CandidateConvergenceError("stage7_handoff_integrity_invalid")
    expected_handoff_sha = sha256(_canonical_json(_handoff_core(payload))).hexdigest()
    if payload.get("handoffSha256") != expected_handoff_sha:
        raise CandidateConvergenceError("stage7_handoff_integrity_invalid")

    return ConvergenceCandidateInput(
        job_id=payload["jobId"],
        plan_id=payload["planId"],
        plan_sha256=payload["planSha256"],
        source_artifact_id=payload["sourceArtifactId"],
        source_sha256=payload["sourceSha256"],
        engine=payload["engine"],
        run_id=payload["runId"],
        candidate_id=payload["candidateId"],
        candidate_sha256=payload["candidateSha256"],
        persistence_record_sha256=payload["persistenceRecordSha256"],
        musicxml_artifact_id=payload["musicxmlArtifactId"],
        musicxml_artifact_ref=payload["musicxmlArtifactRef"],
        musicxml_sha256=payload["musicxmlSha256"],
        handoff_sha256=payload["handoffSha256"],
        engine_version=payload["engineVersion"],
        model_version=payload["modelVersion"],
        document=document,
    )


def _category_counts(admission: EnsembleAdmissionResult) -> dict[str, int]:
    counts: dict[str, int] = {}
    if admission.comparison is not None:
        for difference in admission.comparison.differences:
            counts[difference.category] = counts.get(difference.category, 0) + 1
    return {key: counts[key] for key in sorted(counts)}


def _evidence(admission: EnsembleAdmissionResult) -> dict[str, Any]:
    comparison = admission.comparison
    categories = _category_counts(admission)
    structural_count = sum(categories.get(key, 0) for key in _STRUCTURAL_CATEGORIES)
    musical_count = sum(categories.get(key, 0) for key in _MUSICAL_CATEGORIES)
    if comparison is None:
        agreement_status = "not_comparable"
        structural_status = "not_comparable"
        musical_status = "not_comparable"
        difference_count = 0
    else:
        difference_count = len(comparison.differences)
        agreement_status = "full_agreement" if comparison.identical else "disagreement"
        structural_status = "consistent" if structural_count == 0 else "differences"
        musical_status = "consistent" if musical_count == 0 else "differences"

    return {
        "engineAgreement": {
            "status": agreement_status,
            "acceptedCandidateCount": admission.accepted_candidate_count,
            "rejectedCandidateCount": admission.rejected_candidate_count,
            "differenceCount": difference_count,
        },
        "visualConfidence": {
            "available": False,
            "reason": "not_in_stage6_candidate_contract",
            "authoritative": False,
        },
        "structuralConsistency": {
            "status": structural_status,
            "differenceCount": structural_count,
        },
        "musicalConsistency": {
            "status": musical_status,
            "differenceCount": musical_count,
            "categoryCounts": categories,
        },
        "sourceQuality": {
            "available": False,
            "reason": "not_in_stage6_candidate_contract",
            "authoritative": False,
        },
        "localizationReliability": {
            "available": False,
            "canonicalXmlProvenanceAvailable": comparison is not None,
            "bboxEvidenceAvailable": False,
            "authoritative": False,
        },
        "aggregateConfidenceScore": None,
        "confidenceUsedAsAuthority": False,
    }


@dataclass(frozen=True, slots=True)
class Stage7ConvergenceResult:
    inputs: tuple[ConvergenceCandidateInput, ...]
    admission: EnsembleAdmissionResult
    comparison_report: EnsembleComparisonReport | None

    def __post_init__(self) -> None:
        if not 2 <= len(self.inputs) <= MAX_CONVERGENCE_CANDIDATES:
            raise CandidateConvergenceError("stage7_convergence_candidate_count_invalid")
        engine_order = tuple(_ENGINE_ORDER[item.engine] for item in self.inputs)
        if engine_order != tuple(sorted(engine_order)):
            raise CandidateConvergenceError("stage7_convergence_candidate_order_invalid")
        if self.admission.comparison is None and self.comparison_report is not None:
            raise CandidateConvergenceError("stage7_convergence_report_invalid")
        if self.admission.comparison is not None:
            if self.comparison_report is None:
                raise CandidateConvergenceError("stage7_convergence_report_invalid")
            if self.comparison_report.comparison != self.admission.comparison:
                raise CandidateConvergenceError("stage7_convergence_report_invalid")

    @property
    def status(self) -> str:
        return (
            "comparison_ready"
            if self.admission.comparison is not None
            else "insufficient_canonical_candidates"
        )

    def _payload_without_hash(self) -> dict[str, Any]:
        return {
            "formatVersion": CONVERGENCE_FORMAT_VERSION,
            "status": self.status,
            "inputs": [item.as_safe_dict() for item in self.inputs],
            "candidateSafety": {
                "stage6PersistenceReverified": True,
                "handoffIntegrityReverified": True,
                "canonicalRulesRelaxed": False,
            },
            "canonicalAdmission": self.admission.as_dict(),
            "comparisonReport": (
                None if self.comparison_report is None else self.comparison_report.as_dict()
            ),
            "evidence": _evidence(self.admission),
            "boundaries": {
                "readOnly": True,
                "authoritativeScore": False,
                "engineRanking": False,
                "winnerSelection": False,
                "automaticMerge": False,
                "automaticCorrection": False,
                "teacherApproval": False,
                "publication": False,
            },
        }

    @property
    def result_sha256(self) -> str:
        return sha256(_canonical_json(self._payload_without_hash())).hexdigest()

    def as_safe_dict(self) -> dict[str, Any]:
        payload = self._payload_without_hash()
        payload["resultSha256"] = self.result_sha256
        return payload


def converge_verified_candidates(
    payloads: Iterable[Mapping[str, Any]],
) -> Stage7ConvergenceResult:
    """Canonicalize and neutrally compare independently verified candidate payloads."""

    try:
        inputs = tuple(parse_verified_candidate_handoff(item) for item in payloads)
    except TypeError:
        raise CandidateConvergenceError("stage7_convergence_input_invalid") from None
    if not 2 <= len(inputs) <= MAX_CONVERGENCE_CANDIDATES:
        raise CandidateConvergenceError("stage7_convergence_candidate_count_invalid")

    ordered = tuple(sorted(inputs, key=lambda item: _ENGINE_ORDER[item.engine]))
    if len({item.engine for item in ordered}) != len(ordered):
        raise CandidateConvergenceError("stage7_convergence_duplicate_engine")
    if len({item.candidate_id for item in ordered}) != len(ordered):
        raise CandidateConvergenceError("stage7_convergence_duplicate_candidate")
    if len({item.handoff_sha256 for item in ordered}) != len(ordered):
        raise CandidateConvergenceError("stage7_convergence_duplicate_handoff")

    shared = {
        (item.job_id, item.plan_id, item.plan_sha256, item.source_artifact_id, item.source_sha256)
        for item in ordered
    }
    if len(shared) != 1:
        raise CandidateConvergenceError("stage7_convergence_source_binding_mismatch")

    candidates = tuple(
        CanonicalCandidateInput(
            document=item.document,
            engine=item.engine,
            artifact_ref=item.musicxml_artifact_ref,
            engine_version=item.engine_version,
            model_version=item.model_version,
        )
        for item in ordered
    )
    try:
        admission = admit_and_compare_candidates(candidates)
        report = (
            build_comparison_report(admission.comparison)
            if admission.comparison is not None
            else None
        )
    except (CandidateAdmissionError, ComparisonReportError):
        raise CandidateConvergenceError("stage7_canonical_convergence_failed") from None

    return Stage7ConvergenceResult(
        inputs=ordered,
        admission=admission,
        comparison_report=report,
    )
