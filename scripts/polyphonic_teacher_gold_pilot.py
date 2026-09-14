#!/usr/bin/env python3
"""Fail-closed validation for non-counting Teacher-Gold pilot manifests."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
PILOT_PATH = ROOT / "evaluation" / "polyphonic-teacher-gold-v1" / "pilots" / "doremi-v1-repertoire-pilot.json"
REGISTRY_PATH = ROOT / "evaluation" / "polyphonic-teacher-gold-v1" / "registry.json"
MAX_JSON_BYTES = 1024 * 1024
_SHA_RE = re.compile(r"[0-9a-f]{64}\Z")
_PILOT_ID_RE = re.compile(r"doremi_v1_[0-9]{2}\Z")
_SCORE_KEY_RE = re.compile(r"[a-z0-9_]{3,120}\Z")


class TeacherGoldPilotError(ValueError):
    """Stable fail-closed pilot validation error."""


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise TeacherGoldPilotError("non_canonical_json") from exc


def _load_bounded(path: Path) -> tuple[dict[str, Any], str]:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise TeacherGoldPilotError("pilot_unreadable") from exc
    if not 1 <= len(data) <= MAX_JSON_BYTES:
        raise TeacherGoldPilotError("pilot_size_invalid")
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TeacherGoldPilotError("pilot_json_invalid") from exc
    if type(payload) is not dict:
        raise TeacherGoldPilotError("pilot_root_invalid")
    return payload, sha256(data).hexdigest()


def _exact(value: object, keys: set[str], category: str) -> Mapping[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise TeacherGoldPilotError(category)
    return value


def _sha(value: object) -> bool:
    return type(value) is str and _SHA_RE.fullmatch(value) is not None


def validate_pilot(path: Path = PILOT_PATH, *, registry_path: Path = REGISTRY_PATH) -> dict[str, Any]:
    pilot, pilot_sha = _load_bounded(path)
    expected_top = {
        "schemaVersion",
        "dataset",
        "datasetVersion",
        "releaseUrl",
        "selectionPolicy",
        "datasetRights",
        "discoveryEvidence",
        "pilotCount",
        "records",
        "boundaries",
    }
    _exact(pilot, expected_top, "pilot_schema_invalid")
    if (
        pilot["schemaVersion"] != "scoremosaic-polyphonic-teacher-gold-pilot-v1"
        or pilot["dataset"] != "DoReMi"
        or pilot["datasetVersion"] != "v1.0"
        or pilot["releaseUrl"] != "https://github.com/steinbergmedia/DoReMi/releases/download/v1.0/DoReMi_v1.zip"
        or pilot["selectionPolicy"] != "NAMED_REPERTOIRE_FIRST_AVAILABLE_IMAGE_V1"
        or pilot["pilotCount"] != 5
        or type(pilot["records"]) is not list
        or len(pilot["records"]) != 5
    ):
        raise TeacherGoldPilotError("pilot_contract_invalid")

    rights = _exact(
        pilot["datasetRights"],
        {"licenseReviewStatus", "evaluationAllowed", "trainingAllowed"},
        "pilot_rights_invalid",
    )
    if rights != {
        "licenseReviewStatus": "REVIEW_REQUIRED",
        "evaluationAllowed": "REVIEW_REQUIRED",
        "trainingAllowed": "REVIEW_REQUIRED",
    }:
        raise TeacherGoldPilotError("pilot_rights_invalid")

    evidence = _exact(
        pilot["discoveryEvidence"],
        {
            "sourceCommitSha",
            "workflowRunId",
            "exactUniquePairCount",
            "repertoirePairCount",
            "temporaryArchiveDeleted",
        },
        "pilot_discovery_evidence_invalid",
    )
    if (
        evidence["sourceCommitSha"] != "5b1ac88bbb527187ac8ac0c3fef7abb5bc0fa3c1"
        or evidence["workflowRunId"] != 34878038346
        or evidence["exactUniquePairCount"] != 43
        or evidence["repertoirePairCount"] != 25
        or evidence["temporaryArchiveDeleted"] is not True
    ):
        raise TeacherGoldPilotError("pilot_discovery_evidence_invalid")

    expected_boundaries = {
        "researchEvaluationOnly": True,
        "teacherVerified": False,
        "automaticFixtureAdmission": False,
        "automaticTrainingAuthorization": False,
        "corpusBlobsCommittedToGitHub": False,
        "corpusBlobsPersistedToDriveByThisPilot": False,
        "productionDecisionAuthority": False,
    }
    if pilot["boundaries"] != expected_boundaries:
        raise TeacherGoldPilotError("pilot_boundaries_invalid")

    pilot_ids: list[str] = []
    score_keys: set[str] = set()
    source_hashes: set[str] = set()
    gold_hashes: set[str] = set()
    for index, raw_record in enumerate(pilot["records"], start=1):
        record = _exact(
            raw_record,
            {
                "pilotId",
                "scoreKey",
                "source",
                "gold",
                "teacherVerificationStatus",
                "evaluationEligibility",
                "countTowardTeacherGoldMinimum",
            },
            "pilot_record_schema_invalid",
        )
        expected_id = f"doremi_v1_{index:02d}"
        if (
            record["pilotId"] != expected_id
            or _PILOT_ID_RE.fullmatch(record["pilotId"]) is None
            or type(record["scoreKey"]) is not str
            or _SCORE_KEY_RE.fullmatch(record["scoreKey"]) is None
            or record["teacherVerificationStatus"] != "DRAFT"
            or record["evaluationEligibility"] != "REVIEW_REQUIRED"
            or record["countTowardTeacherGoldMinimum"] is not False
        ):
            raise TeacherGoldPilotError("pilot_record_invalid")
        if record["pilotId"] in pilot_ids or record["scoreKey"] in score_keys:
            raise TeacherGoldPilotError("pilot_record_duplicate")
        pilot_ids.append(record["pilotId"])
        score_keys.add(record["scoreKey"])

        for kind, expected_media, expected_prefix, expected_suffix in (
            ("source", "image/png", "DoReMi_v1/Images/", ".png"),
            ("gold", "application/vnd.recordare.musicxml+xml", "DoReMi_v1/MusicXML/", ".xml"),
        ):
            artifact = _exact(
                record[kind],
                {"archiveMember", "mediaType", "sha256", "byteSize"},
                "pilot_artifact_schema_invalid",
            )
            if (
                artifact["mediaType"] != expected_media
                or type(artifact["archiveMember"]) is not str
                or not artifact["archiveMember"].startswith(expected_prefix)
                or not artifact["archiveMember"].casefold().endswith(expected_suffix)
                or not _sha(artifact["sha256"])
                or type(artifact["byteSize"]) is not int
                or not 1 <= artifact["byteSize"] <= 20_000_000
            ):
                raise TeacherGoldPilotError("pilot_artifact_invalid")
            target = source_hashes if kind == "source" else gold_hashes
            if artifact["sha256"] in target:
                raise TeacherGoldPilotError("pilot_artifact_hash_duplicate")
            target.add(artifact["sha256"])

    registry, _ = _load_bounded(registry_path)
    if type(registry.get("fixtureRecords")) is not list or registry["fixtureRecords"]:
        raise TeacherGoldPilotError("verified_registry_must_remain_empty_during_pilot")

    report: dict[str, Any] = {
        "reportVersion": "scoremosaic-polyphonic-teacher-gold-pilot-report-v1",
        "pilotSha256": pilot_sha,
        "realHashedPairCount": 5,
        "teacherVerifiedCount": 0,
        "evaluationEligibleCount": 0,
        "countedTowardTeacherGoldMinimum": 0,
        "verifiedRegistryFixtureCount": 0,
        "minimumVerifiedFixtures": 500,
        "readiness": "NOT_READY",
        "temporaryCorpusArchivePersisted": False,
        "productionDecisionAuthority": False,
    }
    report["reportSha256"] = sha256(_canonical_json(report)).hexdigest()
    return report


def main() -> int:
    try:
        report = validate_pilot()
    except TeacherGoldPilotError as exc:
        print(f"Teacher-Gold pilot validation failed: {exc}")
        return 1
    print(_canonical_json(report).decode("ascii"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
