#!/usr/bin/env python3
"""Validate non-counting Teacher-Gold source candidates."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
MAX_JSON_BYTES = 256 * 1024
SCHEMA_VERSION = "scoremosaic-polyphonic-teacher-gold-source-candidates-v1"
BENCHMARK_ID = "scoremosaic-polyphonic-teacher-gold-v1"
STATUS = "SOURCE_REVIEWED_NOT_TEACHER_GOLD"
_CANDIDATE_ID_RE = re.compile(r"tg_source_[a-z0-9][a-z0-9_-]{5,95}\Z")

_ROOT_KEYS = {"schemaVersion", "benchmarkId", "candidates", "boundaries"}
_CANDIDATE_KEYS = {
    "candidateId",
    "candidateType",
    "datasetName",
    "sourceUrl",
    "provenanceUrl",
    "licenseEvidenceUrl",
    "licenseState",
    "declaredFormats",
    "useCase",
    "imageEvidenceAvailable",
    "symbolicEvidenceAvailable",
    "scannedEvidenceConditional",
    "teacherVerified",
    "contentHashesVerified",
    "countTowardTeacherGoldMinimum",
    "status",
    "notes",
}
_BOUNDARIES = {
    "researchEvaluationOnly": True,
    "candidateCatalogueSeparateFromFixtureRegistry": True,
    "automaticFixtureAdmission": False,
    "automaticTeacherVerification": False,
    "automaticDownload": False,
    "automaticTrainingAuthorization": False,
    "productionDecisionAuthority": False,
}
_ALLOWED_TYPES = {"DATASET", "SCORE"}
_ALLOWED_LICENSE_STATES = {"CLEAR_CC0", "REVIEW_REQUIRED"}
_ALLOWED_USE_CASES = {
    "POLYPHONIC_MIXED_SCAN_AND_SYNTHETIC",
    "CLEAN_DIGITAL_IMAGE_SYMBOLIC_PAIR",
    "POLYPHONIC_VOICE_PIANO_RENDER_SOURCE",
}


class TeacherGoldSourceCandidateError(ValueError):
    """Stable fail-closed candidate-catalogue error."""


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
        raise TeacherGoldSourceCandidateError("non_canonical_json") from exc


def _load_bounded_json(path: Path) -> tuple[dict[str, Any], str]:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise TeacherGoldSourceCandidateError("catalogue_unreadable") from exc
    if not 1 <= len(data) <= MAX_JSON_BYTES:
        raise TeacherGoldSourceCandidateError("catalogue_size_invalid")
    digest = sha256(data).hexdigest()
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TeacherGoldSourceCandidateError("catalogue_json_invalid") from exc
    if type(value) is not dict:
        raise TeacherGoldSourceCandidateError("catalogue_root_invalid")
    return value, digest


def _exact_dict(value: object, keys: set[str], category: str) -> Mapping[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise TeacherGoldSourceCandidateError(category)
    return value


def _https_url(value: object) -> bool:
    return type(value) is str and 12 <= len(value) <= 1000 and value.startswith("https://")


def _string(value: object, minimum: int, maximum: int) -> bool:
    return type(value) is str and minimum <= len(value) <= maximum


def validate_catalogue(catalogue: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    _exact_dict(catalogue, _ROOT_KEYS, "catalogue_schema_invalid")
    if (
        catalogue["schemaVersion"] != SCHEMA_VERSION
        or catalogue["benchmarkId"] != BENCHMARK_ID
        or catalogue["boundaries"] != _BOUNDARIES
        or type(catalogue["candidates"]) is not list
        or len(catalogue["candidates"]) > 200
    ):
        raise TeacherGoldSourceCandidateError("catalogue_contract_invalid")

    candidates: list[Mapping[str, Any]] = []
    ids: list[str] = []
    source_urls: set[str] = set()
    for raw in catalogue["candidates"]:
        candidate = _exact_dict(raw, _CANDIDATE_KEYS, "candidate_schema_invalid")
        candidate_id = candidate["candidateId"]
        formats = candidate["declaredFormats"]
        if (
            type(candidate_id) is not str
            or _CANDIDATE_ID_RE.fullmatch(candidate_id) is None
            or candidate["candidateType"] not in _ALLOWED_TYPES
            or not _string(candidate["datasetName"], 1, 200)
            or not _https_url(candidate["sourceUrl"])
            or not _https_url(candidate["provenanceUrl"])
            or not _https_url(candidate["licenseEvidenceUrl"])
            or candidate["licenseState"] not in _ALLOWED_LICENSE_STATES
            or type(formats) is not list
            or not 1 <= len(formats) <= 16
            or len(formats) != len(set(formats))
            or any(not _string(item, 1, 40) for item in formats)
            or candidate["useCase"] not in _ALLOWED_USE_CASES
            or type(candidate["imageEvidenceAvailable"]) is not bool
            or type(candidate["symbolicEvidenceAvailable"]) is not bool
            or type(candidate["scannedEvidenceConditional"]) is not bool
            or candidate["teacherVerified"] is not False
            or candidate["contentHashesVerified"] is not False
            or candidate["countTowardTeacherGoldMinimum"] is not False
            or candidate["status"] != STATUS
            or not _string(candidate["notes"], 1, 1000)
        ):
            raise TeacherGoldSourceCandidateError("candidate_invalid")
        if not candidate["imageEvidenceAvailable"] and not candidate["symbolicEvidenceAvailable"]:
            raise TeacherGoldSourceCandidateError("candidate_evidence_unavailable")
        if candidate_id in ids or candidate["sourceUrl"] in source_urls:
            raise TeacherGoldSourceCandidateError("candidate_duplicate")
        ids.append(candidate_id)
        source_urls.add(candidate["sourceUrl"])
        candidates.append(candidate)

    if ids != sorted(ids):
        raise TeacherGoldSourceCandidateError("candidate_order_invalid")
    return candidates


def build_report(path: Path) -> dict[str, Any]:
    catalogue, catalogue_sha = _load_bounded_json(path)
    candidates = validate_catalogue(catalogue)
    clear_cc0 = sum(item["licenseState"] == "CLEAR_CC0" for item in candidates)
    review_required = sum(item["licenseState"] == "REVIEW_REQUIRED" for item in candidates)
    payload: dict[str, Any] = {
        "reportVersion": "scoremosaic-polyphonic-teacher-gold-source-candidate-report-v1",
        "benchmarkId": BENCHMARK_ID,
        "catalogueSha256": catalogue_sha,
        "candidateCount": len(candidates),
        "clearCc0CandidateCount": clear_cc0,
        "licenseReviewRequiredCandidateCount": review_required,
        "teacherVerifiedCandidateCount": 0,
        "countedTowardTeacherGoldMinimum": 0,
        "fixtureAdmissionAuthorized": False,
        "automaticDownload": False,
        "automaticTrainingAuthorization": False,
        "productionDecisionAuthority": False,
    }
    payload["reportSha256"] = sha256(_canonical_json(payload)).hexdigest()
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--catalogue",
        type=Path,
        default=ROOT / "evaluation" / "polyphonic-teacher-gold-v1" / "source-candidates.json",
    )
    args = parser.parse_args(argv)
    try:
        report = build_report(args.catalogue)
    except TeacherGoldSourceCandidateError as exc:
        print(f"Teacher-Gold source candidate validation failed: {exc}", file=sys.stderr)
        return 1
    print(_canonical_json(report).decode("ascii"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
