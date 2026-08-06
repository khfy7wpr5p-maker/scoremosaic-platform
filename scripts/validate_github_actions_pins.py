#!/usr/bin/env python3
"""Fail closed when GitHub Actions use mutable external references."""

from __future__ import annotations

import re
import sys
from pathlib import Path

WORKFLOW_ROOT = Path(".github/workflows")
WORKFLOW_PATTERNS = ("*.yml", "*.yaml")
USES_PATTERN = re.compile(r"^\s*(?:-\s*)?uses:\s*([^\s#]+)")
PINNED_EXTERNAL_PATTERN = re.compile(
    r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_./-]+)?@[0-9a-fA-F]{40}$"
)


def workflow_files(root: Path = WORKFLOW_ROOT) -> list[Path]:
    files: set[Path] = set()
    for pattern in WORKFLOW_PATTERNS:
        files.update(root.glob(pattern))
    return sorted(files)


def validate_file(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        return [f"{path}: unreadable workflow: {exc}"]

    for line_number, line in enumerate(lines, start=1):
        match = USES_PATTERN.match(line)
        if match is None:
            continue
        reference = match.group(1)
        if reference.startswith("./") or reference.startswith("docker://"):
            continue
        if not PINNED_EXTERNAL_PATTERN.fullmatch(reference):
            errors.append(
                f"{path}:{line_number}: external uses reference must use a full "
                f"40-character commit SHA: {reference}"
            )
    return errors


def main() -> int:
    if not WORKFLOW_ROOT.is_dir():
        print(f"workflow directory is missing: {WORKFLOW_ROOT}", file=sys.stderr)
        return 1

    files = workflow_files()
    if not files:
        print(f"no workflow files found under {WORKFLOW_ROOT}", file=sys.stderr)
        return 1

    errors = [error for path in files for error in validate_file(path)]
    if errors:
        print("GitHub Actions pin validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(f"Validated immutable action pins in {len(files)} workflow files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
