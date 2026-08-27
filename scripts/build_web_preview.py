from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import tempfile


ROOT = Path(__file__).resolve().parents[1]
UI_SOURCE = ROOT / "prototypes" / "stage10-ui-application-experience"
APP_SOURCE = ROOT / "prototypes" / "stage11-ui-application-contracts"

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

FORBIDDEN_BROWSER_CAPABILITIES = (
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
"""

PREVIEW_BANNER = (
    '<div class="preview-safety-banner" role="status" aria-label="Preview safety status">'
    '<strong>Non-production preview</strong><span>Fixture data only · No API · No persistence</span>'
    '</div>'
)


def _read(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(path)
    return path.read_text(encoding="utf-8")


def _validate_source_html(html: str) -> None:
    for directive in REQUIRED_CSP_DIRECTIVES:
        if directive not in html:
            raise ValueError(f"required CSP directive missing: {directive}")
    if "https://" in html or "http://" in html:
        raise ValueError("preview source HTML must not reference external HTTP resources")


def _validate_generated_tree(output: Path) -> None:
    index = _read(output / "index.html")
    for directive in REQUIRED_CSP_DIRECTIVES:
        if directive not in index:
            raise ValueError(f"generated preview lost CSP directive: {directive}")
    if "../stage11-ui-application-contracts/" in index:
        raise ValueError("generated preview still escapes its artifact root")
    if "Non-production preview" not in index or "Fixture data only" not in index:
        raise ValueError("generated preview is missing visible safety markers")
    if 'application/score-editor-core-bridge.js' not in index:
        raise ValueError("generated preview is missing the fail-closed Score Editor Core bridge")

    for path in sorted(output.rglob("*")):
        if not path.is_file() or path.suffix not in {".html", ".js", ".css"}:
            continue
        text = path.read_text(encoding="utf-8")
        if "https://" in text or "http://" in text:
            raise ValueError(f"external HTTP reference in {path.relative_to(output)}")
        for token in FORBIDDEN_BROWSER_CAPABILITIES:
            if token in text:
                raise ValueError(f"forbidden browser capability {token!r} in {path.relative_to(output)}")


def _validate_output_target(output: Path) -> None:
    if output.exists() or output.is_symlink():
        raise ValueError("preview output path must not already exist; builder never deletes or overwrites")
    if output == ROOT or ROOT in output.parents:
        raise ValueError("preview output must be outside the repository tree")
    if not output.parent.is_dir():
        raise ValueError("preview output parent directory must already exist")


def _populate(output: Path) -> None:
    application = output / "application"
    application.mkdir()

    for name in UI_FILES:
        if name == "index.html":
            continue
        shutil.copyfile(UI_SOURCE / name, output / name)

    for name in APP_FILES:
        shutil.copyfile(APP_SOURCE / name, application / name)

    source_html = _read(UI_SOURCE / "index.html")
    html = source_html.replace(
        "../stage11-ui-application-contracts/",
        "application/",
    )
    bridge_script = '  <script src="application/score-editor-core-bridge.js" defer></script>\n'
    local_script = '  <script src="application/local-application.js" defer></script>\n'
    if local_script not in html:
        raise ValueError("local application script marker missing from preview source")
    html = html.replace(local_script, local_script + bridge_script, 1)
    html = html.replace(
        '<link rel="stylesheet" href="accessibility.css">',
        '<link rel="stylesheet" href="accessibility.css">\n  <link rel="stylesheet" href="preview.css">',
        1,
    )
    html = html.replace("<body>", f"<body>\n  {PREVIEW_BANNER}", 1)
    (output / "index.html").write_text(html, encoding="utf-8")
    (output / "preview.css").write_text(PREVIEW_STYLES, encoding="utf-8")
    (output / ".nojekyll").write_text("", encoding="utf-8")
    (output / "PREVIEW-NOTICE.txt").write_text(
        "ScoreMosaic Web Preview v1\n"
        "NON-PRODUCTION / FIXTURE DATA ONLY\n"
        "No network, authentication, persistence, upload, approval, publication, or production authority.\n"
        "ST Score Editor Core bridge is present but the core runtime is intentionally not bundled.\n",
        encoding="utf-8",
    )


def build(output: Path) -> None:
    output = output.resolve()
    _validate_output_target(output)
    source_html = _read(UI_SOURCE / "index.html")
    _validate_source_html(source_html)

    temp = Path(tempfile.mkdtemp(prefix=f".{output.name}.build-", dir=output.parent))
    try:
        _populate(temp)
        _validate_generated_tree(temp)
        temp.rename(output)
    finally:
        if temp.exists():
            shutil.rmtree(temp)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the disconnected ScoreMosaic Web Preview v1 artifact")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    build(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
