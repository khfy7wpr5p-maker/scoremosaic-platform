"""Immutable Canonical Score Model primitives for deterministic OMR comparison."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256
import json
import re
from typing import Any, Iterable, Mapping

SCHEMA_VERSION = "1.0"
_ALLOWED_ENGINES = frozenset({"homr", "clarity", "audiveris"})
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")


class CanonicalModelError(ValueError):
    """Raised when canonical data violates an invariant."""


def _require_text(value: str, *, name: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise CanonicalModelError(f"{name} must be a string")
    if not value or len(value) > maximum:
        raise CanonicalModelError(f"{name} length is invalid")
    if any(ord(character) < 32 for character in value):
        raise CanonicalModelError(f"{name} contains control characters")
    return value


def _fraction_payload(value: Fraction) -> dict[str, int]:
    value = Fraction(value)
    return {"numerator": value.numerator, "denominator": value.denominator}


@dataclass(frozen=True, slots=True)
class SourceIdentity:
    engine: str
    artifact_ref: str
    artifact_sha256: str
    engine_version: str | None = None
    model_version: str | None = None

    def __post_init__(self) -> None:
        if self.engine not in _ALLOWED_ENGINES:
            raise CanonicalModelError("unsupported source engine")
        _require_text(self.artifact_ref, name="artifact_ref", maximum=500)
        if ".." in self.artifact_ref.split("/") or "\\" in self.artifact_ref:
            raise CanonicalModelError("artifact_ref contains unsafe path syntax")
        if not _HEX_64.fullmatch(self.artifact_sha256):
            raise CanonicalModelError("artifact_sha256 must be lowercase SHA-256")
        if self.engine_version is not None:
            _require_text(self.engine_version, name="engine_version", maximum=200)
        if self.model_version is not None:
            _require_text(self.model_version, name="model_version", maximum=200)

    def as_dict(self) -> dict[str, Any]:
        return {
            "engine": self.engine,
            "engineVersion": self.engine_version,
            "modelVersion": self.model_version,
            "artifactRef": self.artifact_ref,
            "artifactSha256": self.artifact_sha256,
        }


@dataclass(frozen=True, slots=True)
class TimeSignature:
    beats: str
    beat_type: int

    def __post_init__(self) -> None:
        _require_text(self.beats, name="beats", maximum=40)
        if self.beat_type <= 0 or self.beat_type > 1024:
            raise CanonicalModelError("beat_type is outside the supported range")

    def as_dict(self) -> dict[str, Any]:
        return {"beats": self.beats, "beatType": self.beat_type}


@dataclass(frozen=True, slots=True)
class Pitch:
    step: str
    alter: Fraction
    octave: int

    def __post_init__(self) -> None:
        if self.step not in {"A", "B", "C", "D", "E", "F", "G"}:
            raise CanonicalModelError("pitch step is invalid")
        if self.octave < -2 or self.octave > 12:
            raise CanonicalModelError("pitch octave is outside the supported range")
        if abs(Fraction(self.alter)) > 8:
            raise CanonicalModelError("pitch alteration is outside the supported range")

    def as_dict(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "alter": _fraction_payload(Fraction(self.alter)),
            "octave": self.octave,
        }


@dataclass(frozen=True, slots=True)
class TabPosition:
    string: int
    fret: int

    def __post_init__(self) -> None:
        if self.string < 1 or self.string > 24:
            raise CanonicalModelError("TAB string is outside the supported range")
        if self.fret < 0 or self.fret > 96:
            raise CanonicalModelError("TAB fret is outside the supported range")

    def as_dict(self) -> dict[str, int]:
        return {"string": self.string, "fret": self.fret}


@dataclass(frozen=True, slots=True)
class TupletRatio:
    actual_notes: int
    normal_notes: int

    def __post_init__(self) -> None:
        if self.actual_notes <= 0 or self.actual_notes > 1024:
            raise CanonicalModelError("actual_notes is invalid")
        if self.normal_notes <= 0 or self.normal_notes > 1024:
            raise CanonicalModelError("normal_notes is invalid")

    def as_dict(self) -> dict[str, int]:
        return {
            "actualNotes": self.actual_notes,
            "normalNotes": self.normal_notes,
        }


@dataclass(frozen=True, slots=True)
class EventProvenance:
    xml_path: str
    source_event_index: int

    def __post_init__(self) -> None:
        _require_text(self.xml_path, name="xml_path", maximum=1000)
        if self.source_event_index < 0:
            raise CanonicalModelError("source_event_index must be non-negative")

    def as_dict(self) -> dict[str, Any]:
        return {
            "xmlPath": self.xml_path,
            "sourceEventIndex": self.source_event_index,
        }


@dataclass(frozen=True, slots=True)
class CanonicalEvent:
    event_id: str
    xml_order: int
    kind: str
    onset: Fraction
    effective_duration: Fraction
    written_duration: Fraction | None
    written_type: str | None
    dots: int
    tuplet: TupletRatio | None
    voice: str
    staff: int
    pitch: Pitch | None
    tab: TabPosition | None
    grace: bool
    chord_group: str | None
    chord_index: int | None
    ties: tuple[str, ...]
    provenance: EventProvenance

    def __post_init__(self) -> None:
        if not _SAFE_IDENTIFIER.fullmatch(self.event_id):
            raise CanonicalModelError("event_id is invalid")
        if self.xml_order < 0:
            raise CanonicalModelError("xml_order must be non-negative")
        if self.kind not in {"note", "rest", "unpitched"}:
            raise CanonicalModelError("event kind is invalid")
        if Fraction(self.onset) < 0:
            raise CanonicalModelError("event onset must be non-negative")
        if Fraction(self.effective_duration) < 0:
            raise CanonicalModelError("effective duration must be non-negative")
        if not self.grace and Fraction(self.effective_duration) <= 0:
            raise CanonicalModelError("non-grace events require positive duration")
        if self.written_duration is not None and Fraction(self.written_duration) <= 0:
            raise CanonicalModelError("written duration must be positive")
        if self.written_type is not None:
            _require_text(self.written_type, name="written_type", maximum=40)
        if self.dots < 0 or self.dots > 8:
            raise CanonicalModelError("dot count is invalid")
        _require_text(self.voice, name="voice", maximum=40)
        if self.staff < 1 or self.staff > 128:
            raise CanonicalModelError("staff is outside the supported range")
        if self.kind == "rest" and self.pitch is not None:
            raise CanonicalModelError("rest cannot contain pitch")
        if self.kind == "note" and self.pitch is None:
            raise CanonicalModelError("pitched note requires pitch")
        if self.chord_group is None:
            if self.chord_index is not None:
                raise CanonicalModelError("chord_index requires chord_group")
        else:
            if not _SAFE_IDENTIFIER.fullmatch(self.chord_group):
                raise CanonicalModelError("chord_group is invalid")
            if self.chord_index is None or self.chord_index < 0:
                raise CanonicalModelError("chord_group requires chord_index")
        allowed_ties = {"start", "stop", "continue"}
        if any(tie not in allowed_ties for tie in self.ties):
            raise CanonicalModelError("tie type is invalid")
        if tuple(sorted(set(self.ties))) != self.ties:
            raise CanonicalModelError("ties must be unique and sorted")

    @property
    def end(self) -> Fraction:
        return Fraction(self.onset) + Fraction(self.effective_duration)

    def as_dict(self) -> dict[str, Any]:
        return {
            "eventId": self.event_id,
            "xmlOrder": self.xml_order,
            "kind": self.kind,
            "onset": _fraction_payload(Fraction(self.onset)),
            "effectiveDuration": _fraction_payload(Fraction(self.effective_duration)),
            "writtenDuration": (
                _fraction_payload(Fraction(self.written_duration))
                if self.written_duration is not None
                else None
            ),
            "writtenType": self.written_type,
            "dots": self.dots,
            "tuplet": self.tuplet.as_dict() if self.tuplet else None,
            "voice": self.voice,
            "staff": self.staff,
            "pitch": self.pitch.as_dict() if self.pitch else None,
            "tab": self.tab.as_dict() if self.tab else None,
            "grace": self.grace,
            "chordGroup": self.chord_group,
            "chordIndex": self.chord_index,
            "ties": list(self.ties),
            "provenance": self.provenance.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class TimingMovement:
    kind: str
    xml_order: int
    duration: Fraction
    from_position: Fraction
    to_position: Fraction
    xml_path: str

    def __post_init__(self) -> None:
        if self.kind not in {"backup", "forward"}:
            raise CanonicalModelError("timing movement kind is invalid")
        if self.xml_order < 0:
            raise CanonicalModelError("xml_order must be non-negative")
        if Fraction(self.duration) <= 0:
            raise CanonicalModelError("timing movement duration must be positive")
        if Fraction(self.from_position) < 0 or Fraction(self.to_position) < 0:
            raise CanonicalModelError("timing positions must be non-negative")
        _require_text(self.xml_path, name="xml_path", maximum=1000)

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "xmlOrder": self.xml_order,
            "duration": _fraction_payload(Fraction(self.duration)),
            "fromPosition": _fraction_payload(Fraction(self.from_position)),
            "toPosition": _fraction_payload(Fraction(self.to_position)),
            "xmlPath": self.xml_path,
        }


@dataclass(frozen=True, slots=True)
class DivisionsChange:
    xml_order: int
    onset: Fraction
    divisions: int

    def __post_init__(self) -> None:
        if self.xml_order < 0 or Fraction(self.onset) < 0:
            raise CanonicalModelError("divisions change position is invalid")
        if self.divisions <= 0 or self.divisions > 1_000_000:
            raise CanonicalModelError("divisions is outside the supported range")

    def as_dict(self) -> dict[str, Any]:
        return {
            "xmlOrder": self.xml_order,
            "onset": _fraction_payload(Fraction(self.onset)),
            "divisions": self.divisions,
        }


@dataclass(frozen=True, slots=True)
class TimeSignatureChange:
    xml_order: int
    onset: Fraction
    time_signature: TimeSignature

    def __post_init__(self) -> None:
        if self.xml_order < 0 or Fraction(self.onset) < 0:
            raise CanonicalModelError("time signature change position is invalid")

    def as_dict(self) -> dict[str, Any]:
        return {
            "xmlOrder": self.xml_order,
            "onset": _fraction_payload(Fraction(self.onset)),
            "timeSignature": self.time_signature.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class CanonicalMeasure:
    measure_id: str
    number: str
    ordinal: int
    implicit: bool
    divisions_at_start: int | None
    time_signature_at_start: TimeSignature | None
    expected_duration: Fraction | None
    observed_duration: Fraction
    divisions_changes: tuple[DivisionsChange, ...]
    time_signature_changes: tuple[TimeSignatureChange, ...]
    timing_movements: tuple[TimingMovement, ...]
    events: tuple[CanonicalEvent, ...]

    def __post_init__(self) -> None:
        if not _SAFE_IDENTIFIER.fullmatch(self.measure_id):
            raise CanonicalModelError("measure_id is invalid")
        _require_text(self.number, name="measure number", maximum=40)
        if self.ordinal < 1:
            raise CanonicalModelError("measure ordinal must be positive")
        if self.divisions_at_start is not None and self.divisions_at_start <= 0:
            raise CanonicalModelError("divisions_at_start must be positive")
        if self.expected_duration is not None and Fraction(self.expected_duration) <= 0:
            raise CanonicalModelError("expected_duration must be positive")
        if Fraction(self.observed_duration) < 0:
            raise CanonicalModelError("observed_duration must be non-negative")
        event_ids = [event.event_id for event in self.events]
        if len(event_ids) != len(set(event_ids)):
            raise CanonicalModelError("duplicate event_id in measure")
        if tuple(sorted(self.events, key=lambda event: event.xml_order)) != self.events:
            raise CanonicalModelError("events must preserve XML order")

    def as_dict(self) -> dict[str, Any]:
        return {
            "measureId": self.measure_id,
            "number": self.number,
            "ordinal": self.ordinal,
            "implicit": self.implicit,
            "divisionsAtStart": self.divisions_at_start,
            "timeSignatureAtStart": (
                self.time_signature_at_start.as_dict()
                if self.time_signature_at_start
                else None
            ),
            "expectedDuration": (
                _fraction_payload(Fraction(self.expected_duration))
                if self.expected_duration is not None
                else None
            ),
            "observedDuration": _fraction_payload(Fraction(self.observed_duration)),
            "divisionsChanges": [change.as_dict() for change in self.divisions_changes],
            "timeSignatureChanges": [
                change.as_dict() for change in self.time_signature_changes
            ],
            "timingMovements": [movement.as_dict() for movement in self.timing_movements],
            "events": [event.as_dict() for event in self.events],
        }


@dataclass(frozen=True, slots=True)
class CanonicalPart:
    part_id: str
    name: str | None
    ordinal: int
    measures: tuple[CanonicalMeasure, ...]

    def __post_init__(self) -> None:
        if not _SAFE_IDENTIFIER.fullmatch(self.part_id):
            raise CanonicalModelError("part_id is invalid")
        if self.name is not None:
            _require_text(self.name, name="part name", maximum=300)
        if self.ordinal < 1:
            raise CanonicalModelError("part ordinal must be positive")
        measure_ids = [measure.measure_id for measure in self.measures]
        if len(measure_ids) != len(set(measure_ids)):
            raise CanonicalModelError("duplicate measure_id in part")

    def as_dict(self) -> dict[str, Any]:
        return {
            "partId": self.part_id,
            "name": self.name,
            "ordinal": self.ordinal,
            "measures": [measure.as_dict() for measure in self.measures],
        }


@dataclass(frozen=True, slots=True)
class NormalizationDiagnostic:
    code: str
    severity: str
    message: str
    xml_path: str | None = None

    def __post_init__(self) -> None:
        if not _SAFE_IDENTIFIER.fullmatch(self.code):
            raise CanonicalModelError("diagnostic code is invalid")
        if self.severity not in {"info", "warning"}:
            raise CanonicalModelError("diagnostic severity is invalid")
        _require_text(self.message, name="diagnostic message", maximum=1000)
        if self.xml_path is not None:
            _require_text(self.xml_path, name="xml_path", maximum=1000)

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "xmlPath": self.xml_path,
        }


@dataclass(frozen=True, slots=True)
class CanonicalScore:
    source: SourceIdentity
    root_type: str
    parts: tuple[CanonicalPart, ...]
    diagnostics: tuple[NormalizationDiagnostic, ...] = ()
    movement_title: str | None = None

    def __post_init__(self) -> None:
        if self.root_type != "score-partwise":
            raise CanonicalModelError("only score-partwise is supported in foundation v1")
        if not self.parts:
            raise CanonicalModelError("canonical score requires at least one part")
        if self.movement_title is not None:
            _require_text(self.movement_title, name="movement_title", maximum=500)
        part_ids = [part.part_id for part in self.parts]
        if len(part_ids) != len(set(part_ids)):
            raise CanonicalModelError("duplicate part_id in score")

    def _payload_without_hash(self) -> dict[str, Any]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "source": self.source.as_dict(),
            "rootType": self.root_type,
            "movementTitle": self.movement_title,
            "parts": [part.as_dict() for part in self.parts],
            "diagnostics": [diagnostic.as_dict() for diagnostic in self.diagnostics],
        }

    @property
    def canonical_sha256(self) -> str:
        payload = json.dumps(
            self._payload_without_hash(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return sha256(payload).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        payload = self._payload_without_hash()
        payload["canonicalSha256"] = self.canonical_sha256
        return payload

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(
            self.as_dict(),
            ensure_ascii=False,
            sort_keys=True,
            indent=indent,
            separators=None if indent is not None else (",", ":"),
        )

    @property
    def event_count(self) -> int:
        return sum(
            len(measure.events)
            for part in self.parts
            for measure in part.measures
        )

    @property
    def measure_count(self) -> int:
        return sum(len(part.measures) for part in self.parts)


def ensure_unique_identifiers(values: Iterable[str], *, name: str) -> None:
    collected = tuple(values)
    if len(collected) != len(set(collected)):
        raise CanonicalModelError(f"duplicate {name}")


def canonical_json_digest(payload: Mapping[str, Any]) -> str:
    """Return a deterministic digest for external contract fixtures."""

    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()
