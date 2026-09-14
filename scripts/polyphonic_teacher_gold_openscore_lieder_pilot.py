#!/usr/bin/env python3
"""Validate the non-counting OpenScore Lieder Teacher-Gold pilot."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "evaluation" / "polyphonic-teacher-gold-v1" / "pilots" / "openscore-lieder-v1.json"
MAX_JSON_BYTES = 256 * 1024
SHA_RE = re.compile(r"^[0-9a-f]{64}$")

EXPECTED = {
    "osl_01": {
        "title": "Schubert — Das Rosenband, D.280",
        "sourcePath": "scores/Schubert,_Franz/_/Das_Rosenband,_D.280/lc5946872.mxl",
        "xml": ("a6798bffeae124d256acbd21d998baa215887126676739c2c5d19e7651d64c75", 6678),
        "png": ("b6c7b641891fe718449f46a953b4d74dcdf005749c89cc28956cf46e3993d63e", 90402),
        "structural": {"scorePartCount": 2, "maxStavesPerPart": 2, "noteElementCount": 500, "restElementCount": 16, "hasChordElements": True, "hasTieOrTied": True, "hasSlur": True, "hasTuplet": False, "hasGrace": True, "hasAccidental": True, "voiceValues": ["1", "2", "3", "5", "6"], "timeNumerators": ["2"], "timeDenominators": ["2"], "keyFifths": ["-4"]},
    },
    "osl_02": {
        "title": "Robert Schumann — Dein Angesicht, Op.127 No.2",
        "sourcePath": "scores/Schumann,_Robert/5_Lieder_und_Gesänge,_Op.127/2_Dein_Angesicht/lc6834542.mxl",
        "xml": ("e9610dd969b6e556f42b086e3d122842f19644373aee699fe8c74262a1fcbff4", 7979),
        "png": ("cfe8ed7e0996ab19d727e79d013cf15008ad22c6dcf61b93b71023cbccfbee06", 112466),
        "structural": {"scorePartCount": 2, "maxStavesPerPart": 2, "noteElementCount": 631, "restElementCount": 18, "hasChordElements": True, "hasTieOrTied": True, "hasSlur": True, "hasTuplet": False, "hasGrace": False, "hasAccidental": True, "voiceValues": ["1", "2", "3", "5", "6"], "timeNumerators": ["2"], "timeDenominators": ["4"], "keyFifths": ["-3"]},
    },
    "osl_03": {
        "title": "Brahms — Geistliches Wiegenlied, Op.91 No.2",
        "sourcePath": "scores/Brahms,_Johannes/2_Gesänge,_Op.91/2_Geistliches_Wiegenlied/lc6320420.mxl",
        "xml": ("8ef00c7ac76c56b74c7183417bf8ea04068bb33a251dd5dbfe8e08f47797b250", 26218),
        "png": ("d6030170efd440a5c248385a02d46de89baac3b5214e0cf8bc28efd73f189bfb", 118304),
        "structural": {"scorePartCount": 3, "maxStavesPerPart": 2, "noteElementCount": 2517, "restElementCount": 340, "hasChordElements": True, "hasTieOrTied": True, "hasSlur": True, "hasTuplet": True, "hasGrace": False, "hasAccidental": True, "voiceValues": ["1", "2", "5", "6"], "timeNumerators": ["3", "6"], "timeDenominators": ["4", "8"], "keyFifths": ["-1", "-4"]},
    },
    "osl_04": {
        "title": "Fanny Hensel — Verlust",
        "sourcePath": "scores/Hensel,_Fanny/3_Lieder/2_Verlust/lc6013106.mxl",
        "xml": ("eeb985968e1a8398f92b0aeac65e098692a9c71a62a3f458e2e9eec8d4f90f11", 8897),
        "png": ("9aaf65b083f6a2c4a312331251900fd1aabb95c00b5c9e624c5b36424f808627", 97577),
        "structural": {"scorePartCount": 2, "maxStavesPerPart": 2, "noteElementCount": 720, "restElementCount": 43, "hasChordElements": True, "hasTieOrTied": True, "hasSlur": True, "hasTuplet": False, "hasGrace": False, "hasAccidental": True, "voiceValues": ["1", "2", "5", "6"], "timeNumerators": ["4"], "timeDenominators": ["4"], "keyFifths": ["-1"]},
    },
    "osl_05": {
        "title": "Clara Schumann — Lorelei",
        "sourcePath": "scores/Schumann,_Clara/_/Lorelei/lc4919673.mxl",
        "xml": ("504dd02b4061e16d91750af5808a80abaa0cab04b955cb0b8f4b38cdd539eeac", 18612),
        "png": ("b08adaa8bb7782c87bc978a4ced6620653d39914eb85aa45ec83880eaf7246e0", 71258),
        "structural": {"scorePartCount": 2, "maxStavesPerPart": 2, "noteElementCount": 2627, "restElementCount": 252, "hasChordElements": True, "hasTieOrTied": True, "hasSlur": True, "hasTuplet": True, "hasGrace": True, "hasAccidental": True, "voiceValues": ["1", "2", "4", "5", "6", "7", "8"], "timeNumerators": ["12"], "timeDenominators": ["8"], "keyFifths": ["-2"]},
    },
}

ROOT_KEYS = {"schemaVersion", "dataset", "sourceRepository", "sourceCommitSha", "license", "licenseSha256", "renderer", "reviewImageProcessing", "discoveryEvidence", "pilotCount", "records", "boundaries"}
RECORD_KEYS = {"pilotId", "title", "sourcePath", "symbolicGold", "renderedEvidence", "structuralObservation", "rightsStatus", "teacherVerificationStatus", "evaluationEligibility", "countTowardTeacherGoldMinimum"}
BOUNDARIES = {"researchEvaluationOnly": True, "teacherVerified": False, "automaticFixtureAdmission": False, "automaticTrainingAuthorization": False, "productionDecisionAuthority": False}


class TeacherGoldOpenScoreLiederError(ValueError):
    pass


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("ascii")


def _load(path: Path) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise TeacherGoldOpenScoreLiederError("manifest_unreadable") from exc
    if not 1 <= len(raw) <= MAX_JSON_BYTES:
        raise TeacherGoldOpenScoreLiederError("manifest_size_invalid")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TeacherGoldOpenScoreLiederError("manifest_json_invalid") from exc
    if type(value) is not dict:
        raise TeacherGoldOpenScoreLiederError("manifest_root_invalid")
    return value, sha256(raw).hexdigest()


def _exact(value: object, keys: set[str], error: str) -> Mapping[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise TeacherGoldOpenScoreLiederError(error)
    return value


def validate_manifest(manifest: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    _exact(manifest, ROOT_KEYS, "manifest_schema_invalid")
    if (
        manifest["schemaVersion"] != "scoremosaic-polyphonic-teacher-gold-openscore-lieder-pilot-v1"
        or manifest["dataset"] != "OpenScore Lieder Corpus"
        or manifest["sourceRepository"] != "OpenScore/Lieder"
        or manifest["sourceCommitSha"] != "38c5db510224d9facdc4b08d741fc788cfb58ea8"
        or manifest["license"] != "CC0-1.0"
        or manifest["licenseSha256"] != "a2010f343487d3f7618affe54f789f5487602331c0a8d03f49e9a7c547cf0499"
        or manifest["pilotCount"] != 5
        or manifest["boundaries"] != BOUNDARIES
    ):
        raise TeacherGoldOpenScoreLiederError("manifest_contract_invalid")

    if manifest["renderer"] != {
        "name": "MuseScore",
        "versionOutput": "MuseScore: Music Score Editor; Version 3.6.2; Build 3224f34",
        "releaseTag": "v3.6.2",
        "appImageSha256": "c59a41ee88bc7c565a939b9c73498ac0451bbd86574e95cb6e359302c1465290",
        "imageResolutionDpi": 150,
    }:
        raise TeacherGoldOpenScoreLiederError("renderer_lineage_invalid")
    if manifest["reviewImageProcessing"] != {
        "tool": "ImageMagick",
        "versionOutput": "Version: ImageMagick 6.9.12-98 Q16 x86_64 18038 https://legacy.imagemagick.org",
        "background": "#FFFFFF",
        "alphaRemoved": True,
        "validationMethod": "OPAQUE_NONEMPTY_PAGE_V1",
    }:
        raise TeacherGoldOpenScoreLiederError("image_processing_invalid")
    if manifest["discoveryEvidence"] != {
        "workflowRunId": 34887250970,
        "workflowHeadSha": "b61798e43752233d2de80b8249a2f2b2899c6b2c",
        "artifactId": 10365755626,
        "artifactZipSha256": "220ffffeea22d9f7b1c817ca8043b53ff025b1fd8de8adae8768c3b0ed1fe620",
        "artifactRetentionDays": 14,
        "artifactSizeBytes": 545558,
    }:
        raise TeacherGoldOpenScoreLiederError("discovery_lineage_invalid")

    records = manifest["records"]
    if type(records) is not list or len(records) != 5:
        raise TeacherGoldOpenScoreLiederError("records_invalid")
    ids = [item.get("pilotId") if type(item) is dict else None for item in records]
    if ids != sorted(EXPECTED):
        raise TeacherGoldOpenScoreLiederError("record_order_invalid")

    seen_hashes: set[str] = set()
    validated: list[Mapping[str, Any]] = []
    for raw in records:
        record = _exact(raw, RECORD_KEYS, "record_schema_invalid")
        pilot_id = record["pilotId"]
        expected = EXPECTED.get(pilot_id)
        if expected is None:
            raise TeacherGoldOpenScoreLiederError("record_id_invalid")
        symbolic = _exact(record["symbolicGold"], {"mediaType", "sha256", "byteSize"}, "symbolic_schema_invalid")
        rendered = _exact(record["renderedEvidence"], {"mediaType", "page", "sha256", "byteSize", "background", "alphaChannel"}, "render_schema_invalid")
        if (
            record["title"] != expected["title"]
            or record["sourcePath"] != expected["sourcePath"]
            or symbolic != {"mediaType": "application/vnd.recordare.musicxml", "sha256": expected["xml"][0], "byteSize": expected["xml"][1]}
            or rendered != {"mediaType": "image/png", "page": 1, "sha256": expected["png"][0], "byteSize": expected["png"][1], "background": "#FFFFFF", "alphaChannel": False}
            or record["structuralObservation"] != expected["structural"]
            or record["rightsStatus"] != "CLEAR_CC0"
            or record["teacherVerificationStatus"] != "DRAFT"
            or record["evaluationEligibility"] != "REVIEW_REQUIRED"
            or record["countTowardTeacherGoldMinimum"] is not False
        ):
            raise TeacherGoldOpenScoreLiederError("record_evidence_invalid")
        for digest in (symbolic["sha256"], rendered["sha256"]):
            if SHA_RE.fullmatch(digest) is None or digest in seen_hashes:
                raise TeacherGoldOpenScoreLiederError("record_hash_invalid")
            seen_hashes.add(digest)
        validated.append(record)
    return validated


def build_report(path: Path = MANIFEST) -> dict[str, Any]:
    manifest, manifest_sha = _load(path)
    records = validate_manifest(manifest)
    structural = [r["structuralObservation"] for r in records]
    payload = {
        "reportVersion": "scoremosaic-polyphonic-teacher-gold-openscore-lieder-pilot-report-v1",
        "manifestSha256": manifest_sha,
        "hashedPairCount": len(records),
        "rightsClearPairCount": len(records),
        "opaqueWhiteReviewPairCount": len(records),
        "structuralObservationPairCount": len(records),
        "observedTupletPairCount": sum(1 for item in structural if item["hasTuplet"]),
        "observedGracePairCount": sum(1 for item in structural if item["hasGrace"]),
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
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    args = parser.parse_args(argv)
    try:
        report = build_report(args.manifest)
    except TeacherGoldOpenScoreLiederError as exc:
        print(f"Teacher-Gold OpenScore Lieder pilot validation failed: {exc}", file=sys.stderr)
        return 1
    print(_canonical_json(report).decode("ascii"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
