"""Canonical re-normalization for deterministic Teacher Review MusicXML derivatives.

This module intentionally reuses the existing Canonical MusicXML parser internals while
keeping a distinct source identity. The ordinary OMR normalizer remains restricted to
homr/clarity/audiveris and is not widened by this adapter.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re
import xml.etree.ElementTree as ET

from .canonical import (
    CanonicalModelError,
    CanonicalPart,
    CanonicalScore,
    SourceIdentity,
    _require_text,
)
from .musicxml import (
    MusicXmlNormalizationError,
    _ARTIFACT_REF,
    _MAX_MEASURES,
    _MAX_MUSICXML_BYTES,
    _MAX_PARTS,
    _child,
    _children,
    _local_name,
    _parse_measure,
    _part_names,
    _validate_tree,
)

TEACHER_REVIEW_ENGINE = "teacher-review"
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class TeacherReviewSourceIdentity(SourceIdentity):
    """Source identity reserved for a Teacher Review derived MusicXML artifact."""

    def __post_init__(self) -> None:
        if self.engine != TEACHER_REVIEW_ENGINE:
            raise CanonicalModelError("teacher-review source engine is invalid")
        _require_text(self.artifact_ref, name="artifact_ref", maximum=500)
        if ".." in self.artifact_ref.split("/") or "\\" in self.artifact_ref:
            raise CanonicalModelError("artifact_ref contains unsafe path syntax")
        if not _HEX_64.fullmatch(self.artifact_sha256):
            raise CanonicalModelError("artifact_sha256 must be lowercase SHA-256")
        if self.engine_version is not None:
            _require_text(self.engine_version, name="engine_version", maximum=200)
        if self.model_version is not None:
            _require_text(self.model_version, name="model_version", maximum=200)


def normalize_teacher_review_musicxml(
    document: bytes,
    *,
    artifact_ref: str,
    derivative_version: str = "stage8f-v1",
) -> CanonicalScore:
    """Re-normalize one generated Teacher Review MusicXML derivative.

    No paths, URLs, MXL containers, network I/O, DTDs or entities are accepted. The
    parser and structural budgets are the same ones used by the OMR Canonical
    normalizer. The resulting CanonicalScore is internal round-trip evidence; its
    source identity is explicitly `teacher-review`, never an OMR engine identity.
    """

    if not isinstance(document, bytes):
        raise MusicXmlNormalizationError("MusicXML document must be bytes")
    if not document or len(document) > _MAX_MUSICXML_BYTES:
        raise MusicXmlNormalizationError("MusicXML byte size is outside limits")
    if b"\x00" in document:
        raise MusicXmlNormalizationError("MusicXML contains NUL bytes")
    upper = document.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise MusicXmlNormalizationError("DTD and entity declarations are forbidden")
    if ".." in artifact_ref.split("/") or "\\" in artifact_ref:
        raise MusicXmlNormalizationError("artifact_ref contains unsafe path syntax")
    if not _ARTIFACT_REF.fullmatch(artifact_ref):
        raise MusicXmlNormalizationError("artifact_ref is invalid")

    try:
        root = ET.fromstring(document)
    except ET.ParseError as exc:
        raise MusicXmlNormalizationError("MusicXML is not well-formed XML") from exc
    _validate_tree(root)

    root_type = _local_name(root.tag)
    if root_type != "score-partwise":
        raise MusicXmlNormalizationError("only score-partwise is supported in foundation v1")

    movement_title_element = _child(root, "movement-title")
    movement_title = None
    if movement_title_element is not None and movement_title_element.text:
        movement_title = movement_title_element.text.strip() or None
        if movement_title is not None and len(movement_title) > 500:
            raise MusicXmlNormalizationError("movement-title exceeds limit")

    part_name_map = _part_names(root)
    part_elements = _children(root, "part")
    if not part_elements or len(part_elements) > _MAX_PARTS:
        raise MusicXmlNormalizationError("MusicXML part count is outside limits")

    diagnostics = []
    parts: list[CanonicalPart] = []
    seen_part_ids: set[str] = set()
    total_measure_count = 0
    total_event_count = 0

    for part_ordinal, part in enumerate(part_elements, start=1):
        part_id = part.attrib.get("id", "").strip()
        if not part_id or len(part_id) > 200:
            raise MusicXmlNormalizationError("part id is invalid")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,199}", part_id):
            raise MusicXmlNormalizationError("part id contains unsupported characters")
        if part_id in seen_part_ids:
            raise MusicXmlNormalizationError("duplicate part id")
        seen_part_ids.add(part_id)

        measures = _children(part, "measure")
        if not measures:
            raise MusicXmlNormalizationError("part contains no measures")
        total_measure_count += len(measures)
        if total_measure_count > _MAX_MEASURES:
            raise MusicXmlNormalizationError("MusicXML measure limit exceeded")

        canonical_measures = []
        inherited_divisions = None
        inherited_time_signature = None
        for measure_ordinal, measure in enumerate(measures, start=1):
            (
                canonical_measure,
                inherited_divisions,
                inherited_time_signature,
                total_event_count,
            ) = _parse_measure(
                measure,
                part_id=part_id,
                part_ordinal=part_ordinal,
                measure_ordinal=measure_ordinal,
                inherited_divisions=inherited_divisions,
                inherited_time_signature=inherited_time_signature,
                diagnostics=diagnostics,
                total_event_count=total_event_count,
            )
            canonical_measures.append(canonical_measure)

        parts.append(
            CanonicalPart(
                part_id=part_id,
                name=part_name_map.get(part_id),
                ordinal=part_ordinal,
                measures=tuple(canonical_measures),
            )
        )

    source = TeacherReviewSourceIdentity(
        engine=TEACHER_REVIEW_ENGINE,
        engine_version=derivative_version,
        model_version=None,
        artifact_ref=artifact_ref,
        artifact_sha256=sha256(document).hexdigest(),
    )
    return CanonicalScore(
        source=source,
        root_type=root_type,
        movement_title=movement_title,
        parts=tuple(parts),
        diagnostics=tuple(diagnostics),
    )


__all__ = [
    "TEACHER_REVIEW_ENGINE",
    "TeacherReviewSourceIdentity",
    "normalize_teacher_review_musicxml",
]
