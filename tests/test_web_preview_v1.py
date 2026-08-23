from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / "contracts" / "web-preview-v1.json").read_text(encoding="utf-8"))
WORKFLOW = (ROOT / ".github" / "workflows" / "web-preview-v1-ci.yml")
BUILDER = ROOT / "scripts" / "build_web_preview.py"


def tree_digest(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            result[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


class WebPreviewV1Tests(unittest.TestCase):
    def test_contract_is_fixture_only_with_verified_public_pages_preview(self) -> None:
        self.assertEqual("scoremosaic-web-preview-v1", CONTRACT["version"])
        self.assertIs(CONTRACT["stageNumberAssigned"], False)
        self.assertEqual(
            "PUBLIC_GITHUB_PAGES_FIXTURE_PREVIEW_DEPLOYED_VERIFIED",
            CONTRACT["status"],
        )
        self.assertEqual(
            "fixture_only_static_preview_with_explicit_public_github_pages_authority",
            CONTRACT["scope"],
        )
        self.assertIs(CONTRACT["previewContent"]["fixtureOnly"], True)
        self.assertIs(CONTRACT["previewContent"]["productionArtifact"], False)
        self.assertIs(CONTRACT["previewContent"]["authoritativeTruth"], False)
        deployment = CONTRACT["publicPreviewDeployment"]
        self.assertIs(deployment["authorized"], True)
        self.assertEqual("github_pages", deployment["provider"])
        self.assertEqual("main", deployment["sourceBranch"])
        self.assertIs(deployment["productionDeployment"], False)
        self.assertIs(deployment["productionAuthorityGranted"], False)
        self.assertIs(deployment["apiAuthorityGranted"], False)
        evidence = deployment["deploymentEvidence"]
        self.assertEqual(
            "https://khfy7wpr5p-maker.github.io/scoremosaic-platform/",
            evidence["publicUrl"],
        )
        self.assertEqual(32652403651, evidence["workflowRunId"])
        self.assertEqual(
            "33555ed152d1f8f3bdec0072bec7693c29b2aa1c",
            evidence["verifiedDeploymentCommitSha"],
        )

        activation = CONTRACT["activationLocks"]
        for key in (
            "githubPagesEnabled",
            "publicPreviewDeployed",
            "publicUrlAssigned",
            "publicTrafficActivated",
        ):
            self.assertIs(activation[key], True, key)
        for key in (
            "browserNetworkActivated",
            "liveApiActivated",
            "productionPersistenceActivated",
        ):
            self.assertIs(activation[key], False, key)

    def test_security_contract_forbids_network_persistence_and_authority(self) -> None:
        security = CONTRACT["security"]
        for key in (
            "connectSrcNoneRequired",
            "formActionNoneRequired",
            "objectSrcNoneRequired",
            "frameSrcNoneRequired",
            "baseUriNoneRequired",
        ):
            self.assertIs(security[key], True, key)
        for key in (
            "externalScriptAllowed",
            "externalStyleAllowed",
            "networkApiAllowed",
            "browserPersistenceAllowed",
            "cookieUseAllowed",
            "realUploadAllowed",
            "realAuthenticationAllowed",
            "serverWriteAllowed",
            "approvalExecutionAllowed",
            "publicationExecutionAllowed",
            "productionCredentialsAllowed",
            "realUserDataAllowed",
        ):
            self.assertIs(security[key], False, key)

    def test_builder_produces_standalone_deterministic_preview(self) -> None:
        with tempfile.TemporaryDirectory() as first_tmp, tempfile.TemporaryDirectory() as second_tmp:
            first = Path(first_tmp) / "site"
            second = Path(second_tmp) / "site"
            command = [sys.executable, str(BUILDER), "--output"]
            subprocess.run(command + [str(first)], cwd=ROOT, check=True)
            subprocess.run(command + [str(second)], cwd=ROOT, check=True)

            expected = {
                ".nojekyll",
                "PREVIEW-NOTICE.txt",
                "index.html",
                "styles.css",
                "accessibility.css",
                "edit-intent.css",
                "fixture.js",
                "app.js",
                "edit-intent.js",
                "preview.css",
                "application/read-adapter.js",
                "application/edit-intent-adapter.js",
                "application/application-state.js",
                "application/local-application.js",
            }
            self.assertEqual(expected, set(tree_digest(first)))
            self.assertEqual(tree_digest(first), tree_digest(second))

            index = (first / "index.html").read_text(encoding="utf-8")
            self.assertIn("connect-src 'none'", index)
            self.assertIn("form-action 'none'", index)
            self.assertIn("Non-production preview", index)
            self.assertIn("Fixture data only", index)
            self.assertNotIn("../stage11-ui-application-contracts/", index)
            self.assertIn('src="application/read-adapter.js"', index)

    def test_builder_never_overwrites_or_deletes_existing_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "site"
            output.mkdir()
            sentinel = output / "keep-me.txt"
            sentinel.write_text("user-owned", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(BUILDER), "--output", str(output)],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(0, result.returncode)
            self.assertEqual("user-owned", sentinel.read_text(encoding="utf-8"))
            self.assertEqual({"keep-me.txt"}, {path.name for path in output.iterdir()})

    def test_builder_refuses_output_inside_repository(self) -> None:
        output = ROOT / ".web-preview-v1-unsafe-test-output"
        self.assertFalse(output.exists(), "reserved regression-test path unexpectedly exists")
        result = subprocess.run(
            [sys.executable, str(BUILDER), "--output", str(output)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(0, result.returncode)
        self.assertFalse(output.exists())

    def test_generated_preview_contains_no_network_persistence_or_external_http(self) -> None:
        forbidden = (
            "fetch(",
            "XMLHttpRequest",
            "WebSocket",
            "EventSource",
            "navigator.sendBeacon",
            "localStorage",
            "sessionStorage",
            "indexedDB",
            "document.cookie",
            "http://",
            "https://",
        )
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "site"
            subprocess.run(
                [sys.executable, str(BUILDER), "--output", str(output)],
                cwd=ROOT,
                check=True,
            )
            for path in output.rglob("*"):
                if path.is_file() and path.suffix in {".html", ".js", ".css"}:
                    text = path.read_text(encoding="utf-8")
                    for token in forbidden:
                        self.assertNotIn(token, text, f"{token} in {path.relative_to(output)}")

    def test_artifact_ci_remains_non_deploying(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("actions/upload-artifact@", text)
        self.assertIn("scoremosaic-web-preview-v1", text)
        self.assertNotIn("actions/deploy-pages@", text)
        self.assertNotIn("actions/configure-pages@", text)
        self.assertNotIn("pages: write", text)
        self.assertNotIn("id-token: write", text)
        self.assertNotIn("environment:", text)
        self.assertIn("contents: read", text)


if __name__ == "__main__":
    unittest.main()
