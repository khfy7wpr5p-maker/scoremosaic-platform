"""Research-only source-page quality evidence for polyphonic OMR.

SM-POLY-06 keeps scan/photo quality independent from engine confidence. It
validates normalized degradation evidence supplied by deterministic/heuristic
producers and derives only a transparent worst-observed severity class. It does
not read images, rank engines, create a single quality score, mutate Stage 7, or
gain production authority.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import re
from typing import Any, Mapping

SCHEMA_VERSION = "scoremosaic-polyphonic-source-quality-profile-v1"
MEASUREMENT_POLICY = "DEGRADATION_RISK_BASIS_POINTS_V1"
QUALITY_DIMENSIONS = (
    "blur",
    "skew",
    "rotation",
    "contrast",
    "resolution",
    "perspective",
    "crop",
    "staffVisibility",
    "illumination",
    "compression",
)
MAX_PAGE_DIMENSION_PX = 50_000
MAX_PAGE_PIXELS = 200_000_000

_SHA_RE = re.compile(r"[0-9a-f]{64}\Z")
_PROFILE_RE = re.compile(r"source_quality_[0-9a-f]{24}\Z")
_ARTIFACT_RE = re.compile(r"artifact_[0-9a-f]{24}\Z")
_SAFE_REF_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,499}\Z")
_SAFE_VERSION_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+:-]{0,127}\Z")

_EVIDENCE_SOURCES = frozenset(
    {
        "DETERMINISTIC_HEURISTIC",
        "ENGINE_PREPROCESSING_TELEMETRY",
        "IMPORTED_DATASET_ANNOTATION",
        "TEACHER_ANNOTATION",
    }
)
_BOUNDARIES = {
    "researchOnly": True,
    "readOnly": True,
    "sourceMutation": False,
    "productionDecisionAuthority": False,
    "engineConfidenceIndependent": True,
    "singleQualityScoreAuthority": False,
    "winnerSelection": False,
    "automaticMerge": False,
    "automaticCorrection": False,
    "teacherAuthorityOverride": False,
    "stage7EvidenceMutation": False,
    "stOmrQuorumChange": False,
}
_CORE_KEYS = {
    "schemaVersion",
    "profileId",
    "sourcePage",
    "method",
    "dimensions",
    "boundaries",
}
_FULL_KEYS = _CORE_KEYS | {"derivedState", "profileSha256"}
_DIMENSION_KEYS = {"available", "riskBasisPoints", "rawValue", "unit", "method"}
_DERIVED_KEYS = {
    "coverageCount",
    "maxDegradationRiskBasisPoints",
    "severity",
    "dominantDimensions",
    "singleQualityScore",
    "calibratedProbability",
}


class SourceQualityError(ValueError):
    """Stable fail-closed source-quality validation category."""

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
        raise SourceQualityError("source_quality_state_invalid") from None


def _matches(pattern: re.Pattern[str], value: object) -> bool:
    return type(value) is str and pattern.fullmatch(value) is not None


def _safe_text(value: object, *, maximum: int) -> bool:
    return (
        type(value) is str
        and 1 <= len(value) <= maximum
        and all(ord(character) >= 32 for character in value)
    )


def _safe_ref(value: object) -> bool:
    if not _matches(_SAFE_REF_RE, value):
        return False
    assert isinstance(value, str)
    if value.startswith("/") or "\\" in value or "//" in value:
        return False
    return all(part not in {"", ".", ".."} for part in value.split("/"))


def _require_exact_keys(
    value: object, expected: set[str], category: str
) -> Mapping[str, Any]:
    if type(value) is not dict or set(value) != expected:
        raise SourceQualityError(category)
    return value


def _validate_source_page(value: object) -> None:
    page = _require_exact_keys(
        value,
        {
            "sourceArtifactId",
            "sourceSha256",
            "pageArtifactRef",
            "pageSha256",
            "pageIndex",
            "widthPx",
            "heightPx",
        },
        "source_page_invalid",
    )
    if (
        not _matches(_ARTIFACT_RE, page["sourceArtifactId"])
        or not _matches(_SHA_RE, page["sourceSha256"])
        or not _safe_ref(page["pageArtifactRef"])
        or not _matches(_SHA_RE, page["pageSha256"])
        or type(page["pageIndex"]) is not int
        or not 0 <= page["pageIndex"] <= 9_999
        or type(page["widthPx"]) is not int
        or type(page["heightPx"]) is not int
        or not 1 <= page["widthPx"] <= MAX_PAGE_DIMENSION_PX
        or not 1 <= page["heightPx"] <= MAX_PAGE_DIMENSION_PX
        or page["widthPx"] * page["heightPx"] > MAX_PAGE_PIXELS
    ):
        raise SourceQualityError("source_page_invalid")


def _validate_measurement(value: object) -> None:
    measurement = _require_exact_keys(
        value, _DIMENSION_KEYS, "quality_measurement_invalid"
    )
    if type(measurement["available"]) is not bool:
        raise SourceQualityError("quality_measurement_invalid")
    if measurement["available"]:
        if (
            type(measurement["riskBasisPoints"]) is not int
            or not 0 <= measurement["riskBasisPoints"] <= 10_000
            or not _safe_text(measurement["rawValue"], maximum=120)
            or not _safe_text(measurement["unit"], maximum=80)
            or not _matches(_SAFE_VERSION_RE, measurement["method"])
        ):
            raise SourceQualityError("quality_measurement_invalid")
    elif (
        measurement["riskBasisPoints"] is not None
        or measurement["rawValue"] is not None
        or measurement["unit"] is not None
        or measurement["method"] is not None
    ):
        raise SourceQualityError("unavailable_quality_contains_measurement")


def validate_source_quality_core(payload: Mapping[str, Any]) -> None:
    """Validate unhashed source-quality evidence without deriving authority."""

    core = _require_exact_keys(payload, _CORE_KEYS, "source_quality_schema_invalid")
    if (
        core["schemaVersion"] != SCHEMA_VERSION
        or not _matches(_PROFILE_RE, core["profileId"])
    ):
        raise SourceQualityError("source_quality_schema_invalid")

    _validate_source_page(core["sourcePage"])

    method = _require_exact_keys(
        core["method"],
        {
            "evidenceSource",
            "methodVersion",
            "measurementPolicy",
            "calibrated",
            "qualityProbability",
        },
        "source_quality_method_invalid",
    )
    if (
        method["evidenceSource"] not in _EVIDENCE_SOURCES
        or not _matches(_SAFE_VERSION_RE, method["methodVersion"])
        or method["measurementPolicy"] != MEASUREMENT_POLICY
        or method["calibrated"] is not False
        or method["qualityProbability"] is not None
    ):
        raise SourceQualityError("source_quality_method_invalid")

    dimensions = _require_exact_keys(
        core["dimensions"], set(QUALITY_DIMENSIONS), "quality_dimensions_invalid"
    )
    for dimension in QUALITY_DIMENSIONS:
        _validate_measurement(dimensions[dimension])

    boundaries = _require_exact_keys(
        core["boundaries"], set(_BOUNDARIES), "authority_boundary_invalid"
    )
    if any(boundaries[key] is not expected for key, expected in _BOUNDARIES.items()):
        raise SourceQualityError("authority_boundary_invalid")


def derive_source_quality_state(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Derive a transparent worst-observed category, never an average score."""

    validate_source_quality_core(payload)
    dimensions = payload["dimensions"]
    observed = [
        (name, dimensions[name]["riskBasisPoints"])
        for name in QUALITY_DIMENSIONS
        if dimensions[name]["available"]
    ]
    if not observed:
        return {
            "coverageCount": 0,
            "maxDegradationRiskBasisPoints": None,
            "severity": "UNAVAILABLE",
            "dominantDimensions": [],
            "singleQualityScore": None,
            "calibratedProbability": None,
        }

    maximum = max(risk for _, risk in observed)
    assert type(maximum) is int
    if maximum < 2_000:
        severity = "LOW"
    elif maximum < 4_000:
        severity = "MODERATE"
    elif maximum < 7_000:
        severity = "HIGH"
    else:
        severity = "SEVERE"

    return {
        "coverageCount": len(observed),
        "maxDegradationRiskBasisPoints": maximum,
        "severity": severity,
        "dominantDimensions": [name for name, risk in observed if risk == maximum],
        "singleQualityScore": None,
        "calibratedProbability": None,
    }


def build_source_quality_profile(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Build a detached deterministic profile pinned to exact source-page bytes."""

    validate_source_quality_core(payload)
    detached = json.loads(_canonical_json(payload).decode("ascii"))
    detached["derivedState"] = derive_source_quality_state(detached)
    detached["profileSha256"] = sha256(_canonical_json(detached)).hexdigest()
    return detached


def validate_source_quality_profile(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate complete derived state and deterministic SHA-256 fail closed."""

    if type(payload) is not dict or set(payload) != _FULL_KEYS:
        raise SourceQualityError("source_quality_schema_invalid")
    if not _matches(_SHA_RE, payload["profileSha256"]):
        raise SourceQualityError("source_quality_hash_invalid")

    core = {key: deepcopy(payload[key]) for key in _CORE_KEYS}
    validate_source_quality_core(core)

    derived = _require_exact_keys(
        payload["derivedState"], _DERIVED_KEYS, "source_quality_derived_state_invalid"
    )
    expected_derived = derive_source_quality_state(core)
    if dict(derived) != expected_derived:
        raise SourceQualityError("source_quality_derived_state_invalid")

    expected_hash = build_source_quality_profile(core)["profileSha256"]
    if payload["profileSha256"] != expected_hash:
        raise SourceQualityError("source_quality_hash_invalid")
    return deepcopy(dict(payload))
