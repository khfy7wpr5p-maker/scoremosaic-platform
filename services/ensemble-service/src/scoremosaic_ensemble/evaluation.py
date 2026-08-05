"""Deterministic evaluation of immutable Canonical Score candidates on a frozen dataset."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Mapping

from .canonical import CanonicalEvent, CanonicalScore

DATASET_SCHEMA_VERSION = "1.0"
DATASET_TYPE = "scoremosaic.fixed-omr-evaluation-dataset"
RESULT_SCHEMA_VERSION = "1.0"
RESULT_TYPE = "scoremosaic.fixed-omr-evaluation-result"

METRIC_NAMES = (
    "eventPresence",
    "onset",
    "kind",
    "effectiveDuration",
    "writtenDuration",
    "writtenType",
    "pitch",
    "chord",
    "voice",
    "staff",
    "ties",
    "dots",
    "tuplet",
    "tab",
)
CORE_METRIC_NAMES = (
    "eventPresence",
    "onset",
    "kind",
    "effectiveDuration",
    "pitch",
)

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,99}$")
_ALLOWED_ENGINES = frozenset({"audiveris", "homr", "clarity"})
_MANIFEST_KEYS = frozenset(
    {
        "schemaVersion",
        "datasetType",
        "datasetId",
        "datasetSha256",
        "status",
        "caseCount",
        "generalAccuracyClaim",
        "metricSet",
        "boundaries",
        "cases",
    }
)
_METRIC_SET_KEYS = frozenset(
    {
        "metricNames",
        "coreMetricNames",
        "aggregateScoreEnabled",
        "engineRankingEnabled",
        "winnerSelectionEnabled",
    }
)
_BOUNDARY_KEYS = frozenset(
    {
        "readOnly",
        "datasetMutation",
        "automaticMerge",
        "automaticCorrection",
        "engineRanking",
        "winnerSelection",
        "teacherApproval",
        "publication",
        "liveTraining",
        "stOmrIntegration",
    }
)
_CASE_KEYS = frozenset(
    {
        "caseId",
        "description",
        "profile",
        "reference",
        "candidates",
    }
)
_REFERENCE_KEYS = frozenset(
    {
        "path",
        "sha256",
        "reviewStatus",
        "partCount",
        "measureCount",
        "eventCount",
        "events",
    }
)
_TRUTH_EVENT_KEYS = frozenset(
    {
        "partOrdinal",
        "measureOrdinal",
        "eventOrdinal",
        "onset",
        "kind",
        "effectiveDuration",
        "writtenDuration",
        "writtenType",
        "pitch",
        "chord",
        "voice",
        "staff",
        "ties",
        "dots",
        "tuplet",
        "tab",
    }
)
_CANDIDATE_KEYS = frozenset(
    {
        "engine",
        "engineVersion",
        "modelVersion",
        "path",
        "sha256",
        "expected",
    }
)
_EXPECTED_KEYS = frozenset(
    {
        "partCount",
        "measureCount",
        "eventCount",
        "metrics",
        "coreSuccess",
        "allFieldsPerfect",
    }
)
_RESULT_KEYS = frozenset(
    {
        "schemaVersion",
        "reportType",
        "datasetId",
        "datasetSha256",
        "caseId",
        "candidate",
        "counts",
        "metrics",
        "gates",
        "boundaries",
        "resultSha256",
    }
)


class EvaluationError(ValueError):
    """Raised when a frozen dataset or evaluation result violates its contract."""


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _self_hash(payload: Mapping[str, Any], field: str) -> str:
    body = dict(payload)
    body.pop(field, None)
    return sha256(_canonical_json(body)).hexdigest()


def _require_exact_keys(value: Mapping[str, Any], expected: frozenset[str], name: str) -> None:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise EvaluationError(f"{name} fields are invalid")


def _require_sha256(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _HEX_64.fullmatch(value):
        raise EvaluationError(f"{name} must be lowercase SHA-256")
    return value


def _require_id(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value):
        raise EvaluationError(f"{name} is invalid")
    return value


def _safe_relative_path(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 500:
        raise EvaluationError(f"{name} is invalid")
    path = Path(value)
    if path.is_absolute() or "\\" in value or ".." in path.parts:
        raise EvaluationError(f"{name} contains unsafe path syntax")
    if any(part in {"", "."} for part in path.parts):
        raise EvaluationError(f"{name} contains unsafe path syntax")
    return value


def _resolve_file(root: Path, relative: str) -> Path:
    root = root.resolve()
    path = (root / relative).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise EvaluationError("dataset path escapes repository root") from exc
    if path.is_symlink() or not path.is_file():
        raise EvaluationError("dataset artifact must be a regular non-symlink file")
    return path


def _fraction_payload(value: Fraction) -> dict[str, int]:
    fraction = Fraction(value)
    return {
        "numerator": fraction.numerator,
        "denominator": fraction.denominator,
    }


def _validate_fraction_payload(value: Any, name: str, *, nullable: bool = False) -> None:
    if nullable and value is None:
        return
    if not isinstance(value, Mapping) or set(value) != {"numerator", "denominator"}:
        raise EvaluationError(f"{name} is invalid")
    numerator = value["numerator"]
    denominator = value["denominator"]
    if not isinstance(numerator, int) or isinstance(numerator, bool):
        raise EvaluationError(f"{name} numerator is invalid")
    if not isinstance(denominator, int) or isinstance(denominator, bool) or denominator <= 0:
        raise EvaluationError(f"{name} denominator is invalid")
    fraction = Fraction(numerator, denominator)
    if fraction.numerator != numerator or fraction.denominator != denominator:
        raise EvaluationError(f"{name} must be reduced")


def _validate_truth_event(event: Any, expected_location: tuple[int, int, int]) -> None:
    _require_exact_keys(event, _TRUTH_EVENT_KEYS, "truth event")
    location = (
        event["partOrdinal"],
        event["measureOrdinal"],
        event["eventOrdinal"],
    )
    if location != expected_location:
        raise EvaluationError("truth events must be contiguous and ordered")
    if event["kind"] not in {"note", "rest", "unpitched"}:
        raise EvaluationError("truth event kind is invalid")
    _validate_fraction_payload(event["onset"], "truth onset")
    _validate_fraction_payload(event["effectiveDuration"], "truth effective duration")
    _validate_fraction_payload(event["writtenDuration"], "truth written duration", nullable=True)
    if event["writtenType"] is not None and (
        not isinstance(event["writtenType"], str) or not event["writtenType"]
    ):
        raise EvaluationError("truth written type is invalid")
    pitch = event["pitch"]
    if pitch is not None:
        if not isinstance(pitch, Mapping) or set(pitch) != {"step", "alter", "octave"}:
            raise EvaluationError("truth pitch is invalid")
        if pitch["step"] not in {"A", "B", "C", "D", "E", "F", "G"}:
            raise EvaluationError("truth pitch step is invalid")
        _validate_fraction_payload(pitch["alter"], "truth pitch alteration")
        if not isinstance(pitch["octave"], int) or isinstance(pitch["octave"], bool):
            raise EvaluationError("truth pitch octave is invalid")
    chord = event["chord"]
    if not isinstance(chord, Mapping) or set(chord) != {"member", "index"}:
        raise EvaluationError("truth chord is invalid")
    if not isinstance(chord["member"], bool):
        raise EvaluationError("truth chord membership is invalid")
    if chord["member"]:
        if not isinstance(chord["index"], int) or chord["index"] < 0:
            raise EvaluationError("truth chord index is invalid")
    elif chord["index"] is not None:
        raise EvaluationError("truth chord index requires membership")
    if not isinstance(event["voice"], str) or not event["voice"]:
        raise EvaluationError("truth voice is invalid")
    if not isinstance(event["staff"], int) or isinstance(event["staff"], bool) or event["staff"] < 1:
        raise EvaluationError("truth staff is invalid")
    ties = event["ties"]
    if not isinstance(ties, list) or ties != sorted(set(ties)):
        raise EvaluationError("truth ties are invalid")
    if any(tie not in {"start", "stop", "continue"} for tie in ties):
        raise EvaluationError("truth tie type is invalid")
    if not isinstance(event["dots"], int) or isinstance(event["dots"], bool) or event["dots"] < 0:
        raise EvaluationError("truth dots are invalid")
    for nullable_field in ("tuplet", "tab"):
        value = event[nullable_field]
        if value is not None and not isinstance(value, Mapping):
            raise EvaluationError(f"truth {nullable_field} is invalid")


def _validate_expected(expected: Any, reference: Mapping[str, Any]) -> None:
    _require_exact_keys(expected, _EXPECTED_KEYS, "candidate expected result")
    for field in ("partCount", "measureCount", "eventCount"):
        value = expected[field]
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise EvaluationError(f"candidate expected {field} is invalid")
    metrics = expected["metrics"]
    if not isinstance(metrics, Mapping) or set(metrics) != set(METRIC_NAMES):
        raise EvaluationError("candidate expected metrics are invalid")
    for name in METRIC_NAMES:
        metric = metrics[name]
        if not isinstance(metric, Mapping) or set(metric) != {"correct", "total"}:
            raise EvaluationError("candidate expected metric fields are invalid")
        correct = metric["correct"]
        total = metric["total"]
        if (
            not isinstance(correct, int)
            or isinstance(correct, bool)
            or not isinstance(total, int)
            or isinstance(total, bool)
            or correct < 0
            or total < 0
            or correct > total
        ):
            raise EvaluationError("candidate expected metric count is invalid")
    if metrics["eventPresence"]["total"] < reference["eventCount"]:
        raise EvaluationError("event presence denominator cannot omit truth events")
    for name in METRIC_NAMES[1:]:
        if metrics[name]["total"] != reference["eventCount"]:
            raise EvaluationError("field metric denominator must equal truth event count")
    if not isinstance(expected["coreSuccess"], bool) or not isinstance(
        expected["allFieldsPerfect"], bool
    ):
        raise EvaluationError("candidate expected gates are invalid")


def validate_fixed_dataset(
    payload: Mapping[str, Any],
    repository_root: Path | str | None = None,
) -> None:
    """Validate a frozen dataset manifest and optionally all referenced files."""

    _require_exact_keys(payload, _MANIFEST_KEYS, "dataset")
    if payload["schemaVersion"] != DATASET_SCHEMA_VERSION:
        raise EvaluationError("dataset schema version is unsupported")
    if payload["datasetType"] != DATASET_TYPE:
        raise EvaluationError("dataset type is unsupported")
    _require_id(payload["datasetId"], "datasetId")
    _require_sha256(payload["datasetSha256"], "datasetSha256")
    if payload["datasetSha256"] != _self_hash(payload, "datasetSha256"):
        raise EvaluationError("datasetSha256 does not match canonical dataset content")
    if payload["status"] != "frozen":
        raise EvaluationError("dataset must be frozen")
    if payload["generalAccuracyClaim"] is not False:
        raise EvaluationError("fixed foundation dataset cannot make a general accuracy claim")

    metric_set = payload["metricSet"]
    _require_exact_keys(metric_set, _METRIC_SET_KEYS, "metric set")
    if tuple(metric_set["metricNames"]) != METRIC_NAMES:
        raise EvaluationError("metric names are not the fixed v1 metric set")
    if tuple(metric_set["coreMetricNames"]) != CORE_METRIC_NAMES:
        raise EvaluationError("core metric names are not the fixed v1 core set")
    if any(
        metric_set[field] is not False
        for field in (
            "aggregateScoreEnabled",
            "engineRankingEnabled",
            "winnerSelectionEnabled",
        )
    ):
        raise EvaluationError("aggregate score, ranking, and winner selection must be disabled")

    boundaries = payload["boundaries"]
    _require_exact_keys(boundaries, _BOUNDARY_KEYS, "dataset boundaries")
    if boundaries["readOnly"] is not True:
        raise EvaluationError("dataset must be read-only")
    if any(boundaries[field] is not False for field in _BOUNDARY_KEYS - {"readOnly"}):
        raise EvaluationError("dataset decision and mutation boundaries must be disabled")

    cases = payload["cases"]
    if not isinstance(cases, list) or not cases:
        raise EvaluationError("dataset requires at least one case")
    if payload["caseCount"] != len(cases):
        raise EvaluationError("caseCount does not match cases")
    case_ids: list[str] = []
    root = Path(repository_root) if repository_root is not None else None

    for case in cases:
        _require_exact_keys(case, _CASE_KEYS, "evaluation case")
        case_ids.append(_require_id(case["caseId"], "caseId"))
        if not isinstance(case["description"], str) or not case["description"]:
            raise EvaluationError("case description is invalid")
        profile = case["profile"]
        if (
            not isinstance(profile, list)
            or not profile
            or profile != sorted(set(profile))
            or any(not isinstance(item, str) or not _SAFE_ID.fullmatch(item) for item in profile)
        ):
            raise EvaluationError("case profile must be sorted and unique")

        reference = case["reference"]
        _require_exact_keys(reference, _REFERENCE_KEYS, "reference")
        reference_path = _safe_relative_path(reference["path"], "reference path")
        _require_sha256(reference["sha256"], "reference sha256")
        if reference["reviewStatus"] != "manually-reviewed":
            raise EvaluationError("reference must be manually reviewed")
        for field in ("partCount", "measureCount", "eventCount"):
            value = reference[field]
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise EvaluationError(f"reference {field} is invalid")

        events = reference["events"]
        if not isinstance(events, list) or len(events) != reference["eventCount"]:
            raise EvaluationError("reference events do not match eventCount")
        previous = (0, 0, 0)
        seen_locations: set[tuple[int, int, int]] = set()
        per_measure_counts: dict[tuple[int, int], int] = {}
        for event in events:
            location = (
                event.get("partOrdinal"),
                event.get("measureOrdinal"),
                event.get("eventOrdinal"),
            )
            if (
                not all(isinstance(item, int) and not isinstance(item, bool) and item > 0 for item in location)
                or location <= previous
                or location in seen_locations
            ):
                raise EvaluationError("truth event locations must be unique and ordered")
            expected_ordinal = per_measure_counts.get(location[:2], 0) + 1
            if location[2] != expected_ordinal:
                raise EvaluationError("truth event ordinals must be contiguous per measure")
            per_measure_counts[location[:2]] = expected_ordinal
            _validate_truth_event(event, location)
            seen_locations.add(location)
            previous = location
        if max(item[0] for item in seen_locations) != reference["partCount"]:
            raise EvaluationError("truth part count does not match reference")
        if len({(item[0], item[1]) for item in seen_locations}) != reference["measureCount"]:
            raise EvaluationError("truth measure count does not match reference")

        candidates = case["candidates"]
        if not isinstance(candidates, list) or len(candidates) != 3:
            raise EvaluationError("foundation case requires three engine candidates")
        engines: list[str] = []
        for candidate in candidates:
            _require_exact_keys(candidate, _CANDIDATE_KEYS, "candidate")
            engine = candidate["engine"]
            if engine not in _ALLOWED_ENGINES:
                raise EvaluationError("candidate engine is unsupported")
            engines.append(engine)
            for field in ("engineVersion", "modelVersion"):
                if not isinstance(candidate[field], str) or not candidate[field]:
                    raise EvaluationError(f"candidate {field} is invalid")
            candidate_path = _safe_relative_path(candidate["path"], "candidate path")
            _require_sha256(candidate["sha256"], "candidate sha256")
            _validate_expected(candidate["expected"], reference)

            if root is not None:
                path = _resolve_file(root, candidate_path)
                if sha256(path.read_bytes()).hexdigest() != candidate["sha256"]:
                    raise EvaluationError("candidate artifact hash mismatch")

        if set(engines) != _ALLOWED_ENGINES or len(engines) != len(set(engines)):
            raise EvaluationError("case must pin one candidate for each current engine")

        if root is not None:
            path = _resolve_file(root, reference_path)
            document = path.read_bytes()
            if sha256(document).hexdigest() != reference["sha256"]:
                raise EvaluationError("reference artifact hash mismatch")
            upper = document.upper()
            if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
                raise EvaluationError("reference MusicXML contains unsafe declarations")
            if b"<SCORE-PARTWISE" not in upper:
                raise EvaluationError("reference MusicXML root must be score-partwise")

    if len(case_ids) != len(set(case_ids)):
        raise EvaluationError("duplicate caseId")


def load_fixed_dataset(
    manifest_path: Path | str,
    repository_root: Path | str,
) -> dict[str, Any]:
    """Load and fully verify a frozen fixed-dataset manifest."""

    path = Path(manifest_path)
    if path.is_symlink() or not path.is_file():
        raise EvaluationError("dataset manifest must be a regular non-symlink file")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvaluationError("dataset manifest is unreadable") from exc
    if not isinstance(payload, dict):
        raise EvaluationError("dataset manifest root must be an object")
    validate_fixed_dataset(payload, repository_root)
    return payload


def _event_location_map(score: CanonicalScore) -> dict[tuple[int, int, int], CanonicalEvent]:
    result: dict[tuple[int, int, int], CanonicalEvent] = {}
    for part in score.parts:
        for measure in part.measures:
            for event_ordinal, event in enumerate(measure.events, start=1):
                location = (part.ordinal, measure.ordinal, event_ordinal)
                if location in result:
                    raise EvaluationError("candidate contains duplicate event location")
                result[location] = event
    return result


def _event_metric_value(event: CanonicalEvent, metric: str) -> Any:
    if metric == "onset":
        return _fraction_payload(event.onset)
    if metric == "kind":
        return event.kind
    if metric == "effectiveDuration":
        return _fraction_payload(event.effective_duration)
    if metric == "writtenDuration":
        return (
            _fraction_payload(event.written_duration)
            if event.written_duration is not None
            else None
        )
    if metric == "writtenType":
        return event.written_type
    if metric == "pitch":
        return event.pitch.as_dict() if event.pitch is not None else None
    if metric == "chord":
        return {
            "member": event.chord_group is not None,
            "index": event.chord_index,
        }
    if metric == "voice":
        return event.voice
    if metric == "staff":
        return event.staff
    if metric == "ties":
        return list(event.ties)
    if metric == "dots":
        return event.dots
    if metric == "tuplet":
        return event.tuplet.as_dict() if event.tuplet is not None else None
    if metric == "tab":
        return event.tab.as_dict() if event.tab is not None else None
    raise EvaluationError(f"unsupported metric: {metric}")


@dataclass(frozen=True, slots=True)
class MetricResult:
    name: str
    correct: int
    total: int

    def __post_init__(self) -> None:
        if self.name not in METRIC_NAMES:
            raise EvaluationError("metric result name is invalid")
        if (
            not isinstance(self.correct, int)
            or isinstance(self.correct, bool)
            or not isinstance(self.total, int)
            or isinstance(self.total, bool)
            or self.correct < 0
            or self.total < 0
            or self.correct > self.total
        ):
            raise EvaluationError("metric result counts are invalid")

    @property
    def incorrect(self) -> int:
        return self.total - self.correct

    @property
    def perfect(self) -> bool:
        return self.correct == self.total

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "correct": self.correct,
            "incorrect": self.incorrect,
            "total": self.total,
            "perfect": self.perfect,
        }


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    dataset_id: str
    dataset_sha256: str
    case_id: str
    candidate: dict[str, Any]
    counts: dict[str, Any]
    metrics: tuple[MetricResult, ...]
    gates: dict[str, bool]
    boundaries: dict[str, bool]

    def __post_init__(self) -> None:
        _require_id(self.dataset_id, "dataset_id")
        _require_sha256(self.dataset_sha256, "dataset_sha256")
        _require_id(self.case_id, "case_id")
        if tuple(metric.name for metric in self.metrics) != METRIC_NAMES:
            raise EvaluationError("metric results must follow the fixed metric order")

    def _payload_without_hash(self) -> dict[str, Any]:
        return {
            "schemaVersion": RESULT_SCHEMA_VERSION,
            "reportType": RESULT_TYPE,
            "datasetId": self.dataset_id,
            "datasetSha256": self.dataset_sha256,
            "caseId": self.case_id,
            "candidate": self.candidate,
            "counts": self.counts,
            "metrics": [metric.as_dict() for metric in self.metrics],
            "gates": self.gates,
            "boundaries": self.boundaries,
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


def _find_case(dataset: Mapping[str, Any], case_id: str) -> Mapping[str, Any]:
    for case in dataset["cases"]:
        if case["caseId"] == case_id:
            return case
    raise EvaluationError("caseId is not present in the fixed dataset")


def evaluate_candidate(
    candidate: CanonicalScore,
    dataset: Mapping[str, Any],
    case_id: str,
) -> EvaluationResult:
    """Evaluate one immutable candidate without ranking engines or selecting a winner."""

    if not isinstance(candidate, CanonicalScore):
        raise EvaluationError("candidate must be a CanonicalScore")
    validate_fixed_dataset(dataset)
    case = _find_case(dataset, case_id)
    reference = case["reference"]
    truth_events = {
        (
            event["partOrdinal"],
            event["measureOrdinal"],
            event["eventOrdinal"],
        ): event
        for event in reference["events"]
    }
    candidate_events = _event_location_map(candidate)
    truth_locations = set(truth_events)
    candidate_locations = set(candidate_events)
    all_locations = truth_locations | candidate_locations

    metrics: list[MetricResult] = [
        MetricResult(
            "eventPresence",
            correct=len(truth_locations & candidate_locations),
            total=len(all_locations),
        )
    ]
    for metric_name in METRIC_NAMES[1:]:
        correct = 0
        for location, truth in truth_events.items():
            event = candidate_events.get(location)
            if event is not None and _event_metric_value(event, metric_name) == truth[metric_name]:
                correct += 1
        metrics.append(MetricResult(metric_name, correct=correct, total=len(truth_events)))

    counts = {
        "reference": {
            "partCount": reference["partCount"],
            "measureCount": reference["measureCount"],
            "eventCount": reference["eventCount"],
        },
        "candidate": {
            "partCount": len(candidate.parts),
            "measureCount": candidate.measure_count,
            "eventCount": candidate.event_count,
        },
        "exact": {
            "partCount": len(candidate.parts) == reference["partCount"],
            "measureCount": candidate.measure_count == reference["measureCount"],
            "eventCount": candidate.event_count == reference["eventCount"],
        },
    }
    metric_map = {metric.name: metric for metric in metrics}
    exact_counts = all(counts["exact"].values())
    core_success = exact_counts and all(
        metric_map[name].perfect for name in CORE_METRIC_NAMES
    )
    all_fields_perfect = exact_counts and all(metric.perfect for metric in metrics)
    gates = {
        "exactCounts": exact_counts,
        "coreSuccess": core_success,
        "allFieldsPerfect": all_fields_perfect,
        "generalAccuracyClaim": False,
    }
    boundaries = {
        "readOnly": True,
        "aggregateScore": False,
        "engineRanking": False,
        "winnerSelection": False,
        "automaticMerge": False,
        "automaticCorrection": False,
        "teacherApproval": False,
        "publication": False,
        "liveTraining": False,
        "stOmrIntegration": False,
    }
    result = EvaluationResult(
        dataset_id=dataset["datasetId"],
        dataset_sha256=dataset["datasetSha256"],
        case_id=case_id,
        candidate={
            "engine": candidate.source.engine,
            "engineVersion": candidate.source.engine_version,
            "modelVersion": candidate.source.model_version,
            "artifactRef": candidate.source.artifact_ref,
            "artifactSha256": candidate.source.artifact_sha256,
            "canonicalSha256": candidate.canonical_sha256,
        },
        counts=counts,
        metrics=tuple(metrics),
        gates=gates,
        boundaries=boundaries,
    )
    validate_evaluation_result_payload(result.as_dict())
    return result


def validate_evaluation_result_payload(payload: Mapping[str, Any]) -> None:
    """Validate hashes, exact metric counts, gates, and disabled decision boundaries."""

    _require_exact_keys(payload, _RESULT_KEYS, "evaluation result")
    if payload["schemaVersion"] != RESULT_SCHEMA_VERSION:
        raise EvaluationError("evaluation result schema version is unsupported")
    if payload["reportType"] != RESULT_TYPE:
        raise EvaluationError("evaluation result type is unsupported")
    _require_id(payload["datasetId"], "evaluation datasetId")
    _require_sha256(payload["datasetSha256"], "evaluation datasetSha256")
    _require_id(payload["caseId"], "evaluation caseId")
    _require_sha256(payload["resultSha256"], "resultSha256")
    if payload["resultSha256"] != _self_hash(payload, "resultSha256"):
        raise EvaluationError("resultSha256 does not match canonical result content")

    candidate = payload["candidate"]
    candidate_keys = {
        "engine",
        "engineVersion",
        "modelVersion",
        "artifactRef",
        "artifactSha256",
        "canonicalSha256",
    }
    if not isinstance(candidate, Mapping) or set(candidate) != candidate_keys:
        raise EvaluationError("evaluation candidate fields are invalid")
    if candidate["engine"] not in _ALLOWED_ENGINES:
        raise EvaluationError("evaluation candidate engine is unsupported")
    _safe_relative_path(candidate["artifactRef"], "evaluation artifactRef")
    _require_sha256(candidate["artifactSha256"], "evaluation artifactSha256")
    _require_sha256(candidate["canonicalSha256"], "evaluation canonicalSha256")

    counts = payload["counts"]
    if not isinstance(counts, Mapping) or set(counts) != {"reference", "candidate", "exact"}:
        raise EvaluationError("evaluation count fields are invalid")
    count_names = {"partCount", "measureCount", "eventCount"}
    for side in ("reference", "candidate"):
        if not isinstance(counts[side], Mapping) or set(counts[side]) != count_names:
            raise EvaluationError("evaluation count side is invalid")
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in counts[side].values()
        ):
            raise EvaluationError("evaluation count value is invalid")
    if not isinstance(counts["exact"], Mapping) or set(counts["exact"]) != count_names:
        raise EvaluationError("evaluation exact counts are invalid")
    recomputed_exact = {
        name: counts["reference"][name] == counts["candidate"][name]
        for name in count_names
    }
    if dict(counts["exact"]) != recomputed_exact:
        raise EvaluationError("evaluation exact counts do not verify")

    metrics = payload["metrics"]
    if not isinstance(metrics, list) or len(metrics) != len(METRIC_NAMES):
        raise EvaluationError("evaluation metrics are invalid")
    verified_metrics: dict[str, bool] = {}
    for expected_name, metric in zip(METRIC_NAMES, metrics, strict=True):
        if not isinstance(metric, Mapping) or set(metric) != {
            "name",
            "correct",
            "incorrect",
            "total",
            "perfect",
        }:
            raise EvaluationError("evaluation metric fields are invalid")
        if metric["name"] != expected_name:
            raise EvaluationError("evaluation metric order is invalid")
        correct = metric["correct"]
        incorrect = metric["incorrect"]
        total = metric["total"]
        if (
            not isinstance(correct, int)
            or isinstance(correct, bool)
            or not isinstance(incorrect, int)
            or isinstance(incorrect, bool)
            or not isinstance(total, int)
            or isinstance(total, bool)
            or min(correct, incorrect, total) < 0
            or correct + incorrect != total
        ):
            raise EvaluationError("evaluation metric counts do not verify")
        perfect = correct == total
        if metric["perfect"] is not perfect:
            raise EvaluationError("evaluation metric perfect flag does not verify")
        verified_metrics[expected_name] = perfect

    gates = payload["gates"]
    if not isinstance(gates, Mapping) or set(gates) != {
        "exactCounts",
        "coreSuccess",
        "allFieldsPerfect",
        "generalAccuracyClaim",
    }:
        raise EvaluationError("evaluation gates are invalid")
    exact_counts = all(recomputed_exact.values())
    core_success = exact_counts and all(
        verified_metrics[name] for name in CORE_METRIC_NAMES
    )
    all_fields_perfect = exact_counts and all(verified_metrics.values())
    if dict(gates) != {
        "exactCounts": exact_counts,
        "coreSuccess": core_success,
        "allFieldsPerfect": all_fields_perfect,
        "generalAccuracyClaim": False,
    }:
        raise EvaluationError("evaluation gates do not verify")

    boundaries = payload["boundaries"]
    expected_boundaries = {
        "readOnly": True,
        "aggregateScore": False,
        "engineRanking": False,
        "winnerSelection": False,
        "automaticMerge": False,
        "automaticCorrection": False,
        "teacherApproval": False,
        "publication": False,
        "liveTraining": False,
        "stOmrIntegration": False,
    }
    if dict(boundaries) != expected_boundaries:
        raise EvaluationError("evaluation decision boundaries are invalid")
