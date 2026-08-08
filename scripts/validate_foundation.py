#!/usr/bin/env python3
"""Validate ScoreMosaic foundation files without third-party Python packages."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Iterable

from validate_candidate_safety_convergence import main as validate_candidate_safety_convergence

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS_DIR = ROOT / "contracts"
DEVCONTAINER_PATH = ROOT / ".devcontainer" / "devcontainer.json"
EXPECTED_DRAFT = "https://json-schema.org/draft/2020-12/schema"


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing file: {path.relative_to(ROOT)}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"invalid JSON in {path.relative_to(ROOT)} at line {exc.lineno}, "
            f"column {exc.colno}: {exc.msg}"
        ) from exc


def walk(value: Any) -> Iterable[Any]:
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def validate_schema(path: Path, schema: Any) -> list[str]:
    errors: list[str] = []
    label = str(path.relative_to(ROOT))

    if not isinstance(schema, dict):
        return [f"{label}: root must be a JSON object"]

    if schema.get("$schema") != EXPECTED_DRAFT:
        errors.append(f"{label}: $schema must be {EXPECTED_DRAFT}")
    if not isinstance(schema.get("$id"), str) or not schema["$id"]:
        errors.append(f"{label}: non-empty $id is required")
    if schema.get("type") != "object":
        errors.append(f"{label}: root type must be object")

    definitions = schema.get("$defs")
    if not isinstance(definitions, dict) or not definitions:
        errors.append(f"{label}: non-empty $defs object is required")
        definitions = {}

    for node in walk(schema):
        if not isinstance(node, dict):
            continue

        required = node.get("required")
        if required is not None:
            if not isinstance(required, list) or not all(
                isinstance(item, str) for item in required
            ):
                errors.append(f"{label}: every required value must be a string list")
            else:
                if len(required) != len(set(required)):
                    errors.append(f"{label}: required contains duplicate names")
                properties = node.get("properties")
                if not isinstance(properties, dict):
                    errors.append(f"{label}: required is present without properties")
                else:
                    missing = sorted(set(required) - set(properties))
                    if missing:
                        errors.append(
                            f"{label}: required names missing from properties: "
                            + ", ".join(missing)
                        )

        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            definition_name = ref.removeprefix("#/$defs/")
            if "/" in definition_name or definition_name not in definitions:
                errors.append(f"{label}: unresolved local reference {ref}")

    return errors


def validate_devcontainer(config: Any) -> list[str]:
    errors: list[str] = []
    label = str(DEVCONTAINER_PATH.relative_to(ROOT))

    if not isinstance(config, dict):
        return [f"{label}: root must be a JSON object"]

    image = config.get("image")
    if not isinstance(image, str) or not image.startswith(
        "mcr.microsoft.com/devcontainers/python:"
    ):
        errors.append(f"{label}: approved Python devcontainer image is required")

    features = config.get("features")
    if not isinstance(features, dict):
        errors.append(f"{label}: features must be an object")
    elif "ghcr.io/devcontainers/features/git-lfs:1" not in features:
        errors.append(f"{label}: Git LFS feature is required")

    if config.get("remoteUser") != "vscode":
        errors.append(f"{label}: remoteUser must be vscode")

    return errors


def main() -> int:
    errors: list[str] = []
    schema_ids: dict[str, Path] = {}

    contract_paths = sorted(CONTRACTS_DIR.glob("*.schema.json"))
    if not contract_paths:
        errors.append("contracts: no *.schema.json files found")

    for path in contract_paths:
        try:
            schema = load_json(path)
        except ValueError as exc:
            errors.append(str(exc))
            continue

        errors.extend(validate_schema(path, schema))
        schema_id = schema.get("$id") if isinstance(schema, dict) else None
        if isinstance(schema_id, str):
            previous = schema_ids.get(schema_id)
            if previous is not None:
                errors.append(
                    f"duplicate $id {schema_id}: "
                    f"{previous.relative_to(ROOT)} and {path.relative_to(ROOT)}"
                )
            else:
                schema_ids[schema_id] = path

    try:
        devcontainer = load_json(DEVCONTAINER_PATH)
    except ValueError as exc:
        errors.append(str(exc))
    else:
        errors.extend(validate_devcontainer(devcontainer))

    try:
        validate_candidate_safety_convergence()
    except SystemExit as exc:
        errors.append(f"candidate safety convergence: {exc}")

    if errors:
        print("Foundation validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(f"Validated {len(contract_paths)} JSON Schemas.")
    print("Validated .devcontainer/devcontainer.json.")
    print("Validated Candidate Safety v1 convergence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
