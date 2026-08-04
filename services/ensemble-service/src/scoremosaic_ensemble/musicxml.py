"""Safe, deterministic MusicXML-to-Canonical-Score normalization."""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction
from hashlib import sha256
import re
import xml.etree.ElementTree as ET

from .canonical import (
    CanonicalEvent,
    CanonicalMeasure,
    CanonicalModelError,
    CanonicalPart,
    CanonicalScore,
    DivisionsChange,
    EventProvenance,
    NormalizationDiagnostic,
    Pitch,
    SourceIdentity,
    TabPosition,
    TimeSignature,
    TimeSignatureChange,
    TimingMovement,
    TupletRatio,
)

_MAX_MUSICXML_BYTES = 16 * 1024 * 1024
_MAX_XML_ELEMENTS = 500_000
_MAX_XML_DEPTH = 64
_MAX_PARTS = 64
_MAX_MEASURES = 20_000
_MAX_EVENTS = 1_000_000
_MAX_DIAGNOSTICS = 1_000
_ENGINE_VALUES = frozenset({"homr", "clarity", "audiveris"})
_ARTIFACT_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,499}$")

_WRITTEN_QUARTER_DURATIONS: dict[str, Fraction] = {
    "maxima": Fraction(32),
    "long": Fraction(16),
    "breve": Fraction(8),
    "whole": Fraction(4),
    "half": Fraction(2),
    "quarter": Fraction(1),
    "eighth": Fraction(1, 2),
    "16th": Fraction(1, 4),
    "32nd": Fraction(1, 8),
    "64th": Fraction(1, 16),
    "128th": Fraction(1, 32),
    "256th": Fraction(1, 64),
    "512th": Fraction(1, 128),
    "1024th": Fraction(1, 256),
}


class MusicXmlNormalizationError(CanonicalModelError):
    """Raised when untrusted MusicXML cannot be normalized safely."""


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _children(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in element if _local_name(child.tag) == name]


def _child(element: ET.Element, name: str) -> ET.Element | None:
    for child in element:
        if _local_name(child.tag) == name:
            return child
    return None


def _text(
    element: ET.Element,
    name: str,
    *,
    required: bool = False,
    maximum: int = 500,
) -> str | None:
    child = _child(element, name)
    if child is None or child.text is None:
        if required:
            raise MusicXmlNormalizationError(f"missing MusicXML {name}")
        return None
    value = child.text.strip()
    if not value:
        if required:
            raise MusicXmlNormalizationError(f"empty MusicXML {name}")
        return None
    if len(value) > maximum or any(ord(character) < 32 for character in value):
        raise MusicXmlNormalizationError(f"invalid MusicXML {name}")
    return value


def _positive_int(value: str | None, *, name: str, maximum: int) -> int:
    if value is None:
        raise MusicXmlNormalizationError(f"missing MusicXML {name}")
    try:
        parsed = int(value, 10)
    except ValueError as exc:
        raise MusicXmlNormalizationError(f"invalid MusicXML {name}") from exc
    if parsed <= 0 or parsed > maximum:
        raise MusicXmlNormalizationError(f"MusicXML {name} is outside limits")
    return parsed


def _nonnegative_int(value: str | None, *, name: str, maximum: int) -> int:
    if value is None:
        raise MusicXmlNormalizationError(f"missing MusicXML {name}")
    try:
        parsed = int(value, 10)
    except ValueError as exc:
        raise MusicXmlNormalizationError(f"invalid MusicXML {name}") from exc
    if parsed < 0 or parsed > maximum:
        raise MusicXmlNormalizationError(f"MusicXML {name} is outside limits")
    return parsed


def _fraction(value: str | None, *, name: str, maximum: int = 1_000_000) -> Fraction:
    if value is None:
        raise MusicXmlNormalizationError(f"missing MusicXML {name}")
    try:
        parsed = Fraction(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise MusicXmlNormalizationError(f"invalid MusicXML {name}") from exc
    if abs(parsed) > maximum:
        raise MusicXmlNormalizationError(f"MusicXML {name} is outside limits")
    return parsed


def _duration(element: ET.Element, divisions: int, *, path: str) -> Fraction:
    duration_value = _text(element, "duration", required=True, maximum=40)
    duration_units = _positive_int(duration_value, name="duration", maximum=1_000_000_000)
    duration = Fraction(duration_units, divisions)
    if duration <= 0:
        raise MusicXmlNormalizationError(f"non-positive duration at {path}")
    return duration


def _written_duration(written_type: str | None, dots: int) -> Fraction | None:
    if written_type is None:
        return None
    base = _WRITTEN_QUARTER_DURATIONS.get(written_type)
    if base is None:
        return None
    multiplier = sum((Fraction(1, 2**index) for index in range(dots + 1)), Fraction(0))
    return base * multiplier


def _validate_tree(root: ET.Element) -> None:
    element_count = 0
    stack: list[tuple[ET.Element, int]] = [(root, 1)]
    while stack:
        element, depth = stack.pop()
        element_count += 1
        if element_count > _MAX_XML_ELEMENTS:
            raise MusicXmlNormalizationError("MusicXML element limit exceeded")
        if depth > _MAX_XML_DEPTH:
            raise MusicXmlNormalizationError("MusicXML nesting limit exceeded")
        stack.extend((child, depth + 1) for child in element)


def _parse_time_signature(time: ET.Element) -> TimeSignature:
    symbol = time.attrib.get("symbol")
    if symbol in {"senza-misura"} or _child(time, "senza-misura") is not None:
        raise MusicXmlNormalizationError("senza-misura is not supported in foundation v1")
    beats_values = [
        (child.text or "").strip()
        for child in time
        if _local_name(child.tag) == "beats"
    ]
    beat_type_values = [
        (child.text or "").strip()
        for child in time
        if _local_name(child.tag) == "beat-type"
    ]
    if len(beats_values) != 1 or len(beat_type_values) != 1:
        raise MusicXmlNormalizationError(
            "composite or incomplete time signatures are not supported in foundation v1"
        )
    beats = beats_values[0]
    if not re.fullmatch(r"[1-9][0-9]*(?:\+[1-9][0-9]*)*", beats):
        raise MusicXmlNormalizationError("invalid MusicXML beats")
    beat_type = _positive_int(beat_type_values[0], name="beat-type", maximum=1024)
    return TimeSignature(beats=beats, beat_type=beat_type)


def _expected_measure_duration(time_signature: TimeSignature | None) -> Fraction | None:
    if time_signature is None:
        return None
    beats_total = sum(int(part) for part in time_signature.beats.split("+"))
    return Fraction(beats_total * 4, time_signature.beat_type)


def _parse_pitch(note: ET.Element) -> tuple[str, Pitch | None]:
    if _child(note, "rest") is not None:
        return "rest", None
    pitch_element = _child(note, "pitch")
    if pitch_element is not None:
        step = _text(pitch_element, "step", required=True, maximum=1)
        alter_text = _text(pitch_element, "alter", maximum=40)
        alter = Fraction(0) if alter_text is None else _fraction(alter_text, name="alter")
        octave = _nonnegative_int(
            _text(pitch_element, "octave", required=True, maximum=4),
            name="octave",
            maximum=12,
        )
        return "note", Pitch(step=step or "", alter=alter, octave=octave)
    unpitched = _child(note, "unpitched")
    if unpitched is not None:
        return "unpitched", None
    raise MusicXmlNormalizationError("note has neither pitch, unpitched, nor rest")


def _parse_tab(note: ET.Element) -> TabPosition | None:
    notations = _child(note, "notations")
    if notations is None:
        return None
    technical = _child(notations, "technical")
    if technical is None:
        return None
    string_text = _text(technical, "string", maximum=4)
    fret_text = _text(technical, "fret", maximum=4)
    if string_text is None and fret_text is None:
        return None
    if string_text is None or fret_text is None:
        raise MusicXmlNormalizationError("incomplete MusicXML string/fret pair")
    string = _positive_int(string_text, name="string", maximum=24)
    fret = _nonnegative_int(fret_text, name="fret", maximum=96)
    return TabPosition(string=string, fret=fret)


def _parse_tuplet(note: ET.Element) -> TupletRatio | None:
    modification = _child(note, "time-modification")
    if modification is None:
        return None
    actual = _positive_int(
        _text(modification, "actual-notes", required=True, maximum=10),
        name="actual-notes",
        maximum=1024,
    )
    normal = _positive_int(
        _text(modification, "normal-notes", required=True, maximum=10),
        name="normal-notes",
        maximum=1024,
    )
    return TupletRatio(actual_notes=actual, normal_notes=normal)


def _parse_ties(note: ET.Element) -> tuple[str, ...]:
    values: set[str] = set()
    for tie in _children(note, "tie"):
        tie_type = tie.attrib.get("type", "").strip()
        if tie_type not in {"start", "stop", "continue"}:
            raise MusicXmlNormalizationError("invalid MusicXML tie type")
        values.add(tie_type)
    notations = _child(note, "notations")
    if notations is not None:
        for tied in _children(notations, "tied"):
            tied_type = tied.attrib.get("type", "").strip()
            if tied_type not in {"start", "stop", "continue"}:
                raise MusicXmlNormalizationError("invalid MusicXML tied type")
            values.add(tied_type)
    return tuple(sorted(values))


def _part_names(root: ET.Element) -> dict[str, str | None]:
    part_list = _child(root, "part-list")
    names: dict[str, str | None] = {}
    if part_list is None:
        return names
    for score_part in _children(part_list, "score-part"):
        part_id = score_part.attrib.get("id", "").strip()
        if not part_id or len(part_id) > 200:
            raise MusicXmlNormalizationError("score-part id is invalid")
        if part_id in names:
            raise MusicXmlNormalizationError("duplicate score-part id")
        name = _text(score_part, "part-name", maximum=300)
        names[part_id] = name
    return names


def _diagnostic(
    diagnostics: list[NormalizationDiagnostic],
    *,
    code: str,
    message: str,
    xml_path: str,
) -> None:
    if len(diagnostics) < _MAX_DIAGNOSTICS:
        diagnostics.append(
            NormalizationDiagnostic(
                code=code,
                severity="info",
                message=message,
                xml_path=xml_path,
            )
        )
    elif len(diagnostics) == _MAX_DIAGNOSTICS:
        diagnostics.append(
            NormalizationDiagnostic(
                code="diagnostics-truncated",
                severity="warning",
                message="Additional normalization diagnostics were omitted.",
                xml_path=None,
            )
        )


def _parse_measure(
    measure: ET.Element,
    *,
    part_id: str,
    part_ordinal: int,
    measure_ordinal: int,
    inherited_divisions: int | None,
    inherited_time_signature: TimeSignature | None,
    diagnostics: list[NormalizationDiagnostic],
    total_event_count: int,
) -> tuple[CanonicalMeasure, int | None, TimeSignature | None, int]:
    number = measure.attrib.get("number", str(measure_ordinal)).strip()
    if not number or len(number) > 40:
        raise MusicXmlNormalizationError("measure number is invalid")
    implicit = measure.attrib.get("implicit", "no").strip().lower() == "yes"
    measure_id = f"{part_id}:m{measure_ordinal:06d}"
    measure_path = f"/score-partwise/part[{part_ordinal}]/measure[{measure_ordinal}]"

    current_divisions = inherited_divisions
    current_time_signature = inherited_time_signature
    divisions_at_start = inherited_divisions
    time_signature_at_start = inherited_time_signature
    divisions_changes: list[DivisionsChange] = []
    time_signature_changes: list[TimeSignatureChange] = []
    timing_movements: list[TimingMovement] = []
    events: list[CanonicalEvent] = []
    cursor = Fraction(0)
    observed_duration = Fraction(0)
    source_event_index = 0
    last_note_index: int | None = None

    for xml_order, child in enumerate(measure):
        name = _local_name(child.tag)
        child_path = f"{measure_path}/{name}[{xml_order + 1}]"

        if name == "attributes":
            for attribute_child in child:
                attribute_name = _local_name(attribute_child.tag)
                attribute_path = f"{child_path}/{attribute_name}"
                if attribute_name == "divisions":
                    text = (attribute_child.text or "").strip()
                    new_divisions = _positive_int(text, name="divisions", maximum=1_000_000)
                    current_divisions = new_divisions
                    divisions_changes.append(
                        DivisionsChange(
                            xml_order=xml_order,
                            onset=cursor,
                            divisions=new_divisions,
                        )
                    )
                    if cursor == 0 and not events and not timing_movements:
                        divisions_at_start = new_divisions
                elif attribute_name == "time":
                    new_time_signature = _parse_time_signature(attribute_child)
                    current_time_signature = new_time_signature
                    time_signature_changes.append(
                        TimeSignatureChange(
                            xml_order=xml_order,
                            onset=cursor,
                            time_signature=new_time_signature,
                        )
                    )
                    if cursor == 0 and not events and not timing_movements:
                        time_signature_at_start = new_time_signature
                else:
                    _diagnostic(
                        diagnostics,
                        code="ignored-attribute",
                        message=f"MusicXML attribute '{attribute_name}' is preserved only in the raw candidate.",
                        xml_path=attribute_path,
                    )
            continue

        if name == "note":
            if current_divisions is None:
                raise MusicXmlNormalizationError(
                    f"note encountered before divisions at {child_path}"
                )
            source_event_index += 1
            total_event_count += 1
            if total_event_count > _MAX_EVENTS:
                raise MusicXmlNormalizationError("MusicXML event limit exceeded")

            voice = _text(child, "voice", maximum=40) or "1"
            staff_text = _text(child, "staff", maximum=10)
            staff = 1 if staff_text is None else _positive_int(
                staff_text, name="staff", maximum=128
            )
            grace = _child(child, "grace") is not None
            if grace:
                duration = Fraction(0)
            else:
                duration = _duration(child, current_divisions, path=child_path)

            is_chord = _child(child, "chord") is not None
            if is_chord:
                if last_note_index is None:
                    raise MusicXmlNormalizationError(
                        f"chord note has no preceding note at {child_path}"
                    )
                previous = events[last_note_index]
                if previous.kind == "rest":
                    raise MusicXmlNormalizationError(
                        f"chord note follows a rest at {child_path}"
                    )
                if previous.voice != voice or previous.staff != staff:
                    raise MusicXmlNormalizationError(
                        f"chord note changes voice or staff at {child_path}"
                    )
                onset = previous.onset
                if previous.chord_group is None:
                    chord_group = f"{measure_id}:c{last_note_index + 1:06d}"
                    previous = replace(
                        previous,
                        chord_group=chord_group,
                        chord_index=0,
                    )
                    events[last_note_index] = previous
                else:
                    chord_group = previous.chord_group
                chord_index = (previous.chord_index or 0) + 1
            else:
                onset = cursor
                chord_group = None
                chord_index = None

            kind, pitch = _parse_pitch(child)
            written_type = _text(child, "type", maximum=40)
            dots = len(_children(child, "dot"))
            if dots > 8:
                raise MusicXmlNormalizationError("MusicXML dot count exceeds limit")
            written_duration = _written_duration(written_type, dots)
            if written_type is not None and written_duration is None:
                _diagnostic(
                    diagnostics,
                    code="unknown-written-type",
                    message=f"Written note type '{written_type}' was preserved but not converted.",
                    xml_path=child_path,
                )

            event = CanonicalEvent(
                event_id=f"{measure_id}:e{source_event_index:06d}",
                xml_order=xml_order,
                kind=kind,
                onset=onset,
                effective_duration=duration,
                written_duration=written_duration,
                written_type=written_type,
                dots=dots,
                tuplet=_parse_tuplet(child),
                voice=voice,
                staff=staff,
                pitch=pitch,
                tab=_parse_tab(child),
                grace=grace,
                chord_group=chord_group,
                chord_index=chord_index,
                ties=_parse_ties(child),
                provenance=EventProvenance(
                    xml_path=child_path,
                    source_event_index=source_event_index - 1,
                ),
            )
            events.append(event)
            last_note_index = len(events) - 1

            if not is_chord:
                cursor += duration
            observed_duration = max(observed_duration, event.end, cursor)
            continue

        if name in {"backup", "forward"}:
            if current_divisions is None:
                raise MusicXmlNormalizationError(
                    f"{name} encountered before divisions at {child_path}"
                )
            movement_duration = _duration(child, current_divisions, path=child_path)
            from_position = cursor
            if name == "backup":
                to_position = cursor - movement_duration
                if to_position < 0:
                    raise MusicXmlNormalizationError(
                        f"backup moves before measure start at {child_path}"
                    )
            else:
                to_position = cursor + movement_duration
            timing_movements.append(
                TimingMovement(
                    kind=name,
                    xml_order=xml_order,
                    duration=movement_duration,
                    from_position=from_position,
                    to_position=to_position,
                    xml_path=child_path,
                )
            )
            cursor = to_position
            observed_duration = max(observed_duration, cursor)
            last_note_index = None
            continue

        _diagnostic(
            diagnostics,
            code="ignored-measure-element",
            message=f"MusicXML element '{name}' is preserved only in the raw candidate.",
            xml_path=child_path,
        )
        last_note_index = None

    later_time_changes = [
        change for change in time_signature_changes if change.onset > 0
    ]
    expected_duration = (
        None
        if later_time_changes
        else _expected_measure_duration(time_signature_at_start)
    )

    canonical_measure = CanonicalMeasure(
        measure_id=measure_id,
        number=number,
        ordinal=measure_ordinal,
        implicit=implicit,
        divisions_at_start=divisions_at_start,
        time_signature_at_start=time_signature_at_start,
        expected_duration=expected_duration,
        observed_duration=observed_duration,
        divisions_changes=tuple(divisions_changes),
        time_signature_changes=tuple(time_signature_changes),
        timing_movements=tuple(timing_movements),
        events=tuple(events),
    )
    return canonical_measure, current_divisions, current_time_signature, total_event_count


def normalize_musicxml(
    document: bytes,
    *,
    engine: str,
    artifact_ref: str,
    engine_version: str | None = None,
    model_version: str | None = None,
) -> CanonicalScore:
    """Normalize one immutable MusicXML candidate into the canonical model.

    The function accepts raw MusicXML bytes only. Compressed MXL extraction, file-system
    access, orchestration, comparison, and automatic correction remain out of scope.
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
    if engine not in _ENGINE_VALUES:
        raise MusicXmlNormalizationError("unsupported source engine")
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
        raise MusicXmlNormalizationError(
            "only score-partwise is supported in foundation v1"
        )

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

    diagnostics: list[NormalizationDiagnostic] = []
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

        canonical_measures: list[CanonicalMeasure] = []
        inherited_divisions: int | None = None
        inherited_time_signature: TimeSignature | None = None
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

    source = SourceIdentity(
        engine=engine,
        engine_version=engine_version,
        model_version=model_version,
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
