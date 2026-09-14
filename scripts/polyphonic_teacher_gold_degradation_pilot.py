from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "evaluation" / "polyphonic-teacher-gold-v1" / "pilots" / "degradation-v1.json"
REGISTRY = ROOT / "evaluation" / "polyphonic-teacher-gold-v1" / "registry.json"


class TeacherGoldDegradationPilotError(ValueError):
    pass


EXPECTED_SOURCE_COMMIT = "38c5db510224d9facdc4b08d741fc788cfb58ea8"
EXPECTED_LICENSE_SHA = "a2010f343487d3f7618affe54f789f5487602331c0a8d03f49e9a7c547cf0499"
EXPECTED_RENDERER_SHA = "c59a41ee88bc7c565a939b9c73498ac0451bbd86574e95cb6e359302c1465290"
EXPECTED_DISCOVERY = {
    "workflowRunId": 34891983599,
    "workflowHeadSha": "6c0bf942abbbda2db62bd0628b8796e9adf7d270",
    "artifactId": 10367261196,
    "artifactZipSha256": "f2362cb798a368829d08eed621659b3d08400de30276e2438e6d4dbafbbfcd15",
    "artifactSizeBytes": 1382326,
    "artifactRetentionDays": 14,
}
EXPECTED_RECORDS = {
    "deg_01": {
        "symbolic": "a6798bffeae124d256acbd21d998baa215887126676739c2c5d19e7651d64c75",
        "clean": "a53100b07bfce2ec24e7d9453c03718bbaa9644fe995e3cf0fc80327e0fa25af",
        "degraded": "6a1bfd9ea0a8d9543089992735f22994d0eef9677e7cb51610450d37f78f4a7e",
        "condition": "LOW_CONTRAST",
        "transform": "LOW_CONTRAST_BLEND_GRAY_42_PERCENT_V1",
    },
    "deg_02": {
        "symbolic": "e9610dd969b6e556f42b086e3d122842f19644373aee699fe8c74262a1fcbff4",
        "clean": "67ddc8973a703ee25358741dc11d4a5a9580376a5b0d8251c3d52fab14c81a72",
        "degraded": "29e71ca7f63ba05ec9bba4175826b6e7961f891cb42df74971ddf5d4627778d9",
        "condition": "ROTATION",
        "transform": "ROTATE_CLOCKWISE_2_25_DEG_V1",
    },
    "deg_03": {
        "symbolic": "8ef00c7ac76c56b74c7183417bf8ea04068bb33a251dd5dbfe8e08f47797b250",
        "clean": "66649a454b3dfc8bf5c39127cd8d70ea5097dca3f8457c499b874fb571f35a9b",
        "degraded": "e0b9e48476fbbf799bde6847eab016d635e9ac4a2211db8b3c4e626e90fc4ec1",
        "condition": "SKEW",
        "transform": "HORIZONTAL_SHEAR_3_DEG_V1",
    },
    "deg_04": {
        "symbolic": "eeb985968e1a8398f92b0aeac65e098692a9c71a62a3f458e2e9eec8d4f90f11",
        "clean": "b24364900ff675014f31531958d48c8cf6cd4a34c66b2ce12daa5d76e449447e",
        "degraded": "5621b996696cf9636b89fd7328fff7e639544e056618d79b6952e79b406f9df5",
        "condition": "PERSPECTIVE_DISTORTION",
        "transform": "FOUR_CORNER_PERSPECTIVE_V1",
    },
    "deg_05": {
        "symbolic": "504dd02b4061e16d91750af5808a80abaa0cab04b955cb0b8f4b38cdd539eeac",
        "clean": "5a248a1cc8325a6f4a3a6974d56fd7e9c95a8770d696e9c6b32b2928c374cbd5",
        "degraded": "2079af0602a86d63aeda2fe9bde924c7b0c5d51b69d510b1d2410965d4cae2bc",
        "condition": "LOW_QUALITY_SCAN",
        "transform": "DOWNSAMPLE_42_BLUR_065_UPSCALE_V1",
    },
}


def _load(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    if len(data) > 2_000_000:
        raise TeacherGoldDegradationPilotError("manifest_too_large")
    payload = json.loads(data.decode("utf-8"))
    if type(payload) is not dict:
        raise TeacherGoldDegradationPilotError("manifest_invalid")
    return payload


def validate_manifest(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if payload.get("schemaVersion") != "scoremosaic-polyphonic-teacher-gold-degradation-pilot-v1":
        raise TeacherGoldDegradationPilotError("manifest_contract_invalid")
    if payload.get("sourceRepository") != "OpenScore/Lieder":
        raise TeacherGoldDegradationPilotError("manifest_contract_invalid")
    if payload.get("sourceCommitSha") != EXPECTED_SOURCE_COMMIT:
        raise TeacherGoldDegradationPilotError("manifest_contract_invalid")
    if payload.get("license") != "CC0-1.0" or payload.get("licenseSha256") != EXPECTED_LICENSE_SHA:
        raise TeacherGoldDegradationPilotError("manifest_contract_invalid")

    renderer = payload.get("renderer")
    if type(renderer) is not dict:
        raise TeacherGoldDegradationPilotError("renderer_lineage_invalid")
    if renderer.get("name") != "MuseScore" or renderer.get("releaseTag") != "v3.6.2":
        raise TeacherGoldDegradationPilotError("renderer_lineage_invalid")
    if renderer.get("appImageSha256") != EXPECTED_RENDERER_SHA or renderer.get("imageResolutionDpi") != 150:
        raise TeacherGoldDegradationPilotError("renderer_lineage_invalid")
    if renderer.get("canonicalVersion") != "MuseScore: Music Score Editor; Version 3.6.2; Build 3224f34":
        raise TeacherGoldDegradationPilotError("renderer_lineage_invalid")

    tool = payload.get("degradationTool")
    if type(tool) is not dict or tool.get("name") != "ImageMagick" or tool.get("deterministicProfiles") is not True:
        raise TeacherGoldDegradationPilotError("degradation_tool_invalid")
    if not str(tool.get("versionOutput", "")).startswith("Version: ImageMagick 6.9.12-98"):
        raise TeacherGoldDegradationPilotError("degradation_tool_invalid")

    if payload.get("discoveryEvidence") != EXPECTED_DISCOVERY:
        raise TeacherGoldDegradationPilotError("discovery_lineage_invalid")
    if payload.get("pilotCount") != 5:
        raise TeacherGoldDegradationPilotError("manifest_contract_invalid")

    records = payload.get("records")
    if type(records) is not list or len(records) != 5:
        raise TeacherGoldDegradationPilotError("record_evidence_invalid")
    ids = [record.get("pilotId") for record in records if type(record) is dict]
    if ids != sorted(EXPECTED_RECORDS):
        raise TeacherGoldDegradationPilotError("record_order_invalid")

    symbolic_hashes: set[str] = set()
    degraded_hashes: set[str] = set()
    conditions: set[str] = set()
    for record in records:
        if type(record) is not dict:
            raise TeacherGoldDegradationPilotError("record_evidence_invalid")
        pilot_id = record.get("pilotId")
        expected = EXPECTED_RECORDS.get(str(pilot_id))
        if expected is None:
            raise TeacherGoldDegradationPilotError("record_evidence_invalid")
        symbolic = record.get("symbolicGold")
        clean = record.get("cleanRender")
        degraded = record.get("degradedRender")
        if not all(type(item) is dict for item in (symbolic, clean, degraded)):
            raise TeacherGoldDegradationPilotError("record_evidence_invalid")
        if symbolic.get("sha256") != expected["symbolic"]:
            raise TeacherGoldDegradationPilotError("record_evidence_invalid")
        if clean.get("sha256") != expected["clean"]:
            raise TeacherGoldDegradationPilotError("record_evidence_invalid")
        if degraded.get("sha256") != expected["degraded"] or degraded.get("alphaChannel") is not False:
            raise TeacherGoldDegradationPilotError("record_evidence_invalid")
        if record.get("scanCondition") != expected["condition"]:
            raise TeacherGoldDegradationPilotError("record_evidence_invalid")
        if record.get("degradationTransform") != expected["transform"]:
            raise TeacherGoldDegradationPilotError("record_evidence_invalid")
        if record.get("rightsStatus") != "CLEAR_CC0":
            raise TeacherGoldDegradationPilotError("record_evidence_invalid")
        if record.get("teacherVerificationStatus") != "DRAFT":
            raise TeacherGoldDegradationPilotError("record_evidence_invalid")
        if record.get("evaluationEligibility") != "REVIEW_REQUIRED":
            raise TeacherGoldDegradationPilotError("record_evidence_invalid")
        if record.get("countTowardTeacherGoldMinimum") is not False:
            raise TeacherGoldDegradationPilotError("record_evidence_invalid")
        symbolic_hashes.add(str(symbolic.get("sha256")))
        degraded_hashes.add(str(degraded.get("sha256")))
        conditions.add(str(record.get("scanCondition")))

    if len(symbolic_hashes) != 5 or len(degraded_hashes) != 5 or len(conditions) != 5:
        raise TeacherGoldDegradationPilotError("record_evidence_invalid")

    boundaries = payload.get("boundaries")
    expected_boundaries = {
        "researchEvaluationOnly": True,
        "derivedFromAlreadyVerifiedSymbolicPairs": True,
        "teacherVerifiedDegradedImages": False,
        "automaticFixtureAdmission": False,
        "automaticTrainingAuthorization": False,
        "productionDecisionAuthority": False,
    }
    if boundaries != expected_boundaries:
        raise TeacherGoldDegradationPilotError("manifest_contract_invalid")
    return records


def build_report(path: Path = MANIFEST, *, registry_path: Path = REGISTRY) -> dict[str, Any]:
    payload = _load(path)
    records = validate_manifest(payload)
    registry = _load(registry_path)
    registry_records = registry.get("fixtureRecords")
    if type(registry_records) is not list or len(registry_records) < 10:
        raise TeacherGoldDegradationPilotError("verified_registry_invalid")
    report = {
        "reportVersion": "scoremosaic-polyphonic-teacher-gold-degradation-pilot-report-v1",
        "hashedPairCount": len(records),
        "rightsClearPairCount": sum(record["rightsStatus"] == "CLEAR_CC0" for record in records),
        "degradedReviewPairCount": len(records),
        "teacherVerifiedPairCount": 0,
        "countedTowardTeacherGoldMinimum": 0,
        "verifiedRegistryFixtureCount": len(registry_records),
        "scanConditions": sorted(record["scanCondition"] for record in records),
        "minimumVerifiedFixtures": registry.get("minimumVerifiedFixtures"),
        "targetVerifiedFixtures": registry.get("targetVerifiedFixtures"),
        "readiness": "NOT_READY",
        "fixtureAdmissionAuthorized": False,
        "automaticTrainingAuthorization": False,
        "productionDecisionAuthority": False,
    }
    return report


if __name__ == "__main__":
    try:
        print(json.dumps(build_report(), ensure_ascii=True, sort_keys=True, indent=2))
    except (OSError, json.JSONDecodeError, TeacherGoldDegradationPilotError) as exc:
        raise SystemExit(f"Teacher-Gold degradation pilot failed: {exc}")
