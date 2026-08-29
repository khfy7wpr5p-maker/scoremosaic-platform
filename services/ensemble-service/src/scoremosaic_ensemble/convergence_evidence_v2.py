"""SM-POLY-11 research-only Convergence Evidence Vector v2.

The vector binds immutable evidence produced by earlier ScoreMosaic research
stages beside an existing Stage 7 convergence result. It deliberately treats
upstream artifacts as opaque, SHA-pinned evidence sets: engine/category identity
remains authoritative only inside the validated upstream artifact itself.

This package does not mutate Stage 7, rank engines, choose a winner, merge or
correct MusicXML, promote ST-OMR, or override Teacher Review authority.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import re
from typing import Any, Mapping

SCHEMA_VERSION = "scoremosaic-convergence-evidence-vector-v2"
STAGE7_FORMAT_VERSION = "scoremosaic-stage7-convergence-v1"
PRODUCTION_ENGINES = ("audiveris", "homr", "clarity")
SHADOW_ENGINE = "st-omr"
MAX_ARTIFACTS_PER_SLOT = 10_000
EVIDENCE_FAMILIES = (
    "semanticMetrics",
    "visualEvidence",
    "sourceQuality",
    "polyphonyComplexity",
    "reliabilityCalibration",
    "stOmrShadow",
)

_SHA_RE = re.compile(r"[0-9a-f]{64}\Z")
_VECTOR_RE = re.compile(r"convergence_evidence_v2_[0-9a-f]{24}\Z")
_FIXTURE_RE = re.compile(r"poly_fixture_[A-Za-z0-9_-]{8,96}\Z")
_VERSION_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+:-]{0,127}\Z")

_BOUNDARIES = {
    "researchOnly": True,
    "readOnly": True,
    "descriptiveEvidenceOnly": True,
    "upstreamEvidenceReinterpreted": False,
    "stage7EvidenceMutation": False,
    "stage7QuorumContribution": False,
    "stage7QuorumChange": False,
    "productionDecisionAuthority": False,
    "engineRanking": False,
    "winnerSelection": False,
    "singleAggregateScore": False,
    "confidenceUsedAsAuthority": False,
    "automaticMerge": False,
    "automaticCorrection": False,
    "teacherAuthorityOverride": False,
    "stOmrProductionPromotion": False,
    "gatewayIntegration": False,
}

_FAMILY_SCHEMA_VERSIONS = {
    "semanticMetrics": frozenset({"scoremosaic-polyphonic-engine-semantic-report-v1"}),
    "visualEvidence": frozenset({"scoremosaic-polyphonic-visual-evidence-sidecar-v1"}),
    "sourceQuality": frozenset({"scoremosaic-polyphonic-source-quality-profile-v1"}),
    "polyphonyComplexity": frozenset({"scoremosaic-polyphonic-complexity-profile-v1"}),
    "reliabilityCalibration": frozenset({"scoremosaic-engine-reliability-report-v1"}),
    "stOmrShadow": frozenset({"scoremosaic-st-omr-shadow-report-v1"}),
}


class ConvergenceEvidenceV2Error(ValueError):
    """Stable fail-closed SM-POLY-11 validation category."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


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
        raise ConvergenceEvidenceV2Error("non_canonical_json") from None


def _matches(pattern: re.Pattern[str], value: object) -> bool:
    return type(value) is str and pattern.fullmatch(value) is not None


def _exact(value: object, keys: set[str], category: str) -> Mapping[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise ConvergenceEvidenceV2Error(category)
    return value


def _artifact_set_sha256(values: list[str]) -> str:
    return sha256(_canonical_json(values)).hexdigest()


def unavailable_evidence_slot() -> dict[str, Any]:
    """Return the only legal representation of unavailable evidence."""
    return {
        "available": False,
        "schemaVersion": None,
        "bindingMethodVersion": None,
        "artifactSha256Set": [],
        "artifactSetSha256": None,
    }


def evidence_slot(
    *, schema_version: str, binding_method_version: str, artifact_sha256s: list[str]
) -> dict[str, Any]:
    """Build an immutable evidence-set reference without interpreting its contents."""
    if type(artifact_sha256s) is not list:
        raise ConvergenceEvidenceV2Error("evidence_slot_invalid")
    values = sorted(artifact_sha256s)
    slot = {
        "available": True,
        "schemaVersion": schema_version,
        "bindingMethodVersion": binding_method_version,
        "artifactSha256Set": values,
        "artifactSetSha256": _artifact_set_sha256(values),
    }
    _validate_slot(slot, allowed_schema_versions=None)
    return slot


def _validate_slot(
    value: object, *, allowed_schema_versions: frozenset[str] | None
) -> Mapping[str, Any]:
    slot = _exact(
        value,
        {
            "available",
            "schemaVersion",
            "bindingMethodVersion",
            "artifactSha256Set",
            "artifactSetSha256",
        },
        "evidence_slot_invalid",
    )
    if type(slot["available"]) is not bool or type(slot["artifactSha256Set"]) is not list:
        raise ConvergenceEvidenceV2Error("evidence_slot_invalid")

    values = slot["artifactSha256Set"]
    if slot["available"]:
        if (
            not _matches(_VERSION_RE, slot["schemaVersion"])
            or not _matches(_VERSION_RE, slot["bindingMethodVersion"])
            or not 1 <= len(values) <= MAX_ARTIFACTS_PER_SLOT
            or any(not _matches(_SHA_RE, item) for item in values)
            or values != sorted(values)
            or len(values) != len(set(values))
            or not _matches(_SHA_RE, slot["artifactSetSha256"])
            or slot["artifactSetSha256"] != _artifact_set_sha256(values)
        ):
            raise ConvergenceEvidenceV2Error("evidence_slot_invalid")
        if allowed_schema_versions is not None and slot["schemaVersion"] not in allowed_schema_versions:
            raise ConvergenceEvidenceV2Error("evidence_family_schema_invalid")
    elif (
        slot["schemaVersion"] is not None
        or slot["bindingMethodVersion"] is not None
        or values != []
        or slot["artifactSetSha256"] is not None
    ):
        raise ConvergenceEvidenceV2Error("unavailable_evidence_contains_value")
    return slot


def _vector_identity(payload: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(payload))
    value.pop("vectorId", None)
    value.pop("vectorSha256", None)
    return value


def validate_convergence_evidence_vector(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the complete deterministic v2 vector and its authority boundaries."""
    vector = _exact(
        payload,
        {
            "schemaVersion",
            "vectorId",
            "scope",
            "stage7Convergence",
            "evidence",
            "derivedState",
            "boundaries",
            "vectorSha256",
        },
        "convergence_evidence_v2_schema_invalid",
    )
    if vector["schemaVersion"] != SCHEMA_VERSION or not _matches(_VECTOR_RE, vector["vectorId"]):
        raise ConvergenceEvidenceV2Error("convergence_evidence_v2_schema_invalid")

    scope = _exact(
        vector["scope"],
        {"fixtureId", "teacherGoldReferenceSha256", "sourceDocumentSha256"},
        "convergence_evidence_scope_invalid",
    )
    if (
        not _matches(_FIXTURE_RE, scope["fixtureId"])
        or not _matches(_SHA_RE, scope["teacherGoldReferenceSha256"])
        or not _matches(_SHA_RE, scope["sourceDocumentSha256"])
    ):
        raise ConvergenceEvidenceV2Error("convergence_evidence_scope_invalid")

    stage7 = _exact(
        vector["stage7Convergence"],
        {"formatVersion", "resultSha256", "bindingMethodVersion", "authoritative"},
        "stage7_reference_invalid",
    )
    if (
        stage7["formatVersion"] != STAGE7_FORMAT_VERSION
        or not _matches(_SHA_RE, stage7["resultSha256"])
        or not _matches(_VERSION_RE, stage7["bindingMethodVersion"])
        or stage7["authoritative"] is not False
    ):
        raise ConvergenceEvidenceV2Error("stage7_reference_invalid")

    evidence = _exact(
        vector["evidence"], set(EVIDENCE_FAMILIES), "convergence_evidence_family_set_invalid"
    )
    for family in EVIDENCE_FAMILIES:
        _validate_slot(
            evidence[family], allowed_schema_versions=_FAMILY_SCHEMA_VERSIONS[family]
        )

    derived = _exact(
        vector["derivedState"],
        {
            "productionCandidateEngines",
            "shadowEngine",
            "availableEvidenceFamilyCount",
            "aggregateConfidenceScore",
            "engineRanking",
            "winner",
        },
        "convergence_evidence_derived_state_invalid",
    )
    expected_available = sum(1 for family in EVIDENCE_FAMILIES if evidence[family]["available"])
    if (
        derived["productionCandidateEngines"] != list(PRODUCTION_ENGINES)
        or derived["shadowEngine"] != SHADOW_ENGINE
        or type(derived["availableEvidenceFamilyCount"]) is not int
        or derived["availableEvidenceFamilyCount"] != expected_available
        or derived["aggregateConfidenceScore"] is not None
        or derived["engineRanking"] is not None
        or derived["winner"] is not None
    ):
        raise ConvergenceEvidenceV2Error("convergence_evidence_derived_state_invalid")

    boundaries = _exact(
        vector["boundaries"], set(_BOUNDARIES), "authority_boundary_invalid"
    )
    if any(boundaries[key] is not expected for key, expected in _BOUNDARIES.items()):
        raise ConvergenceEvidenceV2Error("authority_boundary_invalid")

    if not _matches(_SHA_RE, vector["vectorSha256"]):
        raise ConvergenceEvidenceV2Error("convergence_evidence_v2_hash_invalid")
    body = deepcopy(dict(vector))
    body.pop("vectorSha256")
    if vector["vectorSha256"] != sha256(_canonical_json(body)).hexdigest():
        raise ConvergenceEvidenceV2Error("convergence_evidence_v2_hash_invalid")

    expected_id = "convergence_evidence_v2_" + sha256(
        _canonical_json(_vector_identity(vector))
    ).hexdigest()[:24]
    if vector["vectorId"] != expected_id:
        raise ConvergenceEvidenceV2Error("convergence_evidence_v2_id_mismatch")
    return deepcopy(dict(vector))


def build_convergence_evidence_vector(
    *,
    fixture_id: str,
    teacher_gold_reference_sha256: str,
    source_document_sha256: str,
    stage7_result_sha256: str,
    stage7_binding_method_version: str,
    semantic_metrics: Mapping[str, Any],
    visual_evidence: Mapping[str, Any],
    source_quality: Mapping[str, Any],
    polyphony_complexity: Mapping[str, Any],
    reliability_calibration: Mapping[str, Any],
    st_omr_shadow: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a deterministic v2 evidence vector without deriving decision authority."""
    evidence = {
        "semanticMetrics": deepcopy(dict(semantic_metrics)),
        "visualEvidence": deepcopy(dict(visual_evidence)),
        "sourceQuality": deepcopy(dict(source_quality)),
        "polyphonyComplexity": deepcopy(dict(polyphony_complexity)),
        "reliabilityCalibration": deepcopy(dict(reliability_calibration)),
        "stOmrShadow": deepcopy(dict(st_omr_shadow)),
    }
    vector: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "vectorId": "placeholder",
        "scope": {
            "fixtureId": fixture_id,
            "teacherGoldReferenceSha256": teacher_gold_reference_sha256,
            "sourceDocumentSha256": source_document_sha256,
        },
        "stage7Convergence": {
            "formatVersion": STAGE7_FORMAT_VERSION,
            "resultSha256": stage7_result_sha256,
            "bindingMethodVersion": stage7_binding_method_version,
            "authoritative": False,
        },
        "evidence": evidence,
        "derivedState": {
            "productionCandidateEngines": list(PRODUCTION_ENGINES),
            "shadowEngine": SHADOW_ENGINE,
            "availableEvidenceFamilyCount": sum(
                1 for family in EVIDENCE_FAMILIES if evidence[family].get("available") is True
            ),
            "aggregateConfidenceScore": None,
            "engineRanking": None,
            "winner": None,
        },
        "boundaries": deepcopy(_BOUNDARIES),
    }
    vector["vectorId"] = "convergence_evidence_v2_" + sha256(
        _canonical_json(_vector_identity(vector))
    ).hexdigest()[:24]
    vector["vectorSha256"] = sha256(_canonical_json(vector)).hexdigest()
    return validate_convergence_evidence_vector(vector)
