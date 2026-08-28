#!/usr/bin/env python3
"""Deterministic research-only Teacher-Gold benchmark registry harness."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
MAX_JSON_BYTES = 1024 * 1024
REGISTRY_VERSION = "scoremosaic-polyphonic-teacher-gold-registry-v1"
BENCHMARK_ID = "scoremosaic-polyphonic-teacher-gold-v1"
FIXTURE_VERSION = "scoremosaic-polyphonic-benchmark-fixture-v1"
MINIMUM_VERIFIED_FIXTURES = 500
TARGET_VERIFIED_FIXTURES = 1000
_FIXTURE_ID_RE = re.compile(r"poly_fixture_[A-Za-z0-9_-]{8,96}\Z")
_SHA_RE = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,159}\Z")

_REGISTRY_KEYS = {
    "registryVersion",
    "benchmarkId",
    "fixtureSchemaVersion",
    "minimumVerifiedFixtures",
    "targetVerifiedFixtures",
    "fixtureRecords",
    "boundaries",
}
_RECORD_KEYS = {"fixtureId", "metadataRef", "metadataSha256"}
_FIXTURE_REQUIRED_KEYS = {
    "schemaVersion",
    "fixtureId",
    "granularity",
    "location",
    "source",
    "gold",
    "classification",
    "boundaries",
}
_FIXTURE_OPTIONAL_KEYS = {"expectedErrorFocus"}
_LOCATION_KEYS = {"pageIndex", "systemId", "measureId", "staffIds"}
_SOURCE_KEYS = {
    "sourceId",
    "sourceSha256",
    "mediaType",
    "originType",
    "assetAvailability",
    "sourceReference",
    "licenseMetadata",
}
_LICENSE_KEYS = {
    "dataset",
    "version",
    "source",
    "license",
    "redistributionStatus",
    "trainingAllowed",
    "evaluationAllowed",
    "commercialUseImplications",
}
_GOLD_KEYS = {
    "goldId",
    "goldArtifactSha256",
    "goldFormat",
    "verificationStatus",
    "verifiedByRole",
    "separateFromEngineOutputs",
    "teacherCorrectionAutomaticallyTrainingData",
    "trainingAuthorization",
}
_CLASSIFICATION_KEYS = {"notationClasses", "notationFeatures", "scanConditions"}
_FIXTURE_BOUNDARY_KEYS = {
    "researchEvaluationOnly",
    "engineOutputsStoredSeparately",
    "automaticWinnerSelection",
    "automaticMusicXmlMerge",
    "automaticSemanticRepair",
    "teacherAuthority",
    "productionDecisionAuthority",
}
_REGISTRY_BOUNDARIES = {
    "researchEvaluationOnly": True,
    "privateAssetsRemainExternal": True,
    "teacherGoldSeparateFromEngineOutputs": True,
    "teacherCorrectionAutomaticallyTrainingData": False,
    "automaticWinnerSelection": False,
    "automaticMusicXmlMerge": False,
    "automaticSemanticRepair": False,
    "teacherAuthority": True,
    "productionDecisionAuthority": False,
}
_FIXTURE_BOUNDARIES = {
    "researchEvaluationOnly": True,
    "engineOutputsStoredSeparately": True,
    "automaticWinnerSelection": False,
    "automaticMusicXmlMerge": False,
    "automaticSemanticRepair": False,
    "teacherAuthority": True,
    "productionDecisionAuthority": False,
}


class TeacherGoldHarnessError(ValueError):
    """Stable fail-closed benchmark harness error."""


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
        raise TeacherGoldHarnessError("non_canonical_json") from exc


def _load_bounded_json(path: Path) -> tuple[dict[str, Any], str]:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise TeacherGoldHarnessError("metadata_unreadable") from exc
    if not 1 <= len(data) <= MAX_JSON_BYTES:
        raise TeacherGoldHarnessError("metadata_size_invalid")
    digest = sha256(data).hexdigest()
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TeacherGoldHarnessError("metadata_json_invalid") from exc
    if type(value) is not dict:
        raise TeacherGoldHarnessError("metadata_root_invalid")
    return value, digest


def _exact_keys(value: object, expected: set[str], category: str) -> Mapping[str, Any]:
    if type(value) is not dict or set(value) != expected:
        raise TeacherGoldHarnessError(category)
    return value


def _safe_ref(value: object, *, require_fixture_prefix: bool = False) -> bool:
    if type(value) is not str or not 1 <= len(value) <= 500 or "\\" in value:
        return False
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        return False
    return not require_fixture_prefix or (len(path.parts) >= 2 and path.parts[0] == "fixtures")


def _safe_id(value: object) -> bool:
    return type(value) is str and _SAFE_ID_RE.fullmatch(value) is not None


def _sha(value: object) -> bool:
    return type(value) is str and _SHA_RE.fullmatch(value) is not None


def _string(value: object, minimum: int, maximum: int) -> bool:
    return type(value) is str and minimum <= len(value) <= maximum


def _load_fixture_contract(repo_root: Path) -> dict[str, set[str]]:
    schema_path = repo_root / "contracts" / "polyphonic-benchmark-fixture-v1.schema.json"
    schema, _ = _load_bounded_json(schema_path)
    try:
        props = schema["$defs"]["classification"]["properties"]
        return {
            "errorCodes": set(schema["$defs"]["errorCode"]["enum"]),
            "notationClasses": set(props["notationClasses"]["items"]["enum"]),
            "notationFeatures": set(props["notationFeatures"]["items"]["enum"]),
            "scanConditions": set(props["scanConditions"]["items"]["enum"]),
        }
    except (KeyError, TypeError) as exc:
        raise TeacherGoldHarnessError("fixture_schema_contract_invalid") from exc


def _validate_registry(registry: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    _exact_keys(registry, _REGISTRY_KEYS, "registry_schema_invalid")
    if (
        registry["registryVersion"] != REGISTRY_VERSION
        or registry["benchmarkId"] != BENCHMARK_ID
        or registry["fixtureSchemaVersion"] != FIXTURE_VERSION
        or registry["minimumVerifiedFixtures"] != MINIMUM_VERIFIED_FIXTURES
        or registry["targetVerifiedFixtures"] != TARGET_VERIFIED_FIXTURES
        or registry["boundaries"] != _REGISTRY_BOUNDARIES
        or type(registry["fixtureRecords"]) is not list
        or len(registry["fixtureRecords"]) > 10000
    ):
        raise TeacherGoldHarnessError("registry_contract_invalid")

    records: list[Mapping[str, Any]] = []
    fixture_ids: list[str] = []
    refs: set[str] = set()
    for raw_record in registry["fixtureRecords"]:
        record = _exact_keys(raw_record, _RECORD_KEYS, "registry_record_schema_invalid")
        fixture_id = record["fixtureId"]
        metadata_ref = record["metadataRef"]
        if (
            type(fixture_id) is not str
            or _FIXTURE_ID_RE.fullmatch(fixture_id) is None
            or not _safe_ref(metadata_ref, require_fixture_prefix=True)
            or not _sha(record["metadataSha256"])
        ):
            raise TeacherGoldHarnessError("registry_record_invalid")
        if fixture_id in fixture_ids or metadata_ref in refs:
            raise TeacherGoldHarnessError("registry_record_duplicate")
        fixture_ids.append(fixture_id)
        refs.add(metadata_ref)
        records.append(record)

    if fixture_ids != sorted(fixture_ids):
        raise TeacherGoldHarnessError("registry_order_invalid")
    return records


def _validate_string_array(
    value: object, allowed: set[str], *, minimum: int, maximum: int, category: str
) -> list[str]:
    if (
        type(value) is not list
        or not minimum <= len(value) <= maximum
        or any(type(item) is not str for item in value)
        or len(value) != len(set(value))
        or not set(value).issubset(allowed)
    ):
        raise TeacherGoldHarnessError(category)
    return value


def _validate_fixture(
    fixture: Mapping[str, Any], record: Mapping[str, Any], contract: Mapping[str, set[str]]
) -> dict[str, Any]:
    keys = set(fixture)
    if not _FIXTURE_REQUIRED_KEYS.issubset(keys) or not keys.issubset(
        _FIXTURE_REQUIRED_KEYS | _FIXTURE_OPTIONAL_KEYS
    ):
        raise TeacherGoldHarnessError("fixture_schema_invalid")
    if fixture["schemaVersion"] != FIXTURE_VERSION or fixture["fixtureId"] != record["fixtureId"]:
        raise TeacherGoldHarnessError("fixture_identity_invalid")

    granularity = fixture["granularity"]
    if granularity not in {"page", "system", "measure"}:
        raise TeacherGoldHarnessError("fixture_granularity_invalid")

    location = fixture["location"]
    if type(location) is not dict or not set(location).issubset(_LOCATION_KEYS):
        raise TeacherGoldHarnessError("fixture_location_invalid")
    if type(location.get("pageIndex")) is not int or not 0 <= location["pageIndex"] <= 10000:
        raise TeacherGoldHarnessError("fixture_location_invalid")
    if granularity in {"system", "measure"} and not _safe_id(location.get("systemId")):
        raise TeacherGoldHarnessError("fixture_location_invalid")
    if granularity == "measure" and not _safe_id(location.get("measureId")):
        raise TeacherGoldHarnessError("fixture_location_invalid")
    if "systemId" in location and not _safe_id(location["systemId"]):
        raise TeacherGoldHarnessError("fixture_location_invalid")
    if "measureId" in location and not _safe_id(location["measureId"]):
        raise TeacherGoldHarnessError("fixture_location_invalid")
    if "staffIds" in location:
        _validate_string_array(
            location["staffIds"], set(location["staffIds"]), minimum=0, maximum=64, category="fixture_staff_ids_invalid"
        )
        if any(not _safe_id(item) for item in location["staffIds"]):
            raise TeacherGoldHarnessError("fixture_staff_ids_invalid")

    source = _exact_keys(fixture["source"], _SOURCE_KEYS, "fixture_source_schema_invalid")
    if (
        not _safe_id(source["sourceId"])
        or not _sha(source["sourceSha256"])
        or source["mediaType"] not in {"application/pdf", "image/png", "image/jpeg", "image/tiff", "image/webp"}
        or source["originType"] not in {"REPOSITORY_OWNED", "LICENSED_EXTERNAL", "PRIVATE_TEACHER_GOLD", "SYNTHETIC"}
        or source["assetAvailability"] not in {"REPOSITORY_PUBLIC", "PRIVATE_REGISTRY", "EXTERNAL_REFERENCE_ONLY"}
        or not _safe_ref(source["sourceReference"])
    ):
        raise TeacherGoldHarnessError("fixture_source_invalid")

    license_meta = _exact_keys(source["licenseMetadata"], _LICENSE_KEYS, "fixture_license_schema_invalid")
    if (
        not _string(license_meta["dataset"], 1, 200)
        or not _string(license_meta["version"], 1, 100)
        or not _safe_ref(license_meta["source"])
        or not _string(license_meta["license"], 1, 300)
        or license_meta["redistributionStatus"] not in {"ALLOWED", "NOT_ALLOWED", "REVIEW_REQUIRED"}
        or license_meta["trainingAllowed"] not in {"YES", "NO", "REVIEW_REQUIRED"}
        or license_meta["evaluationAllowed"] not in {"YES", "NO", "REVIEW_REQUIRED"}
        or license_meta["commercialUseImplications"] not in {"ALLOWED", "NONCOMMERCIAL_ONLY", "REVIEW_REQUIRED", "UNKNOWN"}
    ):
        raise TeacherGoldHarnessError("fixture_license_invalid")

    gold = _exact_keys(fixture["gold"], _GOLD_KEYS, "fixture_gold_schema_invalid")
    if (
        not _safe_id(gold["goldId"])
        or not _sha(gold["goldArtifactSha256"])
        or gold["goldFormat"] not in {"MUSICXML", "CANONICAL_SCORE", "ANNOTATION_JSON"}
        or gold["verificationStatus"] not in {"DRAFT", "VERIFIED"}
        or gold["verifiedByRole"] not in {"TEACHER", "REVIEW_PANEL"}
        or gold["separateFromEngineOutputs"] is not True
        or gold["teacherCorrectionAutomaticallyTrainingData"] is not False
        or gold["trainingAuthorization"] not in {"NOT_AUTHORIZED", "SEPARATELY_AUTHORIZED"}
    ):
        raise TeacherGoldHarnessError("fixture_gold_invalid")

    classification = _exact_keys(
        fixture["classification"], _CLASSIFICATION_KEYS, "fixture_classification_schema_invalid"
    )
    notation_classes = _validate_string_array(
        classification["notationClasses"],
        contract["notationClasses"],
        minimum=1,
        maximum=len(contract["notationClasses"]),
        category="fixture_notation_classes_invalid",
    )
    notation_features = _validate_string_array(
        classification["notationFeatures"],
        contract["notationFeatures"],
        minimum=0,
        maximum=len(contract["notationFeatures"]),
        category="fixture_notation_features_invalid",
    )
    scan_conditions = _validate_string_array(
        classification["scanConditions"],
        contract["scanConditions"],
        minimum=1,
        maximum=len(contract["scanConditions"]),
        category="fixture_scan_conditions_invalid",
    )

    if fixture["boundaries"] != _FIXTURE_BOUNDARIES:
        raise TeacherGoldHarnessError("fixture_boundaries_invalid")
    if "expectedErrorFocus" in fixture:
        _validate_string_array(
            fixture["expectedErrorFocus"],
            contract["errorCodes"],
            minimum=0,
            maximum=22,
            category="fixture_error_focus_invalid",
        )

    return {
        "verified": gold["verificationStatus"] == "VERIFIED",
        "evaluationAllowed": license_meta["evaluationAllowed"] == "YES",
        "trainingAuthorized": gold["trainingAuthorization"] == "SEPARATELY_AUTHORIZED",
        "notationClasses": notation_classes,
        "notationFeatures": notation_features,
        "scanConditions": scan_conditions,
    }


def determine_readiness(
    eligible_verified_count: int,
    minimum_verified: int,
    target_verified: int,
    missing_coverage_count: int,
) -> str:
    if eligible_verified_count < minimum_verified or missing_coverage_count:
        return "NOT_READY"
    if eligible_verified_count >= target_verified:
        return "TARGET_RESEARCH_BENCHMARK_READY"
    return "MINIMUM_RESEARCH_BENCHMARK_READY"


def _increment(counts: dict[str, int], labels: list[str]) -> None:
    for label in labels:
        counts[label] += 1


def build_report(registry_path: Path, *, repo_root: Path = ROOT) -> dict[str, Any]:
    registry, registry_sha = _load_bounded_json(registry_path)
    records = _validate_registry(registry)
    contract = _load_fixture_contract(repo_root)
    coverage = {
        "notationClasses": {key: 0 for key in sorted(contract["notationClasses"])},
        "notationFeatures": {key: 0 for key in sorted(contract["notationFeatures"])},
        "scanConditions": {key: 0 for key in sorted(contract["scanConditions"])},
    }

    verified_count = 0
    eligible_verified_count = 0
    draft_count = 0
    evaluation_blocked_count = 0
    training_authorized_count = 0

    base = registry_path.parent
    for record in records:
        fixture_path = base / record["metadataRef"]
        fixture, actual_sha = _load_bounded_json(fixture_path)
        if actual_sha != record["metadataSha256"]:
            raise TeacherGoldHarnessError("fixture_metadata_hash_mismatch")
        evidence = _validate_fixture(fixture, record, contract)
        if evidence["verified"]:
            verified_count += 1
        else:
            draft_count += 1
        if not evidence["evaluationAllowed"]:
            evaluation_blocked_count += 1
        if evidence["trainingAuthorized"]:
            training_authorized_count += 1
        if evidence["verified"] and evidence["evaluationAllowed"]:
            eligible_verified_count += 1
            _increment(coverage["notationClasses"], evidence["notationClasses"])
            _increment(coverage["notationFeatures"], evidence["notationFeatures"])
            _increment(coverage["scanConditions"], evidence["scanConditions"])

    missing = {
        dimension: [key for key, count in values.items() if count == 0]
        for dimension, values in coverage.items()
    }
    missing_count = sum(len(values) for values in missing.values())
    readiness = determine_readiness(
        eligible_verified_count,
        MINIMUM_VERIFIED_FIXTURES,
        TARGET_VERIFIED_FIXTURES,
        missing_count,
    )

    payload: dict[str, Any] = {
        "reportVersion": "scoremosaic-polyphonic-teacher-gold-harness-report-v1",
        "benchmarkId": BENCHMARK_ID,
        "registrySha256": registry_sha,
        "fixtureCount": len(records),
        "verifiedFixtureCount": verified_count,
        "eligibleVerifiedFixtureCount": eligible_verified_count,
        "draftFixtureCount": draft_count,
        "evaluationBlockedFixtureCount": evaluation_blocked_count,
        "separatelyTrainingAuthorizedFixtureCount": training_authorized_count,
        "minimumVerifiedFixtures": MINIMUM_VERIFIED_FIXTURES,
        "targetVerifiedFixtures": TARGET_VERIFIED_FIXTURES,
        "coverage": coverage,
        "missingCoverage": missing,
        "readiness": readiness,
        "claims": {
            "generalAccuracyClaim": False,
            "realOmrAccuracyMeasured": False,
            "productionDecisionAuthority": False,
            "automaticWinnerSelection": False,
            "automaticMusicXmlMerge": False,
            "teacherAuthorityPreserved": True,
            "teacherCorrectionsAutomaticallyTrainingData": False,
        },
    }
    payload["reportSha256"] = sha256(_canonical_json(payload)).hexdigest()
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--registry",
        type=Path,
        default=ROOT / "evaluation" / "polyphonic-teacher-gold-v1" / "registry.json",
    )
    args = parser.parse_args(argv)
    try:
        report = build_report(args.registry)
    except TeacherGoldHarnessError as exc:
        print(f"Teacher-Gold harness failed: {exc}", file=sys.stderr)
        return 1
    print(_canonical_json(report).decode("ascii"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
