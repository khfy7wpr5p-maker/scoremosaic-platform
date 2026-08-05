"""Versioned, deterministic Ensemble comparison-report contract."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re
from typing import Any, Mapping

from .comparator import COMPARISON_FORMAT_VERSION, ComparisonResult

REPORT_SCHEMA_VERSION = "1.0"
REPORT_TYPE = "scoremosaic.ensemble.comparison-report"

_SAFE_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_REPORT_ID = re.compile(r"^ensemble_report_[0-9a-f]{24}$")

_NEUTRALITY = {
    "readOnly": True,
    "provenancePreserved": True,
    "accuracyClaim": False,
    "engineRanking": False,
    "winnerSelection": False,
    "preferredCandidate": False,
    "automaticMerge": False,
    "automaticCorrection": False,
}

_EXPECTED_COMPARISON_BOUNDARIES = {
    "readOnly": True,
    "engineRanking": False,
    "winnerSelection": False,
    "automaticMerge": False,
    "automaticCorrection": False,
    "teacherApproval": False,
    "publication": False,
}

_TOP_LEVEL_KEYS = frozenset(
    {
        "schemaVersion",
        "reportType",
        "reportId",
        "comparisonFormatVersion",
        "comparisonResultSha256",
        "neutrality",
        "comparison",
        "reportSha256",
    }
)


class ComparisonReportError(ValueError):
    """Raised when a comparison report violates the versioned contract."""


def _canonical_json(payload: Any) -> bytes:
    try:
        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ComparisonReportError("report payload must contain JSON values only") from exc


def _report_id(comparison_result_sha256: str) -> str:
    identity = {
        "schemaVersion": REPORT_SCHEMA_VERSION,
        "reportType": REPORT_TYPE,
        "comparisonResultSha256": comparison_result_sha256,
    }
    digest = sha256(_canonical_json(identity)).hexdigest()
    return f"ensemble_report_{digest[:24]}"


def _normalized_json_object(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise ComparisonReportError("report payload must be a mapping")
    encoded = _canonical_json(payload)
    decoded = json.loads(encoded)
    if not isinstance(decoded, dict):
        raise ComparisonReportError("report payload must be a JSON object")
    return decoded


def validate_comparison_report_payload(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate hashes, versions, counts, and disabled decision boundaries."""

    normalized = _normalized_json_object(payload)
    if frozenset(normalized) != _TOP_LEVEL_KEYS:
        raise ComparisonReportError("report top-level fields are invalid")

    if normalized["schemaVersion"] != REPORT_SCHEMA_VERSION:
        raise ComparisonReportError("unsupported report schema version")
    if normalized["reportType"] != REPORT_TYPE:
        raise ComparisonReportError("unsupported report type")
    if normalized["comparisonFormatVersion"] != COMPARISON_FORMAT_VERSION:
        raise ComparisonReportError("comparison format version mismatch")

    comparison_sha = normalized["comparisonResultSha256"]
    report_sha = normalized["reportSha256"]
    report_id = normalized["reportId"]
    if not isinstance(comparison_sha, str) or not _SAFE_SHA256.fullmatch(comparison_sha):
        raise ComparisonReportError("comparisonResultSha256 is invalid")
    if not isinstance(report_sha, str) or not _SAFE_SHA256.fullmatch(report_sha):
        raise ComparisonReportError("reportSha256 is invalid")
    if not isinstance(report_id, str) or not _SAFE_REPORT_ID.fullmatch(report_id):
        raise ComparisonReportError("reportId is invalid")
    if report_id != _report_id(comparison_sha):
        raise ComparisonReportError("reportId does not match the comparison result")

    if normalized["neutrality"] != _NEUTRALITY:
        raise ComparisonReportError("neutrality boundaries are invalid")

    comparison = normalized["comparison"]
    if not isinstance(comparison, dict):
        raise ComparisonReportError("comparison must be an object")
    if comparison.get("formatVersion") != normalized["comparisonFormatVersion"]:
        raise ComparisonReportError("nested comparison format version mismatch")
    if comparison.get("resultSha256") != comparison_sha:
        raise ComparisonReportError("nested comparison hash mismatch")
    if comparison.get("boundaries") != _EXPECTED_COMPARISON_BOUNDARIES:
        raise ComparisonReportError("comparison decision boundaries are invalid")

    candidates = comparison.get("candidates")
    differences = comparison.get("differences")
    if not isinstance(candidates, list) or not isinstance(differences, list):
        raise ComparisonReportError("comparison candidates and differences must be arrays")
    if comparison.get("candidateCount") != len(candidates):
        raise ComparisonReportError("candidateCount does not match candidates")
    if comparison.get("differenceCount") != len(differences):
        raise ComparisonReportError("differenceCount does not match differences")
    if comparison.get("identical") is not (len(differences) == 0):
        raise ComparisonReportError("identical does not match differences")

    comparison_without_hash = dict(comparison)
    nested_reported_sha = comparison_without_hash.pop("resultSha256", None)
    nested_computed_sha = sha256(_canonical_json(comparison_without_hash)).hexdigest()
    if nested_reported_sha != nested_computed_sha:
        raise ComparisonReportError("comparison result hash verification failed")

    report_without_hash = dict(normalized)
    reported_report_sha = report_without_hash.pop("reportSha256", None)
    computed_report_sha = sha256(_canonical_json(report_without_hash)).hexdigest()
    if reported_report_sha != computed_report_sha:
        raise ComparisonReportError("report hash verification failed")

    return normalized


@dataclass(frozen=True, slots=True)
class EnsembleComparisonReport:
    """Immutable wrapper around one neutral ComparisonResult."""

    comparison: ComparisonResult

    def _payload_without_hash(self) -> dict[str, Any]:
        comparison_payload = self.comparison.as_dict()
        comparison_sha = self.comparison.result_sha256
        return {
            "schemaVersion": REPORT_SCHEMA_VERSION,
            "reportType": REPORT_TYPE,
            "reportId": _report_id(comparison_sha),
            "comparisonFormatVersion": COMPARISON_FORMAT_VERSION,
            "comparisonResultSha256": comparison_sha,
            "neutrality": dict(_NEUTRALITY),
            "comparison": comparison_payload,
        }

    @property
    def report_sha256(self) -> str:
        return sha256(_canonical_json(self._payload_without_hash())).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        payload = self._payload_without_hash()
        payload["reportSha256"] = self.report_sha256
        return validate_comparison_report_payload(payload)

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(
            self.as_dict(),
            ensure_ascii=False,
            sort_keys=True,
            indent=indent,
            separators=None if indent is not None else (",", ":"),
            allow_nan=False,
        )


def build_comparison_report(result: ComparisonResult) -> EnsembleComparisonReport:
    if not isinstance(result, ComparisonResult):
        raise ComparisonReportError("result must be a ComparisonResult")
    return EnsembleComparisonReport(comparison=result)
