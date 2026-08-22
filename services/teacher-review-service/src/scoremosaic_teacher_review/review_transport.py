from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256
import hmac
import json
import re
from types import MappingProxyType
from typing import Any, Mapping

from .contracts import ReviewAuthorizationGrant
from .durable_revision_store import DurableRevisionStore, RevisionScope
from .musical_state import ReviewMusicalState
from .review_timeline import (
    ReviewTimelineProjection,
    Stage8TimelineError,
    TIMELINE_VERSION,
    build_review_timeline_projection,
)


TRANSPORT_PLAN_VERSION = "scoremosaic-review-transport-plan-v1"
TRANSPORT_STATE_VERSION = "scoremosaic-review-transport-state-v1"
_MAX_CURSOR_POINTS = 500_000
_MAX_EVENTS = 500_000
_MAX_EVENTS_PER_POINT = 512
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")
_PLAN_CONSTRUCTION_SEAL = object()
_STATE_CONSTRUCTION_SEAL = object()

_EXPECTED_TIMELINE_CAPABILITIES = {
    "readOnly": True,
    "cursorNavigation": True,
    "canSeek": True,
    "canLoop": False,
    "canPlay": False,
    "canMutate": False,
    "canApprove": False,
    "canPublish": False,
    "authoritativeTruth": False,
}


class Stage8TransportError(ValueError):
    """Stable fail-closed transport-foundation error."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> None:
    raise Stage8TransportError(code)


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
        _fail("TRANSPORT_NON_CANONICAL_VALUE")


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


def _exact(value: Any, keys: set[str], code: str) -> Mapping[str, Any]:
    if type(value) is not dict or set(value) != keys:
        _fail(code)
    return value


def _hash(value: Any, code: str) -> str:
    if type(value) is not str or _HASH_RE.fullmatch(value) is None:
        _fail(code)
    return value


def _identifier(value: Any, code: str) -> str:
    if type(value) is not str or _ID_RE.fullmatch(value) is None:
        _fail(code)
    return value


def _bounded_int(value: Any, code: str, *, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        _fail(code)
    return value


def _fraction(value: Any, code: str) -> Fraction:
    value = _exact(value, {"numerator", "denominator"}, code)
    numerator = value["numerator"]
    denominator = value["denominator"]
    if (
        type(numerator) is not int
        or type(denominator) is not int
        or denominator < 1
        or denominator > 1_000_000
    ):
        _fail(code)
    result = Fraction(numerator, denominator)
    if result < 0:
        _fail(code)
    return result


def _q(value: Fraction | int) -> dict[str, int]:
    normalized = Fraction(value)
    return {"numerator": normalized.numerator, "denominator": normalized.denominator}


def _validate_snapshot(value: Any) -> dict[str, Any]:
    value = _exact(
        value,
        {"kind", "revisionId", "revisionSha256", "stateSha256"},
        "TRANSPORT_TIMELINE_SNAPSHOT_INVALID",
    )
    kind = value["kind"]
    if kind not in {"base", "revision"}:
        _fail("TRANSPORT_TIMELINE_SNAPSHOT_INVALID")
    state_sha = _hash(value["stateSha256"], "TRANSPORT_TIMELINE_SNAPSHOT_INVALID")
    if kind == "base":
        if value["revisionId"] is not None or value["revisionSha256"] is not None:
            _fail("TRANSPORT_TIMELINE_SNAPSHOT_INVALID")
        revision_id = None
        revision_sha = None
    else:
        revision_id = _identifier(value["revisionId"], "TRANSPORT_TIMELINE_SNAPSHOT_INVALID")
        revision_sha = _hash(value["revisionSha256"], "TRANSPORT_TIMELINE_SNAPSHOT_INVALID")
    return {
        "kind": kind,
        "revisionId": revision_id,
        "revisionSha256": revision_sha,
        "stateSha256": state_sha,
    }


def _validate_timeline_and_points(
    timeline: ReviewTimelineProjection,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if type(timeline) is not ReviewTimelineProjection:
        _fail("TRANSPORT_TIMELINE_TYPE_INVALID")
    data = timeline.to_dict()
    _exact(
        data,
        {
            "schemaVersion",
            "scope",
            "snapshot",
            "validation",
            "capabilities",
            "parts",
            "timelineSha256",
        },
        "TRANSPORT_TIMELINE_INVALID",
    )
    if data["schemaVersion"] != TIMELINE_VERSION:
        _fail("TRANSPORT_TIMELINE_VERSION_INVALID")
    timeline_sha = _hash(data["timelineSha256"], "TRANSPORT_TIMELINE_INVALID")
    if not hmac.compare_digest(timeline_sha, timeline.timeline_sha256):
        _fail("TRANSPORT_TIMELINE_HASH_MISMATCH")
    if data["capabilities"] != _EXPECTED_TIMELINE_CAPABILITIES:
        _fail("TRANSPORT_TIMELINE_CAPABILITY_INVALID")

    scope = _exact(
        data["scope"],
        {
            "tenantId",
            "jobId",
            "reviewerId",
            "reviewReportId",
            "reviewReportSha256",
            "baseCanonicalSha256",
        },
        "TRANSPORT_TIMELINE_SCOPE_INVALID",
    )
    normalized_scope = {
        "tenantId": _identifier(scope["tenantId"], "TRANSPORT_TIMELINE_SCOPE_INVALID"),
        "jobId": _identifier(scope["jobId"], "TRANSPORT_TIMELINE_SCOPE_INVALID"),
        "reviewerId": _identifier(scope["reviewerId"], "TRANSPORT_TIMELINE_SCOPE_INVALID"),
        "reviewReportId": _identifier(scope["reviewReportId"], "TRANSPORT_TIMELINE_SCOPE_INVALID"),
        "reviewReportSha256": _hash(
            scope["reviewReportSha256"], "TRANSPORT_TIMELINE_SCOPE_INVALID"
        ),
        "baseCanonicalSha256": _hash(
            scope["baseCanonicalSha256"], "TRANSPORT_TIMELINE_SCOPE_INVALID"
        ),
    }
    snapshot = _validate_snapshot(data["snapshot"])

    validation = _exact(
        data["validation"],
        {"validationReportSha256", "blockingIssueCount", "unresolvedIssueCount"},
        "TRANSPORT_TIMELINE_VALIDATION_INVALID",
    )
    normalized_validation = {
        "validationReportSha256": _hash(
            validation["validationReportSha256"], "TRANSPORT_TIMELINE_VALIDATION_INVALID"
        ),
        "blockingIssueCount": _bounded_int(
            validation["blockingIssueCount"],
            "TRANSPORT_TIMELINE_VALIDATION_INVALID",
            minimum=0,
            maximum=1_000_000,
        ),
        "unresolvedIssueCount": _bounded_int(
            validation["unresolvedIssueCount"],
            "TRANSPORT_TIMELINE_VALIDATION_INVALID",
            minimum=0,
            maximum=1_000_000,
        ),
    }

    parts = data["parts"]
    if type(parts) is not list or not 1 <= len(parts) <= 64:
        _fail("TRANSPORT_TIMELINE_PARTS_INVALID")

    grouped: dict[tuple[int, Fraction], list[dict[str, Any]]] = {}
    total_events = 0
    previous_part_ordinal = 0
    seen_parts: set[str] = set()
    for part in parts:
        part = _exact(part, {"partId", "ordinal", "measures"}, "TRANSPORT_TIMELINE_PART_INVALID")
        part_id = _identifier(part["partId"], "TRANSPORT_TIMELINE_PART_INVALID")
        if part_id in seen_parts:
            _fail("TRANSPORT_TIMELINE_PART_INVALID")
        seen_parts.add(part_id)
        part_ordinal = _bounded_int(
            part["ordinal"], "TRANSPORT_TIMELINE_PART_INVALID", minimum=1, maximum=1_000_000
        )
        if part_ordinal <= previous_part_ordinal:
            _fail("TRANSPORT_TIMELINE_PART_ORDER_INVALID")
        previous_part_ordinal = part_ordinal
        measures = part["measures"]
        if type(measures) is not list or not measures or len(measures) > 20_000:
            _fail("TRANSPORT_TIMELINE_MEASURE_INVALID")
        previous_measure_ordinal = 0
        seen_measures: set[str] = set()
        for measure in measures:
            measure = _exact(
                measure,
                {
                    "measureId",
                    "number",
                    "ordinal",
                    "timeSignatureAtStart",
                    "expectedDuration",
                    "eventExtentEnd",
                    "loopBounds",
                    "events",
                },
                "TRANSPORT_TIMELINE_MEASURE_INVALID",
            )
            measure_id = _identifier(measure["measureId"], "TRANSPORT_TIMELINE_MEASURE_INVALID")
            if measure_id in seen_measures:
                _fail("TRANSPORT_TIMELINE_MEASURE_INVALID")
            seen_measures.add(measure_id)
            measure_ordinal = _bounded_int(
                measure["ordinal"],
                "TRANSPORT_TIMELINE_MEASURE_INVALID",
                minimum=1,
                maximum=1_000_000,
            )
            if measure_ordinal <= previous_measure_ordinal:
                _fail("TRANSPORT_TIMELINE_MEASURE_ORDER_INVALID")
            previous_measure_ordinal = measure_ordinal
            _fraction(measure["eventExtentEnd"], "TRANSPORT_TIMELINE_MEASURE_INVALID")
            loop_bounds = _exact(
                measure["loopBounds"],
                {
                    "start",
                    "expectedEnd",
                    "eventExtentEnd",
                    "safeWithinExpectedDuration",
                    "playbackAuthority",
                },
                "TRANSPORT_TIMELINE_LOOP_INVALID",
            )
            if loop_bounds["playbackAuthority"] is not False:
                _fail("TRANSPORT_TIMELINE_LOOP_AUTHORITY_FORBIDDEN")
            events = measure["events"]
            if type(events) is not list:
                _fail("TRANSPORT_TIMELINE_EVENT_INVALID")
            for event in events:
                total_events += 1
                if total_events > _MAX_EVENTS:
                    _fail("TRANSPORT_TIMELINE_EVENT_LIMIT_EXCEEDED")
                event = _exact(
                    event,
                    {
                        "eventId",
                        "xmlOrder",
                        "kind",
                        "onset",
                        "effectiveDuration",
                        "end",
                        "staff",
                        "voice",
                        "grace",
                        "chordGroup",
                        "chordIndex",
                        "beat",
                        "simultaneityId",
                        "simultaneousEventIds",
                    },
                    "TRANSPORT_TIMELINE_EVENT_INVALID",
                )
                event_id = _identifier(event["eventId"], "TRANSPORT_TIMELINE_EVENT_INVALID")
                onset = _fraction(event["onset"], "TRANSPORT_TIMELINE_EVENT_INVALID")
                if event["kind"] not in {"note", "rest", "unpitched"}:
                    _fail("TRANSPORT_TIMELINE_EVENT_INVALID")
                staff = _bounded_int(
                    event["staff"], "TRANSPORT_TIMELINE_EVENT_INVALID", minimum=1, maximum=128
                )
                voice = event["voice"]
                if type(voice) is not str or not voice or len(voice) > 40:
                    _fail("TRANSPORT_TIMELINE_EVENT_INVALID")
                key = (measure_ordinal, onset)
                grouped.setdefault(key, []).append(
                    {
                        "partId": part_id,
                        "measureId": measure_id,
                        "eventId": event_id,
                        "staff": staff,
                        "voice": voice,
                        "kind": event["kind"],
                    }
                )

    if len(grouped) > _MAX_CURSOR_POINTS:
        _fail("TRANSPORT_CURSOR_POINT_LIMIT_EXCEEDED")

    points: list[dict[str, Any]] = []
    for index, ((measure_ordinal, onset), refs) in enumerate(
        sorted(grouped.items(), key=lambda item: (item[0][0], item[0][1])),
    ):
        ordered_refs = sorted(
            refs,
            key=lambda item: (
                item["partId"],
                item["measureId"],
                item["eventId"],
                item["staff"],
                item["voice"],
            ),
        )
        if len(ordered_refs) > _MAX_EVENTS_PER_POINT:
            _fail("TRANSPORT_CURSOR_POINT_EVENT_LIMIT_EXCEEDED")
        point_body = {
            "measureOrdinal": measure_ordinal,
            "onset": _q(onset),
            "eventRefs": ordered_refs,
        }
        points.append(
            {
                "index": index,
                "cursorPointId": "cursor_" + _digest(point_body)[:24],
                **point_body,
            }
        )

    identity = {
        "timelineSha256": timeline_sha,
        "scope": normalized_scope,
        "snapshot": snapshot,
        "validation": normalized_validation,
    }
    return identity, points


@dataclass(frozen=True, slots=True, repr=False, init=False)
class ReviewTransportPlan:
    _payload: Mapping[str, Any]

    def __init__(
        self,
        payload: Mapping[str, Any],
        *,
        _construction_seal: object | None = None,
    ) -> None:
        if _construction_seal is not _PLAN_CONSTRUCTION_SEAL:
            _fail("TRANSPORT_PLAN_CONSTRUCTION_FORBIDDEN")
        object.__setattr__(self, "_payload", payload)

    @property
    def plan_sha256(self) -> str:
        return _digest(_thaw(self._payload))

    def to_dict(self) -> dict[str, Any]:
        payload = _thaw(self._payload)
        payload["planSha256"] = self.plan_sha256
        return payload


@dataclass(frozen=True, slots=True, repr=False, init=False)
class ReviewTransportState:
    _payload: Mapping[str, Any]

    def __init__(
        self,
        payload: Mapping[str, Any],
        *,
        _construction_seal: object | None = None,
    ) -> None:
        if _construction_seal is not _STATE_CONSTRUCTION_SEAL:
            _fail("TRANSPORT_STATE_CONSTRUCTION_FORBIDDEN")
        object.__setattr__(self, "_payload", payload)

    @property
    def state_sha256(self) -> str:
        return _digest(_thaw(self._payload))

    def to_dict(self) -> dict[str, Any]:
        payload = _thaw(self._payload)
        payload["transportStateSha256"] = self.state_sha256
        return payload


def _build_plan_from_timeline(timeline: ReviewTimelineProjection) -> ReviewTransportPlan:
    identity, points = _validate_timeline_and_points(timeline)
    body = {
        "schemaVersion": TRANSPORT_PLAN_VERSION,
        **identity,
        "capabilities": {
            "presentationOnly": True,
            "cursorAdvanceAllowed": True,
            "seekAllowed": True,
            "loopExecutionAllowed": False,
            "audioExecutionAllowed": False,
            "mutationAllowed": False,
            "approvalAllowed": False,
            "publicationAllowed": False,
        },
        "cursorPoints": points,
    }
    return ReviewTransportPlan(
        _freeze(body),
        _construction_seal=_PLAN_CONSTRUCTION_SEAL,
    )


def build_review_transport_plan(
    *,
    grant: ReviewAuthorizationGrant,
    signing_key: bytes,
    expected_reviewer_id: str,
    scope: RevisionScope,
    store: DurableRevisionStore,
    state: ReviewMusicalState,
    base_canonical_payload: Mapping[str, Any],
) -> ReviewTransportPlan:
    """Build a non-executing transport plan from a freshly authorized Stage 8-I timeline."""

    try:
        timeline = build_review_timeline_projection(
            grant=grant,
            signing_key=signing_key,
            expected_reviewer_id=expected_reviewer_id,
            scope=scope,
            store=store,
            state=state,
            base_canonical_payload=base_canonical_payload,
        )
    except Stage8TimelineError as exc:
        if exc.code == "TIMELINE_STALE_SNAPSHOT":
            code = "TRANSPORT_STALE_SNAPSHOT"
        elif exc.code == "TIMELINE_AUTHORIZATION_DENIED":
            code = "TRANSPORT_AUTHORIZATION_DENIED"
        else:
            code = "TRANSPORT_TIMELINE_REJECTED"
        raise Stage8TransportError(code) from exc
    return _build_plan_from_timeline(timeline)


def _validate_plan(plan: ReviewTransportPlan) -> dict[str, Any]:
    if type(plan) is not ReviewTransportPlan:
        _fail("TRANSPORT_PLAN_TYPE_INVALID")
    data = plan.to_dict()
    _exact(
        data,
        {
            "schemaVersion",
            "timelineSha256",
            "scope",
            "snapshot",
            "validation",
            "capabilities",
            "cursorPoints",
            "planSha256",
        },
        "TRANSPORT_PLAN_INVALID",
    )
    if data["schemaVersion"] != TRANSPORT_PLAN_VERSION:
        _fail("TRANSPORT_PLAN_VERSION_INVALID")
    _hash(data["timelineSha256"], "TRANSPORT_PLAN_INVALID")
    _hash(data["planSha256"], "TRANSPORT_PLAN_INVALID")
    if not hmac.compare_digest(data["planSha256"], plan.plan_sha256):
        _fail("TRANSPORT_PLAN_HASH_MISMATCH")
    if data["capabilities"] != {
        "presentationOnly": True,
        "cursorAdvanceAllowed": True,
        "seekAllowed": True,
        "loopExecutionAllowed": False,
        "audioExecutionAllowed": False,
        "mutationAllowed": False,
        "approvalAllowed": False,
        "publicationAllowed": False,
    }:
        _fail("TRANSPORT_PLAN_CAPABILITY_INVALID")
    points = data["cursorPoints"]
    if type(points) is not list or len(points) > _MAX_CURSOR_POINTS:
        _fail("TRANSPORT_PLAN_INVALID")
    for expected_index, point in enumerate(points):
        if type(point) is not dict or point.get("index") != expected_index:
            _fail("TRANSPORT_PLAN_INVALID")
    return data


def _cursor_for_index(plan_data: Mapping[str, Any], index: int | None) -> dict[str, Any] | None:
    if index is None:
        return None
    point = plan_data["cursorPoints"][index]
    return {
        "cursorPointId": point["cursorPointId"],
        "measureOrdinal": point["measureOrdinal"],
        "onset": point["onset"],
        "eventRefs": point["eventRefs"],
    }


def _new_state(
    plan_data: Mapping[str, Any],
    *,
    mode: str,
    cursor_index: int | None,
    transition_sequence: int,
) -> ReviewTransportState:
    body = {
        "schemaVersion": TRANSPORT_STATE_VERSION,
        "planSha256": plan_data["planSha256"],
        "timelineSha256": plan_data["timelineSha256"],
        "snapshot": plan_data["snapshot"],
        "mode": mode,
        "cursorIndex": cursor_index,
        "cursor": _cursor_for_index(plan_data, cursor_index),
        "transitionSequence": transition_sequence,
        "executionAllowed": False,
        "audioEmissionAllowed": False,
        "loopExecutionAllowed": False,
        "mutationAllowed": False,
        "approvalAllowed": False,
        "publicationAllowed": False,
    }
    return ReviewTransportState(
        _freeze(body),
        _construction_seal=_STATE_CONSTRUCTION_SEAL,
    )


def initialize_review_transport(plan: ReviewTransportPlan) -> ReviewTransportState:
    data = _validate_plan(plan)
    initial_index = 0 if data["cursorPoints"] else None
    return _new_state(data, mode="stopped", cursor_index=initial_index, transition_sequence=0)


def _validate_state_for_plan(
    plan: ReviewTransportPlan,
    state: ReviewTransportState,
) -> tuple[dict[str, Any], dict[str, Any]]:
    plan_data = _validate_plan(plan)
    if type(state) is not ReviewTransportState:
        _fail("TRANSPORT_STATE_TYPE_INVALID")
    data = state.to_dict()
    _exact(
        data,
        {
            "schemaVersion",
            "planSha256",
            "timelineSha256",
            "snapshot",
            "mode",
            "cursorIndex",
            "cursor",
            "transitionSequence",
            "executionAllowed",
            "audioEmissionAllowed",
            "loopExecutionAllowed",
            "mutationAllowed",
            "approvalAllowed",
            "publicationAllowed",
            "transportStateSha256",
        },
        "TRANSPORT_STATE_INVALID",
    )
    if data["schemaVersion"] != TRANSPORT_STATE_VERSION:
        _fail("TRANSPORT_STATE_VERSION_INVALID")
    if (
        data["planSha256"] != plan_data["planSha256"]
        or data["timelineSha256"] != plan_data["timelineSha256"]
        or data["snapshot"] != plan_data["snapshot"]
    ):
        _fail("TRANSPORT_STALE_PLAN")
    if data["mode"] not in {"stopped", "navigating", "paused"}:
        _fail("TRANSPORT_STATE_INVALID")
    if type(data["transitionSequence"]) is not int or data["transitionSequence"] < 0:
        _fail("TRANSPORT_STATE_INVALID")
    for name in (
        "executionAllowed",
        "audioEmissionAllowed",
        "loopExecutionAllowed",
        "mutationAllowed",
        "approvalAllowed",
        "publicationAllowed",
    ):
        if data[name] is not False:
            _fail("TRANSPORT_AUTHORITY_FORBIDDEN")
    index = data["cursorIndex"]
    if index is not None:
        if type(index) is not int or not 0 <= index < len(plan_data["cursorPoints"]):
            _fail("TRANSPORT_STATE_INVALID")
        if data["cursor"] != _cursor_for_index(plan_data, index):
            _fail("TRANSPORT_CURSOR_MISMATCH")
    elif data["cursor"] is not None or plan_data["cursorPoints"]:
        _fail("TRANSPORT_STATE_INVALID")
    if not hmac.compare_digest(data["transportStateSha256"], state.state_sha256):
        _fail("TRANSPORT_STATE_HASH_MISMATCH")
    return plan_data, data


def start_navigation(
    plan: ReviewTransportPlan,
    state: ReviewTransportState,
) -> ReviewTransportState:
    plan_data, current = _validate_state_for_plan(plan, state)
    if not plan_data["cursorPoints"]:
        _fail("TRANSPORT_EMPTY_PLAN")
    if current["mode"] == "navigating":
        return state
    return _new_state(
        plan_data,
        mode="navigating",
        cursor_index=current["cursorIndex"],
        transition_sequence=current["transitionSequence"] + 1,
    )


def pause_navigation(
    plan: ReviewTransportPlan,
    state: ReviewTransportState,
) -> ReviewTransportState:
    plan_data, current = _validate_state_for_plan(plan, state)
    if current["mode"] == "paused":
        return state
    if current["mode"] != "navigating":
        _fail("TRANSPORT_PAUSE_INVALID_STATE")
    return _new_state(
        plan_data,
        mode="paused",
        cursor_index=current["cursorIndex"],
        transition_sequence=current["transitionSequence"] + 1,
    )


def stop_navigation(
    plan: ReviewTransportPlan,
    state: ReviewTransportState,
) -> ReviewTransportState:
    plan_data, current = _validate_state_for_plan(plan, state)
    first_index = 0 if plan_data["cursorPoints"] else None
    if current["mode"] == "stopped" and current["cursorIndex"] == first_index:
        return state
    return _new_state(
        plan_data,
        mode="stopped",
        cursor_index=first_index,
        transition_sequence=current["transitionSequence"] + 1,
    )


def seek_cursor(
    plan: ReviewTransportPlan,
    state: ReviewTransportState,
    *,
    cursor_index: int,
) -> ReviewTransportState:
    plan_data, current = _validate_state_for_plan(plan, state)
    if type(cursor_index) is not int or not 0 <= cursor_index < len(plan_data["cursorPoints"]):
        _fail("TRANSPORT_SEEK_TARGET_INVALID")
    if current["cursorIndex"] == cursor_index:
        return state
    return _new_state(
        plan_data,
        mode=current["mode"],
        cursor_index=cursor_index,
        transition_sequence=current["transitionSequence"] + 1,
    )


def advance_cursor(
    plan: ReviewTransportPlan,
    state: ReviewTransportState,
) -> ReviewTransportState:
    plan_data, current = _validate_state_for_plan(plan, state)
    if current["mode"] != "navigating":
        _fail("TRANSPORT_ADVANCE_INVALID_STATE")
    index = current["cursorIndex"]
    if index is None:
        _fail("TRANSPORT_EMPTY_PLAN")
    if index + 1 >= len(plan_data["cursorPoints"]):
        return _new_state(
            plan_data,
            mode="stopped",
            cursor_index=index,
            transition_sequence=current["transitionSequence"] + 1,
        )
    return _new_state(
        plan_data,
        mode="navigating",
        cursor_index=index + 1,
        transition_sequence=current["transitionSequence"] + 1,
    )


def request_loop_execution(
    plan: ReviewTransportPlan,
    state: ReviewTransportState,
) -> None:
    _validate_state_for_plan(plan, state)
    _fail("TRANSPORT_LOOP_EXECUTION_FORBIDDEN")


__all__ = [
    "TRANSPORT_PLAN_VERSION",
    "TRANSPORT_STATE_VERSION",
    "ReviewTransportPlan",
    "ReviewTransportState",
    "Stage8TransportError",
    "advance_cursor",
    "build_review_transport_plan",
    "initialize_review_transport",
    "pause_navigation",
    "request_loop_execution",
    "seek_cursor",
    "start_navigation",
    "stop_navigation",
]
