#!/usr/bin/env python3
"""Validate exact ScoreMosaic CLA assent from a GitHub pull-request event."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

CLA_ACCEPTANCE = "CLA: I have read and agree to the ScoreMosaic Contributor License Agreement."
OWNER = "khfy7wpr5p-maker"


def has_acceptance(body: str | None) -> bool:
    return CLA_ACCEPTANCE in (line.strip() for line in (body or "").splitlines())


def validate_event(event: dict[str, Any], owner: str = OWNER) -> tuple[bool, str]:
    pull_request = event.get("pull_request")
    if not isinstance(pull_request, dict):
        return False, "event does not contain a pull_request object"
    user = pull_request.get("user")
    login = user.get("login") if isinstance(user, dict) else None
    if login == owner:
        return True, "repository owner/licensor contribution is exempt"
    if not isinstance(login, str) or not login:
        return False, "pull-request author identity is missing"
    if not has_acceptance(pull_request.get("body")):
        return False, f"external contributor @{login} must add the exact CLA acceptance line"
    return True, f"exact CLA acceptance recorded for @{login}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", required=True, type=Path)
    parser.add_argument("--owner", default=OWNER)
    args = parser.parse_args()
    try:
        event = json.loads(args.event.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"CLA validation failed: {exc}")
        return 1
    valid, message = validate_event(event, owner=args.owner)
    print(message)
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
