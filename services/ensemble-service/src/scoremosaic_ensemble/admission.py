"""Per-candidate Canonical admission isolation for neutral Ensemble comparison."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Iterable

from .canonical import CanonicalModelError, CanonicalScore, SourceIdentity
from .comparator import MAX_CANDIDATES, ComparisonResult, compare_candidates
from .musicxml import normalize_musicxml

ADMISSION_FORMAT_VERSION = "0.1-foundation"
_ADMISSION_REJECTION_REASON = "canonical_normalization_rejected"
_INSUFFICIENT_REASON = "insufficient_canonical_candidates"


class CandidateAdmissionError(ValueError):
    """Raised when the admission request itself violates Ensemble-R1 invariants."""


@dataclass(frozen=True, slots=True)
class CanonicalCandidateInput:
    """One immutable raw MusicXML candidate plus server-owned source metadata."""

    document: bytes
    engine: str
    artifact_ref: str
    engine_version: str | None = None
    model_version: str | None = None

    def __post_init__(self) -> None:
        if type(self.document) is not bytes:
            raise CandidateAdmissionError("candidate document must be exact bytes")
        # Validate server-owned source metadata independently of MusicXML admission.
        self.source_identity()

    def source_identity(self) -> SourceIdentity:
        return SourceIdentity(
            engine=self.engine,
            engine_version=self.engine_version,
            model_version=self.model_version,
            artifact_ref=self.artifact_ref,
            artifact_sha256=sha256(self.document).hexdigest(),
        )


@dataclass(frozen=True, slots=True)
class CanonicalAdmissionEvidence:
    """Bounded evidence for one accepted or rejected Canonical candidate."""

    source: SourceIdentity
    status: str
    reason: str | None
    canonical_sha256: str | None

    def __post_init__(self) -> None:
        if self.status not in {"accepted", "rejected"}:
            raise CandidateAdmissionError("admission status is invalid")
        if self.status == "accepted":
            if self.reason is not None:
                raise CandidateAdmissionError("accepted admission cannot have a reason")
            if self.canonical_sha256 is None or len(self.canonical_sha256) != 64:
                raise CandidateAdmissionError("accepted admission requires Canonical SHA-256")
        else:
            if self.reason != _ADMISSION_REJECTION_REASON:
                raise CandidateAdmissionError("rejected admission reason is invalid")
            if self.canonical_sha256 is not None:
                raise CandidateAdmissionError("rejected admission cannot have Canonical SHA-256")

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source.as_dict(),
            "status": self.status,
            "reason": self.reason,
            "canonicalSha256": self.canonical_sha256,
        }


@dataclass(frozen=True, slots=True)
class EnsembleAdmissionResult:
    """Deterministic admission evidence plus an optional neutral comparison."""

    admissions: tuple[CanonicalAdmissionEvidence, ...]
    comparison: ComparisonResult | None

    def __post_init__(self) -> None:
        if len(self.admissions) < 2 or len(self.admissions) > MAX_CANDIDATES:
            raise CandidateAdmissionError("candidate count is outside admission limits")
        source_keys = tuple(_source_sort_key(item.source) for item in self.admissions)
        if source_keys != tuple(sorted(source_keys)):
            raise CandidateAdmissionError("admission evidence must be sorted")
        if len(source_keys) != len(set(source_keys)):
            raise CandidateAdmissionError("duplicate candidate source identity")

        accepted_count = sum(item.status == "accepted" for item in self.admissions)
        if accepted_count >= 2 and self.comparison is None:
            raise CandidateAdmissionError("eligible admissions require a comparison")
        if accepted_count < 2 and self.comparison is not None:
            raise CandidateAdmissionError("insufficient admissions cannot have a comparison")
        if self.comparison is not None and len(self.comparison.candidates) != accepted_count:
            raise CandidateAdmissionError("comparison candidate count does not match admissions")

    @property
    def accepted_candidate_count(self) -> int:
        return sum(item.status == "accepted" for item in self.admissions)

    @property
    def rejected_candidate_count(self) -> int:
        return len(self.admissions) - self.accepted_candidate_count

    def as_dict(self) -> dict[str, Any]:
        comparison_eligible = self.accepted_candidate_count >= 2
        return {
            "formatVersion": ADMISSION_FORMAT_VERSION,
            "mode": "per-candidate-canonical-admission",
            "boundaries": {
                "readOnly": True,
                "canonicalRulesRelaxed": False,
                "rejectedCandidateRepair": False,
                "engineRanking": False,
                "winnerSelection": False,
                "automaticMerge": False,
                "automaticCorrection": False,
                "teacherApproval": False,
                "publication": False,
            },
            "totalCandidateCount": len(self.admissions),
            "acceptedCandidateCount": self.accepted_candidate_count,
            "rejectedCandidateCount": self.rejected_candidate_count,
            "comparisonEligible": comparison_eligible,
            "failClosed": not comparison_eligible,
            "failClosedReason": None if comparison_eligible else _INSUFFICIENT_REASON,
            "admissions": [item.as_dict() for item in self.admissions],
            "comparison": None if self.comparison is None else self.comparison.as_dict(),
        }


def _source_sort_key(source: SourceIdentity) -> tuple[str, str, str, str, str]:
    return (
        source.engine,
        source.artifact_ref,
        source.artifact_sha256,
        source.engine_version or "",
        source.model_version or "",
    )


def admit_and_compare_candidates(
    candidates: Iterable[CanonicalCandidateInput],
) -> EnsembleAdmissionResult:
    """Admit candidates independently and compare only accepted Canonical scores.

    Canonical normalization rules are unchanged. Expected Canonical-domain rejection of
    one candidate is converted to bounded evidence without exposing exception text.
    Unexpected non-Canonical exceptions are deliberately not swallowed.
    """

    items = tuple(candidates)
    if len(items) < 2 or len(items) > MAX_CANDIDATES:
        raise CandidateAdmissionError("two to eight candidates are required")
    if any(not isinstance(item, CanonicalCandidateInput) for item in items):
        raise CandidateAdmissionError("all candidates must be CanonicalCandidateInput objects")

    ordered = tuple(sorted(items, key=lambda item: _source_sort_key(item.source_identity())))
    source_keys = tuple(_source_sort_key(item.source_identity()) for item in ordered)
    if len(source_keys) != len(set(source_keys)):
        raise CandidateAdmissionError("duplicate candidate source identity")

    admissions: list[CanonicalAdmissionEvidence] = []
    accepted_scores: list[CanonicalScore] = []

    for item in ordered:
        source = item.source_identity()
        try:
            score = normalize_musicxml(
                item.document,
                engine=item.engine,
                artifact_ref=item.artifact_ref,
                engine_version=item.engine_version,
                model_version=item.model_version,
            )
        except CanonicalModelError:
            admissions.append(
                CanonicalAdmissionEvidence(
                    source=source,
                    status="rejected",
                    reason=_ADMISSION_REJECTION_REASON,
                    canonical_sha256=None,
                )
            )
            continue

        if score.source != source:
            raise CandidateAdmissionError("normalized candidate source identity drifted")
        accepted_scores.append(score)
        admissions.append(
            CanonicalAdmissionEvidence(
                source=source,
                status="accepted",
                reason=None,
                canonical_sha256=score.canonical_sha256,
            )
        )

    comparison = (
        compare_candidates(tuple(accepted_scores))
        if len(accepted_scores) >= 2
        else None
    )
    return EnsembleAdmissionResult(
        admissions=tuple(admissions),
        comparison=comparison,
    )
