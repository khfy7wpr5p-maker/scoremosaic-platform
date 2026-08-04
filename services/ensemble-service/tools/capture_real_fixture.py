"""Safe, deterministic capture of real-engine MusicXML fixtures for 10B validation."""

from __future__ import annotations

from argparse import ArgumentParser
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
import re
import stat
import xml.etree.ElementTree as ET
import zipfile

CAPTURE_FORMAT_VERSION = "0.1-foundation"
MAX_ARTIFACT_BYTES = 128 * 1024 * 1024
MAX_XML_BYTES = 64 * 1024 * 1024
MAX_ZIP_ENTRIES = 128
MAX_TOTAL_UNCOMPRESSED_BYTES = 128 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_ENGINES = frozenset({"audiveris", "homr", "clarity"})
_MUSICXML_DOCTYPE_RE = re.compile(
    rb"""
    <!DOCTYPE\s+
    (?P<root>score-partwise|score-timewise)\s+
    PUBLIC\s+
    (?P<public_quote>["'])
    -//Recordare//DTD\s+MusicXML\s+\d+(?:\.\d+)*\s+
    (?P<form>Partwise|Timewise)//EN
    (?P=public_quote)\s+
    (?P<system_quote>["'])
    https?://(?:www\.)?musicxml\.org/dtds/
    (?P<dtd>partwise|timewise)\.dtd
    (?P=system_quote)\s*>
    """,
    re.IGNORECASE | re.VERBOSE,
)


class FixtureCaptureError(ValueError):
    """Raised when a real-engine fixture cannot be captured safely."""


def _digest(document: bytes) -> str:
    return sha256(document).hexdigest()


def _read_bounded(path: Path, maximum: int) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise FixtureCaptureError("input artifact must be a regular non-symlink file")
    size = path.stat().st_size
    if size <= 0 or size > maximum:
        raise FixtureCaptureError("input artifact size is outside the supported range")
    with path.open("rb") as stream:
        document = stream.read(maximum + 1)
    if len(document) > maximum:
        raise FixtureCaptureError("input artifact exceeded the read limit")
    return document


def _safe_member_name(name: str) -> PurePosixPath:
    if not name or len(name) > 1000 or "\\" in name or "\x00" in name:
        raise FixtureCaptureError("unsafe MXL member name")
    member = PurePosixPath(name)
    if member.is_absolute() or any(part in {"", ".", ".."} for part in member.parts):
        raise FixtureCaptureError("unsafe MXL member path")
    return member


def _validate_zip_entries(archive: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    entries = archive.infolist()
    if not entries or len(entries) > MAX_ZIP_ENTRIES:
        raise FixtureCaptureError("MXL entry count is outside the supported range")

    total = 0
    validated: dict[str, zipfile.ZipInfo] = {}
    for info in entries:
        member = _safe_member_name(info.filename)
        if info.flag_bits & 0x1:
            raise FixtureCaptureError("encrypted MXL entries are not allowed")
        mode = info.external_attr >> 16
        if mode and stat.S_ISLNK(mode):
            raise FixtureCaptureError("symbolic-link MXL entries are not allowed")
        if info.file_size < 0 or info.file_size > MAX_XML_BYTES:
            raise FixtureCaptureError("MXL entry size is outside the supported range")
        total += info.file_size
        if total > MAX_TOTAL_UNCOMPRESSED_BYTES:
            raise FixtureCaptureError("MXL uncompressed size limit exceeded")
        if info.file_size and info.compress_size == 0:
            raise FixtureCaptureError("invalid MXL compression metadata")
        if (
            info.compress_size
            and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO
        ):
            raise FixtureCaptureError("MXL compression ratio limit exceeded")
        key = member.as_posix()
        if key in validated:
            raise FixtureCaptureError("duplicate MXL member")
        validated[key] = info
    return validated


def _read_zip_member(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    maximum: int,
) -> bytes:
    if info.file_size > maximum:
        raise FixtureCaptureError("MXL member exceeds the supported size")
    with archive.open(info, "r") as stream:
        document = stream.read(maximum + 1)
    if len(document) > maximum:
        raise FixtureCaptureError("MXL member exceeded the read limit")
    return document


def _reject_declarations(document: bytes, *, allow_canonical_doctype: bool) -> None:
    upper = document.upper()
    if b"<!ENTITY" in upper:
        raise FixtureCaptureError("entity declarations are not allowed")
    if not allow_canonical_doctype and b"<!DOCTYPE" in upper:
        raise FixtureCaptureError("DTD declarations are not allowed")


def _extract_mxl(document: bytes) -> bytes:
    try:
        archive = zipfile.ZipFile(BytesIO(document))
    except zipfile.BadZipFile as exc:
        raise FixtureCaptureError("invalid MXL container") from exc

    with archive:
        entries = _validate_zip_entries(archive)
        container_info = entries.get("META-INF/container.xml")
        if container_info is None:
            raise FixtureCaptureError("MXL container.xml is missing")
        container_document = _read_zip_member(archive, container_info, 1024 * 1024)
        _reject_declarations(container_document, allow_canonical_doctype=False)
        try:
            container_root = ET.fromstring(container_document)
        except ET.ParseError as exc:
            raise FixtureCaptureError("invalid MXL container.xml") from exc

        rootfiles = [
            element
            for element in container_root.iter()
            if element.tag.rsplit("}", 1)[-1] == "rootfile"
        ]
        if len(rootfiles) != 1:
            raise FixtureCaptureError("MXL must declare exactly one rootfile")
        full_path = rootfiles[0].get("full-path", "")
        root_path = _safe_member_name(full_path).as_posix()
        if not root_path.lower().endswith((".xml", ".musicxml")):
            raise FixtureCaptureError("MXL rootfile must be MusicXML")
        root_info = entries.get(root_path)
        if root_info is None:
            raise FixtureCaptureError("MXL rootfile is missing")
        return _read_zip_member(archive, root_info, MAX_XML_BYTES)


def _sanitize_musicxml(document: bytes) -> tuple[bytes, bool]:
    upper = document.upper()
    if b"<!ENTITY" in upper:
        raise FixtureCaptureError("entity declarations are not allowed")

    doctype_index = upper.find(b"<!DOCTYPE")
    if doctype_index < 0:
        sanitized = document
        removed = False
    else:
        if upper.find(b"<!DOCTYPE", doctype_index + 1) >= 0 or doctype_index > 8192:
            raise FixtureCaptureError("noncanonical MusicXML DTD declaration")
        match = _MUSICXML_DOCTYPE_RE.search(document)
        if match is None or match.start() != doctype_index:
            raise FixtureCaptureError("noncanonical MusicXML DTD declaration")
        root_name = match.group("root").lower()
        form = match.group("form").lower()
        dtd = match.group("dtd").lower()
        expected = b"partwise" if root_name == b"score-partwise" else b"timewise"
        if form != expected or dtd != expected:
            raise FixtureCaptureError("mismatched MusicXML DTD declaration")
        sanitized = document[: match.start()] + document[match.end() :]
        removed = True

    sanitized_upper = sanitized.upper()
    if b"<!DOCTYPE" in sanitized_upper or b"<!ENTITY" in sanitized_upper:
        raise FixtureCaptureError("unsafe XML declaration remained after capture")
    if not sanitized or len(sanitized) > MAX_XML_BYTES:
        raise FixtureCaptureError("captured MusicXML size is outside the supported range")
    try:
        root = ET.fromstring(sanitized)
    except ET.ParseError as exc:
        raise FixtureCaptureError("captured MusicXML is not well-formed XML") from exc
    if root.tag.rsplit("}", 1)[-1] != "score-partwise":
        raise FixtureCaptureError(
            "only score-partwise MusicXML can become a Canonical fixture"
        )
    return sanitized, removed


def capture_fixture(
    input_path: Path,
    output_path: Path,
    metadata_path: Path,
    *,
    engine: str,
    engine_version: str,
    model_version: str,
    source_fixture_sha256: str,
) -> dict[str, object]:
    """Capture one real engine artifact without changing its musical content."""

    if engine not in _ALLOWED_ENGINES:
        raise FixtureCaptureError("unsupported engine")
    if not engine_version or len(engine_version) > 200:
        raise FixtureCaptureError("engine version is invalid")
    if not model_version or len(model_version) > 200:
        raise FixtureCaptureError("model version is invalid")
    if not _HEX_64.fullmatch(source_fixture_sha256):
        raise FixtureCaptureError("source fixture SHA-256 is invalid")
    if output_path == metadata_path:
        raise FixtureCaptureError("output and metadata paths must differ")
    for destination in (output_path, metadata_path):
        if destination.exists() or destination.is_symlink():
            raise FixtureCaptureError("capture destination must not already exist")
        destination.parent.mkdir(parents=True, exist_ok=True)

    artifact = _read_bounded(input_path, MAX_ARTIFACT_BYTES)
    is_archive = zipfile.is_zipfile(BytesIO(artifact))
    extracted = _extract_mxl(artifact) if is_archive else artifact
    captured, doctype_removed = _sanitize_musicxml(extracted)

    metadata: dict[str, object] = {
        "captureFormatVersion": CAPTURE_FORMAT_VERSION,
        "engine": engine,
        "engineVersion": engine_version,
        "modelVersion": model_version,
        "sourceFixtureSha256": source_fixture_sha256,
        "inputArtifactSha256": _digest(artifact),
        "extractedMusicXmlSha256": _digest(extracted),
        "capturedMusicXmlSha256": _digest(captured),
        "canonicalDoctypeRemoved": doctype_removed,
        "containerFormat": "mxl" if is_archive else "xml",
        "rootType": "score-partwise",
    }

    with output_path.open("xb") as stream:
        stream.write(captured)
    with metadata_path.open("x", encoding="utf-8") as stream:
        stream.write(
            json.dumps(metadata, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        )
    return metadata


def _parser() -> ArgumentParser:
    parser = ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--engine", required=True, choices=sorted(_ALLOWED_ENGINES))
    parser.add_argument("--engine-version", required=True)
    parser.add_argument("--model-version", required=True)
    parser.add_argument("--source-fixture-sha256", required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    capture_fixture(
        args.input,
        args.output,
        args.metadata,
        engine=args.engine,
        engine_version=args.engine_version,
        model_version=args.model_version,
        source_fixture_sha256=args.source_fixture_sha256,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
