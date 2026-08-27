"""Pure Real Score Intake Adapter v1.

The adapter consumes one already verifiable Real Score Intake v1.1 envelope plus
its exact MusicXML bytes and Canonical Score. It first re-runs the v1.1 trust
checks, then projects the *full* Canonical Score into the pinned ST Score Editor
Core 1.0.0 ScoreDocument/NotationDocument shapes.

No file I/O, network, persistence, rendering, approval, publication or automatic
correction authority is introduced here. Unsupported semantics fail closed.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from math import gcd
import json
import re
from typing import Any, Mapping

from .real_score_intake import RealScoreIntakeError
from .real_score_intake_v1_1 import (
    REAL_SCORE_INTAKE_VERSION_V1_1,
    validate_real_score_intake_v1_1,
)


REAL_SCORE_RUNTIME_VERSION = "scoremosaic-real-score-runtime-v1"
CORE_COMMIT = "b317abef915d1e16b37572221a38feb3e504450d"
CORE_SCORE_SCHEMA_VERSION = "1.0.0"
CORE_NOTATION_VERSION = "1.0.0"

_CORE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SAFE_INT_MAX = 2**53 - 1


class RealScoreIntakeAdapterError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _fail(code: str) -> None:
    raise RealScoreIntakeAdapterError(code)


def _core_id(value: Any, code: str) -> str:
    if type(value) is not str or _CORE_ID_RE.fullmatch(value) is None:
        _fail(code)
    return value


def _record(value: Any, code: str) -> dict[str, Any]:
    if type(value) is not dict:
        _fail(code)
    return value


def _array(value: Any, code: str) -> list[Any]:
    if type(value) is not list:
        _fail(code)
    return value


def _stable_digest(value: Any) -> str:
    try:
        raw = json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeError):
        _fail("ADAPTER_V1_INPUT_INVALID")
    return sha256(raw).hexdigest()


def _rational(value: Any, *, duration: bool, code: str) -> dict[str, int]:
    item = _record(value, code)
    if set(item) != {"numerator", "denominator"}:
        _fail(code)
    numerator = item.get("numerator")
    denominator = item.get("denominator")
    if type(numerator) is not int or type(denominator) is not int or denominator <= 0:
        _fail(code)
    if duration and numerator <= 0:
        _fail(code)
    if not duration and numerator < 0:
        _fail(code)
    divisor = gcd(abs(numerator), denominator)
    numerator //= divisor
    denominator //= divisor
    if abs(numerator) > _SAFE_INT_MAX or denominator > _SAFE_INT_MAX:
        _fail(code)
    return {"numerator": numerator, "denominator": denominator}


def _compare(left: Mapping[str, int], right: Mapping[str, int]) -> int:
    lhs = left["numerator"] * right["denominator"]
    rhs = right["numerator"] * left["denominator"]
    return -1 if lhs < rhs else 1 if lhs > rhs else 0


def _add(left: Mapping[str, int], right: Mapping[str, int]) -> dict[str, int]:
    return _rational(
        {
            "numerator": left["numerator"] * right["denominator"] + right["numerator"] * left["denominator"],
            "denominator": left["denominator"] * right["denominator"],
        },
        duration=False,
        code="ADAPTER_V1_RATIONAL_INVALID",
    )


def _pitch(value: Any) -> dict[str, Any]:
    item = _record(value, "ADAPTER_V1_PITCH_UNSUPPORTED")
    if set(item) != {"step", "alter", "octave"}:
        _fail("ADAPTER_V1_PITCH_UNSUPPORTED")
    step = item.get("step")
    octave = item.get("octave")
    alter = _rational(item.get("alter"), duration=False, code="ADAPTER_V1_PITCH_UNSUPPORTED")
    if step not in {"A", "B", "C", "D", "E", "F", "G"}:
        _fail("ADAPTER_V1_PITCH_UNSUPPORTED")
    if alter["denominator"] != 1 or alter["numerator"] < -2 or alter["numerator"] > 2:
        _fail("ADAPTER_V1_PITCH_UNSUPPORTED")
    if type(octave) is not int or octave < -1 or octave > 9:
        _fail("ADAPTER_V1_PITCH_UNSUPPORTED")
    return {"step": step, "alter": alter["numerator"], "octave": octave}


def _voice_sort_key(value: str) -> tuple[int, int | str]:
    if value.isdigit():
        number = int(value)
        if number <= _SAFE_INT_MAX:
            return (0, number)
    return (1, value)


class _Ids:
    def __init__(self, reserved: list[str]) -> None:
        self.used: set[str] = set()
        for value in reserved:
            value = _core_id(value, "ADAPTER_V1_CORE_TARGET_INVALID")
            if value in self.used:
                _fail("ADAPTER_V1_CORE_TARGET_COLLISION")
            self.used.add(value)

    def claim(self, value: str, code: str = "ADAPTER_V1_CORE_ID_COLLISION") -> str:
        value = _core_id(value, "ADAPTER_V1_CORE_ID_INVALID")
        if value in self.used:
            _fail(code)
        self.used.add(value)
        return value

    def generated(self, kind: str, identity: Any) -> str:
        digest = _stable_digest([kind, identity])
        for attempt in range(64):
            suffix = digest[:24] if attempt == 0 else sha256(f"{digest}:{attempt}".encode("ascii")).hexdigest()[:24]
            candidate = f"sm-{kind}-{suffix}"
            if candidate not in self.used:
                self.used.add(candidate)
                return candidate
        _fail("ADAPTER_V1_CORE_ID_SPACE_EXHAUSTED")


@dataclass(frozen=True, slots=True)
class RealScoreRuntimeProjection:
    payload: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return deepcopy(self.payload)


def _binding_targets(payload: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for raw in _array(payload.get("reviewBindings"), "ADAPTER_V1_BINDINGS_INVALID"):
        item = _record(raw, "ADAPTER_V1_BINDINGS_INVALID")
        event_id = item.get("canonicalEventId")
        target = _record(item.get("coreTarget"), "ADAPTER_V1_BINDINGS_INVALID")
        if type(event_id) is not str:
            _fail("ADAPTER_V1_BINDINGS_INVALID")
        normalized = {key: value for key, value in target.items()}
        previous = result.get(event_id)
        if previous is not None and previous != normalized:
            _fail("ADAPTER_V1_BINDINGS_INVALID")
        result[event_id] = normalized
    return result


def _event_notation(event: Mapping[str, Any], target_event_id: str) -> dict[str, Any] | None:
    dots = event.get("dots")
    if type(dots) is not int or dots < 0 or dots > 3:
        _fail("ADAPTER_V1_DOTS_UNSUPPORTED")
    tuplet_raw = event.get("tuplet")
    tuplet = None
    if tuplet_raw is not None:
        item = _record(tuplet_raw, "ADAPTER_V1_TUPLET_UNSUPPORTED")
        if set(item) != {"actualNotes", "normalNotes"}:
            _fail("ADAPTER_V1_TUPLET_UNSUPPORTED")
        actual = item.get("actualNotes")
        normal = item.get("normalNotes")
        if type(actual) is not int or type(normal) is not int or not 1 <= actual <= 32 or not 1 <= normal <= 32:
            _fail("ADAPTER_V1_TUPLET_UNSUPPORTED")
        tuplet = {"actualNotes": actual, "normalNotes": normal, "marks": []}
    if dots == 0 and tuplet is None:
        return None
    return {
        "target": {"kind": "event", "eventId": target_event_id},
        "notation": {"dots": dots, "beams": [], "tuplet": tuplet},
    }


def _note_notation(event: Mapping[str, Any], event_id: str, note_id: str) -> dict[str, Any] | None:
    raw_ties = _array(event.get("ties"), "ADAPTER_V1_TIES_UNSUPPORTED")
    marks: list[dict[str, Any]] = []
    for tie in raw_ties:
        if tie == "start":
            marks.append({"number": 1, "type": "start"})
        elif tie == "stop":
            marks.append({"number": 1, "type": "stop"})
        elif tie == "continue":
            marks.extend(({"number": 1, "type": "stop"}, {"number": 1, "type": "start"}))
        else:
            _fail("ADAPTER_V1_TIES_UNSUPPORTED")
    keys = {(mark["number"], mark["type"]) for mark in marks}
    if len(keys) != len(marks):
        _fail("ADAPTER_V1_TIES_UNSUPPORTED")
    if not marks:
        return None
    return {
        "target": {"kind": "note", "eventId": event_id, "noteId": note_id},
        "notation": {"accidental": None, "ties": marks, "slurs": []},
    }


def _time_signature(value: Any) -> dict[str, int] | None:
    if value is None:
        return None
    item = _record(value, "ADAPTER_V1_TIME_SIGNATURE_UNSUPPORTED")
    if set(item) != {"beats", "beatType"}:
        _fail("ADAPTER_V1_TIME_SIGNATURE_UNSUPPORTED")
    beats_raw = item.get("beats")
    beat_type = item.get("beatType")
    if type(beats_raw) is not str or not beats_raw.isdigit():
        _fail("ADAPTER_V1_TIME_SIGNATURE_UNSUPPORTED")
    beats = int(beats_raw)
    if not 1 <= beats <= 32 or beat_type not in {1, 2, 4, 8, 16, 32, 64}:
        _fail("ADAPTER_V1_TIME_SIGNATURE_UNSUPPORTED")
    return {"beats": beats, "beatType": beat_type}


def _measure_notation(measure: Mapping[str, Any], measure_id: str) -> dict[str, Any] | None:
    if _array(measure.get("timeSignatureChanges"), "ADAPTER_V1_TIME_SIGNATURE_UNSUPPORTED"):
        _fail("ADAPTER_V1_TIME_SIGNATURE_UNSUPPORTED")
    time = _time_signature(measure.get("timeSignatureAtStart"))
    if time is None:
        return None
    return {
        "target": {"kind": "measure", "measureId": measure_id},
        "notation": {"timeSignature": time, "keySignature": None, "clef": None, "barlines": []},
    }


def _validate_event_capability(event: Mapping[str, Any]) -> None:
    kind = event.get("kind")
    if kind == "unpitched":
        _fail("ADAPTER_V1_UNPITCHED_UNSUPPORTED")
    if kind not in {"note", "rest"}:
        _fail("ADAPTER_V1_EVENT_KIND_UNSUPPORTED")
    if event.get("grace") is not False:
        _fail("ADAPTER_V1_GRACE_UNSUPPORTED")
    if event.get("tab") is not None:
        _fail("ADAPTER_V1_TAB_UNSUPPORTED")
    if kind == "note":
        if event.get("pitch") is None:
            _fail("ADAPTER_V1_PITCH_UNSUPPORTED")
        _pitch(event.get("pitch"))
    elif event.get("pitch") is not None:
        _fail("ADAPTER_V1_REST_PITCH_INVALID")
    _rational(event.get("onset"), duration=False, code="ADAPTER_V1_ONSET_INVALID")
    _rational(event.get("effectiveDuration"), duration=True, code="ADAPTER_V1_DURATION_INVALID")
    dots = event.get("dots")
    if type(dots) is not int or not 0 <= dots <= 3:
        _fail("ADAPTER_V1_DOTS_UNSUPPORTED")
    if event.get("tuplet") is not None:
        _event_notation(event, "placeholder")


def _project_measure_streams(
    *,
    part_identity: Any,
    measure: Mapping[str, Any],
    staff_ordinal: int,
    ids: _Ids,
    targets: Mapping[str, dict[str, str]],
    event_notations: list[dict[str, Any]],
    note_notations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    events = _array(measure.get("events"), "ADAPTER_V1_CANONICAL_SCORE_INVALID")
    by_voice: dict[str, list[Mapping[str, Any]]] = {}
    for raw in events:
        event = _record(raw, "ADAPTER_V1_CANONICAL_SCORE_INVALID")
        _validate_event_capability(event)
        if event.get("staff") != staff_ordinal:
            continue
        voice = event.get("voice")
        if type(voice) is not str or not voice:
            _fail("ADAPTER_V1_VOICE_INVALID")
        by_voice.setdefault(voice, []).append(event)

    if not by_voice:
        voice_id = ids.generated("voice", [part_identity, measure.get("measureId"), staff_ordinal, "empty"])
        return [{"id": voice_id, "ordinal": 1, "events": []}]

    voices: list[dict[str, Any]] = []
    for voice_ordinal, voice_label in enumerate(sorted(by_voice, key=_voice_sort_key), start=1):
        raw_events = sorted(
            by_voice[voice_label],
            key=lambda event: (
                _rational(event.get("onset"), duration=False, code="ADAPTER_V1_ONSET_INVALID")["numerator"]
                / _rational(event.get("onset"), duration=False, code="ADAPTER_V1_ONSET_INVALID")["denominator"],
                event.get("xmlOrder", 0),
            ),
        )
        grouped: list[list[Mapping[str, Any]]] = []
        seen_chords: set[str] = set()
        for event in raw_events:
            chord_group = event.get("chordGroup")
            chord_index = event.get("chordIndex")
            if chord_group is None:
                if chord_index is not None:
                    _fail("ADAPTER_V1_CHORD_INVALID")
                grouped.append([event])
                continue
            if event.get("kind") != "note" or type(chord_group) is not str or not chord_group or type(chord_index) is not int or chord_index < 0:
                _fail("ADAPTER_V1_CHORD_INVALID")
            if chord_group in seen_chords:
                continue
            members = [candidate for candidate in raw_events if candidate.get("chordGroup") == chord_group]
            seen_chords.add(chord_group)
            if len(members) < 2:
                _fail("ADAPTER_V1_CHORD_INVALID")
            indices = [member.get("chordIndex") for member in members]
            if any(type(index) is not int or index < 0 for index in indices) or len(set(indices)) != len(indices):
                _fail("ADAPTER_V1_CHORD_INVALID")
            members.sort(key=lambda member: member["chordIndex"])
            first_onset = _rational(members[0].get("onset"), duration=False, code="ADAPTER_V1_ONSET_INVALID")
            first_duration = _rational(members[0].get("effectiveDuration"), duration=True, code="ADAPTER_V1_DURATION_INVALID")
            for member in members[1:]:
                if _rational(member.get("onset"), duration=False, code="ADAPTER_V1_ONSET_INVALID") != first_onset:
                    _fail("ADAPTER_V1_CHORD_TIMING_MISMATCH")
                if _rational(member.get("effectiveDuration"), duration=True, code="ADAPTER_V1_DURATION_INVALID") != first_duration:
                    _fail("ADAPTER_V1_CHORD_TIMING_MISMATCH")
            grouped.append(members)

        projected_events: list[dict[str, Any]] = []
        for group in grouped:
            first = group[0]
            onset = _rational(first.get("onset"), duration=False, code="ADAPTER_V1_ONSET_INVALID")
            duration = _rational(first.get("effectiveDuration"), duration=True, code="ADAPTER_V1_DURATION_INVALID")
            if len(group) == 1:
                canonical_id = first.get("eventId")
                if type(canonical_id) is not str:
                    _fail("ADAPTER_V1_CANONICAL_EVENT_ID_INVALID")
                target = targets.get(canonical_id)
                if first.get("kind") == "rest":
                    if target is not None:
                        if target.get("kind") != "event":
                            _fail("ADAPTER_V1_TARGET_KIND_MISMATCH")
                        event_id = ids.claim(target["eventId"], "ADAPTER_V1_CORE_TARGET_COLLISION")
                    else:
                        event_id = ids.generated("event", [part_identity, measure.get("measureId"), staff_ordinal, voice_label, canonical_id])
                    projected = {"id": event_id, "kind": "rest", "onset": onset, "duration": duration}
                else:
                    if target is not None:
                        if target.get("kind") != "note":
                            _fail("ADAPTER_V1_TARGET_KIND_MISMATCH")
                        event_id = ids.claim(target["eventId"], "ADAPTER_V1_CORE_TARGET_COLLISION")
                        note_id = ids.claim(target["noteId"], "ADAPTER_V1_CORE_TARGET_COLLISION")
                    else:
                        event_id = ids.generated("event", [part_identity, measure.get("measureId"), staff_ordinal, voice_label, canonical_id])
                        note_id = ids.generated("note", [part_identity, measure.get("measureId"), staff_ordinal, voice_label, canonical_id])
                    projected = {
                        "id": event_id,
                        "kind": "note",
                        "onset": onset,
                        "duration": duration,
                        "note": {"id": note_id, "pitch": _pitch(first.get("pitch"))},
                    }
                    note_notation = _note_notation(first, event_id, note_id)
                    if note_notation is not None:
                        note_notations.append(note_notation)
                event_notation = _event_notation(first, event_id)
                if event_notation is not None:
                    event_notations.append(event_notation)
                projected_events.append(projected)
                continue

            bound_event_ids = {
                targets[event["eventId"]]["eventId"]
                for event in group
                if event.get("eventId") in targets
            }
            if len(bound_event_ids) > 1:
                _fail("ADAPTER_V1_CHORD_TARGET_MISMATCH")
            event_id = ids.claim(next(iter(bound_event_ids)), "ADAPTER_V1_CORE_TARGET_COLLISION") if bound_event_ids else ids.generated(
                "chord", [part_identity, measure.get("measureId"), staff_ordinal, voice_label, first.get("chordGroup")]
            )
            notes: list[dict[str, Any]] = []
            chord_notation_signature: tuple[int, str] | None = None
            for member in group:
                canonical_id = member.get("eventId")
                if type(canonical_id) is not str:
                    _fail("ADAPTER_V1_CANONICAL_EVENT_ID_INVALID")
                target = targets.get(canonical_id)
                if target is not None:
                    if target.get("kind") != "note" or target.get("eventId") != event_id:
                        _fail("ADAPTER_V1_CHORD_TARGET_MISMATCH")
                    note_id = ids.claim(target["noteId"], "ADAPTER_V1_CORE_TARGET_COLLISION")
                else:
                    note_id = ids.generated("note", [part_identity, measure.get("measureId"), staff_ordinal, voice_label, canonical_id])
                notes.append({"id": note_id, "pitch": _pitch(member.get("pitch"))})
                note_notation = _note_notation(member, event_id, note_id)
                if note_notation is not None:
                    note_notations.append(note_notation)
                dots = member.get("dots")
                tuplet_signature = json.dumps(member.get("tuplet"), sort_keys=True, separators=(",", ":"))
                signature = (dots, tuplet_signature)
                if chord_notation_signature is None:
                    chord_notation_signature = signature
                elif signature != chord_notation_signature:
                    _fail("ADAPTER_V1_CHORD_NOTATION_MISMATCH")
            event_notation = _event_notation(first, event_id)
            if event_notation is not None:
                event_notations.append(event_notation)
            projected_events.append({
                "id": event_id,
                "kind": "chord",
                "onset": onset,
                "duration": duration,
                "notes": notes,
            })

        projected_events.sort(key=lambda event: (event["onset"]["numerator"] / event["onset"]["denominator"], event["id"]))
        cursor = {"numerator": 0, "denominator": 1}
        for event in projected_events:
            if _compare(event["onset"], cursor) < 0:
                _fail("ADAPTER_V1_OVERLAPPING_EVENTS")
            cursor = _add(event["onset"], event["duration"])

        voice_id = ids.generated("voice", [part_identity, measure.get("measureId"), staff_ordinal, voice_label])
        voices.append({"id": voice_id, "ordinal": voice_ordinal, "events": projected_events})
    return voices


def build_real_score_runtime_projection(
    payload: Mapping[str, Any],
    *,
    musicxml: bytes,
    canonical_score: Mapping[str, Any],
) -> RealScoreRuntimeProjection:
    """Validate intake and produce a bounded in-memory Core runtime envelope."""

    try:
        receipt = validate_real_score_intake_v1_1(
            payload,
            musicxml=musicxml,
            canonical_score=canonical_score,
        )
    except RealScoreIntakeError:
        raise

    body = _record(payload, "ADAPTER_V1_INPUT_INVALID")
    if body.get("schemaVersion") != REAL_SCORE_INTAKE_VERSION_V1_1:
        _fail("ADAPTER_V1_INPUT_INVALID")
    document = _record(body.get("document"), "ADAPTER_V1_INPUT_INVALID")
    document_id = _core_id(document.get("documentId"), "ADAPTER_V1_DOCUMENT_ID_UNSUPPORTED")
    revision_id = _core_id(document.get("revision"), "ADAPTER_V1_REVISION_ID_UNSUPPORTED")

    targets = _binding_targets(body)
    reserved = [document_id, revision_id]
    for target in targets.values():
        reserved.append(target["eventId"])
        if target.get("kind") == "note":
            reserved.append(target["noteId"])
    ids = _Ids([])
    for value in reserved:
        ids.claim(value, "ADAPTER_V1_CORE_TARGET_COLLISION")

    score = _record(canonical_score, "ADAPTER_V1_CANONICAL_SCORE_INVALID")
    parts_raw = _array(score.get("parts"), "ADAPTER_V1_CANONICAL_SCORE_INVALID")
    if not parts_raw:
        _fail("ADAPTER_V1_CANONICAL_SCORE_INVALID")

    core_parts: list[dict[str, Any]] = []
    measure_notations: list[dict[str, Any]] = []
    event_notations: list[dict[str, Any]] = []
    note_notations: list[dict[str, Any]] = []

    for part_index, raw_part in enumerate(parts_raw, start=1):
        part = _record(raw_part, "ADAPTER_V1_CANONICAL_SCORE_INVALID")
        name = part.get("name")
        if type(name) is not str or not name:
            _fail("ADAPTER_V1_PART_NAME_REQUIRED")
        measures_raw = _array(part.get("measures"), "ADAPTER_V1_CANONICAL_SCORE_INVALID")
        if not measures_raw:
            _fail("ADAPTER_V1_CANONICAL_SCORE_INVALID")
        part_identity = [part_index, part.get("partId")]
        part_id = ids.generated("part", part_identity)

        staff_ordinals: set[int] = set()
        for raw_measure in measures_raw:
            measure = _record(raw_measure, "ADAPTER_V1_CANONICAL_SCORE_INVALID")
            for raw_event in _array(measure.get("events"), "ADAPTER_V1_CANONICAL_SCORE_INVALID"):
                event = _record(raw_event, "ADAPTER_V1_CANONICAL_SCORE_INVALID")
                staff = event.get("staff")
                if type(staff) is not int or staff < 1 or staff > 128:
                    _fail("ADAPTER_V1_STAFF_INVALID")
                staff_ordinals.add(staff)
        if not staff_ordinals:
            staff_ordinals.add(1)

        core_staves: list[dict[str, Any]] = []
        for staff_ordinal in sorted(staff_ordinals):
            staff_id = ids.generated("staff", [part_identity, staff_ordinal])
            core_measures: list[dict[str, Any]] = []
            for expected_ordinal, raw_measure in enumerate(measures_raw, start=1):
                measure = _record(raw_measure, "ADAPTER_V1_CANONICAL_SCORE_INVALID")
                ordinal = measure.get("ordinal")
                if type(ordinal) is not int or ordinal != expected_ordinal:
                    _fail("ADAPTER_V1_MEASURE_ORDINAL_UNSUPPORTED")
                number = measure.get("number")
                if type(number) is not str or not number:
                    _fail("ADAPTER_V1_MEASURE_NUMBER_INVALID")
                measure_id = ids.generated("measure", [part_identity, staff_ordinal, measure.get("measureId"), ordinal])
                notation = _measure_notation(measure, measure_id)
                if notation is not None:
                    measure_notations.append(notation)
                voices = _project_measure_streams(
                    part_identity=part_identity,
                    measure=measure,
                    staff_ordinal=staff_ordinal,
                    ids=ids,
                    targets=targets,
                    event_notations=event_notations,
                    note_notations=note_notations,
                )
                core_measures.append({
                    "id": measure_id,
                    "ordinal": ordinal,
                    "displayNumber": number,
                    "voices": voices,
                })
            core_staves.append({"id": staff_id, "ordinal": staff_ordinal, "measures": core_measures})
        core_parts.append({"id": part_id, "name": name, "staves": core_staves})

    core_score = {
        "schemaVersion": CORE_SCORE_SCHEMA_VERSION,
        "id": document_id,
        "revision": {"id": revision_id, "parentId": None},
        "source": {"sha256": receipt.canonical_sha256, "format": "canonical", "byteLength": None},
        "parts": core_parts,
    }

    existing_targets: set[tuple[str, str, str | None]] = set()
    for part in core_parts:
        for staff in part["staves"]:
            for measure in staff["measures"]:
                for voice in measure["voices"]:
                    for event in voice["events"]:
                        existing_targets.add(("event", event["id"], None))
                        if event["kind"] == "note":
                            existing_targets.add(("note", event["id"], event["note"]["id"]))
                        elif event["kind"] == "chord":
                            for note in event["notes"]:
                                existing_targets.add(("note", event["id"], note["id"]))

    issue_targets: list[dict[str, Any]] = []
    for raw in body["reviewBindings"]:
        target = raw["coreTarget"]
        key = (target["kind"], target["eventId"], target.get("noteId"))
        if key not in existing_targets:
            _fail("ADAPTER_V1_PROJECTED_TARGET_NOT_FOUND")
        issue_targets.append({
            "issueId": raw["issueId"],
            "canonicalEventId": raw["canonicalEventId"],
            "coreTarget": deepcopy(target),
        })

    notation = {
        "contractVersion": CORE_NOTATION_VERSION,
        "documentId": document_id,
        "revisionId": revision_id,
        "measures": measure_notations,
        "events": event_notations,
        "notes": note_notations,
    }
    authority = {
        "authoritative": False,
        "networkCapable": False,
        "persistent": False,
        "serverRevisionAuthority": False,
        "approvalAuthority": False,
        "publicationAuthority": False,
        "automaticCorrectionAuthority": False,
    }
    runtime_payload = {
        "version": REAL_SCORE_RUNTIME_VERSION,
        "coreCommit": CORE_COMMIT,
        "scoreSource": "canonical",
        "synthetic": False,
        "documentId": document_id,
        "revisionId": revision_id,
        "canonicalSha256": receipt.canonical_sha256,
        "score": core_score,
        "notation": notation,
        "issueTargets": issue_targets,
        "authority": authority,
    }
    return RealScoreRuntimeProjection(runtime_payload)
