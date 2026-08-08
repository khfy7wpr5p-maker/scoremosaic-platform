"""Fail-closed MusicXML/MXL candidate validation shared by OMR adapters."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path, PurePosixPath
import re
import stat
import xml.etree.ElementTree as ET
from xml.parsers import expat
import zipfile

MAX_ARTIFACT_BYTES = 128 * 1024 * 1024
MAX_XML_BYTES = 64 * 1024 * 1024
MAX_ZIP_ENTRIES = 128
MAX_TOTAL_UNCOMPRESSED_BYTES = 128 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200
MAX_XML_DEPTH = 64
MAX_XML_ELEMENTS = 500_000
MAX_XML_ATTRIBUTES = 1_000_000
MAX_ATTRIBUTES_PER_ELEMENT = 256
MAX_CONTAINER_XML_BYTES = 1024 * 1024

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


class CandidateSafetyError(ValueError):
    """Raised when an engine-produced candidate violates the safety boundary."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class CandidateSafetyResult:
    container_format: str
    root_type: str
    xml_bytes: int


def _fail(code: str) -> None:
    raise CandidateSafetyError(code)


def _read_bounded_file(path: Path, maximum: int) -> bytes:
    if path.is_symlink() or not path.is_file():
        _fail("artifact_not_regular_file")
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise CandidateSafetyError("artifact_stat_failed") from exc
    if size <= 0 or size > maximum:
        _fail("artifact_size_invalid")
    try:
        with path.open("rb") as stream:
            document = stream.read(maximum + 1)
    except OSError as exc:
        raise CandidateSafetyError("artifact_read_failed") from exc
    if len(document) > maximum:
        _fail("artifact_read_limit_exceeded")
    return document


def _safe_member_name(name: str) -> PurePosixPath:
    if not name or len(name) > 1000 or "\\" in name or "\x00" in name:
        _fail("mxl_member_name_unsafe")
    member = PurePosixPath(name)
    if member.is_absolute() or any(part in {"", ".", ".."} for part in member.parts):
        _fail("mxl_member_path_unsafe")
    return member


def _validate_zip_entries(archive: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    entries = archive.infolist()
    if not entries or len(entries) > MAX_ZIP_ENTRIES:
        _fail("mxl_entry_count_invalid")

    total = 0
    validated: dict[str, zipfile.ZipInfo] = {}
    for info in entries:
        member = _safe_member_name(info.filename)
        if info.flag_bits & 0x1:
            _fail("mxl_encrypted_entry")
        mode = info.external_attr >> 16
        if mode and stat.S_ISLNK(mode):
            _fail("mxl_symlink_entry")
        if info.file_size < 0 or info.file_size > MAX_XML_BYTES:
            _fail("mxl_entry_size_invalid")
        total += info.file_size
        if total > MAX_TOTAL_UNCOMPRESSED_BYTES:
            _fail("mxl_uncompressed_size_exceeded")
        if info.file_size and info.compress_size == 0:
            _fail("mxl_compression_metadata_invalid")
        if info.compress_size and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
            _fail("mxl_compression_ratio_exceeded")
        key = member.as_posix()
        if key in validated:
            _fail("mxl_duplicate_member")
        validated[key] = info
    return validated


def _read_zip_member(archive: zipfile.ZipFile, info: zipfile.ZipInfo, maximum: int) -> bytes:
    if info.file_size > maximum:
        _fail("mxl_member_size_exceeded")
    try:
        with archive.open(info, "r") as stream:
            document = stream.read(maximum + 1)
    except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
        raise CandidateSafetyError("mxl_member_read_failed") from exc
    if len(document) > maximum:
        _fail("mxl_member_read_limit_exceeded")
    return document


def _reject_container_declarations(document: bytes) -> None:
    upper = document.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        _fail("mxl_container_unsafe_declaration")


def _sanitize_musicxml(document: bytes) -> bytes:
    if not document or len(document) > MAX_XML_BYTES:
        _fail("musicxml_size_invalid")
    if b"\x00" in document:
        _fail("musicxml_nul_byte")

    upper = document.upper()
    if b"<!ENTITY" in upper:
        _fail("musicxml_unsafe_declaration")

    doctype_index = upper.find(b"<!DOCTYPE")
    if doctype_index < 0:
        return document
    if upper.find(b"<!DOCTYPE", doctype_index + 1) >= 0 or doctype_index > 8192:
        _fail("musicxml_unsafe_declaration")

    match = _MUSICXML_DOCTYPE_RE.search(document)
    if match is None or match.start() != doctype_index:
        _fail("musicxml_unsafe_declaration")

    root_name = match.group("root").lower()
    form = match.group("form").lower()
    dtd = match.group("dtd").lower()
    expected = b"partwise" if root_name == b"score-partwise" else b"timewise"
    if form != expected or dtd != expected:
        _fail("musicxml_unsafe_declaration")

    sanitized = document[: match.start()] + document[match.end() :]
    sanitized_upper = sanitized.upper()
    if b"<!DOCTYPE" in sanitized_upper or b"<!ENTITY" in sanitized_upper:
        _fail("musicxml_unsafe_declaration")
    return sanitized


def _validate_musicxml_stream(document: bytes) -> str:
    """Apply structural budgets while parsing, without building an XML tree."""

    parser = expat.ParserCreate(namespace_separator="}")
    depth = 0
    elements = 0
    attributes = 0
    root_type: str | None = None

    def start_element(name: str, attrs: dict[str, str]) -> None:
        nonlocal depth, elements, attributes, root_type

        depth += 1
        if depth > MAX_XML_DEPTH:
            _fail("musicxml_depth_exceeded")

        elements += 1
        if elements > MAX_XML_ELEMENTS:
            _fail("musicxml_element_count_exceeded")

        attribute_count = len(attrs)
        if attribute_count > MAX_ATTRIBUTES_PER_ELEMENT:
            _fail("musicxml_attributes_per_element_exceeded")
        attributes += attribute_count
        if attributes > MAX_XML_ATTRIBUTES:
            _fail("musicxml_attribute_count_exceeded")

        if elements == 1:
            root_type = name.rsplit("}", 1)[-1]
            if root_type not in {"score-partwise", "score-timewise"}:
                _fail("musicxml_invalid_root")

    def end_element(_name: str) -> None:
        nonlocal depth
        depth -= 1

    parser.StartElementHandler = start_element
    parser.EndElementHandler = end_element
    try:
        parser.Parse(document, True)
    except CandidateSafetyError:
        raise
    except expat.ExpatError as exc:
        raise CandidateSafetyError("musicxml_invalid_xml") from exc

    if root_type is None or depth != 0:
        _fail("musicxml_invalid_xml")
    return root_type


def validate_musicxml_bytes(document: bytes) -> CandidateSafetyResult:
    """Validate bounded MusicXML without resolving DTDs or external entities."""

    sanitized = _sanitize_musicxml(document)
    root_type = _validate_musicxml_stream(sanitized)
    return CandidateSafetyResult("xml", root_type, len(sanitized))


def validate_musicxml_file(path: Path) -> CandidateSafetyResult:
    """Validate one regular MusicXML file as an untrusted engine output."""

    document = _read_bounded_file(path, MAX_XML_BYTES)
    return validate_musicxml_bytes(document)


def validate_mxl_file(path: Path) -> CandidateSafetyResult:
    """Validate an MXL archive and its single declared MusicXML rootfile."""

    document = _read_bounded_file(path, MAX_ARTIFACT_BYTES)
    try:
        archive = zipfile.ZipFile(BytesIO(document))
    except zipfile.BadZipFile as exc:
        raise CandidateSafetyError("mxl_invalid_container") from exc

    with archive:
        entries = _validate_zip_entries(archive)
        container_info = entries.get("META-INF/container.xml")
        if container_info is None:
            _fail("mxl_container_missing")
        container_document = _read_zip_member(
            archive, container_info, MAX_CONTAINER_XML_BYTES
        )
        _reject_container_declarations(container_document)
        try:
            container_root = ET.fromstring(container_document)
        except ET.ParseError as exc:
            raise CandidateSafetyError("mxl_container_invalid_xml") from exc

        rootfiles = [
            element
            for element in container_root.iter()
            if element.tag.rsplit("}", 1)[-1] == "rootfile"
        ]
        if len(rootfiles) != 1:
            _fail("mxl_rootfile_count_invalid")
        full_path = rootfiles[0].get("full-path", "")
        root_path = _safe_member_name(full_path).as_posix()
        if not root_path.lower().endswith((".xml", ".musicxml")):
            _fail("mxl_rootfile_type_invalid")
        root_info = entries.get(root_path)
        if root_info is None:
            _fail("mxl_rootfile_missing")
        musicxml = _read_zip_member(archive, root_info, MAX_XML_BYTES)

    result = validate_musicxml_bytes(musicxml)
    return CandidateSafetyResult("mxl", result.root_type, result.xml_bytes)
