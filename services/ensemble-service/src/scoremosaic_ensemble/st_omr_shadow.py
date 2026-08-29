"""SM-POLY-09 research-only ST-OMR shadow evidence.

This module records ST-OMR teacher-gold evidence beside immutable references to
current-engine benchmark evidence. It never changes Gateway/Stage 7 authority.
"""
from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
import json
import re
from typing import Any, Iterable, Mapping

OBSERVATION_SCHEMA_VERSION = "scoremosaic-st-omr-shadow-observation-v1"
REPORT_SCHEMA_VERSION = "scoremosaic-st-omr-shadow-report-v1"
SHADOW_ENGINE = "st-omr"
CURRENT_BASELINE_ENGINES = ("audiveris", "homr", "clarity")
SEMANTIC_METRICS = ("pitch", "duration", "onset", "voice", "staff", "tie", "tuplet")
CATEGORY_NAMES = ("parse", "structuralValidity", *SEMANTIC_METRICS, "measureConsistency", "relationCorrectness")
MAX_OBSERVATIONS = 10_000
MAX_BASELINE_REPORTS = 3

_SHA_RE = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
_FIXTURE_RE = re.compile(r"poly_fixture_[A-Za-z0-9_-]{8,96}\Z")
_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_OBS_RE = re.compile(r"st_omr_shadow_obs_[0-9a-f]{24}\Z")
_REPORT_RE = re.compile(r"st_omr_shadow_report_[0-9a-f]{24}\Z")
_VERSION_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+:-]{0,127}\Z")

_BOUNDARIES = {
    "researchOnly": True,
    "shadowOnly": True,
    "readOnly": True,
    "productionEligible": False,
    "gatewayIntegration": False,
    "stage7QuorumContribution": False,
    "stage7EvidenceMutation": False,
    "engineRanking": False,
    "winnerSelection": False,
    "automaticMerge": False,
    "automaticCorrection": False,
    "teacherAuthorityOverride": False,
    "productionDecisionAuthority": False,
}


class StOmrShadowError(ValueError):
    def __init__(self, category: str):
        self.category = category
        super().__init__(category)


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("ascii")
    except (TypeError, ValueError, OverflowError, UnicodeEncodeError):
        raise StOmrShadowError("non_canonical_json") from None


def _match(rx: re.Pattern[str], value: object) -> bool:
    return type(value) is str and rx.fullmatch(value) is not None


def _exact(value: object, keys: set[str], error: str) -> Mapping[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise StOmrShadowError(error)
    return value


def _metric(available: bool, correct: int | None, total: int | None) -> dict[str, Any]:
    out = {"available": available, "correct": correct, "total": total}
    _validate_metric(out, "metric_invalid")
    return out


def _validate_metric(value: object, error: str) -> Mapping[str, Any]:
    metric = _exact(value, {"available", "correct", "total"}, error)
    if type(metric["available"]) is not bool:
        raise StOmrShadowError(error)
    if metric["available"]:
        correct, total = metric["correct"], metric["total"]
        if type(correct) is not int or type(total) is not int or correct < 0 or total < 0 or correct > total:
            raise StOmrShadowError(error)
    elif metric["correct"] is not None or metric["total"] is not None:
        raise StOmrShadowError(error)
    return metric


def _fraction(correct: int, total: int) -> dict[str, int] | None:
    if total == 0:
        return None
    value = Fraction(correct, total)
    return {"numerator": value.numerator, "denominator": value.denominator}


def _observation_identity(payload: Mapping[str, Any]) -> dict[str, Any]:
    value = deepcopy(dict(payload))
    value.pop("observationId", None)
    value.pop("observationSha256", None)
    return value


def validate_shadow_observation(payload: Mapping[str, Any]) -> dict[str, Any]:
    keys = {
        "schemaVersion", "observationId", "fixtureId", "reference", "engine", "runBinding",
        "parse", "structuralValidity", "semanticMetrics", "measureConsistency",
        "relationCorrectness", "context", "boundaries", "observationSha256",
    }
    obs = _exact(payload, keys, "shadow_observation_schema_invalid")
    if obs["schemaVersion"] != OBSERVATION_SCHEMA_VERSION or not _match(_OBS_RE, obs["observationId"]) or not _match(_FIXTURE_RE, obs["fixtureId"]):
        raise StOmrShadowError("shadow_observation_schema_invalid")

    ref = _exact(obs["reference"], {"kind", "artifactSha256", "verified"}, "reference_invalid")
    if ref["kind"] != "TEACHER_GOLD" or not _match(_SHA_RE, ref["artifactSha256"]) or ref["verified"] is not True:
        raise StOmrShadowError("reference_invalid")

    engine = _exact(obs["engine"], {"name", "engineVersion", "modelVersion", "modelManifestSha256", "modelArtifactSha256", "trainingCodeRevision", "candidateArtifactSha256", "canonicalSha256"}, "shadow_engine_invalid")
    if engine["name"] != SHADOW_ENGINE or not _match(_VERSION_RE, engine["engineVersion"]) or not _match(_VERSION_RE, engine["modelVersion"]):
        raise StOmrShadowError("shadow_engine_invalid")
    for key in ("modelManifestSha256", "modelArtifactSha256", "candidateArtifactSha256"):
        if not _match(_SHA_RE, engine[key]):
            raise StOmrShadowError("shadow_engine_invalid")
    if not _match(_COMMIT_RE, engine["trainingCodeRevision"]):
        raise StOmrShadowError("shadow_engine_invalid")
    if engine["canonicalSha256"] is not None and not _match(_SHA_RE, engine["canonicalSha256"]):
        raise StOmrShadowError("shadow_engine_invalid")

    binding = _exact(obs["runBinding"], {"sourceDocumentSha256", "preparedPageSetSha256", "jobId", "runId", "bindingMethodVersion"}, "run_binding_invalid")
    if not _match(_SHA_RE, binding["sourceDocumentSha256"]) or not _match(_SHA_RE, binding["preparedPageSetSha256"]):
        raise StOmrShadowError("run_binding_invalid")
    if not _match(_ID_RE, binding["jobId"]) or not _match(_ID_RE, binding["runId"]) or not _match(_VERSION_RE, binding["bindingMethodVersion"]):
        raise StOmrShadowError("run_binding_invalid")

    parse = _exact(obs["parse"], {"attempted", "success"}, "parse_invalid")
    if parse["attempted"] is not True or type(parse["success"]) is not bool:
        raise StOmrShadowError("parse_invalid")
    validity = _exact(obs["structuralValidity"], {"available", "valid"}, "structural_validity_invalid")
    if type(validity["available"]) is not bool or (validity["available"] and type(validity["valid"]) is not bool) or (not validity["available"] and validity["valid"] is not None):
        raise StOmrShadowError("structural_validity_invalid")

    semantic = obs["semanticMetrics"]
    if type(semantic) is not dict or set(semantic) != set(SEMANTIC_METRICS):
        raise StOmrShadowError("semantic_metrics_invalid")
    for name in SEMANTIC_METRICS:
        _validate_metric(semantic[name], f"semantic_metric_{name}_invalid")
    _validate_metric(obs["measureConsistency"], "measure_consistency_invalid")
    _validate_metric(obs["relationCorrectness"], "relation_correctness_invalid")

    context = _exact(obs["context"], {"complexityProfileId", "complexityProfileSha256", "sourceQualityProfileId", "sourceQualityProfileSha256"}, "context_invalid")
    for id_key, sha_key in (("complexityProfileId", "complexityProfileSha256"), ("sourceQualityProfileId", "sourceQualityProfileSha256")):
        identifier, digest = context[id_key], context[sha_key]
        if (identifier is None) != (digest is None):
            raise StOmrShadowError("context_invalid")
        if identifier is not None and (not _match(_ID_RE, identifier) or not _match(_SHA_RE, digest)):
            raise StOmrShadowError("context_invalid")

    if obs["boundaries"] != _BOUNDARIES:
        raise StOmrShadowError("authority_boundary_invalid")

    if not parse["success"]:
        if engine["canonicalSha256"] is not None or validity["available"]:
            raise StOmrShadowError("parse_failure_evidence_invalid")
        if any(semantic[name]["available"] for name in SEMANTIC_METRICS) or obs["measureConsistency"]["available"] or obs["relationCorrectness"]["available"]:
            raise StOmrShadowError("parse_failure_evidence_invalid")

    if not _match(_SHA_RE, obs["observationSha256"]):
        raise StOmrShadowError("shadow_observation_hash_invalid")
    body = deepcopy(dict(obs))
    body.pop("observationSha256")
    if obs["observationSha256"] != sha256(_canonical_json(body)).hexdigest():
        raise StOmrShadowError("shadow_observation_hash_invalid")
    expected_id = "st_omr_shadow_obs_" + sha256(_canonical_json(_observation_identity(obs))).hexdigest()[:24]
    if obs["observationId"] != expected_id:
        raise StOmrShadowError("shadow_observation_id_mismatch")
    return deepcopy(dict(obs))


def build_shadow_observation(
    *, fixture_id: str, reference_artifact_sha256: str, engine_version: str, model_version: str,
    model_manifest_sha256: str, model_artifact_sha256: str, training_code_revision: str,
    candidate_artifact_sha256: str, canonical_sha256: str | None, source_document_sha256: str,
    prepared_page_set_sha256: str, job_id: str, run_id: str, binding_method_version: str,
    parse_success: bool, structural_validity: bool | None,
    semantic_metrics: Mapping[str, tuple[int, int] | None],
    measure_consistency: tuple[int, int] | None, relation_correctness: tuple[int, int] | None,
    complexity_profile_id: str | None = None, complexity_profile_sha256: str | None = None,
    source_quality_profile_id: str | None = None, source_quality_profile_sha256: str | None = None,
) -> dict[str, Any]:
    semantic = {}
    if set(semantic_metrics) != set(SEMANTIC_METRICS):
        raise StOmrShadowError("semantic_metrics_invalid")
    for name in SEMANTIC_METRICS:
        value = semantic_metrics[name]
        semantic[name] = _metric(False, None, None) if value is None else _metric(True, value[0], value[1])

    def convert(value: tuple[int, int] | None) -> dict[str, Any]:
        return _metric(False, None, None) if value is None else _metric(True, value[0], value[1])

    obs = {
        "schemaVersion": OBSERVATION_SCHEMA_VERSION,
        "observationId": "placeholder",
        "fixtureId": fixture_id,
        "reference": {"kind": "TEACHER_GOLD", "artifactSha256": reference_artifact_sha256, "verified": True},
        "engine": {
            "name": SHADOW_ENGINE,
            "engineVersion": engine_version,
            "modelVersion": model_version,
            "modelManifestSha256": model_manifest_sha256,
            "modelArtifactSha256": model_artifact_sha256,
            "trainingCodeRevision": training_code_revision,
            "candidateArtifactSha256": candidate_artifact_sha256,
            "canonicalSha256": canonical_sha256,
        },
        "runBinding": {
            "sourceDocumentSha256": source_document_sha256,
            "preparedPageSetSha256": prepared_page_set_sha256,
            "jobId": job_id,
            "runId": run_id,
            "bindingMethodVersion": binding_method_version,
        },
        "parse": {"attempted": True, "success": parse_success},
        "structuralValidity": {"available": structural_validity is not None, "valid": structural_validity},
        "semanticMetrics": semantic,
        "measureConsistency": convert(measure_consistency),
        "relationCorrectness": convert(relation_correctness),
        "context": {
            "complexityProfileId": complexity_profile_id,
            "complexityProfileSha256": complexity_profile_sha256,
            "sourceQualityProfileId": source_quality_profile_id,
            "sourceQualityProfileSha256": source_quality_profile_sha256,
        },
        "boundaries": deepcopy(_BOUNDARIES),
    }
    identity = _observation_identity(obs)
    obs["observationId"] = "st_omr_shadow_obs_" + sha256(_canonical_json(identity)).hexdigest()[:24]
    obs["observationSha256"] = sha256(_canonical_json(obs)).hexdigest()
    return validate_shadow_observation(obs)


def _summary_metric(items: list[Mapping[str, Any]], accessor) -> dict[str, Any]:
    available = [accessor(item) for item in items if accessor(item)["available"]]
    correct = sum(metric["correct"] for metric in available)
    total = sum(metric["total"] for metric in available)
    return {"availableObservationCount": len(available), "correct": correct, "total": total, "accuracy": _fraction(correct, total)}


def build_shadow_report(
    observations: Iterable[Mapping[str, Any]], *,
    baseline_report_sha256_by_engine: Mapping[str, str], baseline_method_version: str,
) -> dict[str, Any]:
    items = [validate_shadow_observation(item) for item in observations]
    if not items or len(items) > MAX_OBSERVATIONS:
        raise StOmrShadowError("shadow_observation_count_invalid")
    hashes = [item["observationSha256"] for item in items]
    if len(set(hashes)) != len(hashes):
        raise StOmrShadowError("duplicate_shadow_observation")
    identities = {(i["fixtureId"], i["engine"]["engineVersion"], i["engine"]["modelVersion"], i["runBinding"]["runId"]) for i in items}
    if len(identities) != len(items):
        raise StOmrShadowError("duplicate_shadow_run_evidence")
    if set(baseline_report_sha256_by_engine) != set(CURRENT_BASELINE_ENGINES) or not _match(_VERSION_RE, baseline_method_version):
        raise StOmrShadowError("baseline_binding_invalid")
    for digest in baseline_report_sha256_by_engine.values():
        if not _match(_SHA_RE, digest):
            raise StOmrShadowError("baseline_binding_invalid")
    items.sort(key=lambda x: (x["fixtureId"], x["engine"]["engineVersion"], x["engine"]["modelVersion"], x["runBinding"]["runId"]))
    categories = []
    categories.append({"category": "parse", "metric": _summary_metric(items, lambda i: {"available": True, "correct": 1 if i["parse"]["success"] else 0, "total": 1})})
    categories.append({"category": "structuralValidity", "metric": _summary_metric(items, lambda i: {"available": i["structuralValidity"]["available"], "correct": 1 if i["structuralValidity"]["valid"] else 0, "total": 1})})
    for name in SEMANTIC_METRICS:
        categories.append({"category": name, "metric": _summary_metric(items, lambda i, n=name: i["semanticMetrics"][n])})
    categories.append({"category": "measureConsistency", "metric": _summary_metric(items, lambda i: i["measureConsistency"])})
    categories.append({"category": "relationCorrectness", "metric": _summary_metric(items, lambda i: i["relationCorrectness"])})
    observation_set_sha = sha256(_canonical_json(sorted(hashes))).hexdigest()
    report = {
        "schemaVersion": REPORT_SCHEMA_VERSION,
        "reportId": "placeholder",
        "shadowEngine": SHADOW_ENGINE,
        "observationCount": len(items),
        "observationSetSha256": observation_set_sha,
        "teacherGoldReferenceSha256Set": sorted({i["reference"]["artifactSha256"] for i in items}),
        "modelManifestSha256Set": sorted({i["engine"]["modelManifestSha256"] for i in items}),
        "categoryEvidence": categories,
        "currentEngineBaseline": {
            "methodVersion": baseline_method_version,
            "reportSha256ByEngine": {e: baseline_report_sha256_by_engine[e] for e in CURRENT_BASELINE_ENGINES},
            "completeCurrentEngineSet": True,
        },
        "boundaries": deepcopy(_BOUNDARIES),
    }
    identity = deepcopy(report)
    identity.pop("reportId")
    report["reportId"] = "st_omr_shadow_report_" + sha256(_canonical_json(identity)).hexdigest()[:24]
    report["reportSha256"] = sha256(_canonical_json(report)).hexdigest()
    return validate_shadow_report(report)


def validate_shadow_report(payload: Mapping[str, Any]) -> dict[str, Any]:
    keys = {"schemaVersion", "reportId", "shadowEngine", "observationCount", "observationSetSha256", "teacherGoldReferenceSha256Set", "modelManifestSha256Set", "categoryEvidence", "currentEngineBaseline", "boundaries", "reportSha256"}
    report = _exact(payload, keys, "shadow_report_schema_invalid")
    if report["schemaVersion"] != REPORT_SCHEMA_VERSION or report["shadowEngine"] != SHADOW_ENGINE or not _match(_REPORT_RE, report["reportId"]):
        raise StOmrShadowError("shadow_report_schema_invalid")
    if type(report["observationCount"]) is not int or not 1 <= report["observationCount"] <= MAX_OBSERVATIONS or not _match(_SHA_RE, report["observationSetSha256"]):
        raise StOmrShadowError("shadow_report_schema_invalid")
    for name in ("teacherGoldReferenceSha256Set", "modelManifestSha256Set"):
        value = report[name]
        if type(value) is not list or not value or value != sorted(set(value)) or any(not _match(_SHA_RE, x) for x in value):
            raise StOmrShadowError("shadow_report_provenance_invalid")
    categories = report["categoryEvidence"]
    if type(categories) is not list or [x.get("category") for x in categories] != list(CATEGORY_NAMES):
        raise StOmrShadowError("shadow_report_category_invalid")
    for entry in categories:
        if type(entry) is not dict or set(entry) != {"category", "metric"}:
            raise StOmrShadowError("shadow_report_category_invalid")
        metric = _exact(entry["metric"], {"availableObservationCount", "correct", "total", "accuracy"}, "shadow_report_metric_invalid")
        if type(metric["availableObservationCount"]) is not int or not 0 <= metric["availableObservationCount"] <= report["observationCount"] or type(metric["correct"]) is not int or type(metric["total"]) is not int or not 0 <= metric["correct"] <= metric["total"]:
            raise StOmrShadowError("shadow_report_metric_invalid")
        accuracy = metric["accuracy"]
        if metric["total"] == 0:
            if accuracy is not None:
                raise StOmrShadowError("shadow_report_metric_invalid")
        else:
            f = Fraction(metric["correct"], metric["total"])
            if accuracy != {"numerator": f.numerator, "denominator": f.denominator}:
                raise StOmrShadowError("shadow_report_metric_invalid")
    baseline = _exact(report["currentEngineBaseline"], {"methodVersion", "reportSha256ByEngine", "completeCurrentEngineSet"}, "baseline_binding_invalid")
    if not _match(_VERSION_RE, baseline["methodVersion"]) or baseline["completeCurrentEngineSet"] is not True or type(baseline["reportSha256ByEngine"]) is not dict or set(baseline["reportSha256ByEngine"]) != set(CURRENT_BASELINE_ENGINES):
        raise StOmrShadowError("baseline_binding_invalid")
    if any(not _match(_SHA_RE, baseline["reportSha256ByEngine"][e]) for e in CURRENT_BASELINE_ENGINES):
        raise StOmrShadowError("baseline_binding_invalid")
    if report["boundaries"] != _BOUNDARIES:
        raise StOmrShadowError("authority_boundary_invalid")
    if not _match(_SHA_RE, report["reportSha256"]):
        raise StOmrShadowError("shadow_report_hash_invalid")
    body = deepcopy(dict(report))
    body.pop("reportSha256")
    if report["reportSha256"] != sha256(_canonical_json(body)).hexdigest():
        raise StOmrShadowError("shadow_report_hash_invalid")
    ident = deepcopy(dict(report))
    ident.pop("reportId")
    ident.pop("reportSha256")
    expected = "st_omr_shadow_report_" + sha256(_canonical_json(ident)).hexdigest()[:24]
    if report["reportId"] != expected:
        raise StOmrShadowError("shadow_report_id_mismatch")
    return deepcopy(dict(report))


def validate_shadow_report_against_observations(report: Mapping[str, Any], observations: Iterable[Mapping[str, Any]]) -> None:
    validated = validate_shadow_report(report)
    baseline = validated["currentEngineBaseline"]
    rebuilt = build_shadow_report(observations, baseline_report_sha256_by_engine=baseline["reportSha256ByEngine"], baseline_method_version=baseline["methodVersion"])
    if rebuilt != validated:
        raise StOmrShadowError("shadow_report_recompute_mismatch")
