from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import unittest

from scripts import validate_cla_acceptance
from scripts import validate_license_policy


ROOT = Path(__file__).resolve().parents[1]


class LicensePolicyTests(unittest.TestCase):
    def test_repository_license_policy_is_valid(self) -> None:
        self.assertEqual([], validate_license_policy.validate(ROOT))

    def test_polyform_text_is_the_unmodified_official_version(self) -> None:
        digest = hashlib.sha256((ROOT / "LICENSE").read_bytes()).hexdigest()
        self.assertEqual(validate_license_policy.POLYFORM_SHA256, digest)

    def test_every_declared_runtime_python_pin_is_inventoried(self) -> None:
        declared, errors = validate_license_policy.collect_declared_python_dependencies(ROOT)
        self.assertEqual([], errors)
        inventory = validate_license_policy.load_inventory(ROOT)
        inventoried = {(entry["name"], entry["version"]) for entry in inventory["pythonPackages"]}
        self.assertEqual(declared, inventoried)
        self.assertIn(("homr", "0.7.0"), declared)
        self.assertIn(("torch", "2.13.0+cpu"), declared)
        self.assertIn(("pypdf", "6.14.2"), declared)

    def test_missing_dependency_inventory_entry_fails_closed(self) -> None:
        inventory = copy.deepcopy(validate_license_policy.load_inventory(ROOT))
        removed = inventory["pythonPackages"].pop()
        errors = validate_license_policy.validate_inventory(ROOT, inventory)
        self.assertTrue(
            any(f"missing declared dependency {removed['name']}=={removed['version']}" in error for error in errors),
            errors,
        )

    def test_review_required_item_cannot_be_silently_approved(self) -> None:
        inventory = copy.deepcopy(validate_license_policy.load_inventory(ROOT))
        target = next(entry for entry in inventory["externalComponents"] if entry["classification"] == "review-required")
        target["productionApproved"] = True
        errors = validate_license_policy.validate_inventory(ROOT, inventory)
        self.assertTrue(any("blocked classification cannot be production-approved" in error for error in errors), errors)

    def test_strong_copyleft_package_remains_production_gated(self) -> None:
        inventory = validate_license_policy.load_inventory(ROOT)
        target = next(entry for entry in inventory["pythonPackages"] if entry["name"] == "pymupdf")
        self.assertEqual("strong-copyleft-or-commercial", target["classification"])
        self.assertIs(target["productionApproved"], False)
        self.assertIs(target["redistributionApproved"], False)

    def test_unpinned_requirement_is_rejected(self) -> None:
        errors: list[str] = []
        self.assertIsNone(validate_license_policy._parse_pin("requests>=2", "fixture", errors))
        self.assertIn("dependency must use exact name==version pin", errors[0])

    def test_external_contributor_requires_exact_cla_line(self) -> None:
        event = {"pull_request": {"user": {"login": "external-user"}, "body": "Testing"}}
        valid, _ = validate_cla_acceptance.validate_event(event)
        self.assertIs(valid, False)
        event["pull_request"]["body"] = validate_cla_acceptance.CLA_ACCEPTANCE
        valid, _ = validate_cla_acceptance.validate_event(event)
        self.assertIs(valid, True)

    def test_owner_contribution_is_cla_exempt(self) -> None:
        event = {"pull_request": {"user": {"login": validate_cla_acceptance.OWNER}, "body": None}}
        valid, message = validate_cla_acceptance.validate_event(event)
        self.assertIs(valid, True)
        self.assertIn("exempt", message)

    def test_cla_workflow_checks_default_branch_without_pr_code(self) -> None:
        text = (ROOT / ".github/workflows/cla-ci.yml").read_text(encoding="utf-8")
        self.assertIn("pull_request_target:", text)
        self.assertIn("ref: ${{ github.event.repository.default_branch }}", text)
        self.assertIn("persist-credentials: false", text)
        self.assertNotIn("github.event.pull_request.head", text)

    def test_foundation_ci_also_enforces_license_policy(self) -> None:
        text = (ROOT / ".github/workflows/foundation-ci.yml").read_text(encoding="utf-8")
        self.assertIn("python scripts/validate_license_policy.py", text)
        self.assertIn("test_license_policy.py", text)


if __name__ == "__main__":
    unittest.main()
