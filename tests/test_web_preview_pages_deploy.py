from __future__ import annotations

import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "web-preview-pages-deploy.yml"
CONTRACT = json.loads((ROOT / "contracts" / "web-preview-v1.json").read_text(encoding="utf-8"))


class WebPreviewPagesDeployTests(unittest.TestCase):
    def test_public_preview_authority_is_narrow_and_explicit(self) -> None:
        deployment = CONTRACT["publicPreviewDeployment"]
        self.assertIs(deployment["authorized"], True)
        self.assertEqual("github_pages", deployment["provider"])
        self.assertEqual("main", deployment["sourceBranch"])
        self.assertEqual("github-pages", deployment["environment"])
        self.assertEqual("/scoremosaic-platform/", deployment["expectedBasePath"])
        self.assertIs(deployment["productionDeployment"], False)
        self.assertIs(deployment["productionAuthorityGranted"], False)
        self.assertIs(deployment["apiAuthorityGranted"], False)

        security = CONTRACT["security"]
        self.assertIs(security["realUserDataAllowed"], False)
        self.assertIs(security["productionCredentialsAllowed"], False)
        self.assertIs(security["networkApiAllowed"], False)
        self.assertIs(security["browserPersistenceAllowed"], False)
        self.assertIs(security["serverWriteAllowed"], False)

    def test_pre_deployment_state_does_not_claim_runtime_success(self) -> None:
        for key in (
            "githubPagesEnabled",
            "publicPreviewDeployed",
            "publicUrlAssigned",
            "browserNetworkActivated",
            "liveApiActivated",
            "productionPersistenceActivated",
            "publicTrafficActivated",
        ):
            self.assertIs(CONTRACT["activationLocks"][key], False, key)

    def test_deployment_workflow_is_main_only_and_never_runs_on_pull_request(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("branches:\n      - main", text)
        self.assertNotIn("pull_request:", text)
        self.assertGreaterEqual(text.count("github.ref == 'refs/heads/main'"), 2)
        self.assertIn("workflow_dispatch:", text)

    def test_pages_permissions_are_isolated_to_deploy_job(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertEqual(1, text.count("pages: write"))
        self.assertEqual(1, text.count("id-token: write"))
        self.assertEqual(1, text.count("contents: read"))
        self.assertIn("environment:\n      name: github-pages", text)
        self.assertNotIn("secrets.", text)
        self.assertNotIn("github.token", text)

    def test_only_immutable_official_pages_actions_are_used(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        expected = {
            "actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803",
            "actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1",
            "actions/upload-pages-artifact@fc324d3547104276b827a68afc52ff2a11cc49c9",
            "actions/deploy-pages@cd2ce8fcbc39b97be8ca5fce6e763baed58fa128",
        }
        actual = set(re.findall(r"uses:\s*([^\s#]+)", text))
        self.assertEqual(expected, actual)
        self.assertNotIn("actions/configure-pages@", text)
        self.assertNotIn("enablement:", text)

    def test_workflow_builds_the_hardened_fixture_preview_before_upload(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("python scripts/validate_github_actions_pins.py", text)
        self.assertIn("test_web_preview_v1.py", text)
        self.assertIn("test_web_preview_pages_deploy.py", text)
        self.assertIn("python scripts/build_web_preview.py --output", text)
        self.assertIn("connect-src 'none'", text)
        self.assertIn("Non-production preview", text)
        self.assertIn("Fixture data only", text)
        self.assertNotIn("curl ", text)
        self.assertNotIn("wget ", text)


if __name__ == "__main__":
    unittest.main()
