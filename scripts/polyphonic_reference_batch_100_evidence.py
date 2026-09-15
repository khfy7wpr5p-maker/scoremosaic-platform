#!/usr/bin/env python3
"""Validate the non-counting 100-example OpenScore Lieder reference batch evidence."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evaluation" / "polyphonic-teacher-gold-v1" / "evidence" / "reference-batch-100-v1.json"
REGISTRY = ROOT / "evaluation" / "polyphonic-teacher-gold-v1" / "registry.json"
WORKFLOW = ROOT / ".github" / "workflows" / "teacher-gold-reference-batch-100-discovery-ci.yml"
MAX_JSON_BYTES = 128 * 1024
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SHA40_RE = re.compile(r"^[0-9a-f]{40}$")

EXPECTED_SOURCE_COMMIT = "38c5db510224d9facdc4b08d741fc788cfb58ea8"
EXPECTED_LICENSE_SHA = "a2010f343487d3f7618affe54f789f5487602331c0a8d03f49e9a7c547cf0499"
EXPECTED_RENDERER_SHA = "c59a41ee88bc7c565a939b9c73498ac0451bbd86574e95cb6e359302c1465290"
EXPECTED_DISCOVERY_HEAD = "9a6fbac69d7e5ddfe1cfc9148ef1575ec115943c"
EXPECTED_ARTIFACT_SHA = "f7ab7c508f4ec5717394a9230e1f8badf05dfe06fb6d6d1d07b985665e8bb6bf"
EXPECTED_MANIFEST_SHA = "4afd456a763a7eacc0c02bc62202dd507b4d4f15324f7c2b16beeba3fdef0bc8"
EXPECTED_AUDIT_IDS = ["ref_075", "ref_059", "ref_005", "ref_004", "ref_007", "ref_020", "ref_027", "ref_008", "ref_032", "ref_065"]


class ReferenceBatchEvidenceError(ValueError):
    pass


def _load_json(path: Path, *, max_bytes: int = MAX_JSON_BYTES) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ReferenceBatchEvidenceError(f"unreadable:{path.name}") from exc
    if not 1 <= len(raw) <= max_bytes:
        raise ReferenceBatchEvidenceError(f"size_invalid:{path.name}")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReferenceBatchEvidenceError(f"json_invalid:{path.name}") from exc
    if type(value) is not dict:
        raise ReferenceBatchEvidenceError(f"root_invalid:{path.name}")
    return value


def _exact_keys(value: object, keys: set[str], error: str) -> Mapping[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise ReferenceBatchEvidenceError(error)
    return value


def _sha256(value: object, error: str) -> str:
    if type(value) is not str or SHA256_RE.fullmatch(value) is None:
        raise ReferenceBatchEvidenceError(error)
    return value


def validate(evidence_path: Path = EVIDENCE, registry_path: Path = REGISTRY, workflow_path: Path = WORKFLOW) -> dict[str, Any]:
    evidence = _load_json(evidence_path)
    root_keys = {
        "schemaVersion", "batchId", "dataset", "sourceRepository", "sourceCommitSha", "license", "licenseSha256",
        "renderer", "selectionPolicy", "discoveryEvidence", "auditPolicy", "coverageSummary", "technicalRenderSanity",
        "teacherGoldState", "boundaries",
    }
    _exact_keys(evidence, root_keys, "evidence_schema_invalid")

    if (
        evidence["schemaVersion"] != "scoremosaic-polyphonic-reference-batch-evidence-v1"
        or evidence["batchId"] != "openscore-lieder-reference-100-v1"
        or evidence["dataset"] != "OpenScore Lieder Corpus"
        or evidence["sourceRepository"] != "OpenScore/Lieder"
        or evidence["sourceCommitSha"] != EXPECTED_SOURCE_COMMIT
        or SHA40_RE.fullmatch(evidence["sourceCommitSha"]) is None
        or evidence["license"] != "CC0-1.0"
        or _sha256(evidence["licenseSha256"], "license_sha_invalid") != EXPECTED_LICENSE_SHA
    ):
        raise ReferenceBatchEvidenceError("source_lineage_invalid")

    renderer = _exact_keys(evidence["renderer"], {"name", "releaseTag", "appImageSha256", "imageResolutionDpi"}, "renderer_schema_invalid")
    if renderer != {
        "name": "MuseScore",
        "releaseTag": "v3.6.2",
        "appImageSha256": EXPECTED_RENDERER_SHA,
        "imageResolutionDpi": 150,
    }:
        raise ReferenceBatchEvidenceError("renderer_lineage_invalid")

    selection = _exact_keys(
        evidence["selectionPolicy"],
        {"sourcePathRanking", "admittedTeacherGoldPathsExcluded", "requestedPairCount", "oversampleCandidateCount", "successfulPairCount"},
        "selection_schema_invalid",
    )
    if selection != {
        "sourcePathRanking": "SHA256_PATH_ASC_V1",
        "admittedTeacherGoldPathsExcluded": True,
        "requestedPairCount": 100,
        "oversampleCandidateCount": 180,
        "successfulPairCount": 100,
    }:
        raise ReferenceBatchEvidenceError("selection_policy_invalid")

    discovery = _exact_keys(
        evidence["discoveryEvidence"],
        {"workflowRunId", "workflowHeadSha", "artifactId", "artifactName", "artifactZipSha256", "artifactSizeBytes", "artifactExpiresAt", "discoveryManifestSha256", "discoveryManifestBytes"},
        "discovery_schema_invalid",
    )
    if (
        discovery["workflowRunId"] != 34939313877
        or discovery["workflowHeadSha"] != EXPECTED_DISCOVERY_HEAD
        or SHA40_RE.fullmatch(discovery["workflowHeadSha"]) is None
        or discovery["artifactId"] != 10384459686
        or discovery["artifactName"] != "teacher-gold-reference-batch-100-v1"
        or _sha256(discovery["artifactZipSha256"], "artifact_sha_invalid") != EXPECTED_ARTIFACT_SHA
        or discovery["artifactSizeBytes"] != 1138061
        or discovery["artifactExpiresAt"] != "2026-09-29T07:00:51Z"
        or _sha256(discovery["discoveryManifestSha256"], "manifest_sha_invalid") != EXPECTED_MANIFEST_SHA
        or discovery["discoveryManifestBytes"] != 153299
    ):
        raise ReferenceBatchEvidenceError("discovery_lineage_invalid")

    audit = _exact_keys(
        evidence["auditPolicy"],
        {"method", "sampleCount", "sampleRate", "auditReferenceIds", "teacherDecisionRequiredForAnyFutureFixtureAdmission", "teacherReviewStatus"},
        "audit_schema_invalid",
    )
    if (
        audit["method"] != "GREEDY_STRUCTURAL_TOKEN_COVERAGE_V1"
        or audit["sampleCount"] != 10
        or audit["sampleRate"] != 0.10
        or audit["auditReferenceIds"] != EXPECTED_AUDIT_IDS
        or len(set(audit["auditReferenceIds"])) != 10
        or audit["teacherDecisionRequiredForAnyFutureFixtureAdmission"] is not True
        or audit["teacherReviewStatus"] != "PENDING"
    ):
        raise ReferenceBatchEvidenceError("audit_policy_invalid")

    coverage = _exact_keys(
        evidence["coverageSummary"],
        {"scorePartCountDistribution", "maxStavesPerPartDistribution", "featurePairCounts", "directionSystemCoverage", "noteElementCount"},
        "coverage_schema_invalid",
    )
    if sum(coverage["scorePartCountDistribution"].values()) != 100:
        raise ReferenceBatchEvidenceError("score_part_distribution_invalid")
    if sum(coverage["maxStavesPerPartDistribution"].values()) != 100:
        raise ReferenceBatchEvidenceError("staves_distribution_invalid")
    for key, value in coverage["featurePairCounts"].items():
        if key not in {"hasChordElements", "hasTieOrTied", "hasSlur", "hasTuplet", "hasGrace", "hasAccidental"} or type(value) is not int or not 0 <= value <= 100:
            raise ReferenceBatchEvidenceError("feature_coverage_invalid")
    direction = coverage["directionSystemCoverage"]
    if direction != {"only-top": 92, "absent": 8, "also-top": 0, "none": 0, "invalid": 0}:
        raise ReferenceBatchEvidenceError("direction_system_coverage_invalid")
    notes = coverage["noteElementCount"]
    if notes != {"minimum": 132, "median": 819, "maximum": 6149}:
        raise ReferenceBatchEvidenceError("note_summary_invalid")

    sanity = evidence["technicalRenderSanity"]
    if sanity != {
        "sampleCount": 10,
        "status": "PASS_NON_AUTHORITY",
        "scope": "review-sample blank/corrupt/render-sanity inspection only",
        "teacherVerification": False,
    }:
        raise ReferenceBatchEvidenceError("technical_sanity_invalid")

    teacher_gold = evidence["teacherGoldState"]
    if teacher_gold != {
        "verifiedFixtureCountBefore": 10,
        "verifiedFixtureCountAfter": 10,
        "minimumVerifiedFixtures": 500,
        "targetVerifiedFixtures": 1000,
        "readiness": "NOT_READY",
    }:
        raise ReferenceBatchEvidenceError("teacher_gold_state_invalid")

    boundaries = evidence["boundaries"]
    expected_boundaries = {
        "researchEvaluationOnly": True,
        "referenceBatchIsNotTeacherGold": True,
        "automaticTeacherVerification": False,
        "automaticFixtureAdmission": False,
        "automaticTrainingAuthorization": False,
        "automaticMusicXmlRepair": False,
        "automaticCorrectionOrMerge": False,
        "stage7EngineOrQuorumChange": False,
        "productionDecisionAuthority": False,
    }
    if boundaries != expected_boundaries:
        raise ReferenceBatchEvidenceError("authority_boundary_invalid")

    registry = _load_json(registry_path)
    records = registry.get("fixtureRecords")
    if type(records) is not list or len(records) != 10:
        raise ReferenceBatchEvidenceError("teacher_gold_registry_count_changed")
    if registry.get("minimumVerifiedFixtures") != 500 or registry.get("targetVerifiedFixtures") != 1000:
        raise ReferenceBatchEvidenceError("teacher_gold_threshold_changed")
    if registry.get("boundaries", {}).get("productionDecisionAuthority") is not False:
        raise ReferenceBatchEvidenceError("teacher_gold_authority_expanded")

    try:
        workflow = workflow_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ReferenceBatchEvidenceError("workflow_unreadable") from exc
    required_workflow_tokens = [
        EXPECTED_SOURCE_COMMIT,
        EXPECTED_RENDERER_SHA,
        EXPECTED_LICENSE_SHA,
        "SHA256_PATH_ASC_V1",
        "GREEDY_STRUCTURAL_TOKEN_COVERAGE_V1",
        "requestedPairCount': 100",
        "sampleRate': 0.10",
        "automaticFixtureAdmission': False",
        "automaticTrainingAuthorization': False",
        "productionDecisionAuthority': False",
        "retention-days: 14",
    ]
    if any(token not in workflow for token in required_workflow_tokens):
        raise ReferenceBatchEvidenceError("workflow_contract_drift")
    if "schedule:" in workflow or "branches:\n      - main" in workflow:
        raise ReferenceBatchEvidenceError("workflow_unbounded_trigger")

    report = {
        "reportVersion": "scoremosaic-polyphonic-reference-batch-evidence-report-v1",
        "batchId": evidence["batchId"],
        "successfulPairCount": selection["successfulPairCount"],
        "auditSampleCount": audit["sampleCount"],
        "teacherGoldFixtureCount": len(records),
        "teacherGoldReadiness": teacher_gold["readiness"],
        "teacherReviewStatus": audit["teacherReviewStatus"],
        "trainingAuthorized": False,
        "productionDecisionAuthority": False,
    }
    report["reportSha256"] = sha256(json.dumps(report, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, default=EVIDENCE)
    parser.add_argument("--registry", type=Path, default=REGISTRY)
    parser.add_argument("--workflow", type=Path, default=WORKFLOW)
    args = parser.parse_args(argv)
    try:
        report = validate(args.evidence, args.registry, args.workflow)
    except ReferenceBatchEvidenceError as exc:
        print(f"Reference batch evidence validation failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
