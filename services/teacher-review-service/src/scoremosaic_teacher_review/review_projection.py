from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import hmac
import json
import re
from types import MappingProxyType
from typing import Any, Mapping

from .contracts import (
    ReviewAuthorizationGrant,
    Stage8ContractError,
    TeacherScoreRevision,
    verify_authorization_grant,
)
from .musical_state import ReviewMusicalState, materialize_canonical_state
from ._revision_store_common import RevisionScope
from ._revision_store_validation import validate_revision_for_store

PROJECTION_VERSION = "scoremosaic-teacher-review-projection-v1"
REPORT_SCHEMA_VERSION = "1.0"
REPORT_TYPE = "scoremosaic.ensemble.comparison-report"
COMPARISON_FORMAT_VERSION = "0.1-foundation"

_MAX_JSON_NODES = 650_000
_MAX_DEPTH = 24
_MAX_DIFFERENCES = 200_000
_MAX_PAGE_SIZE = 200
_MAX_VALUE_NODES = 2_000
_MAX_VALUE_DEPTH = 12

_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_REPORT_ID_RE = re.compile(r"^ensemble_report_[0-9a-f]{24}$")
_CANDIDATE_ID_RE = re.compile(r"^candidate_[0-9a-f]{24}$")
_DIFFERENCE_ID_RE = re.compile(r"^difference_[0-9a-f]{24}$")
_SAFE_FIELD_RE = re.compile(r"^[a-z][A-Za-z0-9.]{0,99}$")
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")

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
_EXPECTED_NEUTRALITY = {
    "readOnly": True,
    "provenancePreserved": True,
    "accuracyClaim": False,
    "engineRanking": False,
    "winnerSelection": False,
    "preferredCandidate": False,
    "automaticMerge": False,
    "automaticCorrection": False,
}
_EXPECTED_BOUNDARIES = {
    "readOnly": True,
    "engineRanking": False,
    "winnerSelection": False,
    "automaticMerge": False,
    "automaticCorrection": False,
    "teacherApproval": False,
    "publication": False,
}
_EXPECTED_ALIGNMENT = {
    "parts": "ordinal",
    "measures": "ordinal",
    "events": "xml-event-ordinal",
    "fuzzyAlignment": False,
}
_REPORT_KEYS = frozenset(
    {
        "schemaVersion",
        "reportType",
        "reportId",
        "comparisonFormatVersion",
        "comparisonResultSha256",
        "neutrality",
        "comparison",
        "reportSha256",
    }
)
_COMPARISON_KEYS = frozenset(
    {
        "formatVersion",
        "comparisonMode",
        "alignment",
        "boundaries",
        "candidateCount",
        "differenceCount",
        "identical",
        "candidates",
        "differences",
        "resultSha256",
    }
)
_CANDIDATE_KEYS = frozenset(
    {"candidateId", "source", "canonicalSha256", "partCount", "measureCount", "eventCount"}
)
_SOURCE_KEYS = frozenset(
    {"engine", "engineVersion", "modelVersion", "artifactRef", "artifactSha256"}
)
_DIFFERENCE_KEYS = frozenset(
    {"category", "field", "location", "observations", "differenceId", "description"}
)
_LOCATION_KEYS = frozenset({"partOrdinal", "measureOrdinal", "eventOrdinal"})
_OBSERVATION_KEYS = frozenset(
    {"candidateId", "source", "canonicalSha256", "present", "value", "provenance"}
)
_PROVENANCE_KEYS = frozenset(
    {"partId", "measureId", "measureNumber", "eventId", "xmlPath", "sourceEventIndex"}
)


class Stage8ProjectionError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> None:
    raise Stage8ProjectionError(code)


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
        _fail("PROJECTION_NON_CANONICAL_VALUE")


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


def _bounded_walk(
    value: Any,
    *,
    max_nodes: int = _MAX_JSON_NODES,
    max_depth: int = _MAX_DEPTH,
    depth: int = 0,
    counter: list[int] | None = None,
) -> None:
    if counter is None:
        counter = [0]
    counter[0] += 1
    if counter[0] > max_nodes or depth > max_depth:
        _fail("PROJECTION_INPUT_TOO_COMPLEX")
    if isinstance(value, Mapping):
        if len(value) > 64:
            _fail("PROJECTION_INPUT_TOO_COMPLEX")
        for key, item in value.items():
            if not isinstance(key, str) or len(key) > 200:
                _fail("PROJECTION_INPUT_INVALID")
            _bounded_walk(
                item,
                max_nodes=max_nodes,
                max_depth=max_depth,
                depth=depth + 1,
                counter=counter,
            )
    elif isinstance(value, (list, tuple)):
        if len(value) > _MAX_DIFFERENCES:
            _fail("PROJECTION_INPUT_TOO_COMPLEX")
        for item in value:
            _bounded_walk(
                item,
                max_nodes=max_nodes,
                max_depth=max_depth,
                depth=depth + 1,
                counter=counter,
            )
    elif isinstance(value, str):
        if len(value) > 4_000:
            _fail("PROJECTION_INPUT_TOO_COMPLEX")
    elif value is not None and not isinstance(value, (bool, int, float)):
        _fail("PROJECTION_INPUT_INVALID")


def _exact(value: Any, keys: frozenset[str], code: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != set(keys):
        _fail(code)
    return value


def _hash(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HASH_RE.fullmatch(value) is None:
        _fail(code)
    return value


def _safe_id(value: Any, code: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or _SAFE_ID_RE.fullmatch(value) is None:
        _fail(code)
    return value


def _bounded_int(value: Any, code: str, *, minimum: int = 0, maximum: int = 1_000_000_000) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        _fail(code)
    return value


def _nullable_ordinal(value: Any, code: str) -> int | None:
    if value is None:
        return None
    return _bounded_int(value, code, minimum=1)


def _validate_source(value: Any) -> dict[str, Any]:
    value = _exact(value, _SOURCE_KEYS, "PROJECTION_REPORT_SOURCE_INVALID")
    engine = value["engine"]
    if engine not in {"homr", "clarity", "audiveris"}:
        _fail("PROJECTION_REPORT_SOURCE_INVALID")
    for key in ("engineVersion", "modelVersion"):
        item = value[key]
        if item is not None and (not isinstance(item, str) or not item or len(item) > 200):
            _fail("PROJECTION_REPORT_SOURCE_INVALID")
    artifact_ref = value["artifactRef"]
    if not isinstance(artifact_ref, str) or not artifact_ref or len(artifact_ref) > 500:
        _fail("PROJECTION_REPORT_SOURCE_INVALID")
    artifact_sha = _hash(value["artifactSha256"], "PROJECTION_REPORT_SOURCE_INVALID")
    return {
        "engine": engine,
        "engineVersion": value["engineVersion"],
        "modelVersion": value["modelVersion"],
        "artifactRef": artifact_ref,
        "artifactSha256": artifact_sha,
    }


def _validate_candidate(value: Any) -> dict[str, Any]:
    value = _exact(value, _CANDIDATE_KEYS, "PROJECTION_REPORT_CANDIDATE_INVALID")
    candidate_id = value["candidateId"]
    if not isinstance(candidate_id, str) or _CANDIDATE_ID_RE.fullmatch(candidate_id) is None:
        _fail("PROJECTION_REPORT_CANDIDATE_INVALID")
    return {
        "candidateId": candidate_id,
        "source": _validate_source(value["source"]),
        "canonicalSha256": _hash(value["canonicalSha256"], "PROJECTION_REPORT_CANDIDATE_INVALID"),
        "partCount": _bounded_int(value["partCount"], "PROJECTION_REPORT_CANDIDATE_INVALID"),
        "measureCount": _bounded_int(value["measureCount"], "PROJECTION_REPORT_CANDIDATE_INVALID"),
        "eventCount": _bounded_int(value["eventCount"], "PROJECTION_REPORT_CANDIDATE_INVALID"),
    }


def _validate_provenance(value: Any) -> dict[str, Any]:
    value = _exact(value, _PROVENANCE_KEYS, "PROJECTION_REPORT_PROVENANCE_INVALID")
    measure_number = value["measureNumber"]
    if measure_number is not None and (
        not isinstance(measure_number, str) or not measure_number or len(measure_number) > 40
    ):
        _fail("PROJECTION_REPORT_PROVENANCE_INVALID")
    xml_path = value["xmlPath"]
    if xml_path is not None and (
        not isinstance(xml_path, str) or not xml_path or len(xml_path) > 1000
    ):
        _fail("PROJECTION_REPORT_PROVENANCE_INVALID")
    source_index = value["sourceEventIndex"]
    if source_index is not None:
        source_index = _bounded_int(source_index, "PROJECTION_REPORT_PROVENANCE_INVALID")
    return {
        "partId": _safe_id(value["partId"], "PROJECTION_REPORT_PROVENANCE_INVALID"),
        "measureId": _safe_id(value["measureId"], "PROJECTION_REPORT_PROVENANCE_INVALID"),
        "measureNumber": measure_number,
        "eventId": _safe_id(value["eventId"], "PROJECTION_REPORT_PROVENANCE_INVALID"),
        "xmlPath": xml_path,
        "sourceEventIndex": source_index,
    }


def _validate_observation(value: Any, candidates: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    value = _exact(value, _OBSERVATION_KEYS, "PROJECTION_REPORT_OBSERVATION_INVALID")
    candidate_id = value["candidateId"]
    if candidate_id not in candidates:
        _fail("PROJECTION_REPORT_OBSERVATION_INVALID")
    candidate = candidates[candidate_id]
    canonical_sha = _hash(value["canonicalSha256"], "PROJECTION_REPORT_OBSERVATION_INVALID")
    if not hmac.compare_digest(canonical_sha, candidate["canonicalSha256"]):
        _fail("PROJECTION_REPORT_OBSERVATION_INVALID")
    source = _validate_source(value["source"])
    if source != candidate["source"]:
        _fail("PROJECTION_REPORT_OBSERVATION_INVALID")
    present = value["present"]
    if not isinstance(present, bool):
        _fail("PROJECTION_REPORT_OBSERVATION_INVALID")
    _bounded_walk(
        value["value"],
        max_nodes=_MAX_VALUE_NODES,
        max_depth=_MAX_VALUE_DEPTH,
    )
    return {
        "candidateId": candidate_id,
        "source": source,
        "canonicalSha256": canonical_sha,
        "present": present,
        "value": json.loads(_canonical_json(value["value"])),
        "provenance": _validate_provenance(value["provenance"]),
    }


def _validate_difference(value: Any, candidates: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    value = _exact(value, _DIFFERENCE_KEYS, "PROJECTION_REPORT_DIFFERENCE_INVALID")
    category = value["category"]
    field = value["field"]
    if category not in _ALLOWED_CATEGORIES:
        _fail("PROJECTION_REPORT_DIFFERENCE_INVALID")
    if not isinstance(field, str) or _SAFE_FIELD_RE.fullmatch(field) is None:
        _fail("PROJECTION_REPORT_DIFFERENCE_INVALID")
    location = _exact(value["location"], _LOCATION_KEYS, "PROJECTION_REPORT_LOCATION_INVALID")
    normalized_location = {
        "partOrdinal": _bounded_int(location["partOrdinal"], "PROJECTION_REPORT_LOCATION_INVALID", minimum=1),
        "measureOrdinal": _nullable_ordinal(location["measureOrdinal"], "PROJECTION_REPORT_LOCATION_INVALID"),
        "eventOrdinal": _nullable_ordinal(location["eventOrdinal"], "PROJECTION_REPORT_LOCATION_INVALID"),
    }
    if normalized_location["eventOrdinal"] is not None and normalized_location["measureOrdinal"] is None:
        _fail("PROJECTION_REPORT_LOCATION_INVALID")
    observations_raw = value["observations"]
    if not isinstance(observations_raw, list) or not 2 <= len(observations_raw) <= 8:
        _fail("PROJECTION_REPORT_OBSERVATION_INVALID")
    observations = [_validate_observation(item, candidates) for item in observations_raw]
    candidate_ids = [item["candidateId"] for item in observations]
    if candidate_ids != sorted(candidate_ids) or len(candidate_ids) != len(set(candidate_ids)):
        _fail("PROJECTION_REPORT_OBSERVATION_INVALID")
    signatures = {
        _canonical_json({"present": item["present"], "value": item["value"]})
        for item in observations
    }
    if len(signatures) < 2:
        _fail("PROJECTION_REPORT_DIFFERENCE_INVALID")
    body = {
        "category": category,
        "field": field,
        "location": normalized_location,
        "observations": observations,
    }
    expected_id = f"difference_{_digest(body)[:24]}"
    difference_id = value["differenceId"]
    if (
        not isinstance(difference_id, str)
        or _DIFFERENCE_ID_RE.fullmatch(difference_id) is None
        or not hmac.compare_digest(difference_id, expected_id)
    ):
        _fail("PROJECTION_REPORT_DIFFERENCE_HASH_INVALID")
    if value["description"] != f"Canonical candidates disagree on {field}.":
        _fail("PROJECTION_REPORT_DIFFERENCE_INVALID")
    return {**body, "differenceId": difference_id, "description": value["description"]}


def _report_id(comparison_sha: str) -> str:
    identity = {
        "schemaVersion": REPORT_SCHEMA_VERSION,
        "reportType": REPORT_TYPE,
        "comparisonResultSha256": comparison_sha,
    }
    return f"ensemble_report_{_digest(identity)[:24]}"


def validate_review_report_for_projection(
    payload: Mapping[str, Any],
    *,
    expected_report_id: str,
    expected_report_sha256: str,
) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        _fail("PROJECTION_REPORT_INVALID")
    _bounded_walk(payload)
    report = _exact(payload, _REPORT_KEYS, "PROJECTION_REPORT_INVALID")
    if report["schemaVersion"] != REPORT_SCHEMA_VERSION or report["reportType"] != REPORT_TYPE:
        _fail("PROJECTION_REPORT_VERSION_INVALID")
    if report["comparisonFormatVersion"] != COMPARISON_FORMAT_VERSION:
        _fail("PROJECTION_REPORT_VERSION_INVALID")
    report_sha = _hash(report["reportSha256"], "PROJECTION_REPORT_HASH_INVALID")
    comparison_sha = _hash(report["comparisonResultSha256"], "PROJECTION_REPORT_HASH_INVALID")
    report_id = report["reportId"]
    if not isinstance(report_id, str) or _REPORT_ID_RE.fullmatch(report_id) is None:
        _fail("PROJECTION_REPORT_ID_INVALID")
    if report_id != expected_report_id or not hmac.compare_digest(report_sha, expected_report_sha256):
        _fail("PROJECTION_REPORT_SCOPE_MISMATCH")
    if report_id != _report_id(comparison_sha):
        _fail("PROJECTION_REPORT_ID_INVALID")
    if report["neutrality"] != _EXPECTED_NEUTRALITY:
        _fail("PROJECTION_REPORT_AUTHORITY_INVALID")

    comparison = _exact(report["comparison"], _COMPARISON_KEYS, "PROJECTION_COMPARISON_INVALID")
    if comparison["formatVersion"] != COMPARISON_FORMAT_VERSION:
        _fail("PROJECTION_COMPARISON_INVALID")
    if comparison["comparisonMode"] != "neutral-all-candidates":
        _fail("PROJECTION_COMPARISON_INVALID")
    if comparison["alignment"] != _EXPECTED_ALIGNMENT or comparison["boundaries"] != _EXPECTED_BOUNDARIES:
        _fail("PROJECTION_REPORT_AUTHORITY_INVALID")
    candidates_raw = comparison["candidates"]
    differences_raw = comparison["differences"]
    if not isinstance(candidates_raw, list) or not 2 <= len(candidates_raw) <= 8:
        _fail("PROJECTION_REPORT_CANDIDATE_INVALID")
    if not isinstance(differences_raw, list) or len(differences_raw) > _MAX_DIFFERENCES:
        _fail("PROJECTION_REPORT_DIFFERENCE_INVALID")
    candidates_list = [_validate_candidate(item) for item in candidates_raw]
    candidate_ids = [item["candidateId"] for item in candidates_list]
    if candidate_ids != sorted(candidate_ids) or len(candidate_ids) != len(set(candidate_ids)):
        _fail("PROJECTION_REPORT_CANDIDATE_INVALID")
    candidates = {item["candidateId"]: item for item in candidates_list}
    differences = [_validate_difference(item, candidates) for item in differences_raw]
    if comparison["candidateCount"] != len(candidates_list):
        _fail("PROJECTION_COMPARISON_COUNT_INVALID")
    if comparison["differenceCount"] != len(differences):
        _fail("PROJECTION_COMPARISON_COUNT_INVALID")
    if comparison["identical"] is not (len(differences) == 0):
        _fail("PROJECTION_COMPARISON_COUNT_INVALID")

    comparison_body = {
        "formatVersion": comparison["formatVersion"],
        "comparisonMode": comparison["comparisonMode"],
        "alignment": comparison["alignment"],
        "boundaries": comparison["boundaries"],
        "candidateCount": comparison["candidateCount"],
        "differenceCount": comparison["differenceCount"],
        "identical": comparison["identical"],
        "candidates": candidates_list,
        "differences": differences,
    }
    nested_sha = _hash(comparison["resultSha256"], "PROJECTION_COMPARISON_HASH_INVALID")
    if not hmac.compare_digest(nested_sha, _digest(comparison_body)):
        _fail("PROJECTION_COMPARISON_HASH_INVALID")
    if not hmac.compare_digest(nested_sha, comparison_sha):
        _fail("PROJECTION_COMPARISON_HASH_INVALID")

    report_body = {
        "schemaVersion": report["schemaVersion"],
        "reportType": report["reportType"],
        "reportId": report_id,
        "comparisonFormatVersion": report["comparisonFormatVersion"],
        "comparisonResultSha256": comparison_sha,
        "neutrality": report["neutrality"],
        "comparison": {**comparison_body, "resultSha256": nested_sha},
    }
    if not hmac.compare_digest(_digest(report_body), report_sha):
        _fail("PROJECTION_REPORT_HASH_INVALID")
    return {**report_body, "reportSha256": report_sha}


@dataclass(frozen=True)
class ReviewProjectionPage:
    _payload: Mapping[str, Any]

    @property
    def projection_sha256(self) -> str:
        return _digest(_deep_thaw(self._payload))

    def to_dict(self) -> dict[str, Any]:
        payload = _deep_thaw(self._payload)
        payload["projectionSha256"] = self.projection_sha256
        return payload


def _state_index(state: ReviewMusicalState) -> tuple[set[str], set[str], set[str]]:
    data = state.to_dict()
    part_ids: set[str] = set()
    measure_ids: set[str] = set()
    event_ids: set[str] = set()
    for part in data["parts"]:
        part_ids.add(part["partId"])
        for measure in part["measures"]:
            measure_ids.add(measure["measureId"])
            for event in measure["events"]:
                event_ids.add(event["eventId"])
    return part_ids, measure_ids, event_ids


def _selected_observation(
    difference: Mapping[str, Any],
    *,
    base_candidate_ids: frozenset[str],
) -> Mapping[str, Any] | None:
    matches = [
        item for item in difference["observations"] if item["candidateId"] in base_candidate_ids
    ]
    if not matches:
        return None
    return sorted(matches, key=lambda item: item["candidateId"])[0]


def _project_difference(
    difference: Mapping[str, Any],
    *,
    base_candidate_ids: frozenset[str],
    state_index: tuple[set[str], set[str], set[str]],
) -> dict[str, Any]:
    part_ids, measure_ids, event_ids = state_index
    selected = _selected_observation(difference, base_candidate_ids=base_candidate_ids)
    provenance = selected["provenance"] if selected is not None else None
    part_id = provenance["partId"] if provenance is not None else None
    measure_id = provenance["measureId"] if provenance is not None else None
    event_id = provenance["eventId"] if provenance is not None else None
    focus = {
        "partOrdinal": difference["location"]["partOrdinal"],
        "measureOrdinal": difference["location"]["measureOrdinal"],
        "eventOrdinal": difference["location"]["eventOrdinal"],
        "partId": part_id,
        "measureId": measure_id,
        "eventId": event_id,
        "partPresentInSnapshot": part_id is not None and part_id in part_ids,
        "measurePresentInSnapshot": measure_id is not None and measure_id in measure_ids,
        "eventPresentInSnapshot": event_id is not None and event_id in event_ids,
    }
    observations = [
        {
            "candidateId": item["candidateId"],
            "canonicalSha256": item["canonicalSha256"],
            "present": item["present"],
            "value": item["value"],
        }
        for item in difference["observations"]
    ]
    return {
        "differenceId": difference["differenceId"],
        "category": difference["category"],
        "field": difference["field"],
        "label": f"{difference['category']} · {difference['field']}",
        "focus": focus,
        "observations": observations,
    }


def build_review_projection_page(
    *,
    grant: ReviewAuthorizationGrant,
    signing_key: bytes,
    expected_reviewer_id: str,
    scope: RevisionScope,
    comparison_report: Mapping[str, Any],
    base_canonical_payload: Mapping[str, Any],
    state: ReviewMusicalState,
    revision: TeacherScoreRevision | None = None,
    offset: int = 0,
    limit: int = 100,
) -> ReviewProjectionPage:
    if not isinstance(scope, RevisionScope):
        _fail("PROJECTION_SCOPE_INVALID")
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        _fail("PROJECTION_PAGE_INVALID")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= _MAX_PAGE_SIZE:
        _fail("PROJECTION_PAGE_INVALID")

    revision_id: str | None = None
    revision_sha: str | None = None
    record: dict[str, Any] | None = None
    if revision is not None:
        if not isinstance(revision, TeacherScoreRevision):
            _fail("PROJECTION_REVISION_INVALID")
        record = revision.to_dict()
        revision_id = record.get("revisionId")
        revision_sha = record.get("revisionSha256")

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
        raise Stage8ProjectionError("PROJECTION_AUTHORIZATION_DENIED") from exc

    if not isinstance(state, ReviewMusicalState):
        _fail("PROJECTION_STATE_INVALID")

    if revision is not None:
        assert record is not None
        validated, _ = validate_revision_for_store(
            scope,
            revision,
            expected_parent_revision_id=record.get("parentRevisionId"),
            expected_parent_revision_sha256=record.get("parentRevisionSha256"),
            expected_previous_audit_event_sha256=record.get("previousAuditEventSha256"),
        )
        if not hmac.compare_digest(validated["resultingMusicalStateSha256"], state.state_sha256):
            _fail("PROJECTION_REVISION_STATE_MISMATCH")
        snapshot_kind = "revision"
    else:
        base_state = materialize_canonical_state(scope, base_canonical_payload)
        if not hmac.compare_digest(base_state.state_sha256, state.state_sha256):
            _fail("PROJECTION_BASE_STATE_MISMATCH")
        snapshot_kind = "base"

    report = validate_review_report_for_projection(
        comparison_report,
        expected_report_id=scope.review_report_id,
        expected_report_sha256=scope.review_report_sha256,
    )
    candidates = report["comparison"]["candidates"]
    base_candidate_ids = frozenset(
        item["candidateId"]
        for item in candidates
        if hmac.compare_digest(item["canonicalSha256"], scope.base_canonical_sha256)
    )
    if not base_candidate_ids:
        _fail("PROJECTION_BASE_CANDIDATE_MISSING")

    differences = report["comparison"]["differences"]
    if offset > len(differences):
        _fail("PROJECTION_PAGE_INVALID")
    page_items = differences[offset : offset + limit]
    index = _state_index(state)
    projected = [
        _project_difference(
            item,
            base_candidate_ids=base_candidate_ids,
            state_index=index,
        )
        for item in page_items
    ]
    payload = {
        "schemaVersion": PROJECTION_VERSION,
        "scope": {
            "tenantId": scope.tenant_id,
            "jobId": scope.job_id,
            "reviewerId": expected_reviewer_id,
            "reviewReportId": scope.review_report_id,
            "reviewReportSha256": scope.review_report_sha256,
            "baseCanonicalSha256": scope.base_canonical_sha256,
        },
        "snapshot": {
            "kind": snapshot_kind,
            "revisionId": revision_id,
            "revisionSha256": revision_sha,
            "stateSha256": state.state_sha256,
        },
        "page": {
            "offset": offset,
            "limit": limit,
            "returned": len(projected),
            "totalDifferences": len(differences),
            "hasMore": offset + len(projected) < len(differences),
        },
        "capabilities": {
            "readOnly": True,
            "canEdit": False,
            "canApprove": False,
            "canPublish": False,
            "authoritativeTruth": False,
        },
        "baseCandidateIds": sorted(base_candidate_ids),
        "differences": projected,
    }
    return ReviewProjectionPage(_deep_freeze(payload))


__all__ = [
    "PROJECTION_VERSION",
    "ReviewProjectionPage",
    "Stage8ProjectionError",
    "build_review_projection_page",
    "validate_review_report_for_projection",
]
