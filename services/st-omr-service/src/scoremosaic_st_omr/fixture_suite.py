from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from .offline_fixture_inference import FixtureInferenceError, run_generated_fixture

SUITE_VERSION: Final = "1.0"
SUITE_CORE_VERSION: Final = "generated-fixture-suite-v1"
ALLOWED_FIXTURE_ROOT_NAME: Final = "fixtures"


class FixtureSuiteError(ValueError):
    """Fail-closed error for generated fixture suite execution."""


@dataclass(frozen=True)
class FixtureSuiteResult:
    suite_id: str
    suite_version: str
    fixture_count: int
    fixture_ids: tuple[str, ...]
    suite_sha256: str

    def as_dict(self) -> dict[str, object]:
        return {
            "status": "completed_offline_fixture_suite_only",
            "suiteCoreVersion": SUITE_CORE_VERSION,
            "suiteId": self.suite_id,
            "suiteVersion": self.suite_version,
            "fixtureCount": self.fixture_count,
            "fixtureIds": list(self.fixture_ids),
            "suiteSha256": self.suite_sha256,
            "modelLoaded": False,
            "realOmrInference": False,
            "userInputAccepted": False,
            "networkUsed": False,
        }


def _require_text(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise FixtureSuiteError(f"suite registry field {key!r} must be a non-empty string")
    return value


def _direct_child(root: Path, name: str) -> Path:
    candidate = (root / name).resolve()
    if candidate.parent != root.resolve():
        raise FixtureSuiteError("suite registry entries must be direct children of the fixture root")
    if candidate.is_symlink():
        raise FixtureSuiteError("suite registry symlinks are forbidden")
    return candidate


def _canonical_suite_sha256(results: list[dict[str, object]]) -> str:
    canonical = json.dumps(
        sorted(results, key=lambda item: str(item["fixtureId"])),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def run_generated_fixture_suite(*, registry_path: Path, allowed_root: Path) -> FixtureSuiteResult:
    root = allowed_root.resolve()
    if root.name != ALLOWED_FIXTURE_ROOT_NAME:
        raise FixtureSuiteError("allowed fixture root must be named 'fixtures'")
    if not root.is_dir() or root.is_symlink():
        raise FixtureSuiteError("allowed fixture root must be a real directory")

    resolved_registry = registry_path.resolve()
    if resolved_registry.parent != root or resolved_registry.is_symlink():
        raise FixtureSuiteError("suite registry must be a non-symlink direct child of the fixture root")

    try:
        registry = json.loads(resolved_registry.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FixtureSuiteError("suite registry is unreadable or invalid JSON") from exc
    if not isinstance(registry, dict):
        raise FixtureSuiteError("suite registry root must be an object")

    if _require_text(registry, "suiteVersion") != SUITE_VERSION:
        raise FixtureSuiteError("unsupported suite registry version")
    suite_id = _require_text(registry, "suiteId")
    entries = registry.get("fixtures")
    if not isinstance(entries, list) or not entries:
        raise FixtureSuiteError("suite registry fixtures must be a non-empty array")

    seen_manifest_names: set[str] = set()
    seen_fixture_ids: set[str] = set()
    result_payloads: list[dict[str, object]] = []

    for entry in entries:
        if not isinstance(entry, dict):
            raise FixtureSuiteError("suite registry fixture entries must be objects")
        manifest_name = _require_text(entry, "manifestName")
        if manifest_name in seen_manifest_names:
            raise FixtureSuiteError("duplicate fixture manifest entry")
        seen_manifest_names.add(manifest_name)

        manifest_path = _direct_child(root, manifest_name)
        if not manifest_path.is_file():
            raise FixtureSuiteError("suite fixture manifest is missing")
        try:
            result = run_generated_fixture(manifest_path=manifest_path, allowed_root=root)
        except FixtureInferenceError as exc:
            raise FixtureSuiteError("suite fixture execution failed closed") from exc
        if result.fixture_id in seen_fixture_ids:
            raise FixtureSuiteError("duplicate fixture ID")
        seen_fixture_ids.add(result.fixture_id)
        result_payloads.append(result.as_dict())

    fixture_ids = tuple(sorted(seen_fixture_ids))
    return FixtureSuiteResult(
        suite_id=suite_id,
        suite_version=SUITE_VERSION,
        fixture_count=len(result_payloads),
        fixture_ids=fixture_ids,
        suite_sha256=_canonical_suite_sha256(result_payloads),
    )


def disabled_fixture_suite_evidence() -> dict[str, object]:
    return {
        "status": "offline_fixture_suite_not_requested",
        "suiteCoreVersion": SUITE_CORE_VERSION,
        "fixtureSuiteEnabled": True,
        "realOmrInference": False,
        "userInputAccepted": False,
        "networkUsed": False,
    }
