from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256
import hmac
import json
import re
from types import MappingProxyType
from typing import Any, Mapping

from .contracts import ScoreEditCommand
from ._revision_store_common import RevisionScope

STATE_VERSION = "scoremosaic-review-musical-state-v1"
VALIDATION_VERSION = "scoremosaic-review-validation-report-v1"

_MAX_JSON_NODES = 600_000
_MAX_PARTS = 64
_MAX_MEASURES = 20_000
_MAX_EVENTS = 500_000
_MAX_DEPTH = 20
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_BEATS_RE = re.compile(r"^[1-9][0-9]*(\+[1-9][0-9]*)*$")

_TOP_KEYS = frozenset({
    "schemaVersion", "source", "rootType", "movementTitle", "parts",
    "diagnostics", "canonicalSha256",
})
_PART_KEYS = frozenset({"partId", "name", "ordinal", "measures"})
_MEASURE_KEYS = frozenset({
    "measureId", "number", "ordinal", "implicit", "divisionsAtStart",
    "timeSignatureAtStart", "expectedDuration", "observedDuration",
    "divisionsChanges", "timeSignatureChanges", "timingMovements", "events",
})
_EVENT_KEYS = frozenset({
    "eventId", "xmlOrder", "kind", "onset", "effectiveDuration",
    "writtenDuration", "writtenType", "dots", "tuplet", "voice", "staff",
    "pitch", "tab", "grace", "chordGroup", "chordIndex", "ties", "provenance",
})


class Stage8MaterializationError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> None:
    raise Stage8MaterializationError(code)


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
        _fail("MATERIALIZATION_NON_CANONICAL_VALUE")


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


def _bounded_walk(value: Any, *, depth: int = 0, counter: list[int] | None = None) -> None:
    if counter is None:
        counter = [0]
    counter[0] += 1
    if counter[0] > _MAX_JSON_NODES or depth > _MAX_DEPTH:
        _fail("CANONICAL_INPUT_TOO_COMPLEX")
    if isinstance(value, Mapping):
        if len(value) > 64:
            _fail("CANONICAL_INPUT_TOO_COMPLEX")
        for key, item in value.items():
            if not isinstance(key, str) or len(key) > 200:
                _fail("CANONICAL_INPUT_INVALID")
            _bounded_walk(item, depth=depth + 1, counter=counter)
    elif isinstance(value, (list, tuple)):
        if len(value) > _MAX_EVENTS:
            _fail("CANONICAL_INPUT_TOO_COMPLEX")
        for item in value:
            _bounded_walk(item, depth=depth + 1, counter=counter)
    elif isinstance(value, str):
        if len(value) > 4_000:
            _fail("CANONICAL_INPUT_TOO_COMPLEX")
    elif value is not None and not isinstance(value, (bool, int)):
        _fail("CANONICAL_INPUT_INVALID")


def _require_exact_keys(value: Any, keys: frozenset[str], code: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != set(keys):
        _fail(code)
    return value


def _require_id(value: Any, code: str) -> str:
    if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
        _fail(code)
    return value


def _require_text(value: Any, code: str, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        _fail(code)
    if any(ord(character) < 32 for character in value):
        _fail(code)
    return value


def _require_int(value: Any, code: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        _fail(code)
    return value


def _rational(value: Any, code: str, *, allow_zero: bool = True) -> dict[str, int]:
    value = _require_exact_keys(value, frozenset({"numerator", "denominator"}), code)
    numerator = _require_int(value["numerator"], code, -10**12, 10**12)
    denominator = _require_int(value["denominator"], code, 1, 1_000_000)
    fraction = Fraction(numerator, denominator)
    if not allow_zero and fraction <= 0:
        _fail(code)
    return {"numerator": fraction.numerator, "denominator": fraction.denominator}


def _fraction(value: Mapping[str, int]) -> Fraction:
    return Fraction(value["numerator"], value["denominator"])


def _time_signature(value: Any, code: str) -> dict[str, Any] | None:
    if value is None:
        return None
    value = _require_exact_keys(value, frozenset({"beats", "beatType"}), code)
    beats = _require_text(value["beats"], code, 40)
    if _BEATS_RE.fullmatch(beats) is None:
        _fail(code)
    beat_type = _require_int(value["beatType"], code, 1, 1024)
    return {"beats": beats, "beatType": beat_type}


def _expected_duration(time_signature: Mapping[str, Any]) -> dict[str, int]:
    beats = sum(int(piece) for piece in time_signature["beats"].split("+"))
    value = Fraction(beats * 4, time_signature["beatType"])
    return {"numerator": value.numerator, "denominator": value.denominator}


def _pitch(value: Any, code: str) -> dict[str, Any] | None:
    if value is None:
        return None
    value = _require_exact_keys(value, frozenset({"step", "alter", "octave"}), code)
    if value["step"] not in {"A", "B", "C", "D", "E", "F", "G"}:
        _fail(code)
    alter = _rational(value["alter"], code)
    if abs(_fraction(alter)) > 8:
        _fail(code)
    return {
        "step": value["step"],
        "alter": alter,
        "octave": _require_int(value["octave"], code, -2, 12),
    }


def _tab(value: Any, code: str) -> dict[str, int] | None:
    if value is None:
        return None
    value = _require_exact_keys(value, frozenset({"string", "fret"}), code)
    return {
        "string": _require_int(value["string"], code, 1, 24),
        "fret": _require_int(value["fret"], code, 0, 96),
    }


def _normalize_event(value: Any) -> dict[str, Any]:
    value = _require_exact_keys(value, _EVENT_KEYS, "CANONICAL_EVENT_INVALID")
    event_id = _require_id(value["eventId"], "CANONICAL_EVENT_INVALID")
    xml_order = _require_int(value["xmlOrder"], "CANONICAL_EVENT_INVALID", 0, 10**9)
    kind = value["kind"]
    if kind not in {"note", "rest", "unpitched"}:
        _fail("CANONICAL_EVENT_INVALID")
    onset = _rational(value["onset"], "CANONICAL_EVENT_INVALID")
    if _fraction(onset) < 0:
        _fail("CANONICAL_EVENT_INVALID")
    grace = value["grace"]
    if not isinstance(grace, bool):
        _fail("CANONICAL_EVENT_INVALID")
    effective = _rational(value["effectiveDuration"], "CANONICAL_EVENT_INVALID")
    if _fraction(effective) < 0 or (not grace and _fraction(effective) <= 0):
        _fail("CANONICAL_EVENT_INVALID")
    written_duration = None
    if value["writtenDuration"] is not None:
        written_duration = _rational(
            value["writtenDuration"], "CANONICAL_EVENT_INVALID", allow_zero=False
        )
    written_type = value["writtenType"]
    if written_type is not None:
        written_type = _require_text(written_type, "CANONICAL_EVENT_INVALID", 40)
    dots = _require_int(value["dots"], "CANONICAL_EVENT_INVALID", 0, 8)
    voice = _require_text(value["voice"], "CANONICAL_EVENT_INVALID", 40)
    staff = _require_int(value["staff"], "CANONICAL_EVENT_INVALID", 1, 128)
    pitch = _pitch(value["pitch"], "CANONICAL_EVENT_INVALID")
    tab = _tab(value["tab"], "CANONICAL_EVENT_INVALID")
    if kind == "rest" and pitch is not None:
        _fail("CANONICAL_EVENT_INVALID")
    if kind == "note" and pitch is None:
        _fail("CANONICAL_EVENT_INVALID")

    tuplet = value["tuplet"]
    if tuplet is not None:
        tuplet = _require_exact_keys(
            tuplet, frozenset({"actualNotes", "normalNotes"}), "CANONICAL_EVENT_INVALID"
        )
        tuplet = {
            "actualNotes": _require_int(tuplet["actualNotes"], "CANONICAL_EVENT_INVALID", 1, 1024),
            "normalNotes": _require_int(tuplet["normalNotes"], "CANONICAL_EVENT_INVALID", 1, 1024),
        }

    chord_group = value["chordGroup"]
    chord_index = value["chordIndex"]
    if chord_group is None:
        if chord_index is not None:
            _fail("CANONICAL_EVENT_INVALID")
    else:
        chord_group = _require_id(chord_group, "CANONICAL_EVENT_INVALID")
        chord_index = _require_int(chord_index, "CANONICAL_EVENT_INVALID", 0, 10**6)

    ties = value["ties"]
    if not isinstance(ties, list) or any(item not in {"start", "stop", "continue"} for item in ties):
        _fail("CANONICAL_EVENT_INVALID")
    if ties != sorted(set(ties)):
        _fail("CANONICAL_EVENT_INVALID")

    provenance = _require_exact_keys(
        value["provenance"], frozenset({"xmlPath", "sourceEventIndex"}), "CANONICAL_EVENT_INVALID"
    )
    provenance = {
        "xmlPath": _require_text(provenance["xmlPath"], "CANONICAL_EVENT_INVALID", 1000),
        "sourceEventIndex": _require_int(
            provenance["sourceEventIndex"], "CANONICAL_EVENT_INVALID", 0, 10**9
        ),
    }

    return {
        "eventId": event_id,
        "xmlOrder": xml_order,
        "kind": kind,
        "onset": onset,
        "effectiveDuration": effective,
        "writtenDuration": written_duration,
        "writtenType": written_type,
        "dots": dots,
        "tuplet": tuplet,
        "voice": voice,
        "staff": staff,
        "pitch": pitch,
        "tab": tab,
        "grace": grace,
        "chordGroup": chord_group,
        "chordIndex": chord_index,
        "ties": list(ties),
        "provenance": provenance,
    }


def _normalize_measure(value: Any) -> dict[str, Any]:
    value = _require_exact_keys(value, _MEASURE_KEYS, "CANONICAL_MEASURE_INVALID")
    measure_id = _require_id(value["measureId"], "CANONICAL_MEASURE_INVALID")
    number = _require_text(value["number"], "CANONICAL_MEASURE_INVALID", 40)
    ordinal = _require_int(value["ordinal"], "CANONICAL_MEASURE_INVALID", 1, 10**7)
    if not isinstance(value["implicit"], bool):
        _fail("CANONICAL_MEASURE_INVALID")
    time_signature = _time_signature(value["timeSignatureAtStart"], "CANONICAL_MEASURE_INVALID")
    expected = None
    if value["expectedDuration"] is not None:
        expected = _rational(value["expectedDuration"], "CANONICAL_MEASURE_INVALID", allow_zero=False)
    observed = _rational(value["observedDuration"], "CANONICAL_MEASURE_INVALID")
    if _fraction(observed) < 0:
        _fail("CANONICAL_MEASURE_INVALID")
    if not isinstance(value["timeSignatureChanges"], list):
        _fail("CANONICAL_MEASURE_INVALID")
    time_signature_changes = _deep_thaw(value["timeSignatureChanges"])
    events_raw = value["events"]
    if not isinstance(events_raw, list) or len(events_raw) > _MAX_EVENTS:
        _fail("CANONICAL_MEASURE_INVALID")
    events = [_normalize_event(event) for event in events_raw]
    if len({event["eventId"] for event in events}) != len(events):
        _fail("CANONICAL_EVENT_DUPLICATE")
    if [event["xmlOrder"] for event in events] != sorted(event["xmlOrder"] for event in events):
        _fail("CANONICAL_EVENT_ORDER_INVALID")
    return {
        "measureId": measure_id,
        "number": number,
        "ordinal": ordinal,
        "implicit": value["implicit"],
        "timeSignatureAtStart": time_signature,
        "expectedDuration": expected,
        "observedDuration": observed,
        "timeSignatureChanges": time_signature_changes,
        "events": events,
    }


def canonical_payload_sha256(payload: Mapping[str, Any]) -> str:
    if not isinstance(payload, Mapping):
        _fail("CANONICAL_INPUT_INVALID")
    _bounded_walk(payload)
    payload = _require_exact_keys(payload, _TOP_KEYS, "CANONICAL_INPUT_INVALID")
    claimed = payload["canonicalSha256"]
    if not isinstance(claimed, str) or _HASH_RE.fullmatch(claimed) is None:
        _fail("CANONICAL_HASH_INVALID")
    body = {key: _deep_thaw(value) for key, value in payload.items() if key != "canonicalSha256"}
    return _digest(body)


@dataclass(frozen=True)
class ReviewMusicalState:
    _payload: Mapping[str, Any]

    @property
    def state_sha256(self) -> str:
        return _digest(_deep_thaw(self._payload))

    def to_dict(self) -> dict[str, Any]:
        payload = _deep_thaw(self._payload)
        payload["stateSha256"] = self.state_sha256
        return payload


@dataclass(frozen=True)
class RevisionValidationReport:
    _payload: Mapping[str, Any]

    @property
    def report_sha256(self) -> str:
        return _digest(_deep_thaw(self._payload))

    @property
    def blocking_issue_count(self) -> int:
        return int(self._payload["blockingIssueCount"])

    @property
    def unresolved_issue_count(self) -> int:
        return int(self._payload["unresolvedIssueCount"])

    def to_dict(self) -> dict[str, Any]:
        payload = _deep_thaw(self._payload)
        payload["validationReportSha256"] = self.report_sha256
        return payload


@dataclass(frozen=True)
class AppliedEditResult:
    state: ReviewMusicalState
    validation: RevisionValidationReport
    matched_old_value_sha256: str


def materialize_canonical_state(
    scope: RevisionScope,
    canonical_payload: Mapping[str, Any],
) -> ReviewMusicalState:
    if not isinstance(scope, RevisionScope):
        _fail("MATERIALIZATION_SCOPE_INVALID")
    _bounded_walk(canonical_payload)
    canonical_payload = _require_exact_keys(
        canonical_payload, _TOP_KEYS, "CANONICAL_INPUT_INVALID"
    )
    if canonical_payload["schemaVersion"] != "1.0" or canonical_payload["rootType"] != "score-partwise":
        _fail("CANONICAL_INPUT_VERSION_INVALID")
    computed = canonical_payload_sha256(canonical_payload)
    if not hmac.compare_digest(computed, canonical_payload["canonicalSha256"]):
        _fail("CANONICAL_HASH_MISMATCH")
    if not hmac.compare_digest(computed, scope.base_canonical_sha256):
        _fail("CANONICAL_SCOPE_MISMATCH")
    parts_raw = canonical_payload["parts"]
    if not isinstance(parts_raw, list) or not parts_raw or len(parts_raw) > _MAX_PARTS:
        _fail("CANONICAL_PARTS_INVALID")
    parts: list[dict[str, Any]] = []
    measure_total = 0
    event_total = 0
    part_ids: set[str] = set()
    for part_raw in parts_raw:
        part_raw = _require_exact_keys(part_raw, _PART_KEYS, "CANONICAL_PART_INVALID")
        part_id = _require_id(part_raw["partId"], "CANONICAL_PART_INVALID")
        if part_id in part_ids:
            _fail("CANONICAL_PART_DUPLICATE")
        part_ids.add(part_id)
        measures_raw = part_raw["measures"]
        if not isinstance(measures_raw, list) or not measures_raw:
            _fail("CANONICAL_PART_INVALID")
        measures: list[dict[str, Any]] = []
        measure_ids: set[str] = set()
        for measure_raw in measures_raw:
            measure_total += 1
            if measure_total > _MAX_MEASURES:
                _fail("CANONICAL_INPUT_TOO_COMPLEX")
            measure = _normalize_measure(measure_raw)
            if measure["measureId"] in measure_ids:
                _fail("CANONICAL_MEASURE_DUPLICATE")
            measure_ids.add(measure["measureId"])
            event_total += len(measure["events"])
            if event_total > _MAX_EVENTS:
                _fail("CANONICAL_INPUT_TOO_COMPLEX")
            measures.append(measure)
        parts.append({
            "partId": part_id,
            "ordinal": _require_int(part_raw["ordinal"], "CANONICAL_PART_INVALID", 1, 10**6),
            "measures": measures,
        })
    payload = {
        "schemaVersion": STATE_VERSION,
        "baseCanonicalSha256": computed,
        "parts": parts,
    }
    return ReviewMusicalState(_deep_freeze(payload))


def field_value_sha256(value: Any) -> str:
    return _digest({"value": _deep_thaw(value)})


def _locate_event(
    state_payload: dict[str, Any], command: ScoreEditCommand
) -> tuple[dict[str, Any], list[dict[str, Any]], int, dict[str, Any]]:
    location = _deep_thaw(command.location)
    for part in state_payload["parts"]:
        if part["partId"] != location["partId"]:
            continue
        for measure in part["measures"]:
            if measure["measureId"] != location["measureId"]:
                continue
            for index, event in enumerate(measure["events"]):
                if event["eventId"] != location["eventId"]:
                    continue
                if (
                    event["staff"] != location["staff"]
                    or event["voice"] != location["voice"]
                    or event["onset"] != _rational(location["onset"], "COMMAND_LOCATION_INVALID")
                ):
                    _fail("EDIT_TARGET_LOCATION_STALE")
                return measure, measure["events"], index, event
            _fail("EDIT_TARGET_EVENT_NOT_FOUND")
        _fail("EDIT_TARGET_MEASURE_NOT_FOUND")
    _fail("EDIT_TARGET_PART_NOT_FOUND")


def _current_value(
    measure: Mapping[str, Any], event: Mapping[str, Any], operation_type: str
) -> Any:
    if operation_type == "set_pitch":
        return event["pitch"]
    if operation_type == "set_effective_duration":
        return event["effectiveDuration"]
    if operation_type == "set_written_type":
        return event["writtenType"]
    if operation_type == "set_dots":
        return event["dots"]
    if operation_type == "set_staff_voice":
        return {"staff": event["staff"], "voice": event["voice"]}
    if operation_type == "set_time_signature":
        return measure["timeSignatureAtStart"]
    if operation_type == "set_tab":
        return event["tab"]
    if operation_type == "remove_event":
        return _deep_thaw(event)
    _fail("EDIT_OPERATION_NOT_SUPPORTED")


def expected_old_value_sha256(
    state: ReviewMusicalState,
    *,
    location: Mapping[str, Any],
    operation_type: str,
) -> str:
    if not isinstance(state, ReviewMusicalState):
        _fail("MATERIALIZATION_STATE_INVALID")
    class _Probe:
        pass
    probe = _Probe()
    probe.location = location
    payload = _deep_thaw(state._payload)
    measure, _, _, event = _locate_event(payload, probe)  # type: ignore[arg-type]
    return field_value_sha256(_current_value(measure, event, operation_type))


def _apply_operation(
    measure: dict[str, Any], events: list[dict[str, Any]], index: int,
    event: dict[str, Any], operation: Mapping[str, Any]
) -> None:
    operation_type = operation["type"]
    value = _deep_thaw(operation["value"])
    if operation_type == "set_pitch":
        if event["kind"] != "note":
            _fail("EDIT_PITCH_REQUIRES_NOTE")
        event["pitch"] = _pitch(value, "EDIT_VALUE_INVALID")
    elif operation_type == "set_effective_duration":
        normalized = _rational(value, "EDIT_VALUE_INVALID")
        duration = _fraction(normalized)
        if duration < 0 or (not event["grace"] and duration <= 0):
            _fail("EDIT_DURATION_INVALID")
        event["effectiveDuration"] = normalized
    elif operation_type == "set_written_type":
        event["writtenType"] = _require_text(value, "EDIT_VALUE_INVALID", 40)
    elif operation_type == "set_dots":
        event["dots"] = _require_int(value, "EDIT_VALUE_INVALID", 0, 8)
    elif operation_type == "set_staff_voice":
        value = _require_exact_keys(value, frozenset({"staff", "voice"}), "EDIT_VALUE_INVALID")
        event["staff"] = _require_int(value["staff"], "EDIT_VALUE_INVALID", 1, 128)
        event["voice"] = _require_text(value["voice"], "EDIT_VALUE_INVALID", 40)
    elif operation_type == "set_time_signature":
        if measure["timeSignatureChanges"]:
            _fail("EDIT_MID_MEASURE_TIME_SIGNATURE_UNSUPPORTED")
        normalized = _time_signature(value, "EDIT_VALUE_INVALID")
        if normalized is None:
            _fail("EDIT_VALUE_INVALID")
        measure["timeSignatureAtStart"] = normalized
        measure["expectedDuration"] = _expected_duration(normalized)
    elif operation_type == "set_tab":
        if event["kind"] != "note":
            _fail("EDIT_TAB_REQUIRES_NOTE")
        event["tab"] = _tab(value, "EDIT_VALUE_INVALID")
    elif operation_type == "remove_event":
        if value is not None:
            _fail("EDIT_VALUE_INVALID")
        del events[index]
    else:
        _fail("EDIT_OPERATION_NOT_SUPPORTED")


def apply_score_edit_command(
    state: ReviewMusicalState,
    command: ScoreEditCommand,
) -> AppliedEditResult:
    if not isinstance(state, ReviewMusicalState):
        _fail("MATERIALIZATION_STATE_INVALID")
    if not isinstance(command, ScoreEditCommand):
        _fail("MATERIALIZATION_COMMAND_INVALID")
    payload = _deep_thaw(state._payload)
    if not hmac.compare_digest(command.base_canonical_sha256, payload["baseCanonicalSha256"]):
        _fail("EDIT_CANONICAL_MISMATCH")
    measure, events, index, event = _locate_event(payload, command)
    operation = _deep_thaw(command.operation)
    current = _current_value(measure, event, operation["type"])
    current_sha = field_value_sha256(current)
    if not hmac.compare_digest(command.old_value_sha256, current_sha):
        _fail("EDIT_OLD_VALUE_PRECONDITION_FAILED")
    _apply_operation(measure, events, index, event, operation)
    new_state = ReviewMusicalState(_deep_freeze(payload))
    report = validate_musical_state(new_state)
    return AppliedEditResult(new_state, report, current_sha)


def _issue(
    code: str,
    severity: str,
    *,
    part_id: str,
    measure_id: str,
    event_id: str | None = None,
    detail: str,
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "partId": part_id,
        "measureId": measure_id,
        "eventId": event_id,
        "detail": detail,
    }


def validate_musical_state(state: ReviewMusicalState) -> RevisionValidationReport:
    if not isinstance(state, ReviewMusicalState):
        _fail("MATERIALIZATION_STATE_INVALID")
    payload = _deep_thaw(state._payload)
    issues: list[dict[str, Any]] = []
    for part in payload["parts"]:
        for measure in part["measures"]:
            expected = (
                _fraction(measure["expectedDuration"])
                if measure["expectedDuration"] is not None
                else None
            )
            by_voice: dict[tuple[int, str], list[dict[str, Any]]] = {}
            chord_groups: dict[str, list[dict[str, Any]]] = {}
            max_end = Fraction(0, 1)
            for event in measure["events"]:
                onset = _fraction(event["onset"])
                duration = _fraction(event["effectiveDuration"])
                end = onset + duration
                if not event["grace"]:
                    max_end = max(max_end, end)
                if expected is not None and not event["grace"] and end > expected:
                    issues.append(_issue(
                        "MEASURE_OVERFLOW", "blocking", part_id=part["partId"],
                        measure_id=measure["measureId"], event_id=event["eventId"],
                        detail="Event ends after the measure's expected duration.",
                    ))
                by_voice.setdefault((event["staff"], event["voice"]), []).append(event)
                if event["chordGroup"] is not None:
                    chord_groups.setdefault(event["chordGroup"], []).append(event)

            if (
                expected is not None
                and not measure["implicit"]
                and max_end < expected
            ):
                issues.append(_issue(
                    "MEASURE_UNDERFILL", "warning", part_id=part["partId"],
                    measure_id=measure["measureId"],
                    detail="Observed event extent is shorter than the expected measure duration.",
                ))

            for (staff, voice), events in sorted(by_voice.items()):
                ordered = sorted(events, key=lambda item: (
                    _fraction(item["onset"]), item["xmlOrder"], item["eventId"]
                ))
                previous: dict[str, Any] | None = None
                for event in ordered:
                    if previous is not None:
                        previous_end = _fraction(previous["onset"]) + _fraction(previous["effectiveDuration"])
                        current_onset = _fraction(event["onset"])
                        same_chord = (
                            previous["chordGroup"] is not None
                            and previous["chordGroup"] == event["chordGroup"]
                            and previous["onset"] == event["onset"]
                        )
                        if current_onset < previous_end and not same_chord and not event["grace"]:
                            issues.append(_issue(
                                "VOICE_OVERLAP", "blocking", part_id=part["partId"],
                                measure_id=measure["measureId"], event_id=event["eventId"],
                                detail=f"Overlapping events in staff {staff}, voice {voice}.",
                            ))
                    if previous is None or (
                        _fraction(event["onset"]) + _fraction(event["effectiveDuration"])
                        > _fraction(previous["onset"]) + _fraction(previous["effectiveDuration"])
                    ):
                        previous = event

            for group_id, events in sorted(chord_groups.items()):
                anchor = events[0]
                for event in events[1:]:
                    if (
                        event["onset"] != anchor["onset"]
                        or event["staff"] != anchor["staff"]
                        or event["voice"] != anchor["voice"]
                    ):
                        issues.append(_issue(
                            "CHORD_ALIGNMENT_INVALID", "blocking", part_id=part["partId"],
                            measure_id=measure["measureId"], event_id=event["eventId"],
                            detail=f"Chord group {group_id} is not onset/staff/voice aligned.",
                        ))

    issues.sort(key=lambda item: (
        item["partId"], item["measureId"], item["code"], item["eventId"] or ""
    ))
    blocking = sum(1 for item in issues if item["severity"] == "blocking")
    report_payload = {
        "schemaVersion": VALIDATION_VERSION,
        "baseCanonicalSha256": payload["baseCanonicalSha256"],
        "stateSha256": state.state_sha256,
        "blockingIssueCount": blocking,
        "unresolvedIssueCount": len(issues),
        "issues": issues,
        "authoritativeCorrection": False,
        "approvalEligible": False,
        "publicationEligible": False,
    }
    return RevisionValidationReport(_deep_freeze(report_payload))


__all__ = [
    "STATE_VERSION",
    "VALIDATION_VERSION",
    "AppliedEditResult",
    "ReviewMusicalState",
    "RevisionValidationReport",
    "Stage8MaterializationError",
    "apply_score_edit_command",
    "canonical_payload_sha256",
    "expected_old_value_sha256",
    "field_value_sha256",
    "materialize_canonical_state",
    "validate_musical_state",
]
