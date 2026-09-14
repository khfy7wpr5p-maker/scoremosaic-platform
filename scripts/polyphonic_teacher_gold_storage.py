#!/usr/bin/env python3
"""Validate the research-only Teacher-Gold external storage manifest."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
MAX_JSON_BYTES = 128 * 1024
MANIFEST_VERSION = "scoremosaic-polyphonic-teacher-gold-storage-manifest-v1"
BENCHMARK_ID = "scoremosaic-polyphonic-teacher-gold-v1"
PROVIDER = "GOOGLE_DRIVE"
ROOT_ENV_NAME = "SCOREMOSAIC_TEACHER_GOLD_DRIVE_ROOT_ID"
_DRIVE_FOLDER_ID_RE = re.compile(r"[A-Za-z0-9_-]{10,200}\Z")

_MANIFEST_KEYS = {
    "schemaVersion",
    "benchmarkId",
    "provider",
    "rootFolderRef",
    "folders",
    "boundaries",
}
_ROOT_REF = {"mode": "ENVIRONMENT_VARIABLE", "name": ROOT_ENV_NAME}
_FOLDERS = {
    "registry": "00_registry",
    "imslp": "01_imslp",
    "openscore": "02_openscore",
    "mutopia": "03_mutopia",
    "kernscores": "04_kernscores",
    "mei": "05_mei",
    "cpdl": "06_cpdl",
    "teacherVerified": "07_teacher_verified",
    "benchmarkOutputs": "08_benchmark_outputs",
}
_BOUNDARIES = {
    "researchEvaluationOnly": True,
    "externalAssetsRemainExternal": True,
    "noDriveFolderIdsInRepository": True,
    "githubIsNotCorpusBlobStore": True,
    "automaticDownload": False,
    "automaticUpload": False,
    "productionDecisionAuthority": False,
}


class TeacherGoldStorageError(ValueError):
    """Stable fail-closed storage manifest error."""


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
        raise TeacherGoldStorageError("non_canonical_json") from exc


def _load_bounded_json(path: Path) -> tuple[dict[str, Any], str]:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise TeacherGoldStorageError("manifest_unreadable") from exc
    if not 1 <= len(data) <= MAX_JSON_BYTES:
        raise TeacherGoldStorageError("manifest_size_invalid")
    digest = sha256(data).hexdigest()
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TeacherGoldStorageError("manifest_json_invalid") from exc
    if type(value) is not dict:
        raise TeacherGoldStorageError("manifest_root_invalid")
    return value, digest


def _exact_dict(value: object, expected_keys: set[str], category: str) -> Mapping[str, Any]:
    if type(value) is not dict or set(value) != expected_keys:
        raise TeacherGoldStorageError(category)
    return value


def _contains_drive_url(value: object) -> bool:
    if type(value) is str:
        lowered = value.lower()
        return "drive.google.com/" in lowered or "docs.google.com/" in lowered
    if type(value) is list:
        return any(_contains_drive_url(item) for item in value)
    if type(value) is dict:
        return any(_contains_drive_url(item) for item in value.values())
    return False


def validate_manifest(manifest: Mapping[str, Any]) -> dict[str, str]:
    _exact_dict(manifest, _MANIFEST_KEYS, "manifest_schema_invalid")
    if (
        manifest["schemaVersion"] != MANIFEST_VERSION
        or manifest["benchmarkId"] != BENCHMARK_ID
        or manifest["provider"] != PROVIDER
    ):
        raise TeacherGoldStorageError("manifest_identity_invalid")

    root_ref = _exact_dict(
        manifest["rootFolderRef"], {"mode", "name"}, "root_reference_schema_invalid"
    )
    if dict(root_ref) != _ROOT_REF:
        raise TeacherGoldStorageError("root_reference_invalid")

    folders = _exact_dict(
        manifest["folders"], set(_FOLDERS), "folder_map_schema_invalid"
    )
    if dict(folders) != _FOLDERS:
        raise TeacherGoldStorageError("folder_map_invalid")

    boundaries = _exact_dict(
        manifest["boundaries"], set(_BOUNDARIES), "storage_boundaries_schema_invalid"
    )
    if dict(boundaries) != _BOUNDARIES:
        raise TeacherGoldStorageError("storage_boundaries_invalid")

    if _contains_drive_url(manifest):
        raise TeacherGoldStorageError("raw_drive_locator_forbidden")

    return dict(folders)


def resolve_root_folder_id(
    manifest: Mapping[str, Any], environ: Mapping[str, str] | None = None
) -> str:
    validate_manifest(manifest)
    env = os.environ if environ is None else environ
    value = env.get(ROOT_ENV_NAME)
    if type(value) is not str or _DRIVE_FOLDER_ID_RE.fullmatch(value) is None:
        raise TeacherGoldStorageError("drive_root_binding_missing_or_invalid")
    return value


def build_report(
    manifest_path: Path, *, require_root_binding: bool = False
) -> dict[str, Any]:
    manifest, manifest_sha = _load_bounded_json(manifest_path)
    folders = validate_manifest(manifest)
    root_configured = False
    if require_root_binding:
        resolve_root_folder_id(manifest)
        root_configured = True

    payload: dict[str, Any] = {
        "reportVersion": "scoremosaic-polyphonic-teacher-gold-storage-report-v1",
        "benchmarkId": BENCHMARK_ID,
        "manifestSha256": manifest_sha,
        "provider": PROVIDER,
        "rootFolderEnvironmentVariable": ROOT_ENV_NAME,
        "rootBindingConfigured": root_configured,
        "folderCount": len(folders),
        "driveFolderIdentifiersPublished": False,
        "githubIsCorpusBlobStore": False,
        "automaticDownload": False,
        "automaticUpload": False,
        "productionDecisionAuthority": False,
    }
    payload["reportSha256"] = sha256(_canonical_json(payload)).hexdigest()
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "evaluation" / "polyphonic-teacher-gold-v1" / "storage-manifest.json",
    )
    parser.add_argument("--require-root-binding", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = build_report(
            args.manifest, require_root_binding=args.require_root_binding
        )
    except TeacherGoldStorageError as exc:
        print(f"Teacher-Gold storage validation failed: {exc}", file=sys.stderr)
        return 1
    print(_canonical_json(report).decode("ascii"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
