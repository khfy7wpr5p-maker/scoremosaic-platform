"""Research-only per-engine semantic metric observations and aggregation.

This module layers on the existing frozen evaluation result contract. It does not
rank engines, select a winner, merge MusicXML, or grant production authority.
"""

from __future__ import annotations

from fractions import Fraction
from hashlib import sha256
import json
import re
from typing import Any, Iterable, Mapping

from .evaluation import METRIC_NAMES, validate_evaluation_result_payload


OBSERVATION_SCHEMA_VERSION = "scoremosaic-polyphonic-engine-semantic-observation-v1"
REPORT_SCHEMA_VERSION = "scoremosaic-polyphonic-engine-semantic-report-v1"
CURRENT_ENGINES = ("audiveris", "homr", "clarity")
SEMANTIC_METRICS = ("pitch", "duration", "onset", "voice", "staff", "tie", "tuplet")
REFERENCE_KINDS = ("TEACHER_GOLD", "MANUALLY_REVIEWED_FIXED_BASELINE")
STRUCTURAL_DISTANCE_METHOD = "CANONICAL_STRUCTURE_DISTANCE_V1"
MEASURE_CONSISTENCY_METHOD = "EXACT_MEASURE_COUNT_V1"
RELATION_METHOD = "TIE_TUPLET_CHORD_EXACT_V1"
TEACHER_EDIT_METHOD = "TEACHER_REVISION_COMMAND_COUNT_V1"

_SHA_RE = re.compile(r"[0-9a-f]{64}\Z")
_OBSERVATION_ID_RE = re.compile(r"poly_metric_obs_[0-9a-f]{24}\Z")
_FIXTURE_ID_RE = re.compile(r"poly_fixture_[A-Za-z0-9_-]{8,96}\Z")
_SAFE_VERSION_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+:-]{0,127}\Z")

_OBSERVATION_KEYS = {
    "schemaVersion",
    "observationId",
    "fixtureId",
    "reference",
    "engine",
    "parse",
    "structuralValidity",
    "semanticMetrics",
    "measureConsistency",
    "relationCorrectness",
    "structuralDistance",
    "teacherEdits",
    "sourceEvaluationResultSha256",
    "boundaries",
}
_REFERENCE_KEYS = {"kind", "artifactSha256", "verified"}
_ENGINE_KEYS = {
    "name",
    "engineVersion",
    "modelVersion",
    "candidateArtifactSha256",
    "canonicalSha256",
}
_PARSE_KEYS = {"attempted", "success"}
_VALIDITY_KEYS = {"available", "valid"}
_METRIC_KEYS = {"available", "correct", "total"}
_METHOD_METRIC_KEYS = {"available", "method", "correct", "total"}
_DISTANCE_KEYS = {"available", "method", "numerator", "denominator", "lowerIsBetter"}
_TEACHER_EDIT_KEYS = {"available", "method", "editCount", "measureCount", "pageCount"}
_BOUNDARIES = {
    "researchEvaluationOnly": True,
    "readOnly": True,
    "singleAggregateAccuracyScore": False,
    "engineRanking": False,
    "winnerSelection": False,
    "automaticMerge": False,
    "automaticCorrection": False,
    "teacherApproval": False,
    "productionDecisionAuthority": False,
    "stOmrIntegration": False,
}


class PolyphonicMetricError(ValueError):
    """Stable fail-closed polyphonic metric contract error."""


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    except (TypeError, ValueError, OverflowError, UnicodeEncodeError) as exc:
        raise PolyphonicMetricError("non_canonical_json") from exc


def _sha(value: object) -> bool:
    return type(value) is str and _SHA_RE.fullmatch(value) is not None


def _safe_version(value: object) -> bool:
    return type(value) is str and _SAFE_VERSION_RE.fullmatch(value) is not None


def _exact_mapping(value: object, keys: set[str], category: str) -> Mapping[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise PolyphonicMetricError(category)
    return value


def _metric_payload(correct: int, total: int) -> dict[str, Any]:
    if (
        type(correct) is not int
        or type(total) is not int
        or correct < 0
        or total < 0
        or correct > total
    ):
        raise PolyphonicMetricError("metric_count_invalid")
    return {"available": True, "correct": correct, "total": total}


def _metric_unavailable() -> dict[str, Any]:
    return {"available": False, "correct": None, "total": None}


def _method_metric_payload(method: str, correct: int, total: int) -> dict[str, Any]:
    payload = _metric_payload(correct, total)
    return {"available": True, "method": method, "correct": payload["correct"], "total": payload["total"]}


def _method_metric_unavailable() -> dict[str, Any]:
    return {"available": False, "method": "UNAVAILABLE", "correct": None, "total": None}


def _distance_unavailable() -> dict[str, Any]:
    return {
        "available": False,
        "method": "UNAVAILABLE",
        "numerator": None,
        "denominator": None,
        "lowerIsBetter": True,
    }


def _teacher_edits_unavailable() -> dict[str, Any]:
    return {
        "available": False,
        "method": "UNAVAILABLE",
        "editCount": None,
        "measureCount": None,
        "pageCount": None,
    }


def _validate_nullable_metric(value: object, category: str) -> Mapping[str, Any]:
    metric = _exact_mapping(value, _METRIC_KEYS, category)
    if type(metric["available"]) is not bool:
        raise PolyphonicMetricError(category)
    if metric["available"]:
        correct = metric["correct"]
        total = metric["total"]
        if (
            type(correct) is not int
            or type(total) is not int
            or correct < 0
            or total < 0
            or correct > total
        ):
            raise PolyphonicMetricError(category)
    elif metric["correct"] is not None or metric["total"] is not None:
        raise PolyphonicMetricError(category)
    return metric


def _validate_method_metric(
    value: object,
    allowed_method: str,
    category: str,
) -> Mapping[str, Any]:
    metric = _exact_mapping(value, _METHOD_METRIC_KEYS, category)
    if type(metric["available"]) is not bool:
        raise PolyphonicMetricError(category)
    if metric["available"]:
        if metric["method"] != allowed_method:
            raise PolyphonicMetricError(category)
        _validate_nullable_metric(
            {"available": True, "correct": metric["correct"], "total": metric["total"]},
            category,
        )
    elif (
        metric["method"] != "UNAVAILABLE"
        or metric["correct"] is not None
        or metric["total"] is not None
    ):
        raise PolyphonicMetricError(category)
    return metric


def _validate_distance(value: object) -> Mapping[str, Any]:
    distance = _exact_mapping(value, _DISTANCE_KEYS, "structural_distance_invalid")
    if type(distance["available"]) is not bool or distance["lowerIsBetter"] is not True:
        raise PolyphonicMetricError("structural_distance_invalid")
    if distance["available"]:
        if distance["method"] != STRUCTURAL_DISTANCE_METHOD:
            raise PolyphonicMetricError("structural_distance_invalid")
        numerator = distance["numerator"]
        denominator = distance["denominator"]
        if (
            type(numerator) is not int
            or type(denominator) is not int
            or numerator < 0
            or denominator <= 0
        ):
            raise PolyphonicMetricError("structural_distance_invalid")
        fraction = Fraction(numerator, denominator)
        if fraction.numerator != numerator or fraction.denominator != denominator:
            raise PolyphonicMetricError("structural_distance_not_reduced")
    elif (
        distance["method"] != "UNAVAILABLE"
        or distance["numerator"] is not None
        or distance["denominator"] is not None
    ):
        raise PolyphonicMetricError("structural_distance_invalid")
    return distance


def _validate_teacher_edits(value: object) -> Mapping[str, Any]:
    edits = _exact_mapping(value, _TEACHER_EDIT_KEYS, "teacher_edits_invalid")
    if type(edits["available"]) is not bool:
        raise PolyphonicMetricError("teacher_edits_invalid")
    if edits["available"]:
        if edits["method"] != TEACHER_EDIT_METHOD:
            raise PolyphonicMetricError("teacher_edits_invalid")
        if (
            type(edits["editCount"]) is not int
            or type(edits["measureCount"]) is not int
            or type(edits["pageCount"]) is not int
            or edits["editCount"] < 0
            or edits["measureCount"] <= 0
            or edits["pageCount"] <= 0
        ):
            raise PolyphonicMetricError("teacher_edits_invalid")
    elif (
        edits["method"] != "UNAVAILABLE"
        or edits["editCount"] is not None
        or edits["measureCount"] is not None
        or edits["pageCount"] is not None
    ):
        raise PolyphonicMetricError("teacher_edits_invalid")
    return edits


def validate_semantic_observation(payload: Mapping[str, Any]) -> None:
    """Validate one closed research-only per-engine metric observation."""

    observation = _exact_mapping(payload, _OBSERVATION_KEYS, "observation_schema_invalid")
    if observation["schemaVersion"] != OBSERVATION_SCHEMA_VERSION:
        raise PolyphonicMetricError("observation_version_invalid")
    if type(observation["observationId"]) is not str or _OBSERVATION_ID_RE.fullmatch(observation["observationId"]) is None:
        raise PolyphonicMetricError("observation_id_invalid")
    if type(observation["fixtureId"]) is not str or _FIXTURE_ID_RE.fullmatch(observation["fixtureId"]) is None:
        raise PolyphonicMetricError("fixture_id_invalid")

    reference = _exact_mapping(observation["reference"], _REFERENCE_KEYS, "reference_invalid")
    if (
        reference["kind"] not in REFERENCE_KINDS
        or not _sha(reference["artifactSha256"])
        or reference["verified"] is not True
    ):
        raise PolyphonicMetricError("reference_invalid")

    engine = _exact_mapping(observation["engine"], _ENGINE_KEYS, "engine_invalid")
    if (
        engine["name"] not in CURRENT_ENGINES
        or not _safe_version(engine["engineVersion"])
        or not _safe_version(engine["modelVersion"])
        or not _sha(engine["candidateArtifactSha256"])
        or (engine["canonicalSha256"] is not None and not _sha(engine["canonicalSha256"]))
    ):
        raise PolyphonicMetricError("engine_invalid")

    parse = _exact_mapping(observation["parse"], _PARSE_KEYS, "parse_invalid")
    if parse["attempted"] is not True or type(parse["success"]) is not bool:
        raise PolyphonicMetricError("parse_invalid")

    validity = _exact_mapping(
        observation["structuralValidity"], _VALIDITY_KEYS, "structural_validity_invalid"
    )
    if type(validity["available"]) is not bool:
        raise PolyphonicMetricError("structural_validity_invalid")
    if validity["available"]:
        if type(validity["valid"]) is not bool:
            raise PolyphonicMetricError("structural_validity_invalid")
    elif validity["valid"] is not None:
        raise PolyphonicMetricError("structural_validity_invalid")

    semantic = observation["semanticMetrics"]
    if type(semantic) is not dict or tuple(semantic) != SEMANTIC_METRICS:
        raise PolyphonicMetricError("semantic_metrics_invalid")
    for name in SEMANTIC_METRICS:
        _validate_nullable_metric(semantic[name], f"semantic_metric_{name}_invalid")

    _validate_method_metric(
        observation["measureConsistency"],
        MEASURE_CONSISTENCY_METHOD,
        "measure_consistency_invalid",
    )
    _validate_method_metric(
        observation["relationCorrectness"],
        RELATION_METHOD,
        "relation_correctness_invalid",
    )
    _validate_distance(observation["structuralDistance"])
    _validate_teacher_edits(observation["teacherEdits"])

    result_sha = observation["sourceEvaluationResultSha256"]
    if result_sha is not None and not _sha(result_sha):
        raise PolyphonicMetricError("source_evaluation_result_sha_invalid")
    if observation["boundaries"] != _BOUNDARIES:
        raise PolyphonicMetricError("observation_boundaries_invalid")

    if not parse["success"]:
        if engine["canonicalSha256"] is not None or validity["available"]:
            raise PolyphonicMetricError("parse_failure_evidence_invalid")
        if any(semantic[name]["available"] for name in SEMANTIC_METRICS):
            raise PolyphonicMetricError("parse_failure_semantic_evidence_invalid")
        if observation["measureConsistency"]["available"]:
            raise PolyphonicMetricError("parse_failure_measure_evidence_invalid")
        if observation["relationCorrectness"]["available"]:
            raise PolyphonicMetricError("parse_failure_relation_evidence_invalid")
        if observation["structuralDistance"]["available"]:
            raise PolyphonicMetricError("parse_failure_distance_evidence_invalid")


def _metric_map(evaluation_result: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {item["name"]: item for item in evaluation_result["metrics"]}


def _stable_observation_id(identity: Mapping[str, Any]) -> str:
    return "poly_metric_obs_" + sha256(_canonical_json(identity)).hexdigest()[:24]


def observation_from_fixed_evaluation_result(
    evaluation_result: Mapping[str, Any],
    *,
    fixture_id: str,
    reference_artifact_sha256: str,
) -> dict[str, Any]:
    """Adapt the existing fixed evaluator result without changing its contract.

    This adapter is compatibility evidence only. It does not reclassify fixed-v1 as
    the new teacher-gold benchmark and it does not make a general accuracy claim.
    """

    validate_evaluation_result_payload(evaluation_result)
    if type(fixture_id) is not str or _FIXTURE_ID_RE.fullmatch(fixture_id) is None:
        raise PolyphonicMetricError("fixture_id_invalid")
    if not _sha(reference_artifact_sha256):
        raise PolyphonicMetricError("reference_invalid")

    metrics = _metric_map(evaluation_result)
    mapping = {
        "pitch": "pitch",
        "duration": "effectiveDuration",
        "onset": "onset",
        "voice": "voice",
        "staff": "staff",
        "tie": "ties",
        "tuplet": "tuplet",
    }
    semantic = {
        output_name: _metric_payload(
            metrics[source_name]["correct"], metrics[source_name]["total"]
        )
        for output_name, source_name in mapping.items()
    }

    counts = evaluation_result["counts"]
    measure_consistency = _method_metric_payload(
        MEASURE_CONSISTENCY_METHOD,
        1 if counts["exact"]["measureCount"] else 0,
        1,
    )
    relation_correct = sum(metrics[name]["correct"] for name in ("ties", "tuplet", "chord"))
    relation_total = sum(metrics[name]["total"] for name in ("ties", "tuplet", "chord"))
    relation_correctness = _method_metric_payload(
        RELATION_METHOD,
        relation_correct,
        relation_total,
    )

    event_presence = metrics["eventPresence"]
    distance_numerator = (
        abs(counts["reference"]["partCount"] - counts["candidate"]["partCount"])
        + abs(counts["reference"]["measureCount"] - counts["candidate"]["measureCount"])
        + event_presence["incorrect"]
    )
    distance_denominator = max(
        1,
        counts["reference"]["partCount"]
        + counts["reference"]["measureCount"]
        + event_presence["total"],
    )
    distance = Fraction(distance_numerator, distance_denominator)

    candidate = evaluation_result["candidate"]
    identity = {
        "fixtureId": fixture_id,
        "evaluationResultSha256": evaluation_result["resultSha256"],
        "referenceArtifactSha256": reference_artifact_sha256,
        "engine": candidate["engine"],
    }
    observation = {
        "schemaVersion": OBSERVATION_SCHEMA_VERSION,
        "observationId": _stable_observation_id(identity),
        "fixtureId": fixture_id,
        "reference": {
            "kind": "MANUALLY_REVIEWED_FIXED_BASELINE",
            "artifactSha256": reference_artifact_sha256,
            "verified": True,
        },
        "engine": {
            "name": candidate["engine"],
            "engineVersion": candidate["engineVersion"],
            "modelVersion": candidate["modelVersion"],
            "candidateArtifactSha256": candidate["artifactSha256"],
            "canonicalSha256": candidate["canonicalSha256"],
        },
        "parse": {"attempted": True, "success": True},
        "structuralValidity": {"available": True, "valid": True},
        "semanticMetrics": semantic,
        "measureConsistency": measure_consistency,
        "relationCorrectness": relation_correctness,
        "structuralDistance": {
            "available": True,
            "method": STRUCTURAL_DISTANCE_METHOD,
            "numerator": distance.numerator,
            "denominator": distance.denominator,
            "lowerIsBetter": True,
        },
        "teacherEdits": _teacher_edits_unavailable(),
        "sourceEvaluationResultSha256": evaluation_result["resultSha256"],
        "boundaries": dict(_BOUNDARIES),
    }
    validate_semantic_observation(observation)
    return observation


def build_parse_failure_observation(
    *,
    fixture_id: str,
    reference_kind: str,
    reference_artifact_sha256: str,
    engine: str,
    engine_version: str,
    model_version: str,
    candidate_artifact_sha256: str,
) -> dict[str, Any]:
    """Represent a parse failure without inventing downstream semantic evidence."""

    identity = {
        "fixtureId": fixture_id,
        "referenceKind": reference_kind,
        "referenceArtifactSha256": reference_artifact_sha256,
        "engine": engine,
        "candidateArtifactSha256": candidate_artifact_sha256,
        "failure": "parse",
    }
    observation = {
        "schemaVersion": OBSERVATION_SCHEMA_VERSION,
        "observationId": _stable_observation_id(identity),
        "fixtureId": fixture_id,
        "reference": {
            "kind": reference_kind,
            "artifactSha256": reference_artifact_sha256,
            "verified": True,
        },
        "engine": {
            "name": engine,
            "engineVersion": engine_version,
            "modelVersion": model_version,
            "candidateArtifactSha256": candidate_artifact_sha256,
            "canonicalSha256": None,
        },
        "parse": {"attempted": True, "success": False},
        "structuralValidity": {"available": False, "valid": None},
        "semanticMetrics": {name: _metric_unavailable() for name in SEMANTIC_METRICS},
        "measureConsistency": _method_metric_unavailable(),
        "relationCorrectness": _method_metric_unavailable(),
        "structuralDistance": _distance_unavailable(),
        "teacherEdits": _teacher_edits_unavailable(),
        "sourceEvaluationResultSha256": None,
        "boundaries": dict(_BOUNDARIES),
    }
    validate_semantic_observation(observation)
    return observation


def _ratio(numerator: int, denominator: int) -> dict[str, int] | None:
    if denominator == 0:
        return None
    fraction = Fraction(numerator, denominator)
    return {"numerator": fraction.numerator, "denominator": fraction.denominator}


def _aggregate_metric(observations: list[Mapping[str, Any]], key_path: tuple[str, ...]) -> dict[str, Any]:
    available_count = 0
    correct = 0
    total = 0
    for observation in observations:
        metric: Mapping[str, Any] = observation
        for key in key_path:
            metric = metric[key]
        if metric["available"]:
            available_count += 1
            correct += metric["correct"]
            total += metric["total"]
    return {
        "availableObservationCount": available_count,
        "correct": correct,
        "total": total,
        "ratio": _ratio(correct, total),
    }


def _aggregate_distance(observations: list[Mapping[str, Any]]) -> dict[str, Any]:
    values: list[Fraction] = []
    for observation in observations:
        distance = observation["structuralDistance"]
        if distance["available"]:
            values.append(Fraction(distance["numerator"], distance["denominator"]))
    if not values:
        mean = None
    else:
        value = sum(values, Fraction(0, 1)) / len(values)
        mean = {"numerator": value.numerator, "denominator": value.denominator}
    return {
        "method": STRUCTURAL_DISTANCE_METHOD,
        "availableObservationCount": len(values),
        "mean": mean,
        "lowerIsBetter": True,
        "tednClaimed": False,
    }


def _aggregate_teacher_edits(observations: list[Mapping[str, Any]]) -> dict[str, Any]:
    available = [obs["teacherEdits"] for obs in observations if obs["teacherEdits"]["available"]]
    edits = sum(item["editCount"] for item in available)
    measures = sum(item["measureCount"] for item in available)
    pages = sum(item["pageCount"] for item in available)
    return {
        "method": TEACHER_EDIT_METHOD,
        "availableObservationCount": len(available),
        "totalEdits": edits,
        "totalMeasures": measures,
        "totalPages": pages,
        "editsPerMeasure": _ratio(edits, measures),
        "editsPerPage": _ratio(edits, pages),
    }


def aggregate_engine_semantic_metrics(
    observations: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Aggregate evidence by engine without producing one overall accuracy score."""

    items = [dict(item) for item in observations]
    seen_ids: set[str] = set()
    seen_engine_fixture: set[tuple[str, str]] = set()
    for item in items:
        validate_semantic_observation(item)
        observation_id = item["observationId"]
        pair = (item["engine"]["name"], item["fixtureId"])
        if observation_id in seen_ids or pair in seen_engine_fixture:
            raise PolyphonicMetricError("duplicate_metric_observation")
        seen_ids.add(observation_id)
        seen_engine_fixture.add(pair)

    items.sort(key=lambda item: (CURRENT_ENGINES.index(item["engine"]["name"]), item["fixtureId"]))
    engine_reports: list[dict[str, Any]] = []
    for engine_name in CURRENT_ENGINES:
        group = [item for item in items if item["engine"]["name"] == engine_name]
        if not group:
            continue
        parse_success = sum(1 for item in group if item["parse"]["success"])
        structural_available = [item for item in group if item["structuralValidity"]["available"]]
        structural_valid = sum(1 for item in structural_available if item["structuralValidity"]["valid"])
        reference_kinds = {
            kind: sum(1 for item in group if item["reference"]["kind"] == kind)
            for kind in REFERENCE_KINDS
        }
        engine_reports.append(
            {
                "engine": engine_name,
                "observationCount": len(group),
                "referenceKinds": reference_kinds,
                "musicXmlParseSuccess": {
                    "success": parse_success,
                    "attempted": len(group),
                    "ratio": _ratio(parse_success, len(group)),
                },
                "structuralValidity": {
                    "valid": structural_valid,
                    "available": len(structural_available),
                    "ratio": _ratio(structural_valid, len(structural_available)),
                },
                "semanticMetrics": {
                    name: _aggregate_metric(group, ("semanticMetrics", name))
                    for name in SEMANTIC_METRICS
                },
                "measureConsistency": {
                    "method": MEASURE_CONSISTENCY_METHOD,
                    **_aggregate_metric(group, ("measureConsistency",)),
                },
                "relationCorrectness": {
                    "method": RELATION_METHOD,
                    **_aggregate_metric(group, ("relationCorrectness",)),
                },
                "structuralDistance": _aggregate_distance(group),
                "teacherEdits": _aggregate_teacher_edits(group),
            }
        )

    payload: dict[str, Any] = {
        "schemaVersion": REPORT_SCHEMA_VERSION,
        "status": "NO_OBSERVATIONS" if not items else "RESEARCH_METRICS_AVAILABLE",
        "observationCount": len(items),
        "engineReports": engine_reports,
        "metricPolicy": {
            "singleAggregateAccuracyScore": None,
            "engineRanking": False,
            "winnerSelection": False,
            "tednClaimed": False,
            "structuralDistanceMethod": STRUCTURAL_DISTANCE_METHOD,
            "teacherEditEvidenceMayBeUnavailable": True,
        },
        "boundaries": dict(_BOUNDARIES),
    }
    payload["reportSha256"] = sha256(_canonical_json(payload)).hexdigest()
    return payload
