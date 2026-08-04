"""Deterministic, read-only comparison of Canonical Score Model candidates."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256
import json
import re
from typing import Any, Callable, Iterable, Sequence

from .canonical import (
    CanonicalEvent,
    CanonicalMeasure,
    CanonicalPart,
    CanonicalScore,
    Pitch,
    SourceIdentity,
    TabPosition,
    TimeSignature,
    TupletRatio,
)

COMPARISON_FORMAT_VERSION = "0.1-foundation"
MAX_CANDIDATES = 8
MAX_TOTAL_EVENTS = 250_000
MAX_DIFFERENCES = 200_000

_ALLOWED_CATEGORIES = frozenset(
    {
        "measure",
        "event_time",
        "pitch",
        "duration",
        "rest",
        "chord",
        "voice",
        "staff",
        "tie",
        "dot",
        "tuplet",
        "tab",
    }
)
_SAFE_FIELD = re.compile(r"^[a-z][A-Za-z0-9.]{0,99}$")
_SAFE_CANDIDATE_ID = re.compile(r"^candidate_[0-9a-f]{24}$")


class ComparisonError(ValueError):
    """Raised when candidates cannot be compared inside foundation limits."""


def _fraction_payload(value: Fraction) -> dict[str, int]:
    fraction = Fraction(value)
    return {
        "numerator": fraction.numerator,
        "denominator": fraction.denominator,
    }


def _json_value(value: Any) -> Any:
    if isinstance(value, Fraction):
        return _fraction_payload(value)
    if isinstance(value, (Pitch, TabPosition, TimeSignature, TupletRatio)):
        return value.as_dict()
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): _json_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise ComparisonError(f"unsupported comparison value type: {type(value).__name__}")


def _canonical_json(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _candidate_id(source: SourceIdentity) -> str:
    digest = sha256(_canonical_json(source.as_dict())).hexdigest()
    return f"candidate_{digest[:24]}"


@dataclass(frozen=True, slots=True)
class CandidateSummary:
    candidate_id: str
    source: SourceIdentity
    canonical_sha256: str
    part_count: int
    measure_count: int
    event_count: int

    def __post_init__(self) -> None:
        if not _SAFE_CANDIDATE_ID.fullmatch(self.candidate_id):
            raise ComparisonError("candidate_id is invalid")
        if len(self.canonical_sha256) != 64:
            raise ComparisonError("canonical_sha256 is invalid")
        if min(self.part_count, self.measure_count, self.event_count) < 0:
            raise ComparisonError("candidate counts must be non-negative")

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidateId": self.candidate_id,
            "source": self.source.as_dict(),
            "canonicalSha256": self.canonical_sha256,
            "partCount": self.part_count,
            "measureCount": self.measure_count,
            "eventCount": self.event_count,
        }


@dataclass(frozen=True, slots=True)
class ComparisonLocation:
    part_ordinal: int
    measure_ordinal: int | None = None
    event_ordinal: int | None = None

    def __post_init__(self) -> None:
        if self.part_ordinal < 1:
            raise ComparisonError("part_ordinal must be positive")
        if self.measure_ordinal is not None and self.measure_ordinal < 1:
            raise ComparisonError("measure_ordinal must be positive")
        if self.event_ordinal is not None:
            if self.measure_ordinal is None or self.event_ordinal < 1:
                raise ComparisonError("event_ordinal requires a measure")

    def as_dict(self) -> dict[str, int | None]:
        return {
            "partOrdinal": self.part_ordinal,
            "measureOrdinal": self.measure_ordinal,
            "eventOrdinal": self.event_ordinal,
        }


@dataclass(frozen=True, slots=True)
class CandidateObservation:
    candidate_id: str
    source: SourceIdentity
    canonical_sha256: str
    present: bool
    value: Any
    part_id: str | None = None
    measure_id: str | None = None
    measure_number: str | None = None
    event_id: str | None = None
    xml_path: str | None = None
    source_event_index: int | None = None

    def __post_init__(self) -> None:
        if not _SAFE_CANDIDATE_ID.fullmatch(self.candidate_id):
            raise ComparisonError("observation candidate_id is invalid")
        if len(self.canonical_sha256) != 64:
            raise ComparisonError("observation canonical_sha256 is invalid")
        if self.source_event_index is not None and self.source_event_index < 0:
            raise ComparisonError("source_event_index must be non-negative")
        _json_value(self.value)

    def comparison_payload(self) -> dict[str, Any]:
        return {
            "candidateId": self.candidate_id,
            "present": self.present,
            "value": _json_value(self.value),
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidateId": self.candidate_id,
            "source": self.source.as_dict(),
            "canonicalSha256": self.canonical_sha256,
            "present": self.present,
            "value": _json_value(self.value),
            "provenance": {
                "partId": self.part_id,
                "measureId": self.measure_id,
                "measureNumber": self.measure_number,
                "eventId": self.event_id,
                "xmlPath": self.xml_path,
                "sourceEventIndex": self.source_event_index,
            },
        }


@dataclass(frozen=True, slots=True)
class ComparisonDifference:
    category: str
    field: str
    location: ComparisonLocation
    observations: tuple[CandidateObservation, ...]

    def __post_init__(self) -> None:
        if self.category not in _ALLOWED_CATEGORIES:
            raise ComparisonError("comparison category is invalid")
        if not _SAFE_FIELD.fullmatch(self.field):
            raise ComparisonError("comparison field is invalid")
        if len(self.observations) < 2:
            raise ComparisonError("a difference requires at least two observations")
        candidate_ids = tuple(item.candidate_id for item in self.observations)
        if candidate_ids != tuple(sorted(candidate_ids)):
            raise ComparisonError("observations must be sorted by candidate_id")
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ComparisonError("duplicate candidate observation")
        signatures = {
            _canonical_json(observation.comparison_payload())
            for observation in self.observations
        }
        if len(signatures) < 2:
            raise ComparisonError("difference observations do not disagree")

    def _payload_without_id(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "field": self.field,
            "location": self.location.as_dict(),
            "observations": [item.as_dict() for item in self.observations],
        }

    @property
    def difference_id(self) -> str:
        digest = sha256(_canonical_json(self._payload_without_id())).hexdigest()
        return f"difference_{digest[:24]}"

    def as_dict(self) -> dict[str, Any]:
        payload = self._payload_without_id()
        payload["differenceId"] = self.difference_id
        payload["description"] = f"Canonical candidates disagree on {self.field}."
        return payload


@dataclass(frozen=True, slots=True)
class ComparisonResult:
    candidates: tuple[CandidateSummary, ...]
    differences: tuple[ComparisonDifference, ...]

    def __post_init__(self) -> None:
        candidate_ids = tuple(candidate.candidate_id for candidate in self.candidates)
        if candidate_ids != tuple(sorted(candidate_ids)):
            raise ComparisonError("candidate summaries must be sorted")
        if len(candidate_ids) < 2 or len(candidate_ids) > MAX_CANDIDATES:
            raise ComparisonError("candidate count is outside foundation limits")
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ComparisonError("duplicate candidate summary")
        if len(self.differences) > MAX_DIFFERENCES:
            raise ComparisonError("difference count exceeds foundation limit")

    @property
    def identical(self) -> bool:
        return not self.differences

    def _payload_without_hash(self) -> dict[str, Any]:
        return {
            "formatVersion": COMPARISON_FORMAT_VERSION,
            "comparisonMode": "neutral-all-candidates",
            "alignment": {
                "parts": "ordinal",
                "measures": "ordinal",
                "events": "xml-event-ordinal",
                "fuzzyAlignment": False,
            },
            "boundaries": {
                "readOnly": True,
                "engineRanking": False,
                "winnerSelection": False,
                "automaticMerge": False,
                "automaticCorrection": False,
                "teacherApproval": False,
                "publication": False,
            },
            "candidateCount": len(self.candidates),
            "differenceCount": len(self.differences),
            "identical": self.identical,
            "candidates": [candidate.as_dict() for candidate in self.candidates],
            "differences": [difference.as_dict() for difference in self.differences],
        }

    @property
    def result_sha256(self) -> str:
        return sha256(_canonical_json(self._payload_without_hash())).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        payload = self._payload_without_hash()
        payload["resultSha256"] = self.result_sha256
        return payload

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(
            self.as_dict(),
            ensure_ascii=False,
            sort_keys=True,
            indent=indent,
            separators=None if indent is not None else (",", ":"),
        )


@dataclass(frozen=True, slots=True)
class _CandidateView:
    candidate_id: str
    score: CanonicalScore


ValueGetter = Callable[[Any], Any]


def _index_by_ordinal(items: Sequence[Any], *, name: str) -> dict[int, Any]:
    indexed: dict[int, Any] = {}
    for item in items:
        ordinal = item.ordinal
        if ordinal in indexed:
            raise ComparisonError(f"duplicate {name} ordinal")
        indexed[ordinal] = item
    return indexed


def _observation(
    view: _CandidateView,
    *,
    present: bool,
    value: Any,
    part: CanonicalPart | None = None,
    measure: CanonicalMeasure | None = None,
    event: CanonicalEvent | None = None,
) -> CandidateObservation:
    provenance = event.provenance if event is not None else None
    return CandidateObservation(
        candidate_id=view.candidate_id,
        source=view.score.source,
        canonical_sha256=view.score.canonical_sha256,
        present=present,
        value=_json_value(value),
        part_id=part.part_id if part is not None else None,
        measure_id=measure.measure_id if measure is not None else None,
        measure_number=measure.number if measure is not None else None,
        event_id=event.event_id if event is not None else None,
        xml_path=provenance.xml_path if provenance is not None else None,
        source_event_index=(
            provenance.source_event_index if provenance is not None else None
        ),
    )


def _observations_disagree(observations: Sequence[CandidateObservation]) -> bool:
    signatures = {
        _canonical_json(
            {
                "present": observation.present,
                "value": _json_value(observation.value),
            }
        )
        for observation in observations
    }
    return len(signatures) > 1


def _append_difference(
    differences: list[ComparisonDifference],
    *,
    category: str,
    field: str,
    location: ComparisonLocation,
    observations: Sequence[CandidateObservation],
) -> None:
    ordered = tuple(sorted(observations, key=lambda item: item.candidate_id))
    if not _observations_disagree(ordered):
        return
    if len(differences) >= MAX_DIFFERENCES:
        raise ComparisonError("difference count exceeds foundation limit")
    differences.append(
        ComparisonDifference(
            category=category,
            field=field,
            location=location,
            observations=ordered,
        )
    )


def _compare_present_objects(
    differences: list[ComparisonDifference],
    *,
    views: Sequence[_CandidateView],
    objects: Sequence[Any],
    parts: Sequence[CanonicalPart],
    measures: Sequence[CanonicalMeasure | None],
    events: Sequence[CanonicalEvent | None],
    category: str,
    field: str,
    location: ComparisonLocation,
    getter: ValueGetter,
) -> None:
    observations = [
        _observation(
            view,
            present=True,
            value=getter(item),
            part=part,
            measure=measure,
            event=event,
        )
        for view, item, part, measure, event in zip(
            views,
            objects,
            parts,
            measures,
            events,
            strict=True,
        )
    ]
    _append_difference(
        differences,
        category=category,
        field=field,
        location=location,
        observations=observations,
    )


def _difference_sort_key(difference: ComparisonDifference) -> tuple[Any, ...]:
    location = difference.location
    return (
        location.part_ordinal,
        location.measure_ordinal or 0,
        location.event_ordinal or 0,
        difference.category,
        difference.field,
        difference.difference_id,
    )


def compare_candidates(candidates: Iterable[CanonicalScore]) -> ComparisonResult:
    """Compare two to eight immutable CanonicalScore objects without selecting a winner."""

    scores = tuple(candidates)
    if len(scores) < 2 or len(scores) > MAX_CANDIDATES:
        raise ComparisonError("two to eight candidates are required")
    if any(not isinstance(score, CanonicalScore) for score in scores):
        raise ComparisonError("all candidates must be CanonicalScore objects")

    total_events = sum(score.event_count for score in scores)
    if total_events > MAX_TOTAL_EVENTS:
        raise ComparisonError("candidate event count exceeds foundation limit")

    views = tuple(
        sorted(
            (_CandidateView(_candidate_id(score.source), score) for score in scores),
            key=lambda view: view.candidate_id,
        )
    )
    candidate_ids = tuple(view.candidate_id for view in views)
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ComparisonError("duplicate candidate source identity")

    summaries = tuple(
        CandidateSummary(
            candidate_id=view.candidate_id,
            source=view.score.source,
            canonical_sha256=view.score.canonical_sha256,
            part_count=len(view.score.parts),
            measure_count=view.score.measure_count,
            event_count=view.score.event_count,
        )
        for view in views
    )

    part_maps = {
        view.candidate_id: _index_by_ordinal(view.score.parts, name="part")
        for view in views
    }
    part_ordinals = sorted(
        {
            ordinal
            for mapping in part_maps.values()
            for ordinal in mapping
        }
    )
    differences: list[ComparisonDifference] = []

    for part_ordinal in part_ordinals:
        location = ComparisonLocation(part_ordinal=part_ordinal)
        candidate_parts = [
            part_maps[view.candidate_id].get(part_ordinal)
            for view in views
        ]
        if any(part is None for part in candidate_parts):
            observations = [
                _observation(
                    view,
                    present=part is not None,
                    value=part is not None,
                    part=part,
                )
                for view, part in zip(views, candidate_parts, strict=True)
            ]
            _append_difference(
                differences,
                category="measure",
                field="part.presence",
                location=location,
                observations=observations,
            )
            continue

        parts = tuple(candidate_parts)
        measure_maps = {
            view.candidate_id: _index_by_ordinal(part.measures, name="measure")
            for view, part in zip(views, parts, strict=True)
        }
        measure_ordinals = sorted(
            {
                ordinal
                for mapping in measure_maps.values()
                for ordinal in mapping
            }
        )

        for measure_ordinal in measure_ordinals:
            measure_location = ComparisonLocation(
                part_ordinal=part_ordinal,
                measure_ordinal=measure_ordinal,
            )
            candidate_measures = [
                measure_maps[view.candidate_id].get(measure_ordinal)
                for view in views
            ]
            if any(measure is None for measure in candidate_measures):
                observations = [
                    _observation(
                        view,
                        present=measure is not None,
                        value=measure is not None,
                        part=part,
                        measure=measure,
                    )
                    for view, part, measure in zip(
                        views,
                        parts,
                        candidate_measures,
                        strict=True,
                    )
                ]
                _append_difference(
                    differences,
                    category="measure",
                    field="measure.presence",
                    location=measure_location,
                    observations=observations,
                )
                continue

            measures = tuple(candidate_measures)
            no_events: tuple[None, ...] = tuple(None for _ in views)
            measure_fields: tuple[tuple[str, str, ValueGetter], ...] = (
                ("measure", "measure.number", lambda item: item.number),
                ("measure", "measure.implicit", lambda item: item.implicit),
                (
                    "measure",
                    "measure.expectedDuration",
                    lambda item: item.expected_duration,
                ),
                (
                    "measure",
                    "measure.observedDuration",
                    lambda item: item.observed_duration,
                ),
                (
                    "measure",
                    "measure.timeSignature",
                    lambda item: item.time_signature_at_start,
                ),
            )
            for category, field, getter in measure_fields:
                _compare_present_objects(
                    differences,
                    views=views,
                    objects=measures,
                    parts=parts,
                    measures=measures,
                    events=no_events,
                    category=category,
                    field=field,
                    location=measure_location,
                    getter=getter,
                )

            max_event_count = max(len(measure.events) for measure in measures)
            for event_index in range(max_event_count):
                event_ordinal = event_index + 1
                event_location = ComparisonLocation(
                    part_ordinal=part_ordinal,
                    measure_ordinal=measure_ordinal,
                    event_ordinal=event_ordinal,
                )
                candidate_events = [
                    measure.events[event_index]
                    if event_index < len(measure.events)
                    else None
                    for measure in measures
                ]
                if any(event is None for event in candidate_events):
                    observations = [
                        _observation(
                            view,
                            present=event is not None,
                            value=event is not None,
                            part=part,
                            measure=measure,
                            event=event,
                        )
                        for view, part, measure, event in zip(
                            views,
                            parts,
                            measures,
                            candidate_events,
                            strict=True,
                        )
                    ]
                    _append_difference(
                        differences,
                        category="measure",
                        field="event.presence",
                        location=event_location,
                        observations=observations,
                    )
                    continue

                events = tuple(candidate_events)
                event_fields: tuple[tuple[str, str, ValueGetter], ...] = (
                    ("event_time", "event.onset", lambda item: item.onset),
                    ("rest", "event.kind", lambda item: item.kind),
                    (
                        "duration",
                        "event.effectiveDuration",
                        lambda item: item.effective_duration,
                    ),
                    (
                        "duration",
                        "event.writtenDuration",
                        lambda item: item.written_duration,
                    ),
                    (
                        "duration",
                        "event.writtenType",
                        lambda item: item.written_type,
                    ),
                    ("pitch", "event.pitch", lambda item: item.pitch),
                    (
                        "chord",
                        "event.chord",
                        lambda item: {
                            "member": item.chord_group is not None,
                            "index": item.chord_index,
                        },
                    ),
                    ("voice", "event.voice", lambda item: item.voice),
                    ("staff", "event.staff", lambda item: item.staff),
                    ("tie", "event.ties", lambda item: item.ties),
                    ("dot", "event.dots", lambda item: item.dots),
                    ("tuplet", "event.tuplet", lambda item: item.tuplet),
                    ("tab", "event.tab", lambda item: item.tab),
                )
                for category, field, getter in event_fields:
                    _compare_present_objects(
                        differences,
                        views=views,
                        objects=events,
                        parts=parts,
                        measures=measures,
                        events=events,
                        category=category,
                        field=field,
                        location=event_location,
                        getter=getter,
                    )

    ordered_differences = tuple(sorted(differences, key=_difference_sort_key))
    return ComparisonResult(candidates=summaries, differences=ordered_differences)
