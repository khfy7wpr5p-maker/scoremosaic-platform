#!/usr/bin/env python3
"""Validate the non-counting OSSQ synthetic Teacher-Gold pilot."""

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
SCHEMA_VERSION = "scoremosaic-polyphonic-teacher-gold-synthetic-pilot-v1"
SOURCE_COMMIT = "7a17e45cddc0b7064fc3a179b62caeb57595e993"
RENDERER_SHA = "c59a41ee88bc7c565a939b9c73498ac0451bbd86574e95cb6e359302c1465290"
RENDERER_VERSION = "MuseScore: Music Score Editor; Version 3.6.2; Build 3224f34"
ARTIFACT_SHA = "1b7c75ebefbf2af0bf043721ee96c42d58d1e69149f1b0ae4809f2ac839ed36f"
SHA_RE = re.compile(r"^[0-9a-f]{64}$")

EXPECTED = {
    "ossq_7313978": (
        "Andrée — String Quartet in A major",
        "scores/Andrée,_Elfrida/String_Quartet_in_A_major/sq7313978.musicxml",
        "a12b23404b4d8d4516e084721298b923a3c1f5621fd84e479b351eee179e7649", 4423395,
        "5c192dcd3c1460b3f7bdb02a824dcefc1f45344ae1bf6461d28480022e6c0958", 188546,
    ),
    "ossq_13744399": (
        "Arriaga — String Quartet No.1 in D minor",
        "scores/Arriaga,_Juan_Crisóstomo_de/String_Quartet_No.1_in_D_minor/sq13744399.musicxml",
        "e24a5d843693a538896bbbece71130c6a2da66ced35779c4f5295e4893b9fd48", 5742094,
        "aaad0862b69b54909ced34bb6513b69b56b5d03038086d907f3e06c9d39c8b67", 177136,
    ),
    "ossq_7383977": (
        "Arriaga — String Quartet No.3 in E-flat Major",
        "scores/Arriaga,_Juan_Crisóstomo_de/String_Quartet_No.3_in_E-flat_Major/sq7383977.musicxml",
        "ae821554999bfc0cb70ad4651106f50b9879e227d44daedc97c0e48e8ddf8ea2", 6759894,
        "095fe471b012bf7d909f30c348ec48b123219bf64ff48d2049d827103549f6a4", 172542,
    ),
    "ossq_8071278": (
        "Beethoven — String Quartet No.1, Op.18 No.1",
        "scores/Beethoven,_Ludwig_van/String_Quartet_No.1,_Op.18_No.1/sq8071278.musicxml",
        "6350ea0668db7e4773423293df62507987442dc4b313ca0a38e61de92f5a4631", 6632551,
        "b87ea167199099d26f303f69d9590874faa22199fceaca18f07ef72693f1547d", 159664,
    ),
    "ossq_8454356": (
        "Boccherini — String Quartet in A major, G.213 (Op.39)",
        "scores/Boccherini,_Luigi/String_Quartet_in_A_major,_G.213_(Op.39)/sq8454356.musicxml",
        "bd04cdd017a1e098e358cf9515253c7d7adf473f06e9087e642e55a820636243", 3447637,
        "f62f0f98380494336fd89854890c7444b9af29e555a9244879e7fbe2cb6e4499", 201595,
    ),
}

ROOT_KEYS = {"schemaVersion", "dataset", "sourceRepository", "sourceCommitSha", "license", "renderer", "discoveryEvidence", "pilotCount", "records", "boundaries"}
RECORD_KEYS = {"pilotId", "title", "sourcePath", "symbolicGold", "renderedEvidence", "rightsStatus", "teacherVerificationStatus", "evaluationEligibility", "countTowardTeacherGoldMinimum"}
BOUNDARIES = {"researchEvaluationOnly": True, "teacherVerified": False, "automaticFixtureAdmission": False, "automaticTrainingAuthorization": False, "productionDecisionAuthority": False}

class TeacherGoldSyntheticPilotError(ValueError):
    pass


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("ascii")


def _load(path: Path) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise TeacherGoldSyntheticPilotError("manifest_unreadable") from exc
    if not 1 <= len(raw) <= MAX_JSON_BYTES:
        raise TeacherGoldSyntheticPilotError("manifest_size_invalid")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TeacherGoldSyntheticPilotError("manifest_json_invalid") from exc
    if type(value) is not dict:
        raise TeacherGoldSyntheticPilotError("manifest_root_invalid")
    return value, sha256(raw).hexdigest()


def _exact_dict(value: object, keys: set[str], error: str) -> Mapping[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise TeacherGoldSyntheticPilotError(error)
    return value


def validate_manifest(manifest: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    _exact_dict(manifest, ROOT_KEYS, "manifest_schema_invalid")
    if (
        manifest["schemaVersion"] != SCHEMA_VERSION
        or manifest["dataset"] != "OSSQ-OMR"
        or manifest["sourceRepository"] != "MALerLab/ossq-omr"
        or manifest["sourceCommitSha"] != SOURCE_COMMIT
        or manifest["license"] != "CC0-1.0"
        or manifest["pilotCount"] != 5
        or manifest["boundaries"] != BOUNDARIES
    ):
        raise TeacherGoldSyntheticPilotError("manifest_contract_invalid")

    renderer = _exact_dict(manifest["renderer"], {"name", "versionOutput", "releaseTag", "appImageSha256", "imageResolutionDpi"}, "renderer_schema_invalid")
    if renderer != {"name": "MuseScore", "versionOutput": RENDERER_VERSION, "releaseTag": "v3.6.2", "appImageSha256": RENDERER_SHA, "imageResolutionDpi": 150}:
        raise TeacherGoldSyntheticPilotError("renderer_lineage_invalid")

    evidence = _exact_dict(manifest["discoveryEvidence"], {"workflowRunId", "workflowHeadSha", "artifactId", "artifactZipSha256", "artifactRetentionDays"}, "discovery_evidence_schema_invalid")
    if evidence != {"workflowRunId": 34880978800, "workflowHeadSha": "e8dbcba04711e17dabdf7a158685f469d44d8f4e", "artifactId": 10362957231, "artifactZipSha256": ARTIFACT_SHA, "artifactRetentionDays": 14}:
        raise TeacherGoldSyntheticPilotError("discovery_lineage_invalid")

    records = manifest["records"]
    if type(records) is not list or len(records) != 5:
        raise TeacherGoldSyntheticPilotError("records_invalid")
    ids = [item.get("pilotId") if type(item) is dict else None for item in records]
    if ids != sorted(EXPECTED):
        raise TeacherGoldSyntheticPilotError("record_order_invalid")

    all_hashes: set[str] = set()
    validated: list[Mapping[str, Any]] = []
    for raw in records:
        record = _exact_dict(raw, RECORD_KEYS, "record_schema_invalid")
        pilot_id = record["pilotId"]
        if pilot_id not in EXPECTED:
            raise TeacherGoldSyntheticPilotError("record_id_invalid")
        title, source_path, xml_sha, xml_size, png_sha, png_size = EXPECTED[pilot_id]
        symbolic = _exact_dict(record["symbolicGold"], {"mediaType", "sha256", "byteSize"}, "symbolic_schema_invalid")
        rendered = _exact_dict(record["renderedEvidence"], {"mediaType", "page", "sha256", "byteSize"}, "rendered_schema_invalid")
        if (
            record["title"] != title
            or record["sourcePath"] != source_path
            or symbolic != {"mediaType": "application/vnd.recordare.musicxml+xml", "sha256": xml_sha, "byteSize": xml_size}
            or rendered != {"mediaType": "image/png", "page": 1, "sha256": png_sha, "byteSize": png_size}
            or record["rightsStatus"] != "CLEAR_CC0"
            or record["teacherVerificationStatus"] != "DRAFT"
            or record["evaluationEligibility"] != "REVIEW_REQUIRED"
            or record["countTowardTeacherGoldMinimum"] is not False
        ):
            raise TeacherGoldSyntheticPilotError("record_evidence_invalid")
        for digest in (xml_sha, png_sha):
            if SHA_RE.fullmatch(digest) is None or digest in all_hashes:
                raise TeacherGoldSyntheticPilotError("record_hash_invalid")
            all_hashes.add(digest)
        validated.append(record)
    return validated


def build_report(path: Path) -> dict[str, Any]:
    manifest, digest = _load(path)
    records = validate_manifest(manifest)
    payload = {
        "reportVersion": "scoremosaic-polyphonic-teacher-gold-synthetic-pilot-report-v1",
        "manifestSha256": digest,
        "hashedPairCount": len(records),
        "rightsClearPairCount": len(records),
        "teacherVerifiedPairCount": 0,
        "countedTowardTeacherGoldMinimum": 0,
        "readiness": "NOT_READY",
        "fixtureAdmissionAuthorized": False,
        "automaticTrainingAuthorization": False,
        "productionDecisionAuthority": False,
    }
    payload["reportSha256"] = sha256(_canonical_json(payload)).hexdigest()
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=ROOT / "evaluation" / "polyphonic-teacher-gold-v1" / "pilots" / "ossq-synthetic-v1.json")
    args = parser.parse_args(argv)
    try:
        report = build_report(args.manifest)
    except TeacherGoldSyntheticPilotError as exc:
        print(f"Teacher-Gold OSSQ synthetic pilot validation failed: {exc}", file=sys.stderr)
        return 1
    print(_canonical_json(report).decode("ascii"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
