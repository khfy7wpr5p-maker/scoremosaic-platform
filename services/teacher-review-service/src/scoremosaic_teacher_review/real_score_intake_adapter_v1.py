"""Bounded Real Score Intake Adapter v1.

This pure projection boundary revalidates Real Score Intake v1.1 and projects
the complete Canonical Score into the pinned ST Score Editor Core ScoreDocument
and NotationDocument runtime shapes. It performs no I/O, networking,
persistence, rendering, correction, approval, or publication.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256
import json
import re
from typing import Any, Mapping

from .real_score_intake_v1_1 import (
    REAL_SCORE_INTAKE_VERSION_V1_1,
    validate_real_score_intake_v1_1,
)

REAL_SCORE_RUNTIME_VERSION = "scoremosaic-real-score-runtime-v1"
CORE_COMMIT = "b317abef915d1e16b37572221a38feb3e504450d"
CORE_SCHEMA_VERSION = "1.0.0"
_CORE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_JS_SAFE = 2**53 - 1


class RealScoreIntakeAdapterError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _fail(code: str) -> None:
    raise RealScoreIntakeAdapterError(code)


def _record(value: Any, code: str) -> dict[str, Any]:
    if type(value) is not dict:
        _fail(code)
    return value


def _array(value: Any, code: str) -> list[Any]:
    if type(value) is not list:
        _fail(code)
    return value


def _core_id(value: Any, code: str) -> str:
    if type(value) is not str or _CORE_ID_RE.fullmatch(value) is None:
        _fail(code)
    return value


def _digest(value: Any) -> str:
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


def _fraction(value: Any, *, positive: bool, code: str) -> Fraction:
    item = _record(value, code)
    if set(item) != {"numerator", "denominator"}:
        _fail(code)
    numerator = item.get("numerator")
    denominator = item.get("denominator")
    if type(numerator) is not int or type(denominator) is not int or denominator <= 0:
        _fail(code)
    if positive and numerator <= 0:
        _fail(code)
    if not positive and numerator < 0:
        _fail(code)
    result = Fraction(numerator, denominator)
    if abs(result.numerator) > _JS_SAFE or result.denominator > _JS_SAFE:
        _fail(code)
    return result


def _rat(value: Fraction) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


def _pitch(value: Any) -> dict[str, Any]:
    item = _record(value, "ADAPTER_V1_PITCH_UNSUPPORTED")
    if set(item) != {"step", "alter", "octave"}:
        _fail("ADAPTER_V1_PITCH_UNSUPPORTED")
    step = item.get("step")
    octave = item.get("octave")
    alter = _fraction(
        item.get("alter"),
        positive=False,
        code="ADAPTER_V1_PITCH_UNSUPPORTED",
    )
    if step not in {"A", "B", "C", "D", "E", "F", "G"}:
        _fail("ADAPTER_V1_PITCH_UNSUPPORTED")
    if alter.denominator != 1 or not -2 <= alter.numerator <= 2:
        _fail("ADAPTER_V1_PITCH_UNSUPPORTED")
    if type(octave) is not int or not -1 <= octave <= 9:
        _fail("ADAPTER_V1_PITCH_UNSUPPORTED")
    return {"step": step, "alter": alter.numerator, "octave": octave}


class _IdSpace:
    def __init__(self) -> None:
        self.used: set[str] = set()
        self.reserved: set[str] = set()

    def claim(self, value: str, code: str = "ADAPTER_V1_CORE_ID_COLLISION") -> str:
        value = _core_id(value, "ADAPTER_V1_CORE_ID_INVALID")
        if value in self.used or value in self.reserved:
            _fail(code)
        self.used.add(value)
        return value

    def reserve(self, value: str) -> None:
        value = _core_id(value, "ADAPTER_V1_CORE_TARGET_INVALID")
        if value in self.used or value in self.reserved:
            _fail("ADAPTER_V1_CORE_TARGET_COLLISION")
        self.reserved.add(value)

    def consume(self, value: str) -> str:
        value = _core_id(value, "ADAPTER_V1_CORE_TARGET_INVALID")
        if value not in self.reserved or value in self.used:
            _fail("ADAPTER_V1_CORE_TARGET_COLLISION")
        self.reserved.remove(value)
        self.used.add(value)
        return value

    def generated(self, kind: str, identity: Any) -> str:
        seed = _digest([kind, identity])
        for attempt in range(64):
            suffix = (
                seed[:24]
                if attempt == 0
                else sha256(f"{seed}:{attempt}".encode("ascii")).hexdigest()[:24]
            )
            candidate = f"sm-{kind}-{suffix}"
            if candidate not in self.used and candidate not in self.reserved:
                self.used.add(candidate)
                return candidate
        _fail("ADAPTER_V1_CORE_ID_SPACE_EXHAUSTED")


@dataclass(frozen=True, slots=True)
class RealScoreRuntimeProjection:
    payload: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return deepcopy(self.payload)


def _targets(payload: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for raw in _array(payload.get("reviewBindings"), "ADAPTER_V1_BINDINGS_INVALID"):
        item = _record(raw, "ADAPTER_V1_BINDINGS_INVALID")
        canonical_id = item.get("canonicalEventId")
        target = _record(item.get("coreTarget"), "ADAPTER_V1_BINDINGS_INVALID")
        if type(canonical_id) is not str or target.get("kind") not in {"note", "event"}:
            _fail("ADAPTER_V1_BINDINGS_INVALID")
        normalized = deepcopy(target)
        previous = result.get(canonical_id)
        if previous is not None and previous != normalized:
            _fail("ADAPTER_V1_BINDINGS_INVALID")
        result[canonical_id] = normalized
    return result


def _reserve_targets(ids: _IdSpace, targets: Mapping[str, Mapping[str, str]]) -> None:
    event_ids = {
        _core_id(target.get("eventId"), "ADAPTER_V1_CORE_TARGET_INVALID")
        for target in targets.values()
    }
    note_ids = [
        _core_id(target.get("noteId"), "ADAPTER_V1_CORE_TARGET_INVALID")
        for target in targets.values()
        if target.get("kind") == "note"
    ]
    if len(note_ids) != len(set(note_ids)) or event_ids.intersection(note_ids):
        _fail("ADAPTER_V1_CORE_TARGET_COLLISION")
    for value in sorted(event_ids):
        ids.reserve(value)
    for value in sorted(note_ids):
        ids.reserve(value)


def _time_signature(value: Any) -> dict[str, int] | None:
    if value is None:
        return None
    item = _record(value, "ADAPTER_V1_TIME_SIGNATURE_UNSUPPORTED")
    if set(item) != {"beats", "beatType"}:
        _fail("ADAPTER_V1_TIME_SIGNATURE_UNSUPPORTED")
    beats_text = item.get("beats")
    beat_type = item.get("beatType")
    if type(beats_text) is not str or not beats_text.isdigit():
        _fail("ADAPTER_V1_TIME_SIGNATURE_UNSUPPORTED")
    beats = int(beats_text)
    if not 1 <= beats <= 32 or beat_type not in {1, 2, 4, 8, 16, 32, 64}:
        _fail("ADAPTER_V1_TIME_SIGNATURE_UNSUPPORTED")
    return {"beats": beats, "beatType": beat_type}


def _measure_time(measure: Mapping[str, Any]) -> dict[str, int] | None:
    initial = _time_signature(measure.get("timeSignatureAtStart"))
    changes = _array(
        measure.get("timeSignatureChanges"),
        "ADAPTER_V1_TIME_SIGNATURE_UNSUPPORTED",
    )
    last_at_zero = None
    for raw in changes:
        change = _record(raw, "ADAPTER_V1_TIME_SIGNATURE_UNSUPPORTED")
        onset = _fraction(
            change.get("onset"),
            positive=False,
            code="ADAPTER_V1_TIME_SIGNATURE_UNSUPPORTED",
        )
        if onset != 0:
            _fail("ADAPTER_V1_TIME_SIGNATURE_UNSUPPORTED")
        last_at_zero = _time_signature(change.get("timeSignature"))
    if last_at_zero is not None and last_at_zero != initial:
        _fail("ADAPTER_V1_TIME_SIGNATURE_UNSUPPORTED")
    return initial


def _event_capability(event: Mapping[str, Any]) -> None:
    kind = event.get("kind")
    if kind == "unpitched":
        _fail("ADAPTER_V1_UNPITCHED_UNSUPPORTED")
    if kind not in {"note", "rest"}:
        _fail("ADAPTER_V1_EVENT_KIND_UNSUPPORTED")
    if event.get("grace") is not False:
        _fail("ADAPTER_V1_GRACE_UNSUPPORTED")
    if event.get("tab") is not None:
        _fail("ADAPTER_V1_TAB_UNSUPPORTED")
    _fraction(event.get("onset"), positive=False, code="ADAPTER_V1_ONSET_INVALID")
    _fraction(
        event.get("effectiveDuration"),
        positive=True,
        code="ADAPTER_V1_DURATION_INVALID",
    )
    dots = event.get("dots")
    if type(dots) is not int or not 0 <= dots <= 3:
        _fail("ADAPTER_V1_DOTS_UNSUPPORTED")
    tuplet = event.get("tuplet")
    if tuplet is not None:
        item = _record(tuplet, "ADAPTER_V1_TUPLET_UNSUPPORTED")
        if set(item) != {"actualNotes", "normalNotes"}:
            _fail("ADAPTER_V1_TUPLET_UNSUPPORTED")
        actual, normal = item.get("actualNotes"), item.get("normalNotes")
        if (
            type(actual) is not int
            or type(normal) is not int
            or not 1 <= actual <= 32
            or not 1 <= normal <= 32
        ):
            _fail("ADAPTER_V1_TUPLET_UNSUPPORTED")
    if kind == "note":
        if event.get("pitch") is None:
            _fail("ADAPTER_V1_PITCH_UNSUPPORTED")
        _pitch(event.get("pitch"))
    elif event.get("pitch") is not None:
        _fail("ADAPTER_V1_REST_PITCH_INVALID")
    ties = _array(event.get("ties"), "ADAPTER_V1_TIES_UNSUPPORTED")
    if any(tie not in {"start", "stop", "continue"} for tie in ties):
        _fail("ADAPTER_V1_TIES_UNSUPPORTED")


def _measure_address(path: Mapping[str, str]) -> dict[str, str]:
    return {
        "contractVersion": CORE_SCHEMA_VERSION,
        "kind": "measure",
        "documentId": path["documentId"],
        "revisionId": path["revisionId"],
        "partId": path["partId"],
        "staffId": path["staffId"],
        "measureId": path["measureId"],
    }


def _event_address(path: Mapping[str, str], event_id: str) -> dict[str, str]:
    return {
        "contractVersion": CORE_SCHEMA_VERSION,
        "kind": "event",
        "documentId": path["documentId"],
        "revisionId": path["revisionId"],
        "partId": path["partId"],
        "staffId": path["staffId"],
        "measureId": path["measureId"],
        "voiceId": path["voiceId"],
        "eventId": event_id,
    }


def _note_address(path: Mapping[str, str], event_id: str, note_id: str) -> dict[str, str]:
    result = _event_address(path, event_id)
    result["kind"] = "note"
    result["noteId"] = note_id
    return result


def _event_notation(
    event: Mapping[str, Any],
    path: Mapping[str, str],
    event_id: str,
) -> dict[str, Any] | None:
    dots = event["dots"]
    raw_tuplet = event.get("tuplet")
    tuplet = (
        None
        if raw_tuplet is None
        else {
            "actualNotes": raw_tuplet["actualNotes"],
            "normalNotes": raw_tuplet["normalNotes"],
            "marks": [],
        }
    )
    if dots == 0 and tuplet is None:
        return None
    return {
        "target": _event_address(path, event_id),
        "notation": {"dots": dots, "beams": [], "tuplet": tuplet},
    }


def _note_notation(
    event: Mapping[str, Any],
    path: Mapping[str, str],
    event_id: str,
    note_id: str,
) -> dict[str, Any] | None:
    marks: list[dict[str, Any]] = []
    for tie in event["ties"]:
        if tie == "start":
            marks.append({"number": 1, "type": "start"})
        elif tie == "stop":
            marks.append({"number": 1, "type": "stop"})
        else:
            marks.extend(
                ({"number": 1, "type": "stop"}, {"number": 1, "type": "start"})
            )
    if len({(mark["number"], mark["type"]) for mark in marks}) != len(marks):
        _fail("ADAPTER_V1_TIES_UNSUPPORTED")
    if not marks:
        return None
    return {
        "target": _note_address(path, event_id, note_id),
        "notation": {"accidental": None, "ties": marks, "slurs": []},
    }


def _voice_key(value: str) -> tuple[int, int | str]:
    if value.isdigit() and int(value) <= _JS_SAFE:
        return (0, int(value))
    return (1, value)


def _group_events(events: list[Mapping[str, Any]]) -> list[list[Mapping[str, Any]]]:
    ordered = sorted(
        events,
        key=lambda event: (
            _fraction(event["onset"], positive=False, code="ADAPTER_V1_ONSET_INVALID"),
            event.get("xmlOrder", 0),
        ),
    )
    groups: list[list[Mapping[str, Any]]] = []
    consumed: set[str] = set()
    for event in ordered:
        canonical_id = event.get("eventId")
        if type(canonical_id) is not str:
            _fail("ADAPTER_V1_CANONICAL_EVENT_ID_INVALID")
        if canonical_id in consumed:
            continue
        chord_group = event.get("chordGroup")
        chord_index = event.get("chordIndex")
        if chord_group is None:
            if chord_index is not None:
                _fail("ADAPTER_V1_CHORD_INVALID")
            consumed.add(canonical_id)
            groups.append([event])
            continue
        if (
            event.get("kind") != "note"
            or type(chord_group) is not str
            or not chord_group
            or type(chord_index) is not int
            or chord_index < 0
        ):
            _fail("ADAPTER_V1_CHORD_INVALID")
        members = [candidate for candidate in ordered if candidate.get("chordGroup") == chord_group]
        if len(members) < 2:
            _fail("ADAPTER_V1_CHORD_INVALID")
        indices = [member.get("chordIndex") for member in members]
        if (
            any(type(index) is not int or index < 0 for index in indices)
            or len(set(indices)) != len(indices)
        ):
            _fail("ADAPTER_V1_CHORD_INVALID")
        members.sort(key=lambda member: member["chordIndex"])
        onset = _fraction(
            members[0]["onset"],
            positive=False,
            code="ADAPTER_V1_ONSET_INVALID",
        )
        duration = _fraction(
            members[0]["effectiveDuration"],
            positive=True,
            code="ADAPTER_V1_DURATION_INVALID",
        )
        for member in members:
            member_id = member.get("eventId")
            if type(member_id) is not str:
                _fail("ADAPTER_V1_CANONICAL_EVENT_ID_INVALID")
            if (
                _fraction(member["onset"], positive=False, code="ADAPTER_V1_ONSET_INVALID")
                != onset
                or _fraction(
                    member["effectiveDuration"],
                    positive=True,
                    code="ADAPTER_V1_DURATION_INVALID",
                )
                != duration
            ):
                _fail("ADAPTER_V1_CHORD_TIMING_MISMATCH")
            consumed.add(member_id)
        groups.append(members)
    return groups


def _stream(
    *,
    identity: Any,
    path: Mapping[str, str],
    events: list[Mapping[str, Any]],
    ids: _IdSpace,
    targets: Mapping[str, dict[str, str]],
    event_notation: list[dict[str, Any]],
    note_notation: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    projected: list[dict[str, Any]] = []
    for group in _group_events(events):
        first = group[0]
        onset = _fraction(first["onset"], positive=False, code="ADAPTER_V1_ONSET_INVALID")
        duration = _fraction(
            first["effectiveDuration"],
            positive=True,
            code="ADAPTER_V1_DURATION_INVALID",
        )
        if len(group) == 1:
            canonical_id = first["eventId"]
            target = targets.get(canonical_id)
            if first["kind"] == "rest":
                if target is not None and target.get("kind") != "event":
                    _fail("ADAPTER_V1_TARGET_KIND_MISMATCH")
                event_id = (
                    ids.consume(target["eventId"])
                    if target is not None
                    else ids.generated("event", [identity, canonical_id])
                )
                item = {
                    "id": event_id,
                    "kind": "rest",
                    "onset": _rat(onset),
                    "duration": _rat(duration),
                }
            else:
                if target is not None and target.get("kind") != "note":
                    _fail("ADAPTER_V1_TARGET_KIND_MISMATCH")
                if target is None:
                    event_id = ids.generated("event", [identity, canonical_id])
                    note_id = ids.generated("note", [identity, canonical_id])
                else:
                    event_id = ids.consume(target["eventId"])
                    note_id = ids.consume(target["noteId"])
                item = {
                    "id": event_id,
                    "kind": "note",
                    "onset": _rat(onset),
                    "duration": _rat(duration),
                    "note": {"id": note_id, "pitch": _pitch(first["pitch"])},
                }
                note_entry = _note_notation(first, path, event_id, note_id)
                if note_entry is not None:
                    note_notation.append(note_entry)
            event_entry = _event_notation(first, path, event_id)
            if event_entry is not None:
                event_notation.append(event_entry)
            projected.append(item)
            continue

        bound_event_ids = {
            targets[member["eventId"]]["eventId"]
            for member in group
            if member["eventId"] in targets
        }
        if len(bound_event_ids) > 1:
            _fail("ADAPTER_V1_CHORD_TARGET_MISMATCH")
        event_id = (
            ids.consume(next(iter(bound_event_ids)))
            if bound_event_ids
            else ids.generated("chord", [identity, first["chordGroup"]])
        )
        notes: list[dict[str, Any]] = []
        notation_signature = None
        for member in group:
            canonical_id = member["eventId"]
            target = targets.get(canonical_id)
            if target is not None:
                if target.get("kind") != "note" or target.get("eventId") != event_id:
                    _fail("ADAPTER_V1_CHORD_TARGET_MISMATCH")
                note_id = ids.consume(target["noteId"])
            else:
                note_id = ids.generated("note", [identity, canonical_id])
            notes.append({"id": note_id, "pitch": _pitch(member["pitch"])})
            note_entry = _note_notation(member, path, event_id, note_id)
            if note_entry is not None:
                note_notation.append(note_entry)
            signature = (
                member["dots"],
                json.dumps(member.get("tuplet"), sort_keys=True, separators=(",", ":")),
            )
            if notation_signature is None:
                notation_signature = signature
            elif notation_signature != signature:
                _fail("ADAPTER_V1_CHORD_NOTATION_MISMATCH")
        event_entry = _event_notation(first, path, event_id)
        if event_entry is not None:
            event_notation.append(event_entry)
        projected.append(
            {
                "id": event_id,
                "kind": "chord",
                "onset": _rat(onset),
                "duration": _rat(duration),
                "notes": notes,
            }
        )

    projected.sort(
        key=lambda event: (
            _fraction(event["onset"], positive=False, code="ADAPTER_V1_ONSET_INVALID"),
            event["id"],
        )
    )
    cursor = Fraction(0)
    for event in projected:
        onset = _fraction(event["onset"], positive=False, code="ADAPTER_V1_ONSET_INVALID")
        duration = _fraction(
            event["duration"],
            positive=True,
            code="ADAPTER_V1_DURATION_INVALID",
        )
        if onset < cursor:
            _fail("ADAPTER_V1_OVERLAPPING_EVENTS")
        cursor = onset + duration
    return projected


def _assert_diagnostic_coverage(score: Mapping[str, Any]) -> None:
    for raw in _array(score.get("diagnostics"), "ADAPTER_V1_CANONICAL_SCORE_INVALID"):
        diagnostic = _record(raw, "ADAPTER_V1_CANONICAL_SCORE_INVALID")
        if diagnostic.get("code") in {"ignored-attribute", "ignored-measure-element"}:
            _fail("ADAPTER_V1_NOTATION_COVERAGE_UNSUPPORTED")


def build_real_score_runtime_projection(
    payload: Mapping[str, Any],
    *,
    musicxml: bytes,
    canonical_score: Mapping[str, Any],
) -> RealScoreRuntimeProjection:
    receipt = validate_real_score_intake_v1_1(
        payload,
        musicxml=musicxml,
        canonical_score=canonical_score,
    )
    body = _record(payload, "ADAPTER_V1_INPUT_INVALID")
    if body.get("schemaVersion") != REAL_SCORE_INTAKE_VERSION_V1_1:
        _fail("ADAPTER_V1_INPUT_INVALID")
    document = _record(body.get("document"), "ADAPTER_V1_INPUT_INVALID")
    document_id = _core_id(
        document.get("documentId"),
        "ADAPTER_V1_DOCUMENT_ID_UNSUPPORTED",
    )
    revision_id = _core_id(
        document.get("revision"),
        "ADAPTER_V1_REVISION_ID_UNSUPPORTED",
    )
    score = _record(canonical_score, "ADAPTER_V1_CANONICAL_SCORE_INVALID")
    _assert_diagnostic_coverage(score)
    targets = _targets(body)

    ids = _IdSpace()
    ids.claim(document_id)
    ids.claim(revision_id)
    _reserve_targets(ids, targets)

    parts_raw = _array(score.get("parts"), "ADAPTER_V1_CANONICAL_SCORE_INVALID")
    if not parts_raw:
        _fail("ADAPTER_V1_CANONICAL_SCORE_INVALID")
    part_ordinals = [part.get("ordinal") for part in parts_raw if type(part) is dict]
    if (
        len(part_ordinals) != len(parts_raw)
        or any(type(value) is not int or value < 1 for value in part_ordinals)
        or len(set(part_ordinals)) != len(part_ordinals)
    ):
        _fail("ADAPTER_V1_PART_ORDINAL_INVALID")

    core_parts: list[dict[str, Any]] = []
    measure_notation: list[dict[str, Any]] = []
    event_notation: list[dict[str, Any]] = []
    note_notation: list[dict[str, Any]] = []

    for raw_part in sorted(parts_raw, key=lambda value: value["ordinal"]):
        part = _record(raw_part, "ADAPTER_V1_CANONICAL_SCORE_INVALID")
        name = part.get("name")
        if type(name) is not str or not name:
            _fail("ADAPTER_V1_PART_NAME_REQUIRED")
        measures = _array(part.get("measures"), "ADAPTER_V1_CANONICAL_SCORE_INVALID")
        if not measures:
            _fail("ADAPTER_V1_CANONICAL_SCORE_INVALID")
        ordinals = [measure.get("ordinal") for measure in measures if type(measure) is dict]
        if (
            len(ordinals) != len(measures)
            or any(type(value) is not int or value < 1 for value in ordinals)
            or len(set(ordinals)) != len(ordinals)
        ):
            _fail("ADAPTER_V1_MEASURE_ORDINAL_INVALID")
        measures = sorted(measures, key=lambda value: value["ordinal"])
        part_identity = [part.get("ordinal"), part.get("partId")]
        part_id = ids.generated("part", part_identity)

        staff_ordinals: set[int] = set()
        for measure in measures:
            for raw_event in _array(
                measure.get("events"),
                "ADAPTER_V1_CANONICAL_SCORE_INVALID",
            ):
                event = _record(raw_event, "ADAPTER_V1_CANONICAL_SCORE_INVALID")
                _event_capability(event)
                staff = event.get("staff")
                if type(staff) is not int or not 1 <= staff <= 128:
                    _fail("ADAPTER_V1_STAFF_INVALID")
                staff_ordinals.add(staff)
        if not staff_ordinals:
            staff_ordinals.add(1)

        core_staves: list[dict[str, Any]] = []
        for staff_ordinal in sorted(staff_ordinals):
            staff_id = ids.generated("staff", [part_identity, staff_ordinal])
            core_measures: list[dict[str, Any]] = []
            for measure in measures:
                number = measure.get("number")
                if type(number) is not str or not number:
                    _fail("ADAPTER_V1_MEASURE_NUMBER_INVALID")
                measure_id = ids.generated(
                    "measure",
                    [part_identity, staff_ordinal, measure.get("measureId"), measure["ordinal"]],
                )
                measure_path = {
                    "documentId": document_id,
                    "revisionId": revision_id,
                    "partId": part_id,
                    "staffId": staff_id,
                    "measureId": measure_id,
                }
                time = _measure_time(measure)
                if time is not None:
                    measure_notation.append(
                        {
                            "target": _measure_address(measure_path),
                            "notation": {
                                "timeSignature": time,
                                "keySignature": None,
                                "clef": None,
                                "barlines": [],
                            },
                        }
                    )

                by_voice: dict[str, list[Mapping[str, Any]]] = {}
                for event in measure["events"]:
                    if event.get("staff") != staff_ordinal:
                        continue
                    voice = event.get("voice")
                    if type(voice) is not str or not voice:
                        _fail("ADAPTER_V1_VOICE_INVALID")
                    by_voice.setdefault(voice, []).append(event)
                core_voices: list[dict[str, Any]] = []
                if not by_voice:
                    core_voices.append(
                        {
                            "id": ids.generated(
                                "voice",
                                [part_identity, staff_ordinal, measure.get("measureId"), "empty"],
                            ),
                            "ordinal": 1,
                            "events": [],
                        }
                    )
                else:
                    for voice_ordinal, voice_label in enumerate(
                        sorted(by_voice, key=_voice_key),
                        start=1,
                    ):
                        identity = [
                            part_identity,
                            staff_ordinal,
                            measure.get("measureId"),
                            voice_label,
                        ]
                        voice_id = ids.generated("voice", identity)
                        stream_path = dict(measure_path)
                        stream_path["voiceId"] = voice_id
                        core_voices.append(
                            {
                                "id": voice_id,
                                "ordinal": voice_ordinal,
                                "events": _stream(
                                    identity=identity,
                                    path=stream_path,
                                    events=by_voice[voice_label],
                                    ids=ids,
                                    targets=targets,
                                    event_notation=event_notation,
                                    note_notation=note_notation,
                                ),
                            }
                        )
                core_measures.append(
                    {
                        "id": measure_id,
                        "ordinal": measure["ordinal"],
                        "displayNumber": number,
                        "voices": core_voices,
                    }
                )
            core_staves.append(
                {"id": staff_id, "ordinal": staff_ordinal, "measures": core_measures}
            )
        core_parts.append({"id": part_id, "name": name, "staves": core_staves})

    if ids.reserved:
        _fail("ADAPTER_V1_PROJECTED_TARGET_NOT_FOUND")

    core_score = {
        "schemaVersion": CORE_SCHEMA_VERSION,
        "id": document_id,
        "revision": {"id": revision_id, "parentId": None},
        "source": {
            "sha256": receipt.canonical_sha256,
            "format": "canonical",
            "byteLength": None,
        },
        "parts": core_parts,
    }
    notation = {
        "contractVersion": CORE_SCHEMA_VERSION,
        "documentId": document_id,
        "revisionId": revision_id,
        "measures": measure_notation,
        "events": event_notation,
        "notes": note_notation,
    }
    issue_targets = [
        {
            "issueId": item["issueId"],
            "canonicalEventId": item["canonicalEventId"],
            "coreTarget": deepcopy(item["coreTarget"]),
        }
        for item in body["reviewBindings"]
    ]
    runtime = {
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
        "authority": {
            "authoritative": False,
            "networkCapable": False,
            "persistent": False,
            "serverRevisionAuthority": False,
            "approvalAuthority": False,
            "publicationAuthority": False,
            "automaticCorrectionAuthority": False,
        },
    }
    return RealScoreRuntimeProjection(runtime)
