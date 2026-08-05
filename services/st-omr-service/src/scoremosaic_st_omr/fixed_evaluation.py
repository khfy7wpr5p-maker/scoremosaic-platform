from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from .fixture_suite import FixtureSuiteError, run_generated_fixture_suite
from .offline_fixture_inference import FixtureInferenceError, run_generated_fixture

EVALUATION_VERSION: Final = "1.0"
EVALUATION_CORE_VERSION: Final = "fixed-evaluation-v1"
ALLOWED_EVALUATION_ROOT_NAME: Final = "evaluations"
ALLOWED_FIXTURE_ROOT_NAME: Final = "fixtures"
EXPECTED_OUTCOME_CATEGORY: Final = "closed_fixture_pass"


class FixedEvaluationError(ValueError):
    """Fail-closed error for the fixed synthetic-fixture evaluation."""


@dataclass(frozen=True)
class FixedEvaluationRecord:
    fixture_id: str
    expected_outcome: str
    status: str
    input_sha256: str
    output_sha256: str

    def as_dict(self) -> dict[str, object]:
        return {
            "fixtureId": self.fixture_id,
            "expectedOutcome": self.expected_outcome,
            "status": self.status,
            "inputSha256": self.input_sha256,
            "outputSha256": self.output_sha256,
        }


@dataclass(frozen=True)
class FixedEvaluationResult:
    evaluation_id: str
    evaluation_version: str
    suite_id: str
    suite_version: str
    suite_sha256: str
    fixture_count: int
    pass_count: int
    fail_count: int
    records: tuple[FixedEvaluationRecord, ...]
    evaluation_sha256: str

    def as_dict(self) -> dict[str, object]:
        return {
            "status": "completed_fixed_evaluation_only",
            "evaluationCoreVersion": EVALUATION_CORE_VERSION,
            "evaluationId": self.evaluation_id,
            "evaluationVersion": self.evaluation_version,
            "suiteId": self.suite_id,
            "suiteVersion": self.suite_version,
            "suiteSha256": self.suite_sha256,
            "fixtureCount": self.fixture_count,
            "passCount": self.pass_count,
            "failCount": self.fail_count,
            "records": [record.as_dict() for record in self.records],
            "evaluationSha256": self.evaluation_sha256,
            "modelLoaded": False,
            "realOmrInference": False,
            "realOmrAccuracyMeasured": False,
            "generalAccuracyClaim": False,
            "userInputAccepted": False,
            "networkUsed": False,
        }


def _require_text(payload: dict[str, object], key: str, *, context: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise FixedEvaluationError(f"{context} field {key!r} must be a non-empty string")
    return value


def _direct_child(root: Path, name: str, *, context: str) -> Path:
    candidate = (root / name).resolve()
    if candidate.parent != root.resolve():
        raise FixedEvaluationError(f"{context} must be a direct child of its allowed root")
    if candidate.is_symlink():
        raise FixedEvaluationError(f"{context} symlinks are forbidden")
    return candidate


def _read_json_object(path: Path, *, context: str) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FixedEvaluationError(f"{context} is unreadable or invalid JSON") from exc
    if not isinstance(payload, dict):
        raise FixedEvaluationError(f"{context} root must be an object")
    return payload


def _canonical_evaluation_sha256(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def run_fixed_evaluation(
    *,
    evaluation_manifest_path: Path,
    evaluation_root: Path,
    fixture_root: Path,
) -> FixedEvaluationResult:
    resolved_evaluation_root = evaluation_root.resolve()
    if resolved_evaluation_root.name != ALLOWED_EVALUATION_ROOT_NAME:
        raise FixedEvaluationError("allowed evaluation root must be named 'evaluations'")
    if not resolved_evaluation_root.is_dir() or resolved_evaluation_root.is_symlink():
        raise FixedEvaluationError("allowed evaluation root must be a real directory")

    resolved_fixture_root = fixture_root.resolve()
    if resolved_fixture_root.name != ALLOWED_FIXTURE_ROOT_NAME:
        raise FixedEvaluationError("allowed fixture root must be named 'fixtures'")
    if not resolved_fixture_root.is_dir() or resolved_fixture_root.is_symlink():
        raise FixedEvaluationError("allowed fixture root must be a real directory")

    resolved_manifest = evaluation_manifest_path.resolve()
    if resolved_manifest.parent != resolved_evaluation_root or resolved_manifest.is_symlink():
        raise FixedEvaluationError(
            "evaluation manifest must be a non-symlink direct child of the evaluation root"
        )

    manifest = _read_json_object(resolved_manifest, context="evaluation manifest")
    required_manifest_keys = {
        "evaluationVersion",
        "evaluationId",
        "suiteRegistryName",
        "expectedSuiteId",
        "expectedSuiteVersion",
        "metricContract",
        "cases",
    }
    if set(manifest) != required_manifest_keys:
        raise FixedEvaluationError("evaluation manifest fields must match the closed v1 schema")

    if _require_text(manifest, "evaluationVersion", context="evaluation manifest") != EVALUATION_VERSION:
        raise FixedEvaluationError("unsupported evaluation manifest version")
    evaluation_id = _require_text(manifest, "evaluationId", context="evaluation manifest")
    suite_registry_name = _require_text(
        manifest, "suiteRegistryName", context="evaluation manifest"
    )
    expected_suite_id = _require_text(manifest, "expectedSuiteId", context="evaluation manifest")
    expected_suite_version = _require_text(
        manifest, "expectedSuiteVersion", context="evaluation manifest"
    )

    metric_contract = manifest.get("metricContract")
    expected_metric_contract = {
        "allFixturesMustPass": True,
        "generalAccuracyClaim": False,
        "realOmrAccuracyMeasured": False,
    }
    if metric_contract != expected_metric_contract:
        raise FixedEvaluationError("metric contract must match the closed fixed-evaluation policy")

    cases = manifest.get("cases")
    if not isinstance(cases, list) or not cases:
        raise FixedEvaluationError("evaluation cases must be a non-empty array")

    registry_path = _direct_child(
        resolved_fixture_root,
        suite_registry_name,
        context="suite registry",
    )
    if not registry_path.is_file():
        raise FixedEvaluationError("suite registry is missing")

    try:
        suite_result = run_generated_fixture_suite(
            registry_path=registry_path,
            allowed_root=resolved_fixture_root,
        )
    except FixtureSuiteError as exc:
        raise FixedEvaluationError("generated fixture suite failed closed") from exc

    if suite_result.suite_id != expected_suite_id:
        raise FixedEvaluationError("suite identity does not match the evaluation manifest")
    if suite_result.suite_version != expected_suite_version:
        raise FixedEvaluationError("suite version does not match the evaluation manifest")

    registry = _read_json_object(registry_path, context="suite registry")
    registry_entries = registry.get("fixtures")
    if not isinstance(registry_entries, list) or not registry_entries:
        raise FixedEvaluationError("suite registry fixtures must be a non-empty array")

    actual_results: dict[str, object] = {}
    for entry in registry_entries:
        if not isinstance(entry, dict) or set(entry) != {"manifestName"}:
            raise FixedEvaluationError("suite registry entries must match the closed v1 schema")
        manifest_name = _require_text(entry, "manifestName", context="suite registry entry")
        fixture_manifest_path = _direct_child(
            resolved_fixture_root,
            manifest_name,
            context="fixture manifest",
        )
        if not fixture_manifest_path.is_file():
            raise FixedEvaluationError("fixture manifest is missing")
        try:
            fixture_result = run_generated_fixture(
                manifest_path=fixture_manifest_path,
                allowed_root=resolved_fixture_root,
            )
        except FixtureInferenceError as exc:
            raise FixedEvaluationError("fixture execution failed closed") from exc
        if fixture_result.fixture_id in actual_results:
            raise FixedEvaluationError("duplicate fixture ID in evaluated suite")
        actual_results[fixture_result.fixture_id] = fixture_result

    expected_cases: dict[str, str] = {}
    for case in cases:
        if not isinstance(case, dict) or set(case) != {"fixtureId", "expectedOutcome"}:
            raise FixedEvaluationError("evaluation cases must match the closed v1 schema")
        fixture_id = _require_text(case, "fixtureId", context="evaluation case")
        expected_outcome = _require_text(case, "expectedOutcome", context="evaluation case")
        if expected_outcome != EXPECTED_OUTCOME_CATEGORY:
            raise FixedEvaluationError("unsupported expected outcome category")
        if fixture_id in expected_cases:
            raise FixedEvaluationError("duplicate fixture ID in evaluation cases")
        expected_cases[fixture_id] = expected_outcome

    actual_ids = set(actual_results)
    expected_ids = set(expected_cases)
    if expected_ids != actual_ids:
        unknown = sorted(expected_ids - actual_ids)
        missing = sorted(actual_ids - expected_ids)
        raise FixedEvaluationError(
            f"evaluation fixture coverage mismatch: unknown={unknown}, missing={missing}"
        )

    records: list[FixedEvaluationRecord] = []
    for fixture_id in sorted(actual_ids):
        fixture_result = actual_results[fixture_id]
        payload = fixture_result.as_dict()
        closed_pass = (
            payload.get("status") == "completed_offline_fixture_only"
            and payload.get("modelLoaded") is False
            and payload.get("realOmrInference") is False
            and payload.get("userInputAccepted") is False
            and payload.get("networkUsed") is False
        )
        status = "pass" if closed_pass else "fail"
        records.append(
            FixedEvaluationRecord(
                fixture_id=fixture_id,
                expected_outcome=expected_cases[fixture_id],
                status=status,
                input_sha256=fixture_result.input_sha256,
                output_sha256=fixture_result.output_sha256,
            )
        )

    pass_count = sum(record.status == "pass" for record in records)
    fail_count = len(records) - pass_count
    if fail_count:
        raise FixedEvaluationError("fixed evaluation contains a failed fixture")

    canonical_payload = {
        "evaluationId": evaluation_id,
        "evaluationVersion": EVALUATION_VERSION,
        "suiteId": suite_result.suite_id,
        "suiteVersion": suite_result.suite_version,
        "suiteSha256": suite_result.suite_sha256,
        "fixtureCount": len(records),
        "passCount": pass_count,
        "failCount": fail_count,
        "records": [record.as_dict() for record in records],
    }
    evaluation_sha256 = _canonical_evaluation_sha256(canonical_payload)

    return FixedEvaluationResult(
        evaluation_id=evaluation_id,
        evaluation_version=EVALUATION_VERSION,
        suite_id=suite_result.suite_id,
        suite_version=suite_result.suite_version,
        suite_sha256=suite_result.suite_sha256,
        fixture_count=len(records),
        pass_count=pass_count,
        fail_count=fail_count,
        records=tuple(records),
        evaluation_sha256=evaluation_sha256,
    )


def disabled_fixed_evaluation_evidence() -> dict[str, object]:
    return {
        "status": "fixed_evaluation_not_requested",
        "evaluationCoreVersion": EVALUATION_CORE_VERSION,
        "fixedEvaluationEnabled": True,
        "realOmrAccuracyMeasured": False,
        "generalAccuracyClaim": False,
        "modelLoaded": False,
        "realOmrInference": False,
        "userInputAccepted": False,
        "networkUsed": False,
    }
