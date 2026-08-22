from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256
import hmac
import json
from types import MappingProxyType
from typing import Any, Mapping

from .contracts import ReviewAuthorizationGrant, Stage8ContractError, verify_authorization_grant
from .durable_revision_store import DurableRevisionStore, DurableRevisionStoreError, RevisionScope
from .musical_state import (
    ReviewMusicalState,
    Stage8MaterializationError,
    materialize_canonical_state,
    validate_musical_state,
)


TIMELINE_VERSION = "scoremosaic-teacher-review-timeline-v1"
_MAX_PARTS = 64
_MAX_MEASURES = 20_000
_MAX_EVENTS = 500_000
_MAX_SIMULTANEOUS_EVENTS = 256


class Stage8TimelineError(ValueError):
    """Fail-closed Stage 8-I timeline error with a stable outward category."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> None:
    raise Stage8TimelineError(code)


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
        _fail("TIMELINE_NON_CANONICAL_VALUE")


def _digest(value: Any) -> str:
    return sha256(_canonical_json(value)).hexdigest()


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


def _fraction(value: Mapping[str, Any], *, code: str) -> Fraction:
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
        or denominator > 1_000_000
    ):
        _fail(code)
    return Fraction(numerator, denominator)


def _q(value: Fraction | int) -> dict[str, int]:
    normalized = Fraction(value)
    return {"numerator": normalized.numerator, "denominator": normalized.denominator}


def _time_signature(value: Any) -> tuple[dict[str, Any] | None, int | None, Fraction | None]:
    if value is None:
        return None, None, None
    if not isinstance(value, Mapping) or set(value) != {"beats", "beatType"}:
        _fail("TIMELINE_TIME_SIGNATURE_INVALID")
    beats = value["beats"]
    beat_type = value["beatType"]
    if not isinstance(beats, str) or not beats or len(beats) > 40:
        _fail("TIMELINE_TIME_SIGNATURE_INVALID")
    groups = beats.split("+")
    try:
        group_values = [int(group) for group in groups]
    except ValueError as exc:
        raise Stage8TimelineError("TIMELINE_TIME_SIGNATURE_INVALID") from exc
    if any(group <= 0 for group in group_values):
        _fail("TIMELINE_TIME_SIGNATURE_INVALID")
    if isinstance(beat_type, bool) or not isinstance(beat_type, int) or not 1 <= beat_type <= 1024:
        _fail("TIMELINE_TIME_SIGNATURE_INVALID")
    total_beats = sum(group_values)
    if total_beats > 100_000:
        _fail("TIMELINE_TIME_SIGNATURE_INVALID")
    return {"beats": beats, "beatType": beat_type}, total_beats, Fraction(4, beat_type)


def _beat_position(
    onset: Fraction,
    *,
    total_beats: int | None,
    beat_unit: Fraction | None,
) -> dict[str, Any]:
    if total_beats is None or beat_unit is None:
        return {
            "beatUnit": None,
            "beatIndex": None,
            "offsetWithinBeat": None,
            "insideDeclaredMeter": None,
        }
    quotient = onset // beat_unit
    beat_index = int(quotient) + 1
    offset = onset - (beat_index - 1) * beat_unit
    return {
        "beatUnit": _q(beat_unit),
        "beatIndex": beat_index,
        "offsetWithinBeat": _q(offset),
        "insideDeclaredMeter": 1 <= beat_index <= total_beats,
    }


def _simultaneity_groups(
    events: list[Mapping[str, Any]],
    *,
    part_id: str,
    measure_id: str,
) -> dict[Fraction, tuple[str, tuple[str, ...]]]:
    grouped: dict[Fraction, list[tuple[int, str]]] = {}
    for event in events:
        onset = _fraction(event["onset"], code="TIMELINE_EVENT_INVALID")
        event_id = event["eventId"]
        xml_order = event["xmlOrder"]
        grouped.setdefault(onset, []).append((xml_order, event_id))

    result: dict[Fraction, tuple[str, tuple[str, ...]]] = {}
    for onset, members in grouped.items():
        if len(members) > _MAX_SIMULTANEOUS_EVENTS:
            _fail("TIMELINE_SIMULTANEITY_LIMIT_EXCEEDED")
        ordered_ids = tuple(event_id for _, event_id in sorted(members))
        group_id = "sim_" + _digest(
            {
                "partId": part_id,
                "measureId": measure_id,
                "onset": _q(onset),
                "eventIds": list(ordered_ids),
            }
        )[:24]
        result[onset] = (group_id, ordered_ids)
    return result


def _validate_event_identity(event: Mapping[str, Any], *, seen: set[str]) -> None:
    event_id = event.get("eventId")
    xml_order = event.get("xmlOrder")
    if not isinstance(event_id, str) or not event_id or len(event_id) > 200:
        _fail("TIMELINE_EVENT_INVALID")
    if event_id in seen:
        _fail("TIMELINE_EVENT_ID_DUPLICATE")
    seen.add(event_id)
    if isinstance(xml_order, bool) or not isinstance(xml_order, int) or xml_order < 0:
        _fail("TIMELINE_EVENT_INVALID")


def _project_measure(measure: Mapping[str, Any], *, part_id: str) -> dict[str, Any]:
    measure_id = measure.get("measureId")
    ordinal = measure.get("ordinal")
    number = measure.get("number")
    if not isinstance(measure_id, str) or not measure_id or len(measure_id) > 200:
        _fail("TIMELINE_MEASURE_INVALID")
    if isinstance(ordinal, bool) or not isinstance(ordinal, int) or ordinal < 1:
        _fail("TIMELINE_MEASURE_INVALID")
    if not isinstance(number, str) or not number or len(number) > 40:
        _fail("TIMELINE_MEASURE_INVALID")
    events = measure.get("events")
    if not isinstance(events, list):
        _fail("TIMELINE_MEASURE_INVALID")

    signature, total_beats, beat_unit = _time_signature(measure.get("timeSignatureAtStart"))
    expected_raw = measure.get("expectedDuration")
    expected = None if expected_raw is None else _fraction(expected_raw, code="TIMELINE_MEASURE_INVALID")
    if expected is not None and expected < 0:
        _fail("TIMELINE_MEASURE_INVALID")

    seen: set[str] = set()
    last_xml_order = -1
    event_extent = Fraction(0)
    for event in events:
        if not isinstance(event, Mapping):
            _fail("TIMELINE_EVENT_INVALID")
        _validate_event_identity(event, seen=seen)
        if event["xmlOrder"] <= last_xml_order:
            _fail("TIMELINE_EVENT_ORDER_INVALID")
        last_xml_order = event["xmlOrder"]
        onset = _fraction(event["onset"], code="TIMELINE_EVENT_INVALID")
        duration = _fraction(event["effectiveDuration"], code="TIMELINE_EVENT_INVALID")
        if onset < 0 or duration < 0:
            _fail("TIMELINE_EVENT_INVALID")
        event_extent = max(event_extent, onset + duration)

    groups = _simultaneity_groups(events, part_id=part_id, measure_id=measure_id)
    projected_events: list[dict[str, Any]] = []
    for event in events:
        onset = _fraction(event["onset"], code="TIMELINE_EVENT_INVALID")
        duration = _fraction(event["effectiveDuration"], code="TIMELINE_EVENT_INVALID")
        simultaneity_id, simultaneous_ids = groups[onset]
        kind = event.get("kind")
        voice = event.get("voice")
        staff = event.get("staff")
        grace = event.get("grace")
        chord_group = event.get("chordGroup")
        chord_index = event.get("chordIndex")
        if kind not in {"note", "rest", "unpitched"}:
            _fail("TIMELINE_EVENT_INVALID")
        if not isinstance(voice, str) or not voice or len(voice) > 40:
            _fail("TIMELINE_EVENT_INVALID")
        if isinstance(staff, bool) or not isinstance(staff, int) or not 1 <= staff <= 128:
            _fail("TIMELINE_EVENT_INVALID")
        if not isinstance(grace, bool):
            _fail("TIMELINE_EVENT_INVALID")
        if chord_group is not None and (
            not isinstance(chord_group, str) or not chord_group or len(chord_group) > 200
        ):
            _fail("TIMELINE_EVENT_INVALID")
        if chord_index is not None and (
            isinstance(chord_index, bool) or not isinstance(chord_index, int) or chord_index < 0
        ):
            _fail("TIMELINE_EVENT_INVALID")
        projected_events.append(
            {
                "eventId": event["eventId"],
                "xmlOrder": event["xmlOrder"],
                "kind": kind,
                "onset": _q(onset),
                "effectiveDuration": _q(duration),
                "end": _q(onset + duration),
                "staff": staff,
                "voice": voice,
                "grace": grace,
                "chordGroup": chord_group,
                "chordIndex": chord_index,
                "beat": _beat_position(onset, total_beats=total_beats, beat_unit=beat_unit),
                "simultaneityId": simultaneity_id,
                "simultaneousEventIds": list(simultaneous_ids),
            }
        )

    within_expected = expected is not None and event_extent <= expected
    return {
        "measureId": measure_id,
        "number": number,
        "ordinal": ordinal,
        "timeSignatureAtStart": signature,
        "expectedDuration": None if expected is None else _q(expected),
        "eventExtentEnd": _q(event_extent),
        "loopBounds": {
            "start": _q(0),
            "expectedEnd": None if expected is None else _q(expected),
            "eventExtentEnd": _q(event_extent),
            "safeWithinExpectedDuration": within_expected,
            "playbackAuthority": False,
        },
        "events": projected_events,
    }


def _project_state(state: ReviewMusicalState) -> list[dict[str, Any]]:
    payload = state.to_dict()
    parts = payload.get("parts")
    if not isinstance(parts, list) or not 1 <= len(parts) <= _MAX_PARTS:
        _fail("TIMELINE_STATE_INVALID")
    total_measures = 0
    total_events = 0
    result: list[dict[str, Any]] = []
    seen_parts: set[str] = set()
    last_part_ordinal = 0
    for part in parts:
        if not isinstance(part, Mapping):
            _fail("TIMELINE_STATE_INVALID")
        part_id = part.get("partId")
        ordinal = part.get("ordinal")
        measures = part.get("measures")
        if not isinstance(part_id, str) or not part_id or len(part_id) > 200 or part_id in seen_parts:
            _fail("TIMELINE_PART_INVALID")
        seen_parts.add(part_id)
        if isinstance(ordinal, bool) or not isinstance(ordinal, int) or ordinal <= last_part_ordinal:
            _fail("TIMELINE_PART_ORDER_INVALID")
        last_part_ordinal = ordinal
        if not isinstance(measures, list) or not measures:
            _fail("TIMELINE_PART_INVALID")
        total_measures += len(measures)
        if total_measures > _MAX_MEASURES:
            _fail("TIMELINE_MEASURE_LIMIT_EXCEEDED")
        measure_ids: set[str] = set()
        last_measure_ordinal = 0
        projected_measures: list[dict[str, Any]] = []
        for measure in measures:
            if not isinstance(measure, Mapping):
                _fail("TIMELINE_MEASURE_INVALID")
            measure_id = measure.get("measureId")
            measure_ordinal = measure.get("ordinal")
            if not isinstance(measure_id, str) or measure_id in measure_ids:
                _fail("TIMELINE_MEASURE_INVALID")
            measure_ids.add(measure_id)
            if (
                isinstance(measure_ordinal, bool)
                or not isinstance(measure_ordinal, int)
                or measure_ordinal <= last_measure_ordinal
            ):
                _fail("TIMELINE_MEASURE_ORDER_INVALID")
            last_measure_ordinal = measure_ordinal
            events = measure.get("events")
            if not isinstance(events, list):
                _fail("TIMELINE_MEASURE_INVALID")
            total_events += len(events)
            if total_events > _MAX_EVENTS:
                _fail("TIMELINE_EVENT_LIMIT_EXCEEDED")
            projected_measures.append(_project_measure(measure, part_id=part_id))
        result.append({"partId": part_id, "ordinal": ordinal, "measures": projected_measures})
    return result


def _load_current_snapshot(
    *,
    grant: ReviewAuthorizationGrant,
    signing_key: bytes,
    expected_reviewer_id: str,
    scope: RevisionScope,
    store: DurableRevisionStore,
    state: ReviewMusicalState,
    base_canonical_payload: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    try:
        head = store.load_head(scope)
    except DurableRevisionStoreError as exc:
        raise Stage8TimelineError("TIMELINE_STORE_INVALID") from exc

    revision_id = head.revision_id if head is not None else None
    revision_sha = head.revision_sha256 if head is not None else None
    try:
        verify_authorization_grant(
            grant,
            signing_key=signing_key,
            required_action="revision:read",
            expected_tenant_id=scope.tenant_id,
            expected_job_id=scope.job_id,
            expected_reviewer_id=expected_reviewer_id,
            expected_review_report_id=scope.review_report_id,
            expected_review_report_sha256=scope.review_report_sha256,
            expected_canonical_score_sha256=scope.base_canonical_sha256,
            expected_parent_revision_id=revision_id,
            expected_parent_revision_sha256=revision_sha,
        )
    except Stage8ContractError as exc:
        code = (
            "TIMELINE_STALE_SNAPSHOT"
            if exc.code == "AUTHZ_STALE_PARENT"
            else "TIMELINE_AUTHORIZATION_DENIED"
        )
        raise Stage8TimelineError(code) from exc

    if not isinstance(state, ReviewMusicalState):
        _fail("TIMELINE_STATE_INVALID")

    if head is None:
        try:
            base_state = materialize_canonical_state(scope, base_canonical_payload)
        except Stage8MaterializationError as exc:
            raise Stage8TimelineError("TIMELINE_BASE_CANONICAL_INVALID") from exc
        if not hmac.compare_digest(base_state.state_sha256, state.state_sha256):
            _fail("TIMELINE_STATE_MISMATCH")
        return (
            {
                "kind": "base",
                "revisionId": None,
                "revisionSha256": None,
                "stateSha256": state.state_sha256,
            },
            None,
        )

    try:
        record = store.load_revision(scope, head.revision_sha256)
    except DurableRevisionStoreError as exc:
        raise Stage8TimelineError("TIMELINE_STORE_INVALID") from exc
    if (
        record.get("revisionId") != head.revision_id
        or record.get("revisionSha256") != head.revision_sha256
        or record.get("resultingMusicalStateSha256") != state.state_sha256
    ):
        _fail("TIMELINE_STATE_MISMATCH")
    expected_validation = {
        "validationReportSha256": record.get("validationReportSha256"),
        "blockingIssueCount": record.get("blockingIssueCount"),
        "unresolvedIssueCount": record.get("unresolvedIssueCount"),
    }
    return (
        {
            "kind": "revision",
            "revisionId": head.revision_id,
            "revisionSha256": head.revision_sha256,
            "stateSha256": state.state_sha256,
        },
        expected_validation,
    )


@dataclass(frozen=True)
class ReviewTimelineProjection:
    _payload: Mapping[str, Any]

    @property
    def timeline_sha256(self) -> str:
        return _digest(_thaw(self._payload))

    def to_dict(self) -> dict[str, Any]:
        payload = _thaw(self._payload)
        payload["timelineSha256"] = self.timeline_sha256
        return payload


def build_review_timeline_projection(
    *,
    grant: ReviewAuthorizationGrant,
    signing_key: bytes,
    expected_reviewer_id: str,
    scope: RevisionScope,
    store: DurableRevisionStore,
    state: ReviewMusicalState,
    base_canonical_payload: Mapping[str, Any],
) -> ReviewTimelineProjection:
    """Build one exact-current rational cursor projection without playback authority."""

    if not isinstance(scope, RevisionScope) or not isinstance(store, DurableRevisionStore):
        _fail("TIMELINE_SERVER_CONFIGURATION_INVALID")
    snapshot, expected_validation = _load_current_snapshot(
        grant=grant,
        signing_key=signing_key,
        expected_reviewer_id=expected_reviewer_id,
        scope=scope,
        store=store,
        state=state,
        base_canonical_payload=base_canonical_payload,
    )
    validation = validate_musical_state(state)
    validation_evidence = {
        "validationReportSha256": validation.report_sha256,
        "blockingIssueCount": validation.blocking_issue_count,
        "unresolvedIssueCount": validation.unresolved_issue_count,
    }
    if expected_validation is not None:
        if (
            not isinstance(expected_validation["validationReportSha256"], str)
            or not hmac.compare_digest(
                expected_validation["validationReportSha256"],
                validation_evidence["validationReportSha256"],
            )
            or expected_validation["blockingIssueCount"] != validation_evidence["blockingIssueCount"]
            or expected_validation["unresolvedIssueCount"] != validation_evidence["unresolvedIssueCount"]
        ):
            _fail("TIMELINE_REVISION_VALIDATION_MISMATCH")

    parts = _project_state(state)
    body = {
        "schemaVersion": TIMELINE_VERSION,
        "scope": {
            "tenantId": scope.tenant_id,
            "jobId": scope.job_id,
            "reviewerId": expected_reviewer_id,
            "reviewReportId": scope.review_report_id,
            "reviewReportSha256": scope.review_report_sha256,
            "baseCanonicalSha256": scope.base_canonical_sha256,
        },
        "snapshot": snapshot,
        "validation": validation_evidence,
        "capabilities": {
            "readOnly": True,
            "cursorNavigation": True,
            "canSeek": True,
            "canLoop": False,
            "canPlay": False,
            "canMutate": False,
            "canApprove": False,
            "canPublish": False,
            "authoritativeTruth": False,
        },
        "parts": parts,
    }
    return ReviewTimelineProjection(_freeze(body))


__all__ = [
    "TIMELINE_VERSION",
    "ReviewTimelineProjection",
    "Stage8TimelineError",
    "build_review_timeline_projection",
]
