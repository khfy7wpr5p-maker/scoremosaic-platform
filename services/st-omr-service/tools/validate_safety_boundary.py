"""Validate the closed ST-OMR repository safety boundary."""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path
from typing import NoReturn


def fail(message: str) -> NoReturn:
    raise ValueError(message)


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def main() -> int:
    service_root = Path(__file__).resolve().parents[1]
    project_path = service_root / "pyproject.toml"

    require(project_path.is_file(), f"Missing project file: {project_path}")

    project = tomllib.loads(project_path.read_text(encoding="utf-8"))
    project_metadata = project.get("project")
    boundary = project.get("tool", {}).get("scoremosaic")

    require(isinstance(project_metadata, dict), "Missing [project] table")
    require(
        isinstance(boundary, dict),
        "Missing [tool.scoremosaic] safety boundary",
    )

    require(
        project_metadata.get("dependencies") == [],
        "Runtime dependencies must remain empty",
    )
    require(
        boundary.get("service-role") == "candidate_omr_engine",
        "Unexpected ST-OMR service role",
    )
    require(
        boundary.get("device-policy") == "cpu_only",
        "ST-OMR must remain CPU-only",
    )

    expected_roots = {
        "allowed-model-root": "models",
        "allowed-contracts-root": "contracts",
        "allowed-fixture-root": "fixtures",
        "allowed-evaluation-root": "evaluations",
    }

    for key, expected_value in expected_roots.items():
        require(
            boundary.get(key) == expected_value,
            f"{key} must equal {expected_value!r}",
        )

    required_true_invariants = {
        "dependency-lock-required",
        "resource-limits-required",
        "repository-test-model-only",
        "static-repository-symbol-sample-only",
        "static-repository-membership-sample-only",
    }

    enabled_true = {
        "manifest-validation-enabled",
        "checksum-validation-enabled",
        "pinned-offline-model-runtime-enabled",
        "repository-test-model-loading-enabled",
        "repository-test-model-inference-enabled",
        "offline-generated-fixture-inference-enabled",
        "generated-fixture-suite-enabled",
        "fixed-evaluation-enabled",
        "structured-synthetic-symbol-output-enabled",
        "synthetic-symbol-membership-enabled",
    }

    enabled_false = {
        "model-loading-enabled",
        "inference-enabled",
        "symbol-producing-model-enabled",
        "real-symbol-detection-enabled",
        "musical-interpretation-enabled",
        "pitch-assignment-enabled",
        "duration-assignment-enabled",
        "voice-assignment-enabled",
        "attachment-relations-enabled",
        "beam-membership-enabled",
        "chord-relations-enabled",
        "reading-order-semantics-enabled",
        "notation-graph-enabled",
        "real-omr-evaluation-enabled",
        "real-omr-inference-enabled",
        "general-accuracy-claim-enabled",
        "user-input-enabled",
        "upload-enabled",
        "musicxml-generation-enabled",
        "gateway-integration-enabled",
        "ensemble-integration-enabled",
        "automatic-correction-enabled",
        "ranking-enabled",
        "winner-selection-enabled",
        "training-enabled",
        "self-training-enabled",
        "teacher-approval-enabled",
        "publication-enabled",
        "network-dispatch-enabled",
        "gpu-enabled",
        "persistent-storage-enabled",
        "public-endpoint-enabled",
    }

    for key in sorted(required_true_invariants):
        require(boundary.get(key) is True, f"{key} must remain true")

    for key in sorted(enabled_true):
        require(boundary.get(key) is True, f"{key} must remain true")

    for key in sorted(enabled_false):
        require(boundary.get(key) is False, f"{key} must remain false")

    actual_enabled_keys = {
        key for key in boundary if key.endswith("-enabled")
    }
    reviewed_enabled_keys = enabled_true | enabled_false

    unknown_enabled_keys = sorted(
        actual_enabled_keys - reviewed_enabled_keys
    )
    missing_enabled_keys = sorted(
        reviewed_enabled_keys - actual_enabled_keys
    )

    require(
        not unknown_enabled_keys,
        "Unreviewed capability flags: "
        + ", ".join(unknown_enabled_keys),
    )
    require(
        not missing_enabled_keys,
        "Missing capability flags: "
        + ", ".join(missing_enabled_keys),
    )

    phase = boundary.get("phase")
    require(
        isinstance(phase, str) and bool(phase.strip()),
        "Phase must be a non-empty string",
    )

    print("ST-OMR safety boundary: OK")
    print(f"Phase: {phase}")
    print(f"Required non-capability invariants: {len(required_true_invariants)}")
    print(f"Enabled reviewed capabilities: {len(enabled_true)}")
    print(f"Disabled reviewed capabilities: {len(enabled_false)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        OSError,
        KeyError,
        TypeError,
        ValueError,
        tomllib.TOMLDecodeError,
    ) as error:
        print(
            f"ST-OMR safety boundary: FAILED: {error}",
            file=sys.stderr,
        )
        raise SystemExit(1)
