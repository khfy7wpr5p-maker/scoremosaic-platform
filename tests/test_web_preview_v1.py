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
WORKFLOW = ROOT / ".github" / "workflows" / "web-preview-v1-ci.yml"
BUILDER = ROOT / "scripts" / "build_web_preview.py"


def tree_digest(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            result[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def make_build_inputs(root: Path) -> dict[str, Path]:
    core_dir = root / "core"
    osmd_dir = root / "node_modules" / "opensheetmusicdisplay"
    (osmd_dir / "build").mkdir(parents=True)
    core_dir.mkdir(parents=True)

    core_bundle = core_dir / "st-score-editor-core.runtime.js"
    core_bytes = b"(()=>{window.STScoreEditorCoreRuntime=Object.freeze({runtimeVersion:'1.0.0'});})();\n"
    core_bundle.write_bytes(core_bytes)
    core_manifest = {
        "contract": "ST_SCORE_EDITOR_CORE_BROWSER_BUNDLE",
        "version": "1.0.0",
        "runtimeVersion": "1.0.0",
        "bundler": {"package": "esbuild", "version": "0.28.2", "license": "MIT"},
        "artifact": "st-score-editor-core.runtime.js",
        "format": "iife",
        "target": "es2022",
        "global": "STScoreEditorCoreRuntime",
        "externalImports": 0,
        "networkCapable": False,
        "persistenceCapable": False,
        "serverRevisionAuthority": False,
        "approvalAuthority": False,
        "publicationAuthority": False,
        "bytes": len(core_bytes),
        "sha256": hashlib.sha256(core_bytes).hexdigest(),
    }
    core_manifest_path = core_dir / "st-score-editor-core.runtime.manifest.json"
    core_manifest_path.write_text(json.dumps(core_manifest), encoding="utf-8")

    osmd_bundle = osmd_dir / "build" / "opensheetmusicdisplay.min.js"
    osmd_bundle.write_text(
        "window.opensheetmusicdisplay={OpenSheetMusicDisplay:function(){this.load=async function(){};this.render=function(){};}};\n",
        encoding="utf-8",
    )
    package_json = osmd_dir / "package.json"
    package_json.write_text(
        json.dumps({
            "name": "opensheetmusicdisplay",
            "version": "2.1.1",
            "license": "BSD-3-Clause",
            "main": "build/opensheetmusicdisplay.min.js",
        }),
        encoding="utf-8",
    )
    license_path = osmd_dir / "LICENSE"
    license_path.write_text(
        "BSD 3-Clause License\nCopyright OpenSheetMusicDisplay contributors. Redistribution conditions apply.\n",
        encoding="utf-8",
    )
    return {
        "core_bundle": core_bundle,
        "core_manifest": core_manifest_path,
        "osmd_bundle": osmd_bundle,
        "osmd_package_json": package_json,
        "osmd_license": license_path,
    }


def builder_command(output: Path, inputs: dict[str, Path]) -> list[str]:
    return [
        sys.executable,
        str(BUILDER),
        "--output", str(output),
        "--core-bundle", str(inputs["core_bundle"]),
        "--core-manifest", str(inputs["core_manifest"]),
        "--osmd-bundle", str(inputs["osmd_bundle"]),
        "--osmd-package-json", str(inputs["osmd_package_json"]),
        "--osmd-license", str(inputs["osmd_license"]),
    ]


class WebPreviewV1Tests(unittest.TestCase):
    def test_contract_is_fixture_only_with_local_verified_renderer(self) -> None:
        self.assertEqual("scoremosaic-web-preview-v1", CONTRACT["version"])
        self.assertIs(CONTRACT["stageNumberAssigned"], False)
        self.assertEqual("PUBLIC_GITHUB_PAGES_FIXTURE_PREVIEW_DEPLOYED_VERIFIED", CONTRACT["status"])
        self.assertIn("fixture_only_static_preview", CONTRACT["scope"])
        preview = CONTRACT["previewContent"]
        self.assertIs(preview["fixtureOnly"], True)
        self.assertIs(preview["productionArtifact"], False)
        self.assertIs(preview["authoritativeTruth"], False)
        self.assertIs(preview["localCoreRuntimeBundled"], True)
        self.assertIs(preview["localOsmdRendererBundled"], True)
        self.assertIs(preview["realMusicNotationRenderedFromFixtureCoreSession"], True)
        self.assertIs(preview["structuredEditCreatesLocalCoreRevision"], True)
        self.assertIs(preview["serverScoreEditCommandCreated"], False)
        self.assertIs(preview["fixtureFallbackRetained"], True)

        build = CONTRACT["build"]
        self.assertIs(build["dependencyFree"], False)
        self.assertIs(build["exactLocalBuildInputsRequired"], True)
        self.assertIs(build["remoteRuntimeDependencyAllowed"], False)
        self.assertIs(build["coreArtifactIntegrityVerificationRequired"], True)
        self.assertIs(build["osmdPackageIdentityVerificationRequired"], True)

        third_party = CONTRACT["thirdPartyRuntime"]["opensheetmusicdisplay"]
        self.assertEqual("2.1.1", third_party["version"])
        self.assertEqual("BSD-3-Clause", third_party["license"])
        self.assertIs(third_party["localArtifactOnly"], True)
        self.assertIs(third_party["licenseFileCarried"], True)
        self.assertIs(third_party["presentationOnly"], True)
        self.assertIs(third_party["networkUseAllowed"], False)

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
            "rendererCoordinatesAuthoritative",
            "rendererDomIdsAuthoritative",
            "rendererObjectsAuthoritative",
            "rendererUrlInputAllowedByHost",
        ):
            self.assertIs(security[key], False, key)
        self.assertIs(security["localVerifiedThirdPartyScriptAllowed"], True)

    def test_builder_produces_standalone_deterministic_renderer_preview(self) -> None:
        with tempfile.TemporaryDirectory() as deps_tmp, tempfile.TemporaryDirectory() as first_tmp, tempfile.TemporaryDirectory() as second_tmp:
            inputs = make_build_inputs(Path(deps_tmp))
            first = Path(first_tmp) / "site"
            second = Path(second_tmp) / "site"
            subprocess.run(builder_command(first, inputs), cwd=ROOT, check=True)
            subprocess.run(builder_command(second, inputs), cwd=ROOT, check=True)

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
                "application/score-editor-core-bridge.js",
                "application/score-editor-osmd-host.js",
                "vendor/st-score-editor-core.runtime.js",
                "vendor/st-score-editor-core.runtime.manifest.json",
                "vendor/opensheetmusicdisplay-2.1.1.min.js",
                "vendor/OSMD-LICENSE.txt",
                "vendor/renderer-profile.js",
            }
            self.assertEqual(expected, set(tree_digest(first)))
            self.assertEqual(tree_digest(first), tree_digest(second))

            index = (first / "index.html").read_text(encoding="utf-8")
            self.assertIn("connect-src 'none'", index)
            self.assertIn("form-action 'none'", index)
            self.assertIn("Non-production preview", index)
            self.assertIn("Fixture data only", index)
            self.assertIn('id="score-render-host"', index)
            self.assertIn('id="score-fixture-fallback"', index)
            self.assertNotIn("../stage11-ui-application-contracts/", index)

            ordered = [
                "vendor/opensheetmusicdisplay-2.1.1.min.js",
                "vendor/st-score-editor-core.runtime.js",
                "fixture.js",
                "application/read-adapter.js",
                "application/edit-intent-adapter.js",
                "application/application-state.js",
                "application/local-application.js",
                "application/score-editor-core-bridge.js",
                "vendor/renderer-profile.js",
                "application/score-editor-osmd-host.js",
                "app.js",
                "edit-intent.js",
            ]
            positions = [index.index(marker) for marker in ordered]
            self.assertEqual(positions, sorted(positions))
            self.assertLess(index.index("fixture.js"), index.index("application/local-application.js"))

            profile = (first / "vendor" / "renderer-profile.js").read_text(encoding="utf-8")
            self.assertIn('"packageVersion":"2.1.1"', profile)
            self.assertIn('"networkUseAllowed":false', profile)
            self.assertIn('"coordinatesAuthoritative":false', profile)
            notice = (first / "PREVIEW-NOTICE.txt").read_text(encoding="utf-8")
            self.assertIn("Local ST Score Editor Core + OSMD rendering only", notice)
            self.assertIn("No live score source", notice)

    def test_builder_rejects_corrupt_core_integrity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inputs = make_build_inputs(root / "deps")
            manifest = json.loads(inputs["core_manifest"].read_text(encoding="utf-8"))
            manifest["sha256"] = "0" * 64
            inputs["core_manifest"].write_text(json.dumps(manifest), encoding="utf-8")
            output = root / "site"
            result = subprocess.run(builder_command(output, inputs), cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(0, result.returncode)
            self.assertFalse(output.exists())
            self.assertIn("SHA-256 mismatch", result.stderr)

    def test_builder_rejects_wrong_osmd_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inputs = make_build_inputs(root / "deps")
            package = json.loads(inputs["osmd_package_json"].read_text(encoding="utf-8"))
            package["version"] = "9.9.9"
            inputs["osmd_package_json"].write_text(json.dumps(package), encoding="utf-8")
            output = root / "site"
            result = subprocess.run(builder_command(output, inputs), cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(0, result.returncode)
            self.assertFalse(output.exists())
            self.assertIn("OSMD package version mismatch", result.stderr)

    def test_builder_never_overwrites_or_deletes_existing_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inputs = make_build_inputs(root / "deps")
            output = root / "site"
            output.mkdir()
            sentinel = output / "keep-me.txt"
            sentinel.write_text("user-owned", encoding="utf-8")
            result = subprocess.run(builder_command(output, inputs), cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(0, result.returncode)
            self.assertEqual("user-owned", sentinel.read_text(encoding="utf-8"))
            self.assertEqual({"keep-me.txt"}, {path.name for path in output.iterdir()})

    def test_builder_refuses_output_inside_repository(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            inputs = make_build_inputs(Path(tmp) / "deps")
            output = ROOT / ".web-preview-v1-unsafe-test-output"
            self.assertFalse(output.exists(), "reserved regression-test path unexpectedly exists")
            result = subprocess.run(builder_command(output, inputs), cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(0, result.returncode)
            self.assertFalse(output.exists())

    def test_generated_first_party_preview_contains_no_network_or_persistence_calls(self) -> None:
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
            root = Path(tmp)
            inputs = make_build_inputs(root / "deps")
            output = root / "site"
            subprocess.run(builder_command(output, inputs), cwd=ROOT, check=True)
            for path in output.rglob("*"):
                if not path.is_file() or path.suffix not in {".html", ".js", ".css"}:
                    continue
                if path.relative_to(output).parts[0] == "vendor":
                    continue
                text = path.read_text(encoding="utf-8")
                for token in forbidden:
                    self.assertNotIn(token, text, f"{token} in {path.relative_to(output)}")

    def test_artifact_ci_remains_non_deploying_and_builds_exact_local_inputs(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("actions/upload-artifact@", text)
        self.assertIn("scoremosaic-web-preview-v1", text)
        self.assertIn("CORE_COMMIT: b317abef915d1e16b37572221a38feb3e504450d", text)
        self.assertIn("OSMD_VERSION: 2.1.1", text)
        self.assertIn('opensheetmusicdisplay@$OSMD_VERSION', text)
        self.assertIn("--core-bundle", text)
        self.assertIn("--osmd-bundle", text)
        self.assertNotIn("actions/deploy-pages@", text)
        self.assertNotIn("actions/configure-pages@", text)
        self.assertNotIn("pages: write", text)
        self.assertNotIn("id-token: write", text)
        self.assertNotIn("environment:", text)
        self.assertIn("contents: read", text)


if __name__ == "__main__":
    unittest.main()
