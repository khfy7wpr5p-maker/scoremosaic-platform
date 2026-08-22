"""Deterministic Stage 8 teacher-score materialization and validation.

This module is intentionally private. It creates no route, grants no authority,
and never mutates an upstream Canonical Score artifact in place.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Any, Mapping

from .contracts import ScoreEditCommand, Stage8ContractError

OLD_VALUE_PURPOSE = b"scoremosaic/teacher-review/old-value/v1\x00"
VALIDATION_VERSION = "scoremosaic-revision-validation-v1"

_SCORE_KEYS = frozenset(
    {"schemaVersion", "source", "rootType", "movementTitle", "parts", "diagnostics"}
)
_PART_KEYS = frozenset({"partId", "name", "ordinal", "measures"})
_MEASURE_KEYS = frozenset(
    {
        "measureId",
        "number",
        "ordinal",
        "implicit",
        "divisionsAtStart",
        "timeSignatureAtStart",
        "expectedDuration",
        "observedDuration",
        "divisionsChanges",
        "timeSignatureChanges",
        "timingMovements",
        "events",
    }
)
_EVENT_KEYS = frozenset(
    {
        "eventId",
        "xmlOrder",
        "kind",
        "onset",
        "effectiveDuration",
        "writtenDuration",
        "writtenType",
        "dots",
        "tuplet",
        "voice",
        "staff",
        "pitch",
        "tab",
        "grace",
        "chordGroup",
        "chordIndex",
        "ties",
        "provenance",
    }
)
_NOTE_TYPE_QUARTERS = {
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


def _fail(code: str) -> None:
    raise Stage8ContractError(code)


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return value


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            _json_ready(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError):
        _fail("MATERIALIZATION_NON_CANONICAL_VALUE")


def _sha(value: Any) -> str:
    return sha256(_canonical_json(value)).hexdigest()


def _clone(value: Any) -> Any:
    try:
        return json.loads(_canonical_json(value).decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        _fail("MATERIALIZATION_NON_CANONICAL_VALUE")


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _fraction(value: Any, code: str) -> Fraction:
    if not isinstance(value, Mapping) or set(value) != {"numerator", "denominator"}:
        _fail(code)
    numerator = value["numerator"]
    denominator = value["denominator"]
    if (
        isinstance(numerator, bool)
        or not isinstance(numerator, int)
        or isinstance(denominator, bool)
        or not isinstance(denominator, int)
        or denominator <= 0
    ):
        _fail(code)
    return Fraction(numerator, denominator)


def _rational(value: Fraction) -> dict[str, int]:
    value = Fraction(value)
    return {"numerator": value.numerator, "denominator": value.denominator}


def musical_value_sha256(value: Any) -> str:
    """Purpose-separated deterministic digest used by ScoreEditCommand.oldValueSha256."""

    return sha256(OLD_VALUE_PURPOSE + _canonical_json(value)).hexdigest()


@dataclass(frozen=True)
class TeacherMusicalState:
    base_canonical_sha256: str
    current_revision_id: str | None
    current_revision_sha256: str | None
    score: Mapping[str, Any]
    musical_state_sha256: str

    def score_dict(self) -> dict[str, Any]:
        return _thaw(self.score)


@dataclass(frozen=True)
class RevisionValidationReport:
    record: Mapping[str, Any]

    @property
    def report_sha256(self) -> str:
        return self.record["validationReportSha256"]

    @property
    def blocking_issue_count(self) -> int:
        return self.record["blockingIssueCount"]

    @property
    def unresolved_issue_count(self) -> int:
        return self.record["unresolvedIssueCount"]

    @property
    def valid(self) -> bool:
        return self.blocking_issue_count == 0

    def to_dict(self) -> dict[str, Any]:
        return _thaw(self.record)


@dataclass(frozen=True)
class MaterializedEdit:
    score: Mapping[str, Any]
    musical_state_sha256: str
    validation: RevisionValidationReport

    def score_dict(self) -> dict[str, Any]:
        return _thaw(self.score)


def canonical_base_state(canonical_payload: Mapping[str, Any]) -> TeacherMusicalState:
    if not isinstance(canonical_payload, Mapping):
        _fail("MATERIALIZATION_CANONICAL_TYPE_INVALID")
    payload = _clone(canonical_payload)
    if set(payload) != _SCORE_KEYS | {"canonicalSha256"}:
        _fail("MATERIALIZATION_CANONICAL_SCHEMA_INVALID")
    claimed = payload.pop("canonicalSha256")
    if not isinstance(claimed, str) or len(claimed) != 64:
        _fail("MATERIALIZATION_CANONICAL_HASH_INVALID")
    actual = _sha(payload)
    if claimed != actual:
        _fail("MATERIALIZATION_CANONICAL_HASH_MISMATCH")
    # Independently re-check the closed Canonical projection. Musical findings
    # remain evidence for the reviewer and do not make the immutable base unreadable.
    validate_teacher_score(payload)
    return TeacherMusicalState(
        base_canonical_sha256=claimed,
        current_revision_id=None,
        current_revision_sha256=None,
        score=_freeze(payload),
        musical_state_sha256=actual,
    )


def restore_teacher_state(
    *,
    base_canonical_sha256: str,
    revision_id: str,
    revision_sha256: str,
    score_payload: Mapping[str, Any],
    expected_musical_state_sha256: str,
) -> TeacherMusicalState:
    if not all(
        isinstance(value, str) and value
        for value in (base_canonical_sha256, revision_id, revision_sha256, expected_musical_state_sha256)
    ):
        _fail("MATERIALIZATION_RESTORE_IDENTITY_INVALID")
    payload = _clone(score_payload)
    if set(payload) != _SCORE_KEYS:
        _fail("MATERIALIZATION_RESTORE_SCHEMA_INVALID")
    if _sha(payload) != expected_musical_state_sha256:
        _fail("MATERIALIZATION_RESTORE_HASH_MISMATCH")
    return TeacherMusicalState(
        base_canonical_sha256=base_canonical_sha256,
        current_revision_id=revision_id,
        current_revision_sha256=revision_sha256,
        score=_freeze(payload),
        musical_state_sha256=expected_musical_state_sha256,
    )


def _find_target(score: dict[str, Any], location: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    matching_parts = [part for part in score["parts"] if part.get("partId") == location["partId"]]
    if len(matching_parts) != 1:
        _fail("MATERIALIZATION_PART_NOT_FOUND")
    matching_measures = [
        measure
        for measure in matching_parts[0]["measures"]
        if measure.get("measureId") == location["measureId"]
    ]
    if len(matching_measures) != 1:
        _fail("MATERIALIZATION_MEASURE_NOT_FOUND")
    measure = matching_measures[0]
    matching_events = [event for event in measure["events"] if event.get("eventId") == location["eventId"]]
    if len(matching_events) != 1:
        _fail("MATERIALIZATION_EVENT_NOT_FOUND")
    event = matching_events[0]
    if event.get("staff") != location["staff"] or event.get("voice") != location["voice"]:
        _fail("MATERIALIZATION_LOCATION_MISMATCH")
    if _fraction(event.get("onset"), "MATERIALIZATION_LOCATION_INVALID") != _fraction(
        location["onset"], "MATERIALIZATION_LOCATION_INVALID"
    ):
        _fail("MATERIALIZATION_LOCATION_MISMATCH")
    return measure, event


def _written_duration(written_type: str | None, dots: int) -> dict[str, int] | None:
    if written_type is None:
        return None
    base = _NOTE_TYPE_QUARTERS.get(written_type)
    if base is None:
        _fail("MATERIALIZATION_WRITTEN_TYPE_UNSUPPORTED")
    multiplier = sum((Fraction(1, 2**index) for index in range(dots + 1)), Fraction(0))
    return _rational(base * multiplier)


def _time_signature_duration(value: Mapping[str, Any]) -> Fraction:
    beats = value.get("beats")
    beat_type = value.get("beatType")
    if not isinstance(beats, str) or isinstance(beat_type, bool) or not isinstance(beat_type, int) or beat_type <= 0:
        _fail("MATERIALIZATION_TIME_SIGNATURE_INVALID")
    try:
        beat_count = sum(int(item) for item in beats.split("+"))
    except ValueError:
        _fail("MATERIALIZATION_TIME_SIGNATURE_INVALID")
    if beat_count <= 0:
        _fail("MATERIALIZATION_TIME_SIGNATURE_INVALID")
    return Fraction(beat_count * 4, beat_type)


def _current_target_value(
    measure: dict[str, Any],
    event: dict[str, Any],
    operation_type: str,
    location: Mapping[str, Any],
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
    if operation_type == "set_tab":
        return event["tab"]
    if operation_type == "remove_event":
        return event
    if operation_type == "set_time_signature":
        onset = _fraction(location["onset"], "MATERIALIZATION_LOCATION_INVALID")
        matches = [
            item
            for item in measure["timeSignatureChanges"]
            if _fraction(item["onset"], "MATERIALIZATION_TIME_SIGNATURE_INVALID") == onset
        ]
        if len(matches) == 1:
            return matches[0]["timeSignature"]
        if onset == 0 and not matches:
            return measure["timeSignatureAtStart"]
        _fail("MATERIALIZATION_TIME_SIGNATURE_TARGET_INVALID")
    _fail("MATERIALIZATION_OPERATION_NOT_ALLOWED")


def _apply_operation(
    measure: dict[str, Any],
    event: dict[str, Any],
    operation_type: str,
    new_value: Any,
    location: Mapping[str, Any],
) -> None:
    if operation_type == "set_pitch":
        if event["kind"] != "note":
            _fail("MATERIALIZATION_PITCH_TARGET_INVALID")
        event["pitch"] = _clone(new_value)
        return
    if operation_type == "set_effective_duration":
        event["effectiveDuration"] = _rational(
            _fraction(new_value, "MATERIALIZATION_DURATION_INVALID")
        )
        return
    if operation_type == "set_written_type":
        event["writtenType"] = new_value
        event["writtenDuration"] = _written_duration(new_value, event["dots"])
        return
    if operation_type == "set_dots":
        event["dots"] = new_value
        event["writtenDuration"] = _written_duration(event["writtenType"], new_value)
        return
    if operation_type == "set_staff_voice":
        event["staff"] = new_value["staff"]
        event["voice"] = new_value["voice"]
        return
    if operation_type == "set_tab":
        if event["kind"] != "note":
            _fail("MATERIALIZATION_TAB_TARGET_INVALID")
        event["tab"] = _clone(new_value)
        return
    if operation_type == "remove_event":
        measure["events"] = [item for item in measure["events"] if item["eventId"] != event["eventId"]]
        return
    if operation_type == "set_time_signature":
        onset = _fraction(location["onset"], "MATERIALIZATION_LOCATION_INVALID")
        normalized = _clone(new_value)
        matches = [
            item
            for item in measure["timeSignatureChanges"]
            if _fraction(item["onset"], "MATERIALIZATION_TIME_SIGNATURE_INVALID") == onset
        ]
        if len(matches) == 1:
            matches[0]["timeSignature"] = normalized
        elif onset == 0 and not matches:
            measure["timeSignatureAtStart"] = normalized
        else:
            _fail("MATERIALIZATION_TIME_SIGNATURE_TARGET_INVALID")
        if onset == 0:
            measure["timeSignatureAtStart"] = normalized
            measure["expectedDuration"] = _rational(_time_signature_duration(normalized))
        return
    _fail("MATERIALIZATION_OPERATION_NOT_ALLOWED")


def materialize_score_edit(
    state: TeacherMusicalState,
    command: ScoreEditCommand,
) -> MaterializedEdit:
    if not isinstance(state, TeacherMusicalState):
        _fail("MATERIALIZATION_STATE_TYPE_INVALID")
    if not isinstance(command, ScoreEditCommand):
        _fail("MATERIALIZATION_COMMAND_TYPE_INVALID")
    if command.base_canonical_sha256 != state.base_canonical_sha256:
        _fail("MATERIALIZATION_BASE_CANONICAL_MISMATCH")
    if (
        command.base_revision_id != state.current_revision_id
        or command.base_revision_sha256 != state.current_revision_sha256
    ):
        _fail("MATERIALIZATION_STALE_PARENT")

    score = state.score_dict()
    measure, event = _find_target(score, command.location)
    op_type = command.operation["type"]
    old_value = _current_target_value(measure, event, op_type, command.location)
    if musical_value_sha256(old_value) != command.old_value_sha256:
        _fail("MATERIALIZATION_OLD_VALUE_MISMATCH")

    _apply_operation(measure, event, op_type, command.operation["value"], command.location)
    validation = validate_teacher_score(score)
    return MaterializedEdit(
        score=_freeze(score),
        musical_state_sha256=_sha(score),
        validation=validation,
    )


def _add_issue(
    issues: list[dict[str, Any]],
    *,
    code: str,
    path: str,
    blocking: bool = True,
) -> None:
    issues.append({"code": code, "path": path, "blocking": blocking})


def _validate_score_shape(score: Any) -> dict[str, Any]:
    if not isinstance(score, Mapping):
        _fail("VALIDATION_SCORE_TYPE_INVALID")
    cloned = _clone(score)
    if set(cloned) != _SCORE_KEYS:
        _fail("VALIDATION_SCORE_SCHEMA_INVALID")
    if cloned["schemaVersion"] != "1.0" or cloned["rootType"] != "score-partwise":
        _fail("VALIDATION_SCORE_VERSION_INVALID")
    if not isinstance(cloned["parts"], list) or not cloned["parts"]:
        _fail("VALIDATION_SCORE_PARTS_INVALID")
    return cloned


def validate_teacher_score(score: Mapping[str, Any]) -> RevisionValidationReport:
    """Validate deterministic structural/musical invariants without repairing them."""

    payload = _validate_score_shape(score)
    issues: list[dict[str, Any]] = []
    part_ids: set[str] = set()

    for p_index, part in enumerate(payload["parts"]):
        p_path = f"/parts/{p_index}"
        if not isinstance(part, dict) or set(part) != _PART_KEYS:
            _fail("VALIDATION_PART_SCHEMA_INVALID")
        part_id = part["partId"]
        if not isinstance(part_id, str) or not part_id or part_id in part_ids:
            _add_issue(issues, code="DUPLICATE_OR_INVALID_PART_ID", path=p_path)
        else:
            part_ids.add(part_id)
        if not isinstance(part["measures"], list) or not part["measures"]:
            _add_issue(issues, code="PART_WITHOUT_MEASURES", path=p_path)
            continue

        measure_ids: set[str] = set()
        for m_index, measure in enumerate(part["measures"]):
            m_path = f"{p_path}/measures/{m_index}"
            if not isinstance(measure, dict) or set(measure) != _MEASURE_KEYS:
                _fail("VALIDATION_MEASURE_SCHEMA_INVALID")
            measure_id = measure["measureId"]
            if not isinstance(measure_id, str) or not measure_id or measure_id in measure_ids:
                _add_issue(issues, code="DUPLICATE_OR_INVALID_MEASURE_ID", path=m_path)
            else:
                measure_ids.add(measure_id)

            expected = (
                None
                if measure["expectedDuration"] is None
                else _fraction(measure["expectedDuration"], "VALIDATION_RATIONAL_INVALID")
            )
            observed = _fraction(measure["observedDuration"], "VALIDATION_RATIONAL_INVALID")
            if observed < 0:
                _add_issue(issues, code="NEGATIVE_OBSERVED_DURATION", path=m_path)
            if expected is not None and expected <= 0:
                _add_issue(issues, code="INVALID_EXPECTED_DURATION", path=m_path)
            if expected is not None and observed != expected:
                _add_issue(issues, code="MEASURE_DURATION_MISMATCH", path=m_path)

            active_time = measure["timeSignatureAtStart"]
            if active_time is not None and expected is not None:
                if _time_signature_duration(active_time) != expected:
                    _add_issue(issues, code="METER_EXPECTED_DURATION_MISMATCH", path=m_path)

            event_ids: set[str] = set()
            previous_order = -1
            voice_events: dict[tuple[int, str], list[tuple[Fraction, Fraction, str | None, int | None, str]]] = {}
            chord_groups: dict[str, list[tuple[Fraction, int | None, str]]] = {}

            for e_index, event in enumerate(measure["events"]):
                e_path = f"{m_path}/events/{e_index}"
                if not isinstance(event, dict) or set(event) != _EVENT_KEYS:
                    _fail("VALIDATION_EVENT_SCHEMA_INVALID")
                event_id = event["eventId"]
                if not isinstance(event_id, str) or not event_id or event_id in event_ids:
                    _add_issue(issues, code="DUPLICATE_OR_INVALID_EVENT_ID", path=e_path)
                else:
                    event_ids.add(event_id)

                xml_order = event["xmlOrder"]
                if isinstance(xml_order, bool) or not isinstance(xml_order, int) or xml_order < 0 or xml_order < previous_order:
                    _add_issue(issues, code="EVENT_XML_ORDER_INVALID", path=e_path)
                else:
                    previous_order = xml_order

                onset = _fraction(event["onset"], "VALIDATION_RATIONAL_INVALID")
                duration = _fraction(event["effectiveDuration"], "VALIDATION_RATIONAL_INVALID")
                if onset < 0:
                    _add_issue(issues, code="NEGATIVE_EVENT_ONSET", path=e_path)
                if duration < 0 or (duration == 0 and not event["grace"]):
                    _add_issue(issues, code="INVALID_EFFECTIVE_DURATION", path=e_path)

                kind = event["kind"]
                if kind not in {"note", "rest", "unpitched"}:
                    _add_issue(issues, code="EVENT_KIND_INVALID", path=e_path)
                if kind == "rest" and event["pitch"] is not None:
                    _add_issue(issues, code="REST_WITH_PITCH", path=e_path)
                if kind == "note" and event["pitch"] is None:
                    _add_issue(issues, code="NOTE_WITHOUT_PITCH", path=e_path)

                dots = event["dots"]
                if isinstance(dots, bool) or not isinstance(dots, int) or dots < 0 or dots > 8:
                    _add_issue(issues, code="DOT_COUNT_INVALID", path=e_path)
                if event["writtenType"] is not None:
                    try:
                        derived_written = _written_duration(event["writtenType"], dots)
                    except Stage8ContractError:
                        _add_issue(issues, code="WRITTEN_TYPE_UNSUPPORTED", path=e_path)
                    else:
                        if event["writtenDuration"] != derived_written:
                            _add_issue(issues, code="WRITTEN_DURATION_MISMATCH", path=e_path)

                staff = event["staff"]
                voice = event["voice"]
                if isinstance(staff, bool) or not isinstance(staff, int) or staff < 1 or staff > 128:
                    _add_issue(issues, code="STAFF_INVALID", path=e_path)
                if not isinstance(voice, str) or not voice or len(voice) > 40:
                    _add_issue(issues, code="VOICE_INVALID", path=e_path)

                chord_group = event["chordGroup"]
                chord_index = event["chordIndex"]
                if chord_group is None and chord_index is not None:
                    _add_issue(issues, code="CHORD_INDEX_WITHOUT_GROUP", path=e_path)
                if chord_group is not None:
                    if not isinstance(chord_index, int) or isinstance(chord_index, bool) or chord_index < 0:
                        _add_issue(issues, code="CHORD_INDEX_INVALID", path=e_path)
                    else:
                        chord_groups.setdefault(chord_group, []).append((onset, chord_index, e_path))

                if duration > 0 and isinstance(staff, int) and isinstance(voice, str):
                    voice_events.setdefault((staff, voice), []).append(
                        (onset, onset + duration, chord_group, chord_index, e_path)
                    )

            for group, members in chord_groups.items():
                onsets = {item[0] for item in members}
                indices = sorted(item[1] for item in members if item[1] is not None)
                if len(onsets) != 1 or indices != list(range(len(indices))):
                    _add_issue(issues, code="CHORD_GROUP_INCONSISTENT", path=f"{m_path}/chord/{group}")

            for _, events in voice_events.items():
                ordered = sorted(events, key=lambda item: (item[0], item[1], item[4]))
                for left, right in zip(ordered, ordered[1:]):
                    same_chord = left[2] is not None and left[2] == right[2] and left[0] == right[0]
                    if not same_chord and right[0] < left[1]:
                        _add_issue(issues, code="VOICE_TIMING_OVERLAP", path=right[4])

    issues.sort(key=lambda item: (item["path"], item["code"]))
    blocking_count = sum(1 for issue in issues if issue["blocking"])
    body = {
        "schemaVersion": VALIDATION_VERSION,
        "musicalStateSha256": _sha(payload),
        "blockingIssueCount": blocking_count,
        "unresolvedIssueCount": len(issues),
        "issues": issues,
    }
    report_hash = _sha(body)
    record = {**body, "validationReportSha256": report_hash}
    return RevisionValidationReport(_freeze(record))
