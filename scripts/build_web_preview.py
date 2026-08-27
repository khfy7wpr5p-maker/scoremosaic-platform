from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile


ROOT = Path(__file__).resolve().parents[1]
UI_SOURCE = ROOT / "prototypes" / "stage10-ui-application-experience"
APP_SOURCE = ROOT / "prototypes" / "stage11-ui-application-contracts"

CORE_BUNDLE_CONTRACT = "ST_SCORE_EDITOR_CORE_BROWSER_BUNDLE"
CORE_RUNTIME_VERSION = "1.0.0"
OSMD_PACKAGE = "opensheetmusicdisplay"
OSMD_VERSION = "2.1.1"
OSMD_LICENSE = "BSD-3-Clause"

UI_FILES = (
    "index.html",
    "styles.css",
    "accessibility.css",
    "edit-intent.css",
    "fixture.js",
    "app.js",
    "edit-intent.js",
)
APP_FILES = (
    "read-adapter.js",
    "edit-intent-adapter.js",
    "application-state.js",
    "local-application.js",
    "score-editor-core-bridge.js",
    "score-editor-osmd-host.js",
)

REQUIRED_CSP_DIRECTIVES = (
    "default-src 'none'",
    "style-src 'self'",
    "img-src 'self' data:",
    "connect-src 'none'",
    "script-src 'self'",
    "object-src 'none'",
    "frame-src 'none'",
    "base-uri 'none'",
    "form-action 'none'",
)

FORBIDDEN_FIRST_PARTY_BROWSER_CAPABILITIES = (
    "fetch(",
    "XMLHttpRequest",
    "WebSocket",
    "EventSource",
    "navigator.sendBeacon",
    "localStorage",
    "sessionStorage",
    "indexedDB",
    "document.cookie",
)

CORE_FORBIDDEN_CAPABILITY_TOKENS = (
    "node:",
    "XMLHttpRequest",
    "WebSocket",
    "EventSource",
    "navigator.sendBeacon",
    "localStorage",
    "sessionStorage",
    "indexedDB",
    "document.cookie",
)

PREVIEW_STYLES = """\
.preview-safety-banner {
  display: flex;
  justify-content: center;
  gap: 0.55rem;
  padding: 0.55rem 1rem;
  border-bottom: 1px solid #c4d0dc;
  background: #fff6df;
  color: #10243e;
  font: 700 0.78rem/1.2 Inter, system-ui, sans-serif;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.preview-safety-banner strong {
  color: #a03945;
}
.score-render-host {
  width: 100%;
  min-height: 24rem;
  padding: 1rem;
  background: #ffffff;
  box-sizing: border-box;
  overflow-x: auto;
}
.score-render-host[hidden] {
  display: none;
}
"""

PREVIEW_BANNER = (
    '<div class="preview-safety-banner" role="status" aria-label="Preview safety status">'
    '<strong>Non-production preview</strong><span>Fixture data only · Local renderer · No API · No persistence</span>'
    '</div>'
)


def _read(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(path)
    return path.read_text(encoding="utf-8")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _validate_source_html(html: str) -> None:
    for directive in REQUIRED_CSP_DIRECTIVES:
        if directive not in html:
            raise ValueError(f"required CSP directive missing: {directive}")
    if "https://" in html or "http://" in html:
        raise ValueError("preview source HTML must not reference external HTTP resources")
    if "score-render-host" in html or "ScoreMosaicRendererProfile" in html:
        raise ValueError("source prototype must remain the renderer-independent fallback")


def _validate_output_target(output: Path) -> None:
    if output.exists() or output.is_symlink():
        raise ValueError("preview output path must not already exist; builder never deletes or overwrites")
    if output == ROOT or ROOT in output.parents:
        raise ValueError("preview output must be outside the repository tree")
    if not output.parent.is_dir():
        raise ValueError("preview output parent directory must already exist")


def _validate_core_artifacts(bundle_path: Path, manifest_path: Path) -> tuple[bytes, dict[str, object]]:
    bundle = bundle_path.read_bytes()
    manifest = json.loads(_read(manifest_path))
    required = {
        "contract": CORE_BUNDLE_CONTRACT,
        "version": "1.0.0",
        "runtimeVersion": CORE_RUNTIME_VERSION,
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
    }
    for key, expected in required.items():
        if manifest.get(key) != expected:
            raise ValueError(f"core bundle manifest mismatch for {key}: {manifest.get(key)!r}")
    bundler = manifest.get("bundler")
    if bundler != {"package": "esbuild", "version": "0.28.2", "license": "MIT"}:
        raise ValueError("core bundle bundler identity mismatch")
    if manifest.get("bytes") != len(bundle):
        raise ValueError("core bundle byte length mismatch")
    if manifest.get("sha256") != _sha256_bytes(bundle):
        raise ValueError("core bundle SHA-256 mismatch")
    text = bundle.decode("utf-8")
    if "STScoreEditorCoreRuntime" not in text:
        raise ValueError("core bundle global marker missing")
    for token in CORE_FORBIDDEN_CAPABILITY_TOKENS:
        if token in text:
            raise ValueError(f"core bundle contains forbidden capability token {token!r}")
    return bundle, manifest


def _validate_osmd_artifacts(bundle_path: Path, package_json_path: Path, license_path: Path) -> tuple[bytes, dict[str, object], str]:
    bundle = bundle_path.read_bytes()
    package = json.loads(_read(package_json_path))
    if package.get("name") != OSMD_PACKAGE:
        raise ValueError("OSMD package name mismatch")
    if package.get("version") != OSMD_VERSION:
        raise ValueError("OSMD package version mismatch")
    if package.get("license") != OSMD_LICENSE:
        raise ValueError("OSMD package license mismatch")
    if package.get("main") != "build/opensheetmusicdisplay.min.js":
        raise ValueError("OSMD package main entry mismatch")
    expected_bundle = (package_json_path.parent / str(package["main"])).resolve()
    if expected_bundle != bundle_path.resolve():
        raise ValueError("OSMD bundle is not the verified package main artifact")
    license_text = _read(license_path)
    if len(license_text.strip()) < 40:
        raise ValueError("OSMD license text is missing or unexpectedly short")
    if len(bundle) == 0:
        raise ValueError("OSMD bundle is empty")
    return bundle, package, license_text


def _renderer_profile(bundle: bytes) -> dict[str, object]:
    return {
        "contract": "SCOREMOSAIC_LOCAL_RENDERER_PROFILE",
        "version": "1.0.0",
        "family": "osmd",
        "packageName": OSMD_PACKAGE,
        "packageVersion": OSMD_VERSION,
        "license": OSMD_LICENSE,
        "artifact": f"opensheetmusicdisplay-{OSMD_VERSION}.min.js",
        "artifactBytes": len(bundle),
        "artifactSha256": _sha256_bytes(bundle),
        "presentationOnly": True,
        "coordinatesAuthoritative": False,
        "domIdsAuthoritative": False,
        "rendererObjectsAuthoritative": False,
        "networkUseAllowed": False,
        "cspConnectSrcNoneRequired": True,
        "persistent": False,
    }


def _renderer_profile_script(profile: dict[str, object]) -> str:
    payload = json.dumps(profile, sort_keys=True, separators=(",", ":"))
    return (
        "(() => { 'use strict'; const profile = Object.freeze("
        + payload
        + "); if (Object.prototype.hasOwnProperty.call(window, 'ScoreMosaicRendererProfile')) "
        "throw new Error('SCOREMOSAIC_RENDERER_PROFILE_ALREADY_DEFINED'); "
        "Object.defineProperty(window, 'ScoreMosaicRendererProfile', {value: profile, writable: false, configurable: false, enumerable: true}); })();\n"
    )


def _inject_renderer_html(source_html: str) -> str:
    html = source_html.replace("../stage11-ui-application-contracts/", "application/")
    html = html.replace(
        '<link rel="stylesheet" href="accessibility.css">',
        '<link rel="stylesheet" href="accessibility.css">\n  <link rel="stylesheet" href="preview.css">',
        1,
    )
    html = html.replace("<body>", f"<body>\n  {PREVIEW_BANNER}", 1)
    html = html.replace(
        '<div class="page-stack">',
        '<div id="score-render-host" class="score-render-host" hidden aria-label="Rendered fixture score"></div>\n        <div class="page-stack" id="score-fixture-fallback">',
        1,
    )
    html = html.replace(
        '<script src="application/read-adapter.js"></script>',
        '<script src="vendor/opensheetmusicdisplay-2.1.1.min.js"></script>\n'
        '  <script src="vendor/st-score-editor-core.runtime.js"></script>\n'
        '  <script src="application/read-adapter.js"></script>',
        1,
    )
    html = html.replace(
        '<script src="fixture.js"></script>',
        '<script src="fixture.js"></script>\n'
        '  <script src="application/score-editor-core-bridge.js"></script>\n'
        '  <script src="vendor/renderer-profile.js"></script>\n'
        '  <script src="application/score-editor-osmd-host.js"></script>',
        1,
    )
    return html


def _validate_script_order(index: str) -> None:
    scripts = (
        'vendor/opensheetmusicdisplay-2.1.1.min.js',
        'vendor/st-score-editor-core.runtime.js',
        'application/read-adapter.js',
        'application/edit-intent-adapter.js',
        'application/application-state.js',
        'application/local-application.js',
        'fixture.js',
        'application/score-editor-core-bridge.js',
        'vendor/renderer-profile.js',
        'application/score-editor-osmd-host.js',
        'app.js',
        'edit-intent.js',
    )
    positions = []
    for script in scripts:
        marker = f'src="{script}"'
        if index.count(marker) != 1:
            raise ValueError(f"expected exactly one generated script reference: {script}")
        positions.append(index.index(marker))
    if positions != sorted(positions):
        raise ValueError("generated renderer/application script order is invalid")


def _validate_generated_tree(output: Path) -> None:
    index = _read(output / "index.html")
    for directive in REQUIRED_CSP_DIRECTIVES:
        if directive not in index:
            raise ValueError(f"generated preview lost CSP directive: {directive}")
    if "../stage11-ui-application-contracts/" in index:
        raise ValueError("generated preview still escapes its artifact root")
    if "Non-production preview" not in index or "Fixture data only" not in index:
        raise ValueError("generated preview is missing visible safety markers")
    if 'id="score-render-host"' not in index or 'id="score-fixture-fallback"' not in index:
        raise ValueError("generated preview is missing renderer/fallback score surfaces")
    _validate_script_order(index)

    for path in sorted(output.rglob("*")):
        if not path.is_file() or path.suffix not in {".html", ".js", ".css"}:
            continue
        relative = path.relative_to(output)
        if relative.parts and relative.parts[0] == "vendor":
            continue
        text = path.read_text(encoding="utf-8")
        if "https://" in text or "http://" in text:
            raise ValueError(f"external HTTP reference in {relative}")
        for token in FORBIDDEN_FIRST_PARTY_BROWSER_CAPABILITIES:
            if token in text:
                raise ValueError(f"forbidden first-party browser capability {token!r} in {relative}")


def _populate(
    output: Path,
    core_bundle: bytes,
    core_manifest: dict[str, object],
    osmd_bundle: bytes,
    osmd_license: str,
) -> None:
    application = output / "application"
    vendor = output / "vendor"
    application.mkdir()
    vendor.mkdir()

    for name in UI_FILES:
        if name == "index.html":
            continue
        shutil.copyfile(UI_SOURCE / name, output / name)

    for name in APP_FILES:
        shutil.copyfile(APP_SOURCE / name, application / name)

    source_html = _read(UI_SOURCE / "index.html")
    html = _inject_renderer_html(source_html)
    (output / "index.html").write_text(html, encoding="utf-8")
    (output / "preview.css").write_text(PREVIEW_STYLES, encoding="utf-8")
    (output / ".nojekyll").write_text("", encoding="utf-8")
    (output / "PREVIEW-NOTICE.txt").write_text(
        "ScoreMosaic Web Preview v1\n"
        "NON-PRODUCTION / FIXTURE DATA ONLY\n"
        "Local ST Score Editor Core + OSMD rendering only. No live score source, network API, authentication, persistence, upload, approval, publication, or production authority.\n",
        encoding="utf-8",
    )

    (vendor / "st-score-editor-core.runtime.js").write_bytes(core_bundle)
    (vendor / "st-score-editor-core.runtime.manifest.json").write_text(
        f"{json.dumps(core_manifest, indent=2, sort_keys=True)}\n", encoding="utf-8"
    )
    (vendor / f"opensheetmusicdisplay-{OSMD_VERSION}.min.js").write_bytes(osmd_bundle)
    (vendor / "OSMD-LICENSE.txt").write_text(osmd_license, encoding="utf-8")
    (vendor / "renderer-profile.js").write_text(
        _renderer_profile_script(_renderer_profile(osmd_bundle)), encoding="utf-8"
    )


def build(
    output: Path,
    core_bundle_path: Path,
    core_manifest_path: Path,
    osmd_bundle_path: Path,
    osmd_package_json_path: Path,
    osmd_license_path: Path,
) -> None:
    output = output.resolve()
    _validate_output_target(output)
    source_html = _read(UI_SOURCE / "index.html")
    _validate_source_html(source_html)
    core_bundle, core_manifest = _validate_core_artifacts(core_bundle_path, core_manifest_path)
    osmd_bundle, _, osmd_license = _validate_osmd_artifacts(
        osmd_bundle_path, osmd_package_json_path, osmd_license_path
    )

    temp = Path(tempfile.mkdtemp(prefix=f".{output.name}.build-", dir=output.parent))
    try:
        _populate(temp, core_bundle, core_manifest, osmd_bundle, osmd_license)
        _validate_generated_tree(temp)
        temp.rename(output)
    finally:
        if temp.exists():
            shutil.rmtree(temp)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the disconnected ScoreMosaic Web Preview v1 artifact")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--core-bundle", required=True, type=Path)
    parser.add_argument("--core-manifest", required=True, type=Path)
    parser.add_argument("--osmd-bundle", required=True, type=Path)
    parser.add_argument("--osmd-package-json", required=True, type=Path)
    parser.add_argument("--osmd-license", required=True, type=Path)
    args = parser.parse_args()
    build(
        args.output,
        args.core_bundle.resolve(),
        args.core_manifest.resolve(),
        args.osmd_bundle.resolve(),
        args.osmd_package_json.resolve(),
        args.osmd_license.resolve(),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
