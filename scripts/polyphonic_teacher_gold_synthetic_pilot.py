#!/usr/bin/env python3
"""Validate the active non-counting OSSQ synthetic Teacher-Gold review pilot."""

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
SCHEMA_VERSION = "scoremosaic-polyphonic-teacher-gold-synthetic-pilot-v2"
SOURCE_COMMIT = "7a17e45cddc0b7064fc3a179b62caeb57595e993"
RENDERER_SHA = "c59a41ee88bc7c565a939b9c73498ac0451bbd86574e95cb6e359302c1465290"
RENDERER_VERSION = "MuseScore: Music Score Editor; Version 3.6.2; Build 3224f34"
IMAGE_PROCESSING = {
    "tool": "ImageMagick",
    "versionOutput": "Version: ImageMagick 6.9.12-98 Q16 x86_64 18038 https://legacy.imagemagick.org",
    "background": "#FFFFFF",
    "alphaRemoved": True,
    "validationMethod": "OPAQUE_NONEMPTY_PAGE_V1",
}
DISCOVERY_EVIDENCE = {
    "workflowRunId": 34883487564,
    "workflowHeadSha": "97cdded35aa401ae74f7959d21ddfcf1546ab7b9",
    "artifactId": 10363841418,
    "artifactZipSha256": "7815fe6c144e1b85e13c994879ff78aa57c78846be2a8f1f504cb22ea95b6b7d",
    "artifactRetentionDays": 14,
}
SUPERSEDES = {
    "schemaVersion": "scoremosaic-polyphonic-teacher-gold-synthetic-pilot-v1",
    "manifestPath": "evaluation/polyphonic-teacher-gold-v1/pilots/ossq-synthetic-v1.json",
    "artifactId": 10362957231,
    "reason": "TRANSPARENT_REVIEW_RENDER_UNREADABLE_ON_DARK_PREVIEW",
    "reviewUseAuthorized": False,
}
SHA_RE = re.compile(r"^[0-9a-f]{64}$")

EXPECTED = {
    "ossq_13744399": (
        "Arriaga — String Quartet No.1 in D minor",
        "scores/Arriaga,_Juan_Crisóstomo_de/String_Quartet_No.1_in_D_minor/sq13744399.musicxml",
        "e24a5d843693a538896bbbece71130c6a2da66ced35779c4f5295e4893b9fd48", 5742094,
        "858c16667d609d81cce0a9e472688a795c80654c55e8faea003f2b5ae21fcc1e", 118631,
    ),
    "ossq_7313978": (
        "Andrée — String Quartet in A major",
        "scores/Andrée,_Elfrida/String_Quartet_in_A_major/sq7313978.musicxml",
        "a12b23404b4d8d4516e084721298b923a3c1f5621fd84e479b351eee179e7649", 4423395,
        "c5230e2949dc8906d9f4c6b17b4a85cbdd2a1caaae8e20de5b1d272c4714e937", 126771,
    ),
    "ossq_7383977": (
        "Arriaga — String Quartet No.3 in E-flat Major",
        "scores/Arriaga,_Juan_Crisóstomo_de/String_Quartet_No.3_in_E-flat_Major/sq7383977.musicxml",
        "ae821554999bfc0cb70ad4651106f50b9879e227d44daedc97c0e48e8ddf8ea2", 6759894,
        "c210c4fbd0423790f0833bdc26e3e5c0f0498af0c4f46077a61155c1025f01e8", 117048,
    ),
    "ossq_8071278": (
        "Beethoven — String Quartet No.1, Op.18 No.1",
        "scores/Beethoven,_Ludwig_van/String_Quartet_No.1,_Op.18_No.1/sq8071278.musicxml",
        "6350ea0668db7e4773423293df62507987442dc4b313ca0a38e61de92f5a4631", 6632551,
        "d62c2578911b9d9685c841a4a6d1c78dc4a25d9c2075fef619fa9b21e979f76c", 109716,
    ),
    "ossq_8454356": (
        "Boccherini — String Quartet in A major, G.213 (Op.39)",
        "scores/Boccherini,_Luigi/String_Quartet_in_A_major,_G.213_(Op.39)/sq8454356.musicxml",
        "bd04cdd017a1e098e358cf9515253c7d7adf473f06e9087e642e55a820636243", 3447637,
        "f0e748d4adaa67ee5ea26e7cc9b9c111755715b4fff30705959687a529a20235", 136398,
    ),
}

ROOT_KEYS = {
    "schemaVersion", "dataset", "sourceRepository", "sourceCommitSha", "license",
    "renderer", "reviewImageProcessing", "discoveryEvidence", "supersedes",
    "pilotCount", "records", "boundaries",
}
RECORD_KEYS = {
    "pilotId", "title", "sourcePath", "symbolicGold", "renderedEvidence",
    "rightsStatus", "teacherVerificationStatus", "evaluationEligibility",
    "countTowardTeacherGoldMinimum",
}
BOUNDARIES = {
    "researchEvaluationOnly": True,
    "teacherVerified": False,
    "automaticFixtureAdmission": False,
    "automaticTrainingAuthorization": False,
    "productionDecisionAuthority": False,
}


class TeacherGoldSyntheticPilotError(ValueError):
    pass


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")


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

    renderer = _exact_dict(
        manifest["renderer"],
        {"name", "versionOutput", "releaseTag", "appImageSha256", "imageResolutionDpi"},
        "renderer_schema_invalid",
    )
    if renderer != {
        "name": "MuseScore",
        "versionOutput": RENDERER_VERSION,
        "releaseTag": "v3.6.2",
        "appImageSha256": RENDERER_SHA,
        "imageResolutionDpi": 150,
    }:
        raise TeacherGoldSyntheticPilotError("renderer_lineage_invalid")

    processing = _exact_dict(
        manifest["reviewImageProcessing"],
        {"tool", "versionOutput", "background", "alphaRemoved", "validationMethod"},
        "review_image_processing_schema_invalid",
    )
    if processing != IMAGE_PROCESSING:
        raise TeacherGoldSyntheticPilotError("review_image_processing_invalid")

    evidence = _exact_dict(
        manifest["discoveryEvidence"],
        {"workflowRunId", "workflowHeadSha", "artifactId", "artifactZipSha256", "artifactRetentionDays"},
        "discovery_evidence_schema_invalid",
    )
    if evidence != DISCOVERY_EVIDENCE:
        raise TeacherGoldSyntheticPilotError("discovery_lineage_invalid")

    supersedes = _exact_dict(
        manifest["supersedes"],
        {"schemaVersion", "manifestPath", "artifactId", "reason", "reviewUseAuthorized"},
        "supersedes_schema_invalid",
    )
    if supersedes != SUPERSEDES:
        raise TeacherGoldSyntheticPilotError("supersedes_invalid")

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
        symbolic = _exact_dict(
            record["symbolicGold"],
            {"mediaType", "sha256", "byteSize"},
            "symbolic_schema_invalid",
        )
        rendered = _exact_dict(
            record["renderedEvidence"],
            {"mediaType", "page", "sha256", "byteSize", "background", "alphaChannel"},
            "rendered_schema_invalid",
        )
        if (
            record["title"] != title
            or record["sourcePath"] != source_path
            or symbolic != {
                "mediaType": "application/vnd.recordare.musicxml+xml",
                "sha256": xml_sha,
                "byteSize": xml_size,
            }
            or rendered != {
                "mediaType": "image/png",
                "page": 1,
                "sha256": png_sha,
                "byteSize": png_size,
                "background": "#FFFFFF",
                "alphaChannel": False,
            }
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
        "reportVersion": "scoremosaic-polyphonic-teacher-gold-synthetic-pilot-report-v2",
        "manifestSha256": digest,
        "hashedPairCount": len(records),
        "rightsClearPairCount": len(records),
        "opaqueWhiteReviewPairCount": len(records),
        "teacherVerifiedPairCount": 0,
        "countedTowardTeacherGoldMinimum": 0,
        "readiness": "NOT_READY",
        "supersededV1ReviewArtifactAuthorized": False,
        "fixtureAdmissionAuthorized": False,
        "automaticTrainingAuthorization": False,
        "productionDecisionAuthority": False,
    }
    payload["reportSha256"] = sha256(_canonical_json(payload)).hexdigest()
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "evaluation" / "polyphonic-teacher-gold-v1" / "pilots" / "ossq-synthetic-v2.json",
    )
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
