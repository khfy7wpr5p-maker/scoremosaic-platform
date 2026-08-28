"""Research-only engine reliability calibration evidence for polyphonic OMR.

SM-POLY-08 measures how reported engine confidence relates to teacher-gold
correctness under explicitly referenced notation-complexity and source-quality
context. It never rewrites engine confidence, ranks engines, selects a winner,
changes Stage 7, or creates production thresholds.
"""
from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
import json
import re
from typing import Any, Iterable, Mapping

OBSERVATION_SCHEMA_VERSION = "scoremosaic-engine-reliability-observation-v1"
REPORT_SCHEMA_VERSION = "scoremosaic-engine-reliability-report-v1"
BINNING_METHOD = "FIXED_10_BIN_BASIS_POINTS_V1"
BRIER_METHOD = "BINARY_BRIER_EXACT_RATIONAL_V1"
ECE_METHOD = "FIXED_BIN_ECE_EXACT_RATIONAL_V1"
CORRECTNESS_METHOD = "TEACHER_GOLD_BINARY_CORRECTNESS_V1"
CONFIDENCE_SCALE = "CORRECTNESS_CONFIDENCE_BASIS_POINTS_V1"
CURRENT_ENGINES = ("audiveris", "homr", "clarity")
TARGET_CATEGORIES = (
    "parse",
    "structuralValidity",
    "pitch",
    "duration",
    "onset",
    "voice",
    "staff",
    "tie",
    "tuplet",
    "measureConsistency",
    "relationCorrectness",
)
SOURCE_QUALITY_SEVERITIES = ("LOW", "MODERATE", "HIGH", "SEVERE", "UNAVAILABLE")
CONFIDENCE_SOURCES = (
    "ENGINE_NATIVE_REPORTED",
    "IMPORTED_BENCHMARK_TELEMETRY",
    "REPOSITORY_RESEARCH_FIXTURE",
)
MAX_OBSERVATIONS = 100_000
MAX_GROUPS = 2_048
MAX_CONTEXT_SLICES = 8_192

_SHA_RE = re.compile(r"[0-9a-f]{64}\Z")
_OBS_ID_RE = re.compile(r"reliability_obs_[0-9a-f]{24}\Z")
_REPORT_ID_RE = re.compile(r"reliability_report_[0-9a-f]{24}\Z")
_FIXTURE_ID_RE = re.compile(r"poly_fixture_[A-Za-z0-9_-]{8,96}\Z")
_SAFE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_SAFE_VERSION_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+:-]{0,127}\Z")
_PROFILE_ID_RE = re.compile(r"(?:complexity|source_quality)_[0-9a-f]{24}\Z")

_BOUNDARIES = {
    "researchOnly": True,
    "readOnly": True,
    "confidenceRewriting": False,
    "recalibratedProbabilityOutput": False,
    "engineRanking": False,
    "winnerSelection": False,
    "selectivePrediction": False,
    "productionThreshold": False,
    "productionDecisionAuthority": False,
    "automaticMerge": False,
    "automaticCorrection": False,
    "teacherAuthorityOverride": False,
    "stage7EvidenceMutation": False,
    "stage7QuorumChange": False,
    "stOmrIntegration": False,
}

_OBSERVATION_KEYS = {
    "schemaVersion",
    "observationId",
    "fixtureId",
    "target",
    "engine",
    "confidence",
    "context",
    "provenance",
    "boundaries",
    "observationSha256",
}
_TARGET_KEYS = {"category", "targetUnitId", "correct", "method"}
_ENGINE_KEYS = {"name", "engineVersion", "modelVersion"}
_CONFIDENCE_KEYS = {
    "available",
    "basisPoints",
    "evidenceSource",
    "methodVersion",
    "scale",
    "scope",
    "calibratedInput",
}
_CONTEXT_KEYS = {"complexity", "sourceQuality"}
_COMPLEXITY_KEYS = {
    "available",
    "profileId",
    "profileSha256",
    "voiceCount",
    "maxSimultaneousVoiceCount",
    "multiStaffPresent",
    "tupletPresent",
    "overlapDensityBasisPoints",
}
_SOURCE_QUALITY_KEYS = {
    "available",
    "profileId",
    "profileSha256",
    "severity",
    "maxDegradationRiskBasisPoints",
}
_PROVENANCE_KEYS = {
    "teacherGoldReferenceSha256",
    "semanticEvidenceSha256",
    "contextBindingMethodVersion",
}
_REPORT_KEYS = {
    "schemaVersion",
    "reportId",
    "method",
    "observationCount",
    "eligibleObservationCount",
    "observationSetSha256",
    "groups",
    "contextSlices",
    "boundaries",
    "reportSha256",
}
_GROUP_KEYS = {
    "engine",
    "category",
    "confidenceMethodVersion",
    "observationCount",
    "correctCount",
    "empiricalAccuracy",
    "meanReportedConfidenceBasisPoints",
    "brierScore",
    "expectedCalibrationError",
    "reliabilityBins",
    "contextCoverage",
}
_SLICE_KEYS = {
    "engine",
    "category",
    "confidenceMethodVersion",
    "dimension",
    "value",
    "observationCount",
    "correctCount",
    "empiricalAccuracy",
    "meanReportedConfidenceBasisPoints",
    "brierScore",
    "expectedCalibrationError",
}
_FRACTION_KEYS = {"numerator", "denominator"}
_BIN_KEYS = {
    "index",
    "lowerInclusiveBasisPoints",
    "upperInclusiveBasisPoints",
    "observationCount",
    "correctCount",
    "empiricalAccuracy",
    "meanReportedConfidenceBasisPoints",
    "absoluteCalibrationGap",
}
_COVERAGE_KEYS = {"complexityObservationCount", "sourceQualityObservationCount"}


class ReliabilityCalibrationError(ValueError):
    """Stable fail-closed SM-POLY-08 validation error."""

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
        raise ReliabilityCalibrationError("non_canonical_json") from None


def _matches(pattern: re.Pattern[str], value: object) -> bool:
    return type(value) is str and pattern.fullmatch(value) is not None


def _exact(value: object, keys: set[str], category: str) -> Mapping[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise ReliabilityCalibrationError(category)
    return value


def _fraction(value: Fraction) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


def _validate_fraction(
    value: object, category: str, *, zero_to_one: bool = False
) -> None:
    item = _exact(value, _FRACTION_KEYS, category)
    numerator = item["numerator"]
    denominator = item["denominator"]
    if type(numerator) is not int or type(denominator) is not int or denominator <= 0:
        raise ReliabilityCalibrationError(category)
    reduced = Fraction(numerator, denominator)
    if reduced.numerator != numerator or reduced.denominator != denominator:
        raise ReliabilityCalibrationError(category)
    if zero_to_one and not 0 <= reduced <= 1:
        raise ReliabilityCalibrationError(category)


def _unavailable_complexity() -> dict[str, Any]:
    return {
        "available": False,
        "profileId": None,
        "profileSha256": None,
        "voiceCount": None,
        "maxSimultaneousVoiceCount": None,
        "multiStaffPresent": None,
        "tupletPresent": None,
        "overlapDensityBasisPoints": None,
    }


def _unavailable_source_quality() -> dict[str, Any]:
    return {
        "available": False,
        "profileId": None,
        "profileSha256": None,
        "severity": None,
        "maxDegradationRiskBasisPoints": None,
    }


def _validate_complexity(value: object) -> None:
    item = _exact(value, _COMPLEXITY_KEYS, "complexity_context_invalid")
    if type(item["available"]) is not bool:
        raise ReliabilityCalibrationError("complexity_context_invalid")
    if not item["available"]:
        if any(item[key] is not None for key in _COMPLEXITY_KEYS - {"available"}):
            raise ReliabilityCalibrationError("complexity_context_invalid")
        return
    if (
        not _matches(_PROFILE_ID_RE, item["profileId"])
        or not str(item["profileId"]).startswith("complexity_")
        or not _matches(_SHA_RE, item["profileSha256"])
        or type(item["voiceCount"]) is not int
        or not 0 <= item["voiceCount"] <= 512
        or (
            item["maxSimultaneousVoiceCount"] is not None
            and (
                type(item["maxSimultaneousVoiceCount"]) is not int
                or not 0 <= item["maxSimultaneousVoiceCount"] <= 512
            )
        )
        or type(item["multiStaffPresent"]) is not bool
        or type(item["tupletPresent"]) is not bool
        or type(item["overlapDensityBasisPoints"]) is not int
        or not 0 <= item["overlapDensityBasisPoints"] <= 10_000
    ):
        raise ReliabilityCalibrationError("complexity_context_invalid")


def _validate_source_quality(value: object) -> None:
    item = _exact(value, _SOURCE_QUALITY_KEYS, "source_quality_context_invalid")
    if type(item["available"]) is not bool:
        raise ReliabilityCalibrationError("source_quality_context_invalid")
    if not item["available"]:
        if any(item[key] is not None for key in _SOURCE_QUALITY_KEYS - {"available"}):
            raise ReliabilityCalibrationError("source_quality_context_invalid")
        return
    risk = item["maxDegradationRiskBasisPoints"]
    if (
        not _matches(_PROFILE_ID_RE, item["profileId"])
        or not str(item["profileId"]).startswith("source_quality_")
        or not _matches(_SHA_RE, item["profileSha256"])
        or item["severity"] not in SOURCE_QUALITY_SEVERITIES
        or (risk is not None and (type(risk) is not int or not 0 <= risk <= 10_000))
        or (item["severity"] == "UNAVAILABLE" and risk is not None)
        or (item["severity"] != "UNAVAILABLE" and risk is None)
    ):
        raise ReliabilityCalibrationError("source_quality_context_invalid")


def validate_reliability_observation(payload: Mapping[str, Any]) -> dict[str, Any]:
    item = _exact(payload, _OBSERVATION_KEYS, "reliability_observation_schema_invalid")
    if (
        item["schemaVersion"] != OBSERVATION_SCHEMA_VERSION
        or not _matches(_OBS_ID_RE, item["observationId"])
        or not _matches(_FIXTURE_ID_RE, item["fixtureId"])
    ):
        raise ReliabilityCalibrationError("reliability_observation_schema_invalid")

    target = _exact(item["target"], _TARGET_KEYS, "reliability_target_invalid")
    if (
        target["category"] not in TARGET_CATEGORIES
        or not _matches(_SAFE_ID_RE, target["targetUnitId"])
        or type(target["correct"]) is not bool
        or target["method"] != CORRECTNESS_METHOD
    ):
        raise ReliabilityCalibrationError("reliability_target_invalid")

    engine = _exact(item["engine"], _ENGINE_KEYS, "reliability_engine_invalid")
    if (
        engine["name"] not in CURRENT_ENGINES
        or not _matches(_SAFE_VERSION_RE, engine["engineVersion"])
        or not _matches(_SAFE_VERSION_RE, engine["modelVersion"])
    ):
        raise ReliabilityCalibrationError("reliability_engine_invalid")

    confidence = _exact(
        item["confidence"], _CONFIDENCE_KEYS, "confidence_evidence_invalid"
    )
    if type(confidence["available"]) is not bool:
        raise ReliabilityCalibrationError("confidence_evidence_invalid")
    if confidence["available"]:
        if (
            type(confidence["basisPoints"]) is not int
            or not 0 <= confidence["basisPoints"] <= 10_000
            or confidence["evidenceSource"] not in CONFIDENCE_SOURCES
            or not _matches(_SAFE_VERSION_RE, confidence["methodVersion"])
            or confidence["scale"] != CONFIDENCE_SCALE
            or confidence["scope"] != "TARGET_UNIT_CORRECTNESS"
            or confidence["calibratedInput"] is not False
        ):
            raise ReliabilityCalibrationError("confidence_evidence_invalid")
    elif any(
        confidence[key] is not None
        for key in (
            "basisPoints",
            "evidenceSource",
            "methodVersion",
            "scale",
            "scope",
            "calibratedInput",
        )
    ):
        raise ReliabilityCalibrationError("confidence_evidence_invalid")

    context = _exact(item["context"], _CONTEXT_KEYS, "reliability_context_invalid")
    _validate_complexity(context["complexity"])
    _validate_source_quality(context["sourceQuality"])

    provenance = _exact(
        item["provenance"], _PROVENANCE_KEYS, "reliability_provenance_invalid"
    )
    if (
        not _matches(_SHA_RE, provenance["teacherGoldReferenceSha256"])
        or not _matches(_SHA_RE, provenance["semanticEvidenceSha256"])
        or not _matches(_SAFE_VERSION_RE, provenance["contextBindingMethodVersion"])
    ):
        raise ReliabilityCalibrationError("reliability_provenance_invalid")

    boundaries = _exact(
        item["boundaries"], set(_BOUNDARIES), "authority_boundary_invalid"
    )
    if any(boundaries[key] is not expected for key, expected in _BOUNDARIES.items()):
        raise ReliabilityCalibrationError("authority_boundary_invalid")

    if not _matches(_SHA_RE, item["observationSha256"]):
        raise ReliabilityCalibrationError("reliability_observation_hash_invalid")
    without_hash = deepcopy(dict(item))
    without_hash.pop("observationSha256")
    expected = sha256(_canonical_json(without_hash)).hexdigest()
    if item["observationSha256"] != expected:
        raise ReliabilityCalibrationError("reliability_observation_hash_invalid")

    identity = deepcopy(dict(item))
    identity.pop("observationId")
    identity.pop("observationSha256")
    expected_id = "reliability_obs_" + sha256(_canonical_json(identity)).hexdigest()[:24]
    if item["observationId"] != expected_id:
        raise ReliabilityCalibrationError("reliability_observation_id_mismatch")
    return deepcopy(dict(item))


def complexity_context_from_profile(profile: Mapping[str, Any]) -> dict[str, Any]:
    """Extract only componentized SM-POLY-07 context from a validated profile."""
    from .polyphony_complexity import validate_polyphony_complexity_profile

    item = validate_polyphony_complexity_profile(profile)
    dimensions = item["dimensions"]

    def value(dimension: str, metric: str) -> Any:
        evidence = dimensions[dimension][metric]
        return evidence["value"] if evidence["available"] else None

    context = {
        "available": True,
        "profileId": item["profileId"],
        "profileSha256": item["profileSha256"],
        "voiceCount": value("voiceComplexity", "voiceCount"),
        "maxSimultaneousVoiceCount": value(
            "voiceComplexity", "maxSimultaneousVoiceCount"
        ),
        "multiStaffPresent": value("staffComplexity", "multiStaffPresent"),
        "tupletPresent": value("tupletComplexity", "tupletPresent"),
        "overlapDensityBasisPoints": value("overlapComplexity", "overlapDensity"),
    }
    _validate_complexity(context)
    return context


def source_quality_context_from_profile(profile: Mapping[str, Any]) -> dict[str, Any]:
    """Extract deterministic SM-POLY-06 severity context without changing confidence."""
    from .source_quality import validate_source_quality_profile

    item = validate_source_quality_profile(profile)
    derived = item["derivedState"]
    context = {
        "available": True,
        "profileId": item["profileId"],
        "profileSha256": item["profileSha256"],
        "severity": derived["severity"],
        "maxDegradationRiskBasisPoints": derived["maxDegradationRiskBasisPoints"],
    }
    _validate_source_quality(context)
    return context


def build_reliability_observation(
    *,
    fixture_id: str,
    target_category: str,
    target_unit_id: str,
    correct: bool,
    engine: str,
    engine_version: str,
    model_version: str,
    confidence_basis_points: int | None,
    confidence_evidence_source: str | None,
    confidence_method_version: str | None,
    teacher_gold_reference_sha256: str,
    semantic_evidence_sha256: str,
    context_binding_method_version: str,
    complexity: Mapping[str, Any] | None = None,
    source_quality: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one deterministic binary research observation.

    ``complexity`` and ``source_quality`` are already extracted, validated sidecar
    references/values. This function intentionally does not infer them from engine
    confidence or modify the confidence value.
    """
    confidence_available = confidence_basis_points is not None
    if not confidence_available and (
        confidence_evidence_source is not None or confidence_method_version is not None
    ):
        raise ReliabilityCalibrationError("confidence_evidence_invalid")
    confidence = (
        {
            "available": True,
            "basisPoints": confidence_basis_points,
            "evidenceSource": confidence_evidence_source,
            "methodVersion": confidence_method_version,
            "scale": CONFIDENCE_SCALE,
            "scope": "TARGET_UNIT_CORRECTNESS",
            "calibratedInput": False,
        }
        if confidence_available
        else {
            "available": False,
            "basisPoints": None,
            "evidenceSource": None,
            "methodVersion": None,
            "scale": None,
            "scope": None,
            "calibratedInput": None,
        }
    )
    core = {
        "schemaVersion": OBSERVATION_SCHEMA_VERSION,
        "observationId": "placeholder",
        "fixtureId": fixture_id,
        "target": {
            "category": target_category,
            "targetUnitId": target_unit_id,
            "correct": correct,
            "method": CORRECTNESS_METHOD,
        },
        "engine": {
            "name": engine,
            "engineVersion": engine_version,
            "modelVersion": model_version,
        },
        "confidence": confidence,
        "context": {
            "complexity": (
                deepcopy(dict(complexity))
                if complexity is not None
                else _unavailable_complexity()
            ),
            "sourceQuality": (
                deepcopy(dict(source_quality))
                if source_quality is not None
                else _unavailable_source_quality()
            ),
        },
        "provenance": {
            "teacherGoldReferenceSha256": teacher_gold_reference_sha256,
            "semanticEvidenceSha256": semantic_evidence_sha256,
            "contextBindingMethodVersion": context_binding_method_version,
        },
        "boundaries": deepcopy(_BOUNDARIES),
    }
    identity = deepcopy(core)
    identity.pop("observationId")
    core["observationId"] = "reliability_obs_" + sha256(_canonical_json(identity)).hexdigest()[:24]
    core["observationSha256"] = sha256(_canonical_json(core)).hexdigest()
    return validate_reliability_observation(core)


def _bin_index(basis_points: int) -> int:
    return min(9, basis_points // 1000)


def _metrics(items: list[Mapping[str, Any]]) -> dict[str, Any]:
    count = len(items)
    if count <= 0:
        raise ReliabilityCalibrationError("empty_calibration_group")
    correct = sum(1 for item in items if item["target"]["correct"])
    confidence_sum = sum(item["confidence"]["basisPoints"] for item in items)
    brier_numerator = sum(
        (10_000 - item["confidence"]["basisPoints"]) ** 2
        if item["target"]["correct"]
        else item["confidence"]["basisPoints"] ** 2
        for item in items
    )
    brier = Fraction(brier_numerator, count * 100_000_000)

    bins: list[dict[str, Any]] = []
    ece_abs_sum = 0
    for index in range(10):
        bucket = [
            item
            for item in items
            if _bin_index(item["confidence"]["basisPoints"]) == index
        ]
        lower = index * 1000
        upper = 10_000 if index == 9 else (index + 1) * 1000 - 1
        if bucket:
            bucket_count = len(bucket)
            bucket_correct = sum(1 for item in bucket if item["target"]["correct"])
            bucket_conf_sum = sum(
                item["confidence"]["basisPoints"] for item in bucket
            )
            empirical = Fraction(bucket_correct, bucket_count)
            mean_conf_bp = Fraction(bucket_conf_sum, bucket_count)
            gap = abs(
                Fraction(
                    bucket_correct * 10_000 - bucket_conf_sum,
                    bucket_count * 10_000,
                )
            )
            ece_abs_sum += abs(bucket_correct * 10_000 - bucket_conf_sum)
            bins.append(
                {
                    "index": index,
                    "lowerInclusiveBasisPoints": lower,
                    "upperInclusiveBasisPoints": upper,
                    "observationCount": bucket_count,
                    "correctCount": bucket_correct,
                    "empiricalAccuracy": _fraction(empirical),
                    "meanReportedConfidenceBasisPoints": _fraction(mean_conf_bp),
                    "absoluteCalibrationGap": _fraction(gap),
                }
            )
        else:
            bins.append(
                {
                    "index": index,
                    "lowerInclusiveBasisPoints": lower,
                    "upperInclusiveBasisPoints": upper,
                    "observationCount": 0,
                    "correctCount": 0,
                    "empiricalAccuracy": None,
                    "meanReportedConfidenceBasisPoints": None,
                    "absoluteCalibrationGap": None,
                }
            )
    ece = Fraction(ece_abs_sum, count * 10_000)
    return {
        "observationCount": count,
        "correctCount": correct,
        "empiricalAccuracy": _fraction(Fraction(correct, count)),
        "meanReportedConfidenceBasisPoints": _fraction(
            Fraction(confidence_sum, count)
        ),
        "brierScore": _fraction(brier),
        "expectedCalibrationError": _fraction(ece),
        "reliabilityBins": bins,
    }


def _overlap_band(value: int) -> str:
    if value == 0:
        return "ZERO"
    if value < 2500:
        return "LOW_NONZERO"
    if value < 5000:
        return "MODERATE"
    if value < 7500:
        return "HIGH"
    return "VERY_HIGH"


def _slice_values(item: Mapping[str, Any]) -> list[tuple[str, str]]:
    output: list[tuple[str, str]] = []
    complexity = item["context"]["complexity"]
    if complexity["available"]:
        output.extend(
            [
                ("voiceCount", str(complexity["voiceCount"])),
                (
                    "multiStaffPresent",
                    "true" if complexity["multiStaffPresent"] else "false",
                ),
                (
                    "tupletPresent",
                    "true" if complexity["tupletPresent"] else "false",
                ),
                (
                    "overlapDensityBand",
                    _overlap_band(complexity["overlapDensityBasisPoints"]),
                ),
            ]
        )
        if complexity["maxSimultaneousVoiceCount"] is not None:
            output.append(
                (
                    "maxSimultaneousVoiceCount",
                    str(complexity["maxSimultaneousVoiceCount"]),
                )
            )
    quality = item["context"]["sourceQuality"]
    if quality["available"]:
        output.append(("sourceQualitySeverity", quality["severity"]))
    return output


def build_reliability_report(
    observations: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Aggregate exact calibration evidence without fitting or decision authority."""
    items = [validate_reliability_observation(item) for item in observations]
    if len(items) > MAX_OBSERVATIONS:
        raise ReliabilityCalibrationError("observation_limit_exceeded")
    seen: set[str] = set()
    seen_units: set[tuple[Any, ...]] = set()
    for item in items:
        if item["observationId"] in seen:
            raise ReliabilityCalibrationError("duplicate_reliability_observation")
        seen.add(item["observationId"])
        confidence = item["confidence"]
        unit_key = (
            item["fixtureId"],
            item["engine"]["name"],
            item["engine"]["engineVersion"],
            item["engine"]["modelVersion"],
            item["target"]["category"],
            item["target"]["targetUnitId"],
            confidence["evidenceSource"],
            confidence["methodVersion"],
        )
        if unit_key in seen_units:
            raise ReliabilityCalibrationError("duplicate_reliability_target_unit")
        seen_units.add(unit_key)

    eligible = [item for item in items if item["confidence"]["available"]]
    grouped: dict[tuple[str, str, str], list[Mapping[str, Any]]] = {}
    for item in eligible:
        key = (
            item["engine"]["name"],
            item["target"]["category"],
            item["confidence"]["methodVersion"],
        )
        grouped.setdefault(key, []).append(item)
    if len(grouped) > MAX_GROUPS:
        raise ReliabilityCalibrationError("group_limit_exceeded")

    groups: list[dict[str, Any]] = []
    for key in sorted(
        grouped,
        key=lambda value: (CURRENT_ENGINES.index(value[0]), value[1], value[2]),
    ):
        group_items = grouped[key]
        stats = _metrics(group_items)
        groups.append(
            {
                "engine": key[0],
                "category": key[1],
                "confidenceMethodVersion": key[2],
                **stats,
                "contextCoverage": {
                    "complexityObservationCount": sum(
                        1
                        for item in group_items
                        if item["context"]["complexity"]["available"]
                    ),
                    "sourceQualityObservationCount": sum(
                        1
                        for item in group_items
                        if item["context"]["sourceQuality"]["available"]
                    ),
                },
            }
        )

    slices_map: dict[
        tuple[str, str, str, str, str], list[Mapping[str, Any]]
    ] = {}
    for item in eligible:
        base = (
            item["engine"]["name"],
            item["target"]["category"],
            item["confidence"]["methodVersion"],
        )
        for dimension, value in _slice_values(item):
            slices_map.setdefault(base + (dimension, value), []).append(item)
    if len(slices_map) > MAX_CONTEXT_SLICES:
        raise ReliabilityCalibrationError("context_slice_limit_exceeded")

    context_slices: list[dict[str, Any]] = []
    for key in sorted(
        slices_map,
        key=lambda value: (
            CURRENT_ENGINES.index(value[0]),
            value[1],
            value[2],
            value[3],
            value[4],
        ),
    ):
        stats = _metrics(slices_map[key])
        stats.pop("reliabilityBins")
        context_slices.append(
            {
                "engine": key[0],
                "category": key[1],
                "confidenceMethodVersion": key[2],
                "dimension": key[3],
                "value": key[4],
                **stats,
            }
        )

    core = {
        "schemaVersion": REPORT_SCHEMA_VERSION,
        "reportId": "placeholder",
        "method": {
            "binning": BINNING_METHOD,
            "brier": BRIER_METHOD,
            "expectedCalibrationError": ECE_METHOD,
            "fittedCalibrationModel": None,
            "recalibratedProbability": None,
        },
        "observationCount": len(items),
        "eligibleObservationCount": len(eligible),
        "observationSetSha256": sha256(
            _canonical_json(sorted(item["observationSha256"] for item in items))
        ).hexdigest(),
        "groups": groups,
        "contextSlices": context_slices,
        "boundaries": deepcopy(_BOUNDARIES),
    }
    identity = deepcopy(core)
    identity.pop("reportId")
    core["reportId"] = (
        "reliability_report_" + sha256(_canonical_json(identity)).hexdigest()[:24]
    )
    core["reportSha256"] = sha256(_canonical_json(core)).hexdigest()
    return validate_reliability_report(core)


def _validate_metric_bundle(item: Mapping[str, Any], *, bins: bool) -> None:
    if type(item["observationCount"]) is not int or item["observationCount"] <= 0:
        raise ReliabilityCalibrationError("calibration_metric_invalid")
    if (
        type(item["correctCount"]) is not int
        or not 0 <= item["correctCount"] <= item["observationCount"]
    ):
        raise ReliabilityCalibrationError("calibration_metric_invalid")
    _validate_fraction(
        item["empiricalAccuracy"], "calibration_metric_invalid", zero_to_one=True
    )
    _validate_fraction(
        item["meanReportedConfidenceBasisPoints"], "calibration_metric_invalid"
    )
    mean = Fraction(
        item["meanReportedConfidenceBasisPoints"]["numerator"],
        item["meanReportedConfidenceBasisPoints"]["denominator"],
    )
    if not 0 <= mean <= 10_000:
        raise ReliabilityCalibrationError("calibration_metric_invalid")
    _validate_fraction(
        item["brierScore"], "calibration_metric_invalid", zero_to_one=True
    )
    _validate_fraction(
        item["expectedCalibrationError"],
        "calibration_metric_invalid",
        zero_to_one=True,
    )
    if bins:
        if type(item["reliabilityBins"]) is not list or len(item["reliabilityBins"]) != 10:
            raise ReliabilityCalibrationError("reliability_bins_invalid")
        total = 0
        correct = 0
        for index, raw in enumerate(item["reliabilityBins"]):
            bucket = _exact(raw, _BIN_KEYS, "reliability_bins_invalid")
            expected_lower = index * 1000
            expected_upper = 10_000 if index == 9 else (index + 1) * 1000 - 1
            if (
                bucket["index"] != index
                or bucket["lowerInclusiveBasisPoints"] != expected_lower
                or bucket["upperInclusiveBasisPoints"] != expected_upper
                or type(bucket["observationCount"]) is not int
                or type(bucket["correctCount"]) is not int
                or bucket["observationCount"] < 0
                or not 0 <= bucket["correctCount"] <= bucket["observationCount"]
            ):
                raise ReliabilityCalibrationError("reliability_bins_invalid")
            total += bucket["observationCount"]
            correct += bucket["correctCount"]
            optional = (
                bucket["empiricalAccuracy"],
                bucket["meanReportedConfidenceBasisPoints"],
                bucket["absoluteCalibrationGap"],
            )
            if bucket["observationCount"] == 0:
                if any(value is not None for value in optional):
                    raise ReliabilityCalibrationError("reliability_bins_invalid")
            else:
                _validate_fraction(
                    bucket["empiricalAccuracy"],
                    "reliability_bins_invalid",
                    zero_to_one=True,
                )
                _validate_fraction(
                    bucket["meanReportedConfidenceBasisPoints"],
                    "reliability_bins_invalid",
                )
                _validate_fraction(
                    bucket["absoluteCalibrationGap"],
                    "reliability_bins_invalid",
                    zero_to_one=True,
                )
        if total != item["observationCount"] or correct != item["correctCount"]:
            raise ReliabilityCalibrationError("reliability_bins_invalid")


def validate_reliability_report(payload: Mapping[str, Any]) -> dict[str, Any]:
    item = _exact(payload, _REPORT_KEYS, "reliability_report_schema_invalid")
    if item["schemaVersion"] != REPORT_SCHEMA_VERSION or not _matches(
        _REPORT_ID_RE, item["reportId"]
    ):
        raise ReliabilityCalibrationError("reliability_report_schema_invalid")
    method = _exact(
        item["method"],
        {
            "binning",
            "brier",
            "expectedCalibrationError",
            "fittedCalibrationModel",
            "recalibratedProbability",
        },
        "reliability_report_method_invalid",
    )
    if (
        method["binning"] != BINNING_METHOD
        or method["brier"] != BRIER_METHOD
        or method["expectedCalibrationError"] != ECE_METHOD
        or method["fittedCalibrationModel"] is not None
        or method["recalibratedProbability"] is not None
    ):
        raise ReliabilityCalibrationError("reliability_report_method_invalid")
    if (
        type(item["observationCount"]) is not int
        or not 0 <= item["observationCount"] <= MAX_OBSERVATIONS
        or type(item["eligibleObservationCount"]) is not int
        or not 0 <= item["eligibleObservationCount"] <= item["observationCount"]
        or not _matches(_SHA_RE, item["observationSetSha256"])
        or type(item["groups"]) is not list
        or len(item["groups"]) > MAX_GROUPS
        or type(item["contextSlices"]) is not list
        or len(item["contextSlices"]) > MAX_CONTEXT_SLICES
    ):
        raise ReliabilityCalibrationError("reliability_report_counts_invalid")

    group_total = 0
    group_keys: set[tuple[str, str, str]] = set()
    for raw in item["groups"]:
        group = _exact(raw, _GROUP_KEYS, "reliability_group_invalid")
        key = (
            group["engine"],
            group["category"],
            group["confidenceMethodVersion"],
        )
        if (
            group["engine"] not in CURRENT_ENGINES
            or group["category"] not in TARGET_CATEGORIES
            or not _matches(_SAFE_VERSION_RE, group["confidenceMethodVersion"])
            or key in group_keys
        ):
            raise ReliabilityCalibrationError("reliability_group_invalid")
        group_keys.add(key)
        _validate_metric_bundle(group, bins=True)
        coverage = _exact(
            group["contextCoverage"], _COVERAGE_KEYS, "context_coverage_invalid"
        )
        for value in coverage.values():
            if type(value) is not int or not 0 <= value <= group["observationCount"]:
                raise ReliabilityCalibrationError("context_coverage_invalid")
        group_total += group["observationCount"]
    if group_total != item["eligibleObservationCount"]:
        raise ReliabilityCalibrationError("eligible_group_count_mismatch")

    slice_keys: set[tuple[str, str, str, str, str]] = set()
    for raw in item["contextSlices"]:
        slice_item = _exact(raw, _SLICE_KEYS, "context_slice_invalid")
        key = (
            slice_item["engine"],
            slice_item["category"],
            slice_item["confidenceMethodVersion"],
            slice_item["dimension"],
            slice_item["value"],
        )
        if (
            slice_item["engine"] not in CURRENT_ENGINES
            or slice_item["category"] not in TARGET_CATEGORIES
            or not _matches(_SAFE_VERSION_RE, slice_item["confidenceMethodVersion"])
            or not _matches(_SAFE_ID_RE, slice_item["dimension"])
            or not _matches(_SAFE_ID_RE, slice_item["value"])
            or key in slice_keys
        ):
            raise ReliabilityCalibrationError("context_slice_invalid")
        slice_keys.add(key)
        _validate_metric_bundle(slice_item, bins=False)

    boundaries = _exact(
        item["boundaries"], set(_BOUNDARIES), "authority_boundary_invalid"
    )
    if any(boundaries[key] is not expected for key, expected in _BOUNDARIES.items()):
        raise ReliabilityCalibrationError("authority_boundary_invalid")

    if not _matches(_SHA_RE, item["reportSha256"]):
        raise ReliabilityCalibrationError("reliability_report_hash_invalid")
    without_hash = deepcopy(dict(item))
    without_hash.pop("reportSha256")
    expected = sha256(_canonical_json(without_hash)).hexdigest()
    if item["reportSha256"] != expected:
        raise ReliabilityCalibrationError("reliability_report_hash_invalid")

    identity = deepcopy(dict(item))
    identity.pop("reportId")
    identity.pop("reportSha256")
    expected_id = "reliability_report_" + sha256(_canonical_json(identity)).hexdigest()[:24]
    if item["reportId"] != expected_id:
        raise ReliabilityCalibrationError("reliability_report_id_mismatch")
    return deepcopy(dict(item))


def validate_reliability_report_against_observations(
    payload: Mapping[str, Any], observations: Iterable[Mapping[str, Any]]
) -> dict[str, Any]:
    """Recompute the complete report from source observations and compare exactly."""
    validated = validate_reliability_report(payload)
    items = [validate_reliability_observation(item) for item in observations]
    expected_set_sha = sha256(
        _canonical_json(sorted(item["observationSha256"] for item in items))
    ).hexdigest()
    if validated["observationSetSha256"] != expected_set_sha:
        raise ReliabilityCalibrationError("observation_set_mismatch")
    expected = build_reliability_report(items)
    if validated != expected:
        raise ReliabilityCalibrationError("reliability_report_recompute_mismatch")
    return validated
