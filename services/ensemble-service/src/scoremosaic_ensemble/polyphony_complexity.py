"""Research-only polyphony complexity evidence derived from Canonical Score.

SM-POLY-07 describes notation complexity independently from engine confidence,
source quality, visual evidence, correctness, or any production decision. V1 is
measure-scoped because Canonical Score v1 has deterministic measure timing but
does not carry page/system layout, cross-staff attachment, or nested-tuples.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
import json
import re
from typing import Any, Iterable, Mapping

from .canonical import CanonicalEvent, CanonicalMeasure, CanonicalScore

SCHEMA_VERSION = "scoremosaic-polyphonic-complexity-profile-v1"
CALCULATION_METHOD_VERSION = "polyphony-complexity-measure-v1"
MAX_EVENTS_PER_SCOPE = 4096
MAX_VOICE_STREAMS_PER_SCOPE = 512

_SHA_RE = re.compile(r"[0-9a-f]{64}\Z")
_PROFILE_RE = re.compile(r"complexity_[0-9a-f]{24}\Z")
_SAFE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,199}\Z")
_SAFE_VERSION_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+:-]{0,127}\Z")

_BOUNDARIES = {
    "researchOnly": True,
    "readOnly": True,
    "sourceMutation": False,
    "productionDecisionAuthority": False,
    "engineConfidenceIndependent": True,
    "sourceQualityIndependent": True,
    "visualEvidenceIndependent": True,
    "aggregateComplexityScoreAuthority": False,
    "winnerSelection": False,
    "automaticMerge": False,
    "automaticCorrection": False,
    "teacherAuthorityOverride": False,
    "stage7EvidenceMutation": False,
    "stage7QuorumChange": False,
    "stOmrQuorumChange": False,
}
_CORE_KEYS = {
    "schemaVersion",
    "profileId",
    "canonicalReference",
    "scope",
    "method",
    "dimensions",
    "boundaries",
}
_FULL_KEYS = _CORE_KEYS | {"derivedState", "profileSha256"}
_METRIC_KEYS = {
    "available",
    "value",
    "numerator",
    "denominator",
    "unit",
    "method",
    "reason",
}
_DIMENSION_KEYS = {
    "voiceComplexity",
    "simultaneousNoteDensity",
    "staffComplexity",
    "tupletComplexity",
    "tieComplexity",
    "graceComplexity",
    "overlapComplexity",
    "rhythmicComplexity",
}
_DERIVED_KEYS = {
    "calculationMethodVersion",
    "descriptiveComponentsOnly",
    "aggregateComplexityScore",
    "complexityClass",
    "authoritative",
}


class PolyphonyComplexityError(ValueError):
    """Stable fail-closed SM-POLY-07 validation category."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    except (TypeError, ValueError, OverflowError, UnicodeEncodeError):
        raise PolyphonyComplexityError("polyphony_complexity_state_invalid") from None


def _matches(pattern: re.Pattern[str], value: object) -> bool:
    return type(value) is str and pattern.fullmatch(value) is not None


def _require_exact_keys(
    value: object, expected: set[str], category: str
) -> Mapping[str, Any]:
    if type(value) is not dict or set(value) != expected:
        raise PolyphonyComplexityError(category)
    return value


def _available_metric(
    value: int | bool,
    *,
    unit: str,
    method: str,
    numerator: int | None = None,
    denominator: int | None = None,
) -> dict[str, Any]:
    return {
        "available": True,
        "value": value,
        "numerator": numerator,
        "denominator": denominator,
        "unit": unit,
        "method": method,
        "reason": None,
    }


def _unavailable_metric(reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "value": None,
        "numerator": None,
        "denominator": None,
        "unit": None,
        "method": None,
        "reason": reason,
    }


def _ratio_metric(
    numerator: int,
    denominator: int,
    *,
    method: str,
    zero_denominator_is_zero: bool = False,
) -> dict[str, Any]:
    if denominator == 0:
        if not zero_denominator_is_zero:
            return _unavailable_metric("no_eligible_events")
        value = 0
    else:
        value = (numerator * 10_000) // denominator
    return _available_metric(
        value,
        unit="basis_points",
        method=method,
        numerator=numerator,
        denominator=denominator,
    )


def _validate_metric(value: object, *, value_type: type) -> None:
    metric = _require_exact_keys(value, _METRIC_KEYS, "complexity_metric_invalid")
    if type(metric["available"]) is not bool:
        raise PolyphonyComplexityError("complexity_metric_invalid")
    if metric["available"]:
        if value_type is bool:
            valid_value = type(metric["value"]) is bool
        else:
            valid_value = type(metric["value"]) is int and metric["value"] >= 0
        if (
            not valid_value
            or type(metric["unit"]) is not str
            or not metric["unit"]
            or not _matches(_SAFE_VERSION_RE, metric["method"])
            or metric["reason"] is not None
        ):
            raise PolyphonyComplexityError("complexity_metric_invalid")
        for key in ("numerator", "denominator"):
            if metric[key] is not None and (
                type(metric[key]) is not int or metric[key] < 0
            ):
                raise PolyphonyComplexityError("complexity_metric_invalid")
        if metric["unit"] == "basis_points":
            if (
                type(metric["value"]) is not int
                or not 0 <= metric["value"] <= 10_000
                or type(metric["numerator"]) is not int
                or type(metric["denominator"]) is not int
                or metric["numerator"] > metric["denominator"]
                or (
                    metric["denominator"] == 0
                    and (metric["numerator"] != 0 or metric["value"] != 0)
                )
            ):
                raise PolyphonyComplexityError("complexity_metric_invalid")
    else:
        if any(
            metric[key] is not None
            for key in ("value", "numerator", "denominator", "unit", "method")
        ):
            raise PolyphonyComplexityError("unavailable_complexity_contains_value")
        if (
            type(metric["reason"]) is not str
            or not metric["reason"]
            or len(metric["reason"]) > 160
        ):
            raise PolyphonyComplexityError("complexity_metric_invalid")


def _timed_events(events: Iterable[CanonicalEvent]) -> tuple[CanonicalEvent, ...]:
    return tuple(
        event
        for event in events
        if not event.grace and Fraction(event.effective_duration) > 0
    )


def _sounding_events(events: Iterable[CanonicalEvent]) -> tuple[CanonicalEvent, ...]:
    return tuple(
        event
        for event in events
        if not event.grace
        and event.kind in {"note", "unpitched"}
        and Fraction(event.effective_duration) > 0
    )


def _voice_stream(event: CanonicalEvent) -> tuple[int, str]:
    return (event.staff, event.voice)


def _max_simultaneous_voice_count(events: tuple[CanonicalEvent, ...]) -> int:
    if not events:
        return 0
    points = sorted(
        {Fraction(event.onset) for event in events} | {event.end for event in events}
    )
    maximum = 0
    for point in points:
        active = {
            _voice_stream(event)
            for event in events
            if Fraction(event.onset) <= point < event.end
        }
        maximum = max(maximum, len(active))
    return maximum


def _simultaneous_note_metrics(
    events: tuple[CanonicalEvent, ...],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    notes = _sounding_events(events)
    if not notes:
        unavailable = _unavailable_metric("no_eligible_note_events")
        return unavailable, deepcopy(unavailable), deepcopy(unavailable)

    by_onset: dict[Fraction, list[CanonicalEvent]] = defaultdict(list)
    for event in notes:
        by_onset[Fraction(event.onset)].append(event)

    simultaneous = 0
    chord_members = 0
    independent_voice_simultaneous = 0
    for group in by_onset.values():
        if len(group) > 1:
            simultaneous += len(group)
        chord_members += sum(event.chord_group is not None for event in group)
        streams = {_voice_stream(event) for event in group}
        if len(streams) > 1:
            independent_voice_simultaneous += len(group)

    denominator = len(notes)
    return (
        _ratio_metric(
            simultaneous,
            denominator,
            method="NOTE_EVENTS_SHARING_ONSET_V1",
        ),
        _ratio_metric(
            chord_members,
            denominator,
            method="CANONICAL_CHORD_MEMBER_EVENTS_V1",
        ),
        _ratio_metric(
            independent_voice_simultaneous,
            denominator,
            method="NOTE_EVENTS_AT_MULTI_VOICE_ONSETS_V1",
        ),
    )


def _overlap_pair_counts(events: tuple[CanonicalEvent, ...]) -> tuple[int, int]:
    notes = _sounding_events(events)
    by_staff: dict[int, list[CanonicalEvent]] = defaultdict(list)
    for event in notes:
        by_staff[event.staff].append(event)

    overlap_count = 0
    denominator = 0
    for staff_events in by_staff.values():
        for left_index, left in enumerate(staff_events):
            for right in staff_events[left_index + 1 :]:
                if _voice_stream(left) == _voice_stream(right):
                    continue
                denominator += 1
                if max(Fraction(left.onset), Fraction(right.onset)) < min(
                    left.end, right.end
                ):
                    overlap_count += 1
    return overlap_count, denominator


def _profile_id(canonical_sha256: str, part_id: str, measure_id: str) -> str:
    seed = {
        "schemaVersion": SCHEMA_VERSION,
        "canonicalScoreSha256": canonical_sha256,
        "scope": {"type": "MEASURE", "partId": part_id, "measureId": measure_id},
        "calculationMethodVersion": CALCULATION_METHOD_VERSION,
    }
    return "complexity_" + sha256(_canonical_json(seed)).hexdigest()[:24]


def _find_measure(
    score: CanonicalScore, part_id: str, measure_id: str
) -> CanonicalMeasure:
    matches = [
        measure
        for part in score.parts
        if part.part_id == part_id
        for measure in part.measures
        if measure.measure_id == measure_id
    ]
    if len(matches) != 1:
        raise PolyphonyComplexityError("complexity_scope_not_found")
    return matches[0]


def _build_dimensions(measure: CanonicalMeasure) -> dict[str, Any]:
    events = tuple(measure.events)
    if len(events) > MAX_EVENTS_PER_SCOPE:
        raise PolyphonyComplexityError("complexity_scope_event_bound_exceeded")

    timed = _timed_events(events)
    streams = {_voice_stream(event) for event in events}
    if len(streams) > MAX_VOICE_STREAMS_PER_SCOPE:
        raise PolyphonyComplexityError("complexity_scope_voice_bound_exceeded")

    voice_labels = {event.voice for event in events}

    simultaneous_density, chord_density, independent_voice_density = (
        _simultaneous_note_metrics(events)
    )

    staff_ids = {event.staff for event in events}
    if staff_ids:
        staff_count = _available_metric(
            len(staff_ids),
            unit="count",
            method="DISTINCT_CANONICAL_EVENT_STAFFS_V1",
        )
        multi_staff = _available_metric(
            len(staff_ids) > 1,
            unit="boolean",
            method="DISTINCT_CANONICAL_EVENT_STAFFS_V1",
        )
    else:
        staff_count = _unavailable_metric("canonical_measure_has_no_events")
        multi_staff = _unavailable_metric("canonical_measure_has_no_events")

    tuplet_count = sum(event.tuplet is not None for event in events)
    tie_eligible = _sounding_events(events)
    tie_count = sum(bool(event.ties) for event in tie_eligible)
    grace_count = sum(event.grace for event in events)

    overlap_count, overlap_denominator = _overlap_pair_counts(events)
    overlap_density = _ratio_metric(
        overlap_count,
        overlap_denominator,
        method="DISTINCT_VOICE_SOUNDING_EVENT_PAIR_OVERLAP_V1",
        zero_denominator_is_zero=True,
    )

    rhythmic_events = timed
    distinct_durations = {
        Fraction(event.effective_duration) for event in rhythmic_events
    }
    onset_denominators = {
        Fraction(event.onset).denominator for event in rhythmic_events
    }
    dotted_count = sum(event.dots > 0 for event in rhythmic_events)

    return {
        "voiceComplexity": {
            "voiceCount": _available_metric(
                len(voice_labels),
                unit="count",
                method="DISTINCT_CANONICAL_VOICE_LABELS_V1",
            ),
            "independentVoiceCount": _available_metric(
                len(streams),
                unit="count",
                method="DISTINCT_STAFF_VOICE_STREAMS_V1",
            ),
            "maxSimultaneousVoiceCount": (
                _available_metric(
                    _max_simultaneous_voice_count(timed),
                    unit="count",
                    method="ACTIVE_CANONICAL_VOICE_STREAMS_V1",
                )
                if timed
                else _unavailable_metric("no_timed_events")
            ),
        },
        "simultaneousNoteDensity": {
            "simultaneousNoteDensity": simultaneous_density,
            "chordDensity": chord_density,
            "independentVoiceOnsetDensity": independent_voice_density,
        },
        "staffComplexity": {
            "staffCount": staff_count,
            "multiStaffPresent": multi_staff,
            "crossStaffPresent": _unavailable_metric(
                "canonical_v1_has_no_cross_staff_attachment"
            ),
        },
        "tupletComplexity": {
            "tupletPresent": _available_metric(
                tuplet_count > 0,
                unit="boolean",
                method="CANONICAL_TUPLET_FIELD_V1",
            ),
            "tupletEventCount": _available_metric(
                tuplet_count,
                unit="count",
                method="CANONICAL_TUPLET_FIELD_V1",
            ),
            "nestedTupletAvailable": _available_metric(
                False,
                unit="boolean",
                method="CANONICAL_V1_CAPABILITY_DECLARATION",
            ),
            "nestedTupletPresent": _unavailable_metric(
                "canonical_v1_has_no_nested_tuplet_structure"
            ),
        },
        "tieComplexity": {
            "tieCount": _available_metric(
                tie_count,
                unit="events",
                method="EVENTS_WITH_CANONICAL_TIE_MARKER_V1",
            ),
            "tieDensity": _ratio_metric(
                tie_count,
                len(tie_eligible),
                method="TIE_BEARING_SOUNDING_EVENT_DENSITY_V1",
            ),
        },
        "graceComplexity": {
            "gracePresent": _available_metric(
                grace_count > 0,
                unit="boolean",
                method="CANONICAL_GRACE_FLAG_V1",
            ),
            "graceEventCount": _available_metric(
                grace_count,
                unit="count",
                method="CANONICAL_GRACE_FLAG_V1",
            ),
        },
        "overlapComplexity": {
            "overlapDensity": overlap_density,
            "overlapPairCount": _available_metric(
                overlap_count,
                unit="pairs",
                method="DISTINCT_VOICE_SOUNDING_EVENT_PAIR_OVERLAP_V1",
                numerator=overlap_count,
                denominator=overlap_denominator,
            ),
        },
        "rhythmicComplexity": {
            "distinctDurationCount": _available_metric(
                len(distinct_durations),
                unit="count",
                method="DISTINCT_EFFECTIVE_DURATION_FRACTIONS_V1",
            ),
            "dottedEventDensity": _ratio_metric(
                dotted_count,
                len(rhythmic_events),
                method="DOTTED_TIMED_EVENT_DENSITY_V1",
            ),
            "onsetSubdivisionDiversity": _available_metric(
                len(onset_denominators),
                unit="count",
                method="DISTINCT_REDUCED_ONSET_DENOMINATORS_V1",
            ),
            "overlappingRhythmPresent": _available_metric(
                overlap_count > 0,
                unit="boolean",
                method="DISTINCT_VOICE_SOUNDING_EVENT_PAIR_OVERLAP_V1",
            ),
            "tupletPresent": _available_metric(
                tuplet_count > 0,
                unit="boolean",
                method="CANONICAL_TUPLET_FIELD_V1",
            ),
        },
    }


def _derive_state() -> dict[str, Any]:
    return {
        "calculationMethodVersion": CALCULATION_METHOD_VERSION,
        "descriptiveComponentsOnly": True,
        "aggregateComplexityScore": None,
        "complexityClass": None,
        "authoritative": False,
    }


def build_polyphony_complexity_profile(
    score: CanonicalScore, *, part_id: str, measure_id: str
) -> dict[str, Any]:
    """Build a deterministic measure-scoped complexity sidecar from Canonical Score."""

    if not isinstance(score, CanonicalScore):
        raise PolyphonyComplexityError("canonical_score_required")
    if not _matches(_SAFE_ID_RE, part_id) or not _matches(_SAFE_ID_RE, measure_id):
        raise PolyphonyComplexityError("complexity_scope_invalid")

    measure = _find_measure(score, part_id, measure_id)
    canonical_sha = score.canonical_sha256
    core = {
        "schemaVersion": SCHEMA_VERSION,
        "profileId": _profile_id(canonical_sha, part_id, measure_id),
        "canonicalReference": {
            "canonicalScoreSha256": canonical_sha,
            "partId": part_id,
            "measureId": measure_id,
        },
        "scope": {
            "type": "MEASURE",
            "pageRef": None,
            "systemRef": None,
            "partId": part_id,
            "measureId": measure_id,
        },
        "method": {
            "calculationMethodVersion": CALCULATION_METHOD_VERSION,
            "canonicalSchemaVersion": "1.0",
            "pageScopeSupported": False,
            "systemScopeSupported": False,
            "measureScopeSupported": True,
        },
        "dimensions": _build_dimensions(measure),
        "boundaries": deepcopy(_BOUNDARIES),
    }
    detached = json.loads(_canonical_json(core).decode("ascii"))
    detached["derivedState"] = _derive_state()
    detached["profileSha256"] = sha256(_canonical_json(detached)).hexdigest()
    return detached


def _validate_dimensions(value: object) -> None:
    dimensions = _require_exact_keys(
        value, _DIMENSION_KEYS, "complexity_dimensions_invalid"
    )
    expected_types = {
        "voiceComplexity": {
            "voiceCount": int,
            "independentVoiceCount": int,
            "maxSimultaneousVoiceCount": int,
        },
        "simultaneousNoteDensity": {
            "simultaneousNoteDensity": int,
            "chordDensity": int,
            "independentVoiceOnsetDensity": int,
        },
        "staffComplexity": {
            "staffCount": int,
            "multiStaffPresent": bool,
            "crossStaffPresent": bool,
        },
        "tupletComplexity": {
            "tupletPresent": bool,
            "tupletEventCount": int,
            "nestedTupletAvailable": bool,
            "nestedTupletPresent": bool,
        },
        "tieComplexity": {
            "tieCount": int,
            "tieDensity": int,
        },
        "graceComplexity": {
            "gracePresent": bool,
            "graceEventCount": int,
        },
        "overlapComplexity": {
            "overlapDensity": int,
            "overlapPairCount": int,
        },
        "rhythmicComplexity": {
            "distinctDurationCount": int,
            "dottedEventDensity": int,
            "onsetSubdivisionDiversity": int,
            "overlappingRhythmPresent": bool,
            "tupletPresent": bool,
        },
    }
    for dimension_name, metric_types in expected_types.items():
        dimension = _require_exact_keys(
            dimensions[dimension_name],
            set(metric_types),
            "complexity_dimension_invalid",
        )
        for metric_name, value_type in metric_types.items():
            _validate_metric(dimension[metric_name], value_type=value_type)

    cross_staff = dimensions["staffComplexity"]["crossStaffPresent"]
    if cross_staff["available"] is not False:
        raise PolyphonyComplexityError("cross_staff_availability_invalid")
    nested_available = dimensions["tupletComplexity"]["nestedTupletAvailable"]
    nested_present = dimensions["tupletComplexity"]["nestedTupletPresent"]
    if nested_available["available"] is not True or nested_available["value"] is not False:
        raise PolyphonyComplexityError("nested_tuplet_availability_invalid")
    if nested_present["available"] is not False:
        raise PolyphonyComplexityError("nested_tuplet_availability_invalid")


def validate_polyphony_complexity_profile(
    payload: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate structure, unavailable states, authority boundaries, and SHA-256."""

    if type(payload) is not dict or set(payload) != _FULL_KEYS:
        raise PolyphonyComplexityError("polyphony_complexity_schema_invalid")
    if payload["schemaVersion"] != SCHEMA_VERSION or not _matches(
        _PROFILE_RE, payload["profileId"]
    ):
        raise PolyphonyComplexityError("polyphony_complexity_schema_invalid")

    reference = _require_exact_keys(
        payload["canonicalReference"],
        {"canonicalScoreSha256", "partId", "measureId"},
        "canonical_reference_invalid",
    )
    if (
        not _matches(_SHA_RE, reference["canonicalScoreSha256"])
        or not _matches(_SAFE_ID_RE, reference["partId"])
        or not _matches(_SAFE_ID_RE, reference["measureId"])
    ):
        raise PolyphonyComplexityError("canonical_reference_invalid")

    scope = _require_exact_keys(
        payload["scope"],
        {"type", "pageRef", "systemRef", "partId", "measureId"},
        "complexity_scope_invalid",
    )
    if (
        scope["type"] != "MEASURE"
        or scope["pageRef"] is not None
        or scope["systemRef"] is not None
        or scope["partId"] != reference["partId"]
        or scope["measureId"] != reference["measureId"]
    ):
        raise PolyphonyComplexityError("complexity_scope_invalid")

    method = _require_exact_keys(
        payload["method"],
        {
            "calculationMethodVersion",
            "canonicalSchemaVersion",
            "pageScopeSupported",
            "systemScopeSupported",
            "measureScopeSupported",
        },
        "complexity_method_invalid",
    )
    if (
        method["calculationMethodVersion"] != CALCULATION_METHOD_VERSION
        or method["canonicalSchemaVersion"] != "1.0"
        or method["pageScopeSupported"] is not False
        or method["systemScopeSupported"] is not False
        or method["measureScopeSupported"] is not True
    ):
        raise PolyphonyComplexityError("complexity_method_invalid")

    _validate_dimensions(payload["dimensions"])

    boundaries = _require_exact_keys(
        payload["boundaries"], set(_BOUNDARIES), "authority_boundary_invalid"
    )
    if any(boundaries[key] is not expected for key, expected in _BOUNDARIES.items()):
        raise PolyphonyComplexityError("authority_boundary_invalid")

    derived = _require_exact_keys(
        payload["derivedState"], _DERIVED_KEYS, "complexity_derived_state_invalid"
    )
    if dict(derived) != _derive_state():
        raise PolyphonyComplexityError("complexity_derived_state_invalid")

    if not _matches(_SHA_RE, payload["profileSha256"]):
        raise PolyphonyComplexityError("polyphony_complexity_hash_invalid")
    without_hash = {
        key: deepcopy(payload[key]) for key in _FULL_KEYS - {"profileSha256"}
    }
    expected_hash = sha256(_canonical_json(without_hash)).hexdigest()
    if payload["profileSha256"] != expected_hash:
        raise PolyphonyComplexityError("polyphony_complexity_hash_invalid")
    return deepcopy(dict(payload))


def validate_polyphony_complexity_profile_against_score(
    payload: Mapping[str, Any], score: CanonicalScore
) -> dict[str, Any]:
    """Recompute the sidecar from the referenced Canonical Score and compare exactly."""

    validated = validate_polyphony_complexity_profile(payload)
    reference = validated["canonicalReference"]
    if not isinstance(score, CanonicalScore) or (
        score.canonical_sha256 != reference["canonicalScoreSha256"]
    ):
        raise PolyphonyComplexityError("canonical_reference_mismatch")
    expected = build_polyphony_complexity_profile(
        score,
        part_id=reference["partId"],
        measure_id=reference["measureId"],
    )
    if validated != expected:
        raise PolyphonyComplexityError("polyphony_complexity_recompute_mismatch")
    return validated
