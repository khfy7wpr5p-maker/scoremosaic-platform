from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256
from math import gcd
import hmac
import json
from types import MappingProxyType
from typing import Any, Mapping
import xml.etree.ElementTree as ET
from xml.parsers import expat

from .contracts import TeacherScoreRevision
from .musical_state import ReviewMusicalState, validate_musical_state
from ._revision_store_common import DurableRevisionStoreError, RevisionScope
from ._revision_store_validation import validate_revision_for_store

from scoremosaic_ensemble.canonical import CanonicalModelError, CanonicalScore
from scoremosaic_ensemble.teacher_review_musicxml import normalize_teacher_review_musicxml


ARTIFACT_VERSION = "scoremosaic-corrected-musicxml-artifact-v1"
SAFETY_VERSION = "scoremosaic-generated-musicxml-safety-v1"
ROUNDTRIP_VERSION = "scoremosaic-review-musicxml-semantic-roundtrip-v1"
MEDIA_TYPE = "application/vnd.recordare.musicxml+xml"

_MAX_XML_BYTES = 16 * 1024 * 1024
_MAX_XML_DEPTH = 64
_MAX_XML_ELEMENTS = 500_000
_MAX_XML_ATTRIBUTES = 1_000_000
_MAX_ATTRIBUTES_PER_ELEMENT = 256
_MAX_DIVISIONS = 1_000_000
_MAX_PARTS = 64
_MAX_MEASURES = 20_000
_MAX_EVENTS = 500_000


class CorrectedMusicXmlError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> None:
    raise CorrectedMusicXmlError(code)


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError):
        _fail("CORRECTED_XML_NON_CANONICAL_VALUE")


def _digest(value: Any) -> str:
    return sha256(_canonical_json(value)).hexdigest()


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _deep_freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_deep_freeze(item) for item in value)
    return value


def _deep_thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _deep_thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_deep_thaw(item) for item in value]
    return value


def _fraction(value: Mapping[str, int]) -> Fraction:
    return Fraction(value["numerator"], value["denominator"])


def _lcm(left: int, right: int) -> int:
    result = left // gcd(left, right) * right
    if result > _MAX_DIVISIONS:
        _fail("CORRECTED_XML_DIVISIONS_LIMIT_EXCEEDED")
    return result


def _measure_divisions(measure: Mapping[str, Any]) -> int:
    divisions = 1
    for event in measure["events"]:
        divisions = _lcm(divisions, _fraction(event["onset"]).denominator)
        divisions = _lcm(divisions, _fraction(event["effectiveDuration"]).denominator)
    return divisions


def _duration_units(value: Fraction, divisions: int) -> int:
    units = value * divisions
    if units.denominator != 1 or units.numerator <= 0:
        _fail("CORRECTED_XML_DURATION_UNREPRESENTABLE")
    if units.numerator > 1_000_000_000:
        _fail("CORRECTED_XML_DURATION_LIMIT_EXCEEDED")
    return units.numerator


def _exact_decimal(value: Mapping[str, int]) -> str:
    fraction = _fraction(value)
    denominator = fraction.denominator
    twos = 0
    fives = 0
    while denominator % 2 == 0:
        twos += 1
        denominator //= 2
    while denominator % 5 == 0:
        fives += 1
        denominator //= 5
    if denominator != 1:
        _fail("CORRECTED_XML_ALTER_NOT_EXACT_DECIMAL")
    places = max(twos, fives)
    scaled = fraction.numerator * (10**places) // fraction.denominator
    sign = "-" if scaled < 0 else ""
    digits = str(abs(scaled)).rjust(places + 1, "0")
    if places == 0:
        return sign + digits
    integer = digits[:-places] or "0"
    decimal = digits[-places:].rstrip("0")
    return sign + integer if not decimal else f"{sign}{integer}.{decimal}"


def _append_text(parent: ET.Element, tag: str, value: Any) -> ET.Element:
    child = ET.SubElement(parent, tag)
    child.text = str(value)
    return child


def _append_movement(measure_node: ET.Element, kind: str, amount: Fraction, divisions: int) -> None:
    if amount <= 0:
        _fail("CORRECTED_XML_CURSOR_MOVEMENT_INVALID")
    node = ET.SubElement(measure_node, kind)
    _append_text(node, "duration", _duration_units(amount, divisions))


def _append_pitch(note: ET.Element, pitch: Mapping[str, Any]) -> None:
    pitch_node = ET.SubElement(note, "pitch")
    _append_text(pitch_node, "step", pitch["step"])
    alter = _fraction(pitch["alter"])
    if alter != 0:
        _append_text(pitch_node, "alter", _exact_decimal(pitch["alter"]))
    _append_text(pitch_node, "octave", pitch["octave"])


def _append_notations(note: ET.Element, event: Mapping[str, Any]) -> None:
    ties = event["ties"]
    tab = event["tab"]
    if not ties and tab is None:
        return
    notations = ET.SubElement(note, "notations")
    for tie_type in ties:
        ET.SubElement(notations, "tied", {"type": tie_type})
    if tab is not None:
        technical = ET.SubElement(notations, "technical")
        _append_text(technical, "string", tab["string"])
        _append_text(technical, "fret", tab["fret"])


def _append_event(
    measure_node: ET.Element,
    event: Mapping[str, Any],
    *,
    divisions: int,
    chord_follower: bool,
) -> None:
    if event["kind"] == "unpitched":
        _fail("CORRECTED_XML_UNPITCHED_UNSUPPORTED")

    note = ET.SubElement(measure_node, "note")
    if chord_follower:
        ET.SubElement(note, "chord")
    if event["grace"]:
        if _fraction(event["effectiveDuration"]) != 0:
            _fail("CORRECTED_XML_GRACE_DURATION_INVALID")
        ET.SubElement(note, "grace")

    if event["kind"] == "rest":
        ET.SubElement(note, "rest")
    else:
        pitch = event["pitch"]
        if pitch is None:
            _fail("CORRECTED_XML_NOTE_PITCH_MISSING")
        _append_pitch(note, pitch)

    if not event["grace"]:
        _append_text(
            note,
            "duration",
            _duration_units(_fraction(event["effectiveDuration"]), divisions),
        )

    for tie_type in event["ties"]:
        ET.SubElement(note, "tie", {"type": tie_type})

    _append_text(note, "voice", event["voice"])
    if event["writtenType"] is not None:
        _append_text(note, "type", event["writtenType"])
    for _ in range(event["dots"]):
        ET.SubElement(note, "dot")
    if event["tuplet"] is not None:
        modification = ET.SubElement(note, "time-modification")
        _append_text(modification, "actual-notes", event["tuplet"]["actualNotes"])
        _append_text(modification, "normal-notes", event["tuplet"]["normalNotes"])
    _append_text(note, "staff", event["staff"])
    _append_notations(note, event)


def _emit_measure(part_node: ET.Element, measure: Mapping[str, Any]) -> None:
    if measure["timeSignatureChanges"]:
        _fail("CORRECTED_XML_MID_MEASURE_TIME_CHANGE_UNSUPPORTED")
    attrs = {"number": measure["number"]}
    if measure["implicit"]:
        attrs["implicit"] = "yes"
    measure_node = ET.SubElement(part_node, "measure", attrs)
    divisions = _measure_divisions(measure)

    attributes = ET.SubElement(measure_node, "attributes")
    _append_text(attributes, "divisions", divisions)
    time_signature = measure["timeSignatureAtStart"]
    if time_signature is not None:
        time_node = ET.SubElement(attributes, "time")
        _append_text(time_node, "beats", time_signature["beats"])
        _append_text(time_node, "beat-type", time_signature["beatType"])

    cursor = Fraction(0)
    active_chord_group: str | None = None
    active_chord_onset: Fraction | None = None
    active_chord_staff: int | None = None
    active_chord_voice: str | None = None
    active_chord_index: int | None = None

    for event in measure["events"]:
        onset = _fraction(event["onset"])
        chord_group = event["chordGroup"]
        chord_index = event["chordIndex"]
        if chord_group is not None and event["kind"] != "note":
            _fail("CORRECTED_XML_CHORD_STRUCTURE_UNREPRESENTABLE")
        chord_follower = chord_group is not None and chord_index is not None and chord_index > 0

        if chord_follower:
            if (
                active_chord_group != chord_group
                or active_chord_onset != onset
                or active_chord_staff != event["staff"]
                or active_chord_voice != event["voice"]
                or active_chord_index is None
                or chord_index != active_chord_index + 1
            ):
                _fail("CORRECTED_XML_CHORD_STRUCTURE_UNREPRESENTABLE")
            active_chord_index = chord_index
        else:
            if chord_group is not None and chord_index != 0:
                _fail("CORRECTED_XML_CHORD_STRUCTURE_UNREPRESENTABLE")
            if onset > cursor:
                _append_movement(measure_node, "forward", onset - cursor, divisions)
            elif onset < cursor:
                _append_movement(measure_node, "backup", cursor - onset, divisions)
            cursor = onset
            if chord_group is None:
                active_chord_group = None
                active_chord_onset = None
                active_chord_staff = None
                active_chord_voice = None
                active_chord_index = None
            else:
                active_chord_group = chord_group
                active_chord_onset = onset
                active_chord_staff = event["staff"]
                active_chord_voice = event["voice"]
                active_chord_index = 0

        _append_event(
            measure_node,
            event,
            divisions=divisions,
            chord_follower=chord_follower,
        )
        if not chord_follower:
            cursor = onset + _fraction(event["effectiveDuration"])


def materialize_musicxml_bytes(state: ReviewMusicalState) -> bytes:
    if not isinstance(state, ReviewMusicalState):
        _fail("CORRECTED_XML_STATE_INVALID")
    payload = state.to_dict()
    parts = payload["parts"]
    if not parts or len(parts) > _MAX_PARTS:
        _fail("CORRECTED_XML_PART_COUNT_INVALID")

    root = ET.Element("score-partwise", {"version": "4.0"})
    part_list = ET.SubElement(root, "part-list")
    measure_total = 0
    event_total = 0
    for part in parts:
        score_part = ET.SubElement(part_list, "score-part", {"id": part["partId"]})
        _append_text(score_part, "part-name", part["partId"])
        measure_total += len(part["measures"])
        if measure_total > _MAX_MEASURES:
            _fail("CORRECTED_XML_MEASURE_LIMIT_EXCEEDED")
        for measure in part["measures"]:
            event_total += len(measure["events"])
            if event_total > _MAX_EVENTS:
                _fail("CORRECTED_XML_EVENT_LIMIT_EXCEEDED")

    for part in parts:
        part_node = ET.SubElement(root, "part", {"id": part["partId"]})
        for measure in part["measures"]:
            _emit_measure(part_node, measure)

    document = ET.tostring(
        root,
        encoding="utf-8",
        xml_declaration=True,
        short_empty_elements=True,
    )
    if not document or len(document) > _MAX_XML_BYTES:
        _fail("CORRECTED_XML_SIZE_INVALID")
    return document


@dataclass(frozen=True)
class GeneratedMusicXmlSafetyReport:
    _payload: Mapping[str, Any]

    @property
    def report_sha256(self) -> str:
        return _digest(_deep_thaw(self._payload))

    def to_dict(self) -> dict[str, Any]:
        payload = _deep_thaw(self._payload)
        payload["safetyReportSha256"] = self.report_sha256
        return payload


def validate_generated_musicxml(document: bytes) -> GeneratedMusicXmlSafetyReport:
    if not isinstance(document, bytes) or not document or len(document) > _MAX_XML_BYTES:
        _fail("CORRECTED_XML_SAFETY_SIZE_INVALID")
    if b"\x00" in document:
        _fail("CORRECTED_XML_SAFETY_NUL_BYTE")
    upper = document.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        _fail("CORRECTED_XML_SAFETY_DECLARATION_FORBIDDEN")

    parser = expat.ParserCreate(namespace_separator="}")
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    depth = 0
    elements = 0
    attributes = 0
    root_type: str | None = None

    def start_element(name: str, attrs: dict[str, str]) -> None:
        nonlocal depth, elements, attributes, root_type
        depth += 1
        if depth > _MAX_XML_DEPTH:
            _fail("CORRECTED_XML_SAFETY_DEPTH_EXCEEDED")
        elements += 1
        if elements > _MAX_XML_ELEMENTS:
            _fail("CORRECTED_XML_SAFETY_ELEMENT_LIMIT_EXCEEDED")
        count = len(attrs)
        if count > _MAX_ATTRIBUTES_PER_ELEMENT:
            _fail("CORRECTED_XML_SAFETY_ATTRIBUTE_LIMIT_EXCEEDED")
        attributes += count
        if attributes > _MAX_XML_ATTRIBUTES:
            _fail("CORRECTED_XML_SAFETY_ATTRIBUTE_LIMIT_EXCEEDED")
        if elements == 1:
            root_type = name.rsplit("}", 1)[-1]
            if root_type != "score-partwise":
                _fail("CORRECTED_XML_SAFETY_ROOT_INVALID")

    def end_element(_name: str) -> None:
        nonlocal depth
        depth -= 1

    def external_entity(*_args: Any) -> int:
        _fail("CORRECTED_XML_SAFETY_EXTERNAL_ENTITY_FORBIDDEN")

    parser.StartElementHandler = start_element
    parser.EndElementHandler = end_element
    parser.ExternalEntityRefHandler = external_entity
    try:
        parser.Parse(document, True)
    except CorrectedMusicXmlError:
        raise
    except expat.ExpatError as exc:
        raise CorrectedMusicXmlError("CORRECTED_XML_SAFETY_PARSE_INVALID") from exc
    if depth != 0 or root_type is None:
        _fail("CORRECTED_XML_SAFETY_PARSE_INVALID")

    payload = {
        "schemaVersion": SAFETY_VERSION,
        "safe": True,
        "rootType": root_type,
        "byteSize": len(document),
        "musicXmlSha256": sha256(document).hexdigest(),
        "elementCount": elements,
        "attributeCount": attributes,
        "externalResolution": False,
        "dtdAllowed": False,
        "entityAllowed": False,
    }
    return GeneratedMusicXmlSafetyReport(_deep_freeze(payload))


def _semantic_chord_map(events: list[Mapping[str, Any]]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for event in events:
        group = event.get("chordGroup")
        if group is not None and group not in mapping:
            mapping[group] = len(mapping) + 1
    return mapping


def _event_semantic(event: Mapping[str, Any], chord_map: Mapping[str, int]) -> dict[str, Any]:
    group = event.get("chordGroup")
    return {
        "kind": event["kind"],
        "onset": _deep_thaw(event["onset"]),
        "effectiveDuration": _deep_thaw(event["effectiveDuration"]),
        "writtenType": event["writtenType"],
        "dots": event["dots"],
        "tuplet": _deep_thaw(event["tuplet"]),
        "voice": event["voice"],
        "staff": event["staff"],
        "pitch": _deep_thaw(event["pitch"]),
        "tab": _deep_thaw(event["tab"]),
        "grace": event["grace"],
        "chordGroupOrdinal": chord_map[group] if group is not None else None,
        "chordIndex": event["chordIndex"],
        "ties": list(event["ties"]),
    }


def semantic_projection_from_state(state: ReviewMusicalState) -> dict[str, Any]:
    if not isinstance(state, ReviewMusicalState):
        _fail("CORRECTED_XML_STATE_INVALID")
    payload = state.to_dict()
    result_parts = []
    for part in payload["parts"]:
        measures = []
        for measure in part["measures"]:
            chord_map = _semantic_chord_map(measure["events"])
            measures.append({
                "number": measure["number"],
                "ordinal": measure["ordinal"],
                "implicit": measure["implicit"],
                "timeSignatureAtStart": _deep_thaw(measure["timeSignatureAtStart"]),
                "events": [_event_semantic(event, chord_map) for event in measure["events"]],
            })
        result_parts.append({
            "partId": part["partId"],
            "ordinal": part["ordinal"],
            "measures": measures,
        })
    return {
        "schemaVersion": ROUNDTRIP_VERSION,
        "parts": result_parts,
    }


def semantic_projection_from_canonical(score: CanonicalScore) -> dict[str, Any]:
    if not isinstance(score, CanonicalScore):
        _fail("CORRECTED_XML_CANONICAL_TYPE_INVALID")
    result_parts = []
    for part in score.parts:
        measures = []
        for measure in part.measures:
            event_dicts = [event.as_dict() for event in measure.events]
            chord_map = _semantic_chord_map(event_dicts)
            measures.append({
                "number": measure.number,
                "ordinal": measure.ordinal,
                "implicit": measure.implicit,
                "timeSignatureAtStart": (
                    measure.time_signature_at_start.as_dict()
                    if measure.time_signature_at_start is not None
                    else None
                ),
                "events": [_event_semantic(event, chord_map) for event in event_dicts],
            })
        result_parts.append({
            "partId": part.part_id,
            "ordinal": part.ordinal,
            "measures": measures,
        })
    return {
        "schemaVersion": ROUNDTRIP_VERSION,
        "parts": result_parts,
    }


@dataclass(frozen=True)
class CorrectedMusicXmlArtifact:
    document: bytes
    _record: Mapping[str, Any]

    @property
    def artifact_record_sha256(self) -> str:
        return _digest(_deep_thaw(self._record))

    def to_dict(self) -> dict[str, Any]:
        payload = _deep_thaw(self._record)
        payload["artifactRecordSha256"] = self.artifact_record_sha256
        return payload


def build_corrected_musicxml_artifact(
    *,
    scope: RevisionScope,
    revision: TeacherScoreRevision,
    state: ReviewMusicalState,
) -> CorrectedMusicXmlArtifact:
    if not isinstance(scope, RevisionScope):
        _fail("CORRECTED_XML_SCOPE_INVALID")
    if not isinstance(revision, TeacherScoreRevision):
        _fail("CORRECTED_XML_REVISION_INVALID")
    if not isinstance(state, ReviewMusicalState):
        _fail("CORRECTED_XML_STATE_INVALID")

    record = revision.to_dict()
    try:
        validated, _ = validate_revision_for_store(
            scope,
            revision,
            expected_parent_revision_id=record.get("parentRevisionId"),
            expected_parent_revision_sha256=record.get("parentRevisionSha256"),
            expected_previous_audit_event_sha256=record.get("previousAuditEventSha256"),
        )
    except DurableRevisionStoreError as exc:
        raise CorrectedMusicXmlError("CORRECTED_XML_REVISION_VALIDATION_FAILED") from exc

    if not hmac.compare_digest(validated["resultingMusicalStateSha256"], state.state_sha256):
        _fail("CORRECTED_XML_REVISION_STATE_MISMATCH")

    validation = validate_musical_state(state)
    if not hmac.compare_digest(validated["validationReportSha256"], validation.report_sha256):
        _fail("CORRECTED_XML_VALIDATION_REPORT_MISMATCH")
    if validated["blockingIssueCount"] != validation.blocking_issue_count:
        _fail("CORRECTED_XML_BLOCKING_COUNT_MISMATCH")
    if validated["unresolvedIssueCount"] != validation.unresolved_issue_count:
        _fail("CORRECTED_XML_UNRESOLVED_COUNT_MISMATCH")

    document = materialize_musicxml_bytes(state)
    safety = validate_generated_musicxml(document)
    musicxml_sha = sha256(document).hexdigest()
    revision_id = validated["revisionId"]
    revision_sha = validated["revisionSha256"]
    derivative_ref = f"teacher-review/{revision_id}/{musicxml_sha}.musicxml"

    try:
        regenerated = normalize_teacher_review_musicxml(
            document,
            artifact_ref=derivative_ref,
            derivative_version="stage8f-v1",
        )
    except CanonicalModelError as exc:
        raise CorrectedMusicXmlError("CORRECTED_XML_CANONICAL_RENORMALIZATION_FAILED") from exc

    expected_semantic = semantic_projection_from_state(state)
    regenerated_semantic = semantic_projection_from_canonical(regenerated)
    expected_semantic_sha = _digest(expected_semantic)
    regenerated_semantic_sha = _digest(regenerated_semantic)
    if not hmac.compare_digest(expected_semantic_sha, regenerated_semantic_sha):
        _fail("CORRECTED_XML_SEMANTIC_ROUNDTRIP_MISMATCH")

    body = {
        "schemaVersion": ARTIFACT_VERSION,
        "tenantId": validated["tenantId"],
        "jobId": validated["jobId"],
        "reviewerId": validated["reviewerId"],
        "reviewReportId": validated["reviewReportId"],
        "reviewReportSha256": validated["reviewReportSha256"],
        "baseCanonicalSha256": validated["baseCanonicalSha256"],
        "revisionId": revision_id,
        "revisionSha256": revision_sha,
        "stateSha256": state.state_sha256,
        "validationReportSha256": validation.report_sha256,
        "blockingIssueCount": validation.blocking_issue_count,
        "unresolvedIssueCount": validation.unresolved_issue_count,
        "mediaType": MEDIA_TYPE,
        "byteSize": len(document),
        "musicXmlSha256": musicxml_sha,
        "safetyPolicyVersion": SAFETY_VERSION,
        "safetyReportSha256": safety.report_sha256,
        "regeneratedCanonicalSha256": regenerated.canonical_sha256,
        "roundTripContractVersion": ROUNDTRIP_VERSION,
        "expectedSemanticSha256": expected_semantic_sha,
        "regeneratedSemanticSha256": regenerated_semantic_sha,
        "roundTripMatch": True,
        "status": "draft",
        "immutable": True,
        "approvalEligible": False,
        "publicationEligible": False,
    }
    artifact_body_sha = _digest(body)
    body["artifactId"] = f"corrected_{artifact_body_sha[:32]}"
    return CorrectedMusicXmlArtifact(document=document, _record=_deep_freeze(body))


__all__ = [
    "ARTIFACT_VERSION",
    "MEDIA_TYPE",
    "ROUNDTRIP_VERSION",
    "SAFETY_VERSION",
    "CorrectedMusicXmlArtifact",
    "CorrectedMusicXmlError",
    "GeneratedMusicXmlSafetyReport",
    "build_corrected_musicxml_artifact",
    "materialize_musicxml_bytes",
    "semantic_projection_from_canonical",
    "semantic_projection_from_state",
    "validate_generated_musicxml",
]
