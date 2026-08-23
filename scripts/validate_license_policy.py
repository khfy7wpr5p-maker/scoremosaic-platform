#!/usr/bin/env python3
"""Validate ScoreMosaic licensing documents and third-party inventory offline."""

from __future__ import annotations

import hashlib
import json
import re
import sys
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = Path("third_party/dependency-licenses.json")
POLYFORM_SHA256 = "ffcca38841adb694b6f380647e15f17c446a4d1656fed51a1e2041d064c94cc8"
CLA_ACCEPTANCE = "CLA: I have read and agree to the ScoreMosaic Contributor License Agreement."
PIN_PATTERN = re.compile(r"^([A-Za-z0-9_.-]+)==([A-Za-z0-9][A-Za-z0-9.+-]*)$")
NORMALIZE_PATTERN = re.compile(r"[-_.]+")
ALLOWED_CLASSIFICATIONS = {
    "permissive",
    "weak-copyleft",
    "strong-copyleft",
    "strong-copyleft-or-commercial",
    "review-required",
}
BLOCKED_CLASSIFICATIONS = {
    "strong-copyleft",
    "strong-copyleft-or-commercial",
    "review-required",
}
DOCKER_PINS = (
    ("services/homr-service/Dockerfile", "homr", re.compile(r"^ARG HOMR_VERSION=([^\s]+)$", re.MULTILINE)),
    ("services/clarity-service/Dockerfile", "torch", re.compile(r'"torch==([^"]+)"')),
    ("services/clarity-service/Dockerfile", "torchvision", re.compile(r'"torchvision==([^"]+)"')),
)
REQUIRED_EXTERNAL_COMPONENTS = {
    "audiveris-5.11.0",
    "homr-onnx-checkpoints-0.7.0",
    "clarity-omr-source",
    "clarity-omr-models",
    "container-os-and-bundled-artifacts",
}


def normalize_name(value: str) -> str:
    return NORMALIZE_PATTERN.sub("-", value).lower()


def _parse_pin(raw: str, location: str, errors: list[str]) -> tuple[str, str] | None:
    match = PIN_PATTERN.fullmatch(raw.strip())
    if match is None:
        errors.append(f"{location}: dependency must use exact name==version pin: {raw!r}")
        return None
    return normalize_name(match.group(1)), match.group(2)


def collect_declared_python_dependencies(root: Path = ROOT) -> tuple[set[tuple[str, str]], list[str]]:
    dependencies: set[tuple[str, str]] = set()
    errors: list[str] = []

    for path in sorted(root.glob("services/*/requirements-runtime.txt")):
        for line_number, source_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            line = source_line.strip()
            if not line or line.startswith("#"):
                continue
            pin = _parse_pin(line, f"{path.relative_to(root)}:{line_number}", errors)
            if pin is not None:
                dependencies.add(pin)

    for path in sorted(root.glob("services/*/pyproject.toml")):
        try:
            project = tomllib.loads(path.read_text(encoding="utf-8")).get("project", {})
        except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
            errors.append(f"{path.relative_to(root)}: invalid TOML: {exc}")
            continue
        declared = project.get("dependencies", [])
        if not isinstance(declared, list):
            errors.append(f"{path.relative_to(root)}: project.dependencies must be a list")
            continue
        for index, raw in enumerate(declared):
            if not isinstance(raw, str):
                errors.append(f"{path.relative_to(root)}: dependency {index} must be a string")
                continue
            pin = _parse_pin(raw, f"{path.relative_to(root)}:project.dependencies[{index}]", errors)
            if pin is not None:
                dependencies.add(pin)

    for relative_path, name, pattern in DOCKER_PINS:
        path = root / relative_path
        if not path.is_file():
            errors.append(f"{relative_path}: required Dockerfile is missing")
            continue
        match = pattern.search(path.read_text(encoding="utf-8"))
        if match is None:
            errors.append(f"{relative_path}: exact {name} pin is missing")
            continue
        dependencies.add((normalize_name(name), match.group(1)))

    return dependencies, errors


def load_inventory(root: Path = ROOT) -> dict[str, Any]:
    return json.loads((root / INVENTORY).read_text(encoding="utf-8"))


def _validate_entry(entry: Any, location: str, errors: list[str]) -> None:
    if not isinstance(entry, dict):
        errors.append(f"{location}: entry must be an object")
        return
    required = {
        "declaredLicense",
        "classification",
        "coveredByScoreMosaicLicense",
        "productionApproved",
        "redistributionApproved",
        "source",
        "reviewNote",
    }
    missing = sorted(required - entry.keys())
    if missing:
        errors.append(f"{location}: missing fields: {', '.join(missing)}")
        return
    classification = entry["classification"]
    if classification not in ALLOWED_CLASSIFICATIONS:
        errors.append(f"{location}: unsupported classification: {classification!r}")
    if entry["coveredByScoreMosaicLicense"] is not False:
        errors.append(f"{location}: third-party material cannot be covered by the ScoreMosaic license")
    for key in ("productionApproved", "redistributionApproved"):
        if not isinstance(entry[key], bool):
            errors.append(f"{location}: {key} must be boolean")
    if classification in BLOCKED_CLASSIFICATIONS:
        if entry["productionApproved"] is not False:
            errors.append(f"{location}: blocked classification cannot be production-approved")
        if entry["redistributionApproved"] is not False:
            errors.append(f"{location}: blocked classification cannot be redistribution-approved")
    for key in ("declaredLicense", "source", "reviewNote"):
        if not isinstance(entry[key], str) or not entry[key].strip():
            errors.append(f"{location}: {key} must be a non-empty string")


def validate_inventory(root: Path, inventory: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if inventory.get("version") != "scoremosaic-third-party-license-inventory-v1":
        errors.append("inventory: unexpected or missing version")

    policy = inventory.get("policy")
    expected_policy = {
        "defaultDecision": "deny",
        "commercialProductionRequiresAllIncludedComponentsApproved": True,
        "redistributionRequiresAllIncludedComponentsApproved": True,
        "unresolvedLicenseMayEnterProduction": False,
        "scoremosaicLicenseRelicensesThirdPartyMaterials": False,
    }
    if policy != expected_policy:
        errors.append("inventory.policy: fail-closed policy changed")

    declared, declaration_errors = collect_declared_python_dependencies(root)
    errors.extend(declaration_errors)

    packages = inventory.get("pythonPackages")
    if not isinstance(packages, list):
        return errors + ["inventory.pythonPackages must be a list"]
    inventoried: set[tuple[str, str]] = set()
    for index, entry in enumerate(packages):
        location = f"inventory.pythonPackages[{index}]"
        _validate_entry(entry, location, errors)
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        version = entry.get("version")
        if not isinstance(name, str) or normalize_name(name) != name:
            errors.append(f"{location}: name must be normalized lowercase package name")
            continue
        if not isinstance(version, str) or not version:
            errors.append(f"{location}: version must be a non-empty string")
            continue
        key = (name, version)
        if key in inventoried:
            errors.append(f"{location}: duplicate package pin {name}=={version}")
        inventoried.add(key)

    missing = sorted(declared - inventoried)
    extra = sorted(inventoried - declared)
    for name, version in missing:
        errors.append(f"inventory: missing declared dependency {name}=={version}")
    for name, version in extra:
        errors.append(f"inventory: package is not declared by a tracked runtime input: {name}=={version}")

    components = inventory.get("externalComponents")
    if not isinstance(components, list):
        return errors + ["inventory.externalComponents must be a list"]
    ids: set[str] = set()
    for index, entry in enumerate(components):
        location = f"inventory.externalComponents[{index}]"
        _validate_entry(entry, location, errors)
        if not isinstance(entry, dict):
            continue
        component_id = entry.get("id")
        for key in ("id", "kind", "versionOrRevision", "notice"):
            if not isinstance(entry.get(key), str) or not entry[key].strip():
                errors.append(f"{location}: {key} must be a non-empty string")
        if isinstance(component_id, str):
            if component_id in ids:
                errors.append(f"{location}: duplicate component id {component_id}")
            ids.add(component_id)
        notice = entry.get("notice")
        if isinstance(notice, str) and not (root / notice).is_file():
            errors.append(f"{location}: notice file does not exist: {notice}")
    if ids != REQUIRED_EXTERNAL_COMPONENTS:
        errors.append(
            "inventory.externalComponents: expected exact component ids; "
            f"missing={sorted(REQUIRED_EXTERNAL_COMPONENTS - ids)}, "
            f"extra={sorted(ids - REQUIRED_EXTERNAL_COMPONENTS)}"
        )
    return errors


def validate_policy_documents(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    required_files = (
        "LICENSE",
        "NOTICE",
        "LICENSE-SCOPE.md",
        "COMMERCIAL-LICENSE.md",
        "TRADEMARKS.md",
        "CONTRIBUTOR-LICENSE-AGREEMENT.md",
        "CONTRIBUTING.md",
        "README.md",
        "docs/licensing-governance.md",
        ".github/pull_request_template.md",
    )
    for relative in required_files:
        if not (root / relative).is_file():
            errors.append(f"policy: missing required file {relative}")

    license_path = root / "LICENSE"
    if license_path.is_file():
        digest = hashlib.sha256(license_path.read_bytes()).hexdigest()
        if digest != POLYFORM_SHA256:
            errors.append("LICENSE: text differs from official PolyForm Noncommercial 1.0.0")

    phrase_requirements = {
        "NOTICE": (
            "Required Notice: Copyright 2026 Önder Özüdoğru.",
            "services/audiveris-service/THIRD_PARTY_NOTICES.md",
            "services/homr-service/THIRD_PARTY_NOTICES.md",
            "services/clarity-service/THIRD_PARTY_NOTICES.md",
        ),
        "LICENSE-SCOPE.md": (
            "PolyForm Noncommercial License 1.0.0",
            "creativecommons.org/licenses/by-nc/4.0/legalcode",
            "Critical production model weights",
            "Copyright licenses govern protected expression, not abstract ideas",
        ),
        "COMMERCIAL-LICENSE.md": (
            "not a commercial license and not a grant",
            "requires a separate written commercial agreement signed",
            "cannot relicense third-party components",
        ),
        "TRADEMARKS.md": ("grant no trademark rights", "No registration status is asserted"),
        "README.md": ("source-available, not OSI open source", "COMMERCIAL-LICENSE.md"),
        "docs/architecture.md": ("docs/licensing-governance.md", "licensing activation locks"),
        "docs/licensing-governance.md": (
            "commercial production dependency clearance\nnot complete",
            "No repository workflow currently declares commercial production approved",
        ),
    }
    for relative, phrases in phrase_requirements.items():
        path = root / relative
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        normalized_text = " ".join(text.split())
        for phrase in phrases:
            if " ".join(phrase.split()) not in normalized_text:
                errors.append(f"{relative}: required policy marker missing: {phrase!r}")

    for relative in (
        "CONTRIBUTOR-LICENSE-AGREEMENT.md",
        "CONTRIBUTING.md",
        ".github/pull_request_template.md",
    ):
        path = root / relative
        if path.is_file() and CLA_ACCEPTANCE not in path.read_text(encoding="utf-8"):
            errors.append(f"{relative}: exact CLA acceptance statement is missing")
    return errors


def validate(root: Path = ROOT, inventory: dict[str, Any] | None = None) -> list[str]:
    errors = validate_policy_documents(root)
    try:
        loaded = load_inventory(root) if inventory is None else inventory
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return errors + [f"{INVENTORY}: unreadable or invalid JSON: {exc}"]
    errors.extend(validate_inventory(root, loaded))
    return errors


def main() -> int:
    errors = validate()
    if errors:
        print("License policy validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    inventory = load_inventory()
    blocked_packages = sum(
        entry["classification"] in BLOCKED_CLASSIFICATIONS
        for entry in inventory["pythonPackages"]
    )
    blocked_components = sum(
        not entry["productionApproved"] for entry in inventory["externalComponents"]
    )
    print(
        "License policy valid: "
        f"{len(inventory['pythonPackages'])} exact Python pins inventoried; "
        f"{blocked_packages} package pins and {blocked_components} external components "
        "remain production-gated."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
