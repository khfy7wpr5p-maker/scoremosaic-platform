"""Renderer-independent MusicXML ``direction@system`` semantic gate.

The gate is intentionally narrow. It validates the MusicXML 4.0
``system-relation`` values carried by ``<direction system=\"...\">`` and
provides fail-closed routing for renderer-fidelity mismatches. It does not
validate an entire MusicXML document, mutate source bytes, admit Teacher-Gold
fixtures, or authorize model training / production decisions.
"""

from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import io
import json
from pathlib import Path, PurePosixPath
from typing import Iterable
import xml.etree.ElementTree as ET
import zipfile


MAX_INPUT_BYTES = 32 * 1024 * 1024
MAX_XML_BYTES = 32 * 1024 * 1024
MAX_ZIP_MEMBERS = 512
MAX_XML_ELEMENTS = 500_000
MAX_XML_DEPTH = 64
MAX_DIRECTION_SYSTEM_RECORDS = 20_000

ALLOWED_SYSTEM_RELATIONS = frozenset({"only-top", "also-top", "none"})
RENDERER_SENSITIVE_SYSTEM_RELATIONS = frozenset({"only-top", "also-top"})


class DirectionSystemSemanticGateError(ValueError):
    """Raised when bounded symbolic inspection cannot be completed safely."""


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _safe_zip_member_name(name: str) -> bool:
    path = PurePosixPath(name.replace("\\", "/"))
    return bool(name) and not path.is_absolute() and ".." not in path.parts


def _validate_tree(root: ET.Element) -> None:
    count = 0
    stack: list[tuple[ET.Element, int]] = [(root, 1)]
    while stack:
        element, depth = stack.pop()
        count += 1
        if count > MAX_XML_ELEMENTS:
            raise DirectionSystemSemanticGateError("MusicXML element limit exceeded")
        if depth > MAX_XML_DEPTH:
            raise DirectionSystemSemanticGateError("MusicXML nesting limit exceeded")
        stack.extend((child, depth + 1) for child in element)


def _container_rootfile(zf: zipfile.ZipFile) -> str | None:
    try:
        info = zf.getinfo("META-INF/container.xml")
    except KeyError:
        return None
    if info.file_size > 256 * 1024:
        raise DirectionSystemSemanticGateError("MXL container.xml is outside limits")
    try:
        root = ET.fromstring(zf.read(info))
    except ET.ParseError as exc:
        raise DirectionSystemSemanticGateError("invalid MXL container.xml") from exc
    for element in root.iter():
        if _local_name(element.tag) != "rootfile":
            continue
        full_path = (element.attrib.get("full-path") or "").strip()
        if full_path:
            return full_path
    return None


def _read_mxl_payload(data: bytes) -> tuple[bytes, str]:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise DirectionSystemSemanticGateError("invalid MXL ZIP container") from exc

    with zf:
        infos = zf.infolist()
        if not infos or len(infos) > MAX_ZIP_MEMBERS:
            raise DirectionSystemSemanticGateError("MXL member count is outside limits")
        for info in infos:
            if not _safe_zip_member_name(info.filename):
                raise DirectionSystemSemanticGateError("unsafe MXL member path")
            if info.flag_bits & 0x1:
                raise DirectionSystemSemanticGateError("encrypted MXL members are not supported")
            if info.file_size > MAX_XML_BYTES:
                raise DirectionSystemSemanticGateError("MXL member is outside limits")

        rootfile = _container_rootfile(zf)
        if rootfile is not None:
            if not _safe_zip_member_name(rootfile):
                raise DirectionSystemSemanticGateError("unsafe MXL rootfile path")
            try:
                info = zf.getinfo(rootfile)
            except KeyError as exc:
                raise DirectionSystemSemanticGateError("MXL rootfile is missing") from exc
            payload = zf.read(info)
            if len(payload) > MAX_XML_BYTES:
                raise DirectionSystemSemanticGateError("MusicXML payload is outside limits")
            return payload, rootfile

        candidates = [
            info
            for info in infos
            if not info.is_dir()
            and not info.filename.startswith("META-INF/")
            and info.filename.lower().endswith((".musicxml", ".xml"))
        ]
        if len(candidates) != 1:
            raise DirectionSystemSemanticGateError(
                "MXL rootfile is ambiguous without META-INF/container.xml"
            )
        payload = zf.read(candidates[0])
        if len(payload) > MAX_XML_BYTES:
            raise DirectionSystemSemanticGateError("MusicXML payload is outside limits")
        return payload, candidates[0].filename


def _musicxml_payload(data: bytes) -> tuple[bytes, str]:
    if len(data) > MAX_INPUT_BYTES:
        raise DirectionSystemSemanticGateError("input is outside limits")
    if data.startswith(b"PK\x03\x04"):
        return _read_mxl_payload(data)
    return data, "raw-musicxml"


def _parse_root(data: bytes) -> tuple[ET.Element, str, str]:
    payload, member = _musicxml_payload(data)
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise DirectionSystemSemanticGateError("invalid MusicXML XML") from exc
    _validate_tree(root)
    root_name = _local_name(root.tag)
    if root_name not in {"score-partwise", "score-timewise"}:
        raise DirectionSystemSemanticGateError("unsupported MusicXML root element")
    return root, member, sha256(payload).hexdigest()


def _direction_words(direction: ET.Element) -> str:
    values: list[str] = []
    for element in direction.iter():
        if _local_name(element.tag) != "words":
            continue
        text = "".join(element.itertext()).strip()
        if text:
            values.append(text)
    return " ".join(values)[:1000]


def _collect_direction_system_records(root: ET.Element) -> list[dict[str, str | None]]:
    records: list[dict[str, str | None]] = []

    def walk(
        element: ET.Element,
        *,
        part_id: str | None = None,
        measure_number: str | None = None,
    ) -> None:
        nonlocal records
        name = _local_name(element.tag)
        current_part = part_id
        current_measure = measure_number
        if name == "part":
            value = (element.attrib.get("id") or "").strip()
            current_part = value or part_id
        elif name == "measure":
            value = (element.attrib.get("number") or "").strip()
            current_measure = value or measure_number
        elif name == "direction" and "system" in element.attrib:
            if len(records) >= MAX_DIRECTION_SYSTEM_RECORDS:
                raise DirectionSystemSemanticGateError("direction@system record limit exceeded")
            records.append(
                {
                    "part": current_part,
                    "measure": current_measure,
                    "placement": (element.attrib.get("placement") or "").strip() or None,
                    "system": (element.attrib.get("system") or "").strip(),
                    "text": _direction_words(element) or None,
                }
            )
        for child in element:
            walk(child, part_id=current_part, measure_number=current_measure)

    walk(root)
    return records


def build_report(data: bytes, *, source_name: str = "input") -> dict[str, object]:
    """Inspect one raw MusicXML or MXL byte stream without mutating it."""

    root, member, payload_sha = _parse_root(data)
    records = _collect_direction_system_records(root)
    invalid = sorted({
        str(record["system"])
        for record in records
        if record["system"] not in ALLOWED_SYSTEM_RELATIONS
    })
    counts = Counter(str(record["system"]) for record in records)
    sensitive_count = sum(counts[value] for value in RENDERER_SENSITIVE_SYSTEM_RELATIONS)

    if invalid:
        status = "SEMANTIC_VALIDATION_REVIEW_REQUIRED"
        symbolic_reference_eligible = False
        technical_review_required = True
    elif records:
        status = "VALID_DIRECTION_SYSTEM_SEMANTICS"
        symbolic_reference_eligible = True
        technical_review_required = False
    else:
        status = "NOT_APPLICABLE_NO_DIRECTION_SYSTEM"
        symbolic_reference_eligible = True
        technical_review_required = False

    return {
        "gateVersion": "scoremosaic-musicxml-direction-system-semantic-gate-v1",
        "sourceName": source_name,
        "sourceContainerSha256": sha256(data).hexdigest(),
        "musicXmlPayloadSha256": payload_sha,
        "musicXmlMember": member,
        "musicXmlRoot": _local_name(root.tag),
        "musicXmlVersion": (root.attrib.get("version") or "").strip() or None,
        "status": status,
        "directionSystemRecordCount": len(records),
        "rendererSensitiveDirectionCount": sensitive_count,
        "systemRelationCounts": {
            value: counts[value]
            for value in sorted(counts)
        },
        "invalidSystemRelations": invalid,
        "records": records,
        "symbolicReferenceEligibleForFurtherEvaluation": symbolic_reference_eligible,
        "technicalReviewRequired": technical_review_required,
        "teacherReviewRequiredByThisGate": False,
        "sourceMutationAuthorized": False,
        "teacherGoldAdmissionAuthorized": False,
        "modelTrainingAuthorized": False,
        "productionDecisionAuthorityGranted": False,
    }


def route_renderer_mismatch(
    report: dict[str, object],
    *,
    implicated_system_relations: Iterable[str] | None,
) -> dict[str, object]:
    """Route one renderer mismatch without treating the renderer as an oracle.

    Teacher review is suppressed only when callers explicitly identify the
    implicated relations and every relation is one of the known renderer-
    sensitive MusicXML 4.0 values. Missing/unknown context fails closed to the
    existing teacher-review path.
    """

    implicated = tuple(sorted(set(implicated_system_relations or ())))
    valid = report.get("status") == "VALID_DIRECTION_SYSTEM_SEMANTICS"
    observed = {
        str(record.get("system"))
        for record in report.get("records", [])
        if isinstance(record, dict)
    }
    known_sensitive = (
        bool(implicated)
        and set(implicated).issubset(RENDERER_SENSITIVE_SYSTEM_RELATIONS)
        and set(implicated).issubset(observed)
    )

    if valid and known_sensitive:
        return {
            "decision": "RENDERER_COMPATIBILITY_REVIEW_REQUIRED",
            "teacherReviewRequired": False,
            "technicalReviewRequired": True,
            "symbolicReferenceRejected": False,
            "reasonCode": "KNOWN_DIRECTION_SYSTEM_RENDERER_COMPATIBILITY",
            "implicatedSystemRelations": list(implicated),
            "automaticMusicXmlRepairAuthorized": False,
        }

    return {
        "decision": "TEACHER_REVIEW_REQUIRED",
        "teacherReviewRequired": True,
        "technicalReviewRequired": report.get("technicalReviewRequired") is True,
        "symbolicReferenceRejected": report.get(
            "symbolicReferenceEligibleForFurtherEvaluation"
        ) is False,
        "reasonCode": "RENDERER_MISMATCH_NOT_PROVEN_KNOWN_DIRECTION_SYSTEM_COMPATIBILITY",
        "implicatedSystemRelations": list(implicated),
        "automaticMusicXmlRepairAuthorized": False,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="MusicXML or MXL file")
    parser.add_argument(
        "--renderer-mismatch-system",
        dest="renderer_mismatch_system",
        action="append",
        default=[],
        help="Explicit system relation implicated in a renderer mismatch; may repeat.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    data = args.path.read_bytes()
    report = build_report(data, source_name=args.path.name)
    output: dict[str, object] = {"semanticReport": report}
    if args.renderer_mismatch_system:
        output["rendererMismatchRouting"] = route_renderer_mismatch(
            report,
            implicated_system_relations=args.renderer_mismatch_system,
        )
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
