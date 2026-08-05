from __future__ import annotations

import re
from pathlib import Path
from typing import Any


class JsonSchemaContractError(ValueError):
    """Closed JSON Schema 2020-12 subset validation error."""


def _fail(path: str, message: str) -> None:
    raise JsonSchemaContractError(f"{path}: {message}")


def validate_json_schema_2020_12_subset(instance: Any, schema: dict[str, Any], *, path: str = "$") -> None:
    """Evaluate the closed keyword subset used by the Phase 22 schema.

    Supported keywords are intentionally limited and fail closed: type, const, enum,
    required, properties, additionalProperties=false, pattern, minLength, maxLength,
    minimum, maximum, minItems, maxItems, and items.
    """
    allowed_keywords = {
        "$schema",
        "$id",
        "title",
        "type",
        "const",
        "enum",
        "required",
        "properties",
        "additionalProperties",
        "pattern",
        "minLength",
        "maxLength",
        "minimum",
        "maximum",
        "minItems",
        "maxItems",
        "items",
    }
    unknown_keywords = set(schema) - allowed_keywords
    if unknown_keywords:
        _fail(path, f"unsupported schema keywords: {sorted(unknown_keywords)}")

    if "const" in schema and instance != schema["const"]:
        _fail(path, "value does not match const")
    if "enum" in schema and instance not in schema["enum"]:
        _fail(path, "value is not in enum")

    expected_type = schema.get("type")
    if expected_type == "object":
        if not isinstance(instance, dict):
            _fail(path, "expected object")
        required = schema.get("required", [])
        if not isinstance(required, list) or any(not isinstance(key, str) for key in required):
            _fail(path, "schema required must be a string array")
        missing = [key for key in required if key not in instance]
        if missing:
            _fail(path, f"missing required properties: {missing}")
        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            _fail(path, "schema properties must be an object")
        if schema.get("additionalProperties") is not False:
            _fail(path, "object schemas must set additionalProperties=false")
        extra = set(instance) - set(properties)
        if extra:
            _fail(path, f"additional properties are forbidden: {sorted(extra)}")
        for key, value in instance.items():
            child_schema = properties.get(key)
            if not isinstance(child_schema, dict):
                _fail(path, f"property {key!r} has no closed child schema")
            validate_json_schema_2020_12_subset(value, child_schema, path=f"{path}.{key}")
        return

    if expected_type == "array":
        if not isinstance(instance, list):
            _fail(path, "expected array")
        minimum = schema.get("minItems")
        maximum = schema.get("maxItems")
        if minimum is not None and len(instance) < minimum:
            _fail(path, "array is shorter than minItems")
        if maximum is not None and len(instance) > maximum:
            _fail(path, "array is longer than maxItems")
        item_schema = schema.get("items")
        if not isinstance(item_schema, dict):
            _fail(path, "array items schema is required")
        for index, value in enumerate(instance):
            validate_json_schema_2020_12_subset(value, item_schema, path=f"{path}[{index}]")
        return

    if expected_type == "string":
        if not isinstance(instance, str):
            _fail(path, "expected string")
        if "minLength" in schema and len(instance) < schema["minLength"]:
            _fail(path, "string is shorter than minLength")
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            _fail(path, "string is longer than maxLength")
        if "pattern" in schema and re.fullmatch(schema["pattern"], instance) is None:
            _fail(path, "string does not match pattern")
        return

    if expected_type == "integer":
        if not isinstance(instance, int) or isinstance(instance, bool):
            _fail(path, "expected integer")
        if "minimum" in schema and instance < schema["minimum"]:
            _fail(path, "integer is below minimum")
        if "maximum" in schema and instance > schema["maximum"]:
            _fail(path, "integer is above maximum")
        return

    if expected_type is not None:
        _fail(path, f"unsupported type keyword: {expected_type!r}")


def load_and_validate_json_schema_2020_12_subset(instance: Any, *, schema_path: Path) -> None:
    import json

    if schema_path.is_symlink() or not schema_path.is_file():
        raise JsonSchemaContractError("schema path must be a real non-symlink file")
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise JsonSchemaContractError("schema is unreadable or invalid JSON") from exc
    if not isinstance(schema, dict):
        raise JsonSchemaContractError("schema root must be an object")
    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        raise JsonSchemaContractError("schema must declare JSON Schema 2020-12")
    validate_json_schema_2020_12_subset(instance, schema)
