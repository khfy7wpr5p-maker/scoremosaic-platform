from __future__ import annotations

from fractions import Fraction
from hashlib import sha256
import hmac
import json
import re
from typing import Any, Iterable, Mapping

from .contracts import Stage8ContractError, validate_score_edit_command


EVIDENCE_SCHEMA_VERSION = "scoremosaic-polyphonic-teacher-workload-evidence-v1"
TEACHER_EDIT_METHOD = "TEACHER_REVISION_COMMAND_COUNT_V1"
REVISION_SCHEMA_VERSION = "scoremosaic-teacher-score-revision-v1"

_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_FIXTURE_RE = re.compile(r"^poly_fixture_[A-Za-z0-9_-]{8,96}$")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")
_JOB_RE = re.compile(r"^job_[A-Za-z0-9_-]{8,80}$")
_REVISION_ID_RE = re.compile(r"^rev_[0-9a-f]{32}$")
_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

_REVISION_KEYS = frozenset(
    {
        "schemaVersion",
        "revisionId",
        "revisionSha256",
        "jobId",
        "reviewerId",
        "tenantId",
        "authorizationDecisionId",
        "authorizationGrantSha256",
        "reviewReportId",
        "reviewReportSha256",
        "baseCanonicalSha256",
        "parentRevisionId",
        "parentRevisionSha256",
        "commandId",
        "commandSha256",
        "resultingMusicalStateSha256",
        "validationReportSha256",
        "blockingIssueCount",
        "unresolvedIssueCount",
        "createdAt",
        "previousAuditEventSha256",
        "auditEventSha256",
        "status",
        "immutable",
        "approvalEligible",
        "publicationEligible",
    }
)

_BOUNDARIES = {
    "researchEvaluationOnly": True,
    "readOnly": True,
    "modelTrainingSideEffect": False,
    "engineRanking": False,
    "winnerSelection": False,
    "automaticCorrection": False,
    "teacherApproval": False,
    "publicationAuthority": False,
    "productionDecisionAuthority": False,
}


class TeacherWorkloadEvidenceError(ValueError):
    """Stable fail-closed SM-POLY-13 evidence error."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> None:
    raise TeacherWorkloadEvidenceError(code)


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
        _fail("non_canonical_value")


def _sha(value: Any) -> str:
    return sha256(_canonical_json(value)).hexdigest()


def _require_string(value: Any, pattern: re.Pattern[str], code: str) -> str:
    if type(value) is not str or pattern.fullmatch(value) is None:
        _fail(code)
    return value


def _require_hash(value: Any, code: str) -> str:
    return _require_string(value, _HASH_RE, code)


def _require_int(value: Any, *, minimum: int, code: str) -> int:
    if type(value) is not int or value < minimum or value > 1_000_000:
        _fail(code)
    return value


def _require_parent_pair(parent_id: Any, parent_sha: Any, code: str) -> tuple[str | None, str | None]:
    if (parent_id is None) != (parent_sha is None):
        _fail(code)
    if parent_id is None:
        return None, None
    return (
        _require_string(parent_id, _REVISION_ID_RE, code),
        _require_hash(parent_sha, code),
    )


def _ratio(numerator: int, denominator: int) -> dict[str, int]:
    value = Fraction(numerator, denominator)
    return {"numerator": value.numerator, "denominator": value.denominator}


def _validate_revision(payload: Mapping[str, Any]) -> dict[str, Any]:
    if type(payload) is not dict or set(payload) != set(_REVISION_KEYS):
        _fail("revision_schema_invalid")
    if payload.get("schemaVersion") != REVISION_SCHEMA_VERSION:
        _fail("revision_version_invalid")
    if payload.get("status") != "draft":
        _fail("revision_status_invalid")
    if payload.get("immutable") is not True:
        _fail("revision_mutability_invalid")
    if payload.get("approvalEligible") is not False or payload.get("publicationEligible") is not False:
        _fail("revision_authority_invalid")

    record = dict(payload)
    revision_id = _require_string(record["revisionId"], _REVISION_ID_RE, "revision_id_invalid")
    revision_sha = _require_hash(record["revisionSha256"], "revision_hash_invalid")
    _require_string(record["jobId"], _JOB_RE, "revision_job_invalid")
    for key in ("reviewerId", "tenantId", "authorizationDecisionId", "reviewReportId", "commandId"):
        _require_string(record[key], _ID_RE, "revision_identity_invalid")
    for key in (
        "authorizationGrantSha256",
        "reviewReportSha256",
        "baseCanonicalSha256",
        "commandSha256",
        "resultingMusicalStateSha256",
        "validationReportSha256",
        "auditEventSha256",
    ):
        _require_hash(record[key], "revision_hash_invalid")
    parent_id, parent_sha = _require_parent_pair(
        record["parentRevisionId"], record["parentRevisionSha256"], "revision_parent_invalid"
    )
    record["parentRevisionId"] = parent_id
    record["parentRevisionSha256"] = parent_sha
    previous_audit = record["previousAuditEventSha256"]
    if previous_audit is not None:
        _require_hash(previous_audit, "revision_audit_parent_invalid")
    _require_int(record["blockingIssueCount"], minimum=0, code="revision_count_invalid")
    _require_int(record["unresolvedIssueCount"], minimum=0, code="revision_count_invalid")
    _require_string(record["createdAt"], _TIMESTAMP_RE, "revision_timestamp_invalid")

    expected_audit = _sha(
        {
            "actorId": record["reviewerId"],
            "authorizationDecisionId": record["authorizationDecisionId"],
            "commandSha256": record["commandSha256"],
            "resultingMusicalStateSha256": record["resultingMusicalStateSha256"],
            "previousAuditEventSha256": previous_audit,
            "createdAt": record["createdAt"],
        }
    )
    if not hmac.compare_digest(record["auditEventSha256"], expected_audit):
        _fail("revision_audit_hash_mismatch")

    revision_body = {
        key: value
        for key, value in record.items()
        if key not in {"revisionId", "revisionSha256"}
    }
    expected_revision_sha = _sha(revision_body)
    if not hmac.compare_digest(revision_sha, expected_revision_sha):
        _fail("revision_hash_mismatch")
    if revision_id != f"rev_{revision_sha[:32]}":
        _fail("revision_id_hash_mismatch")
    return record


def _evidence_body_without_id(evidence: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in evidence.items()
        if key not in {"evidenceId", "evidenceSha256"}
    }


def _validate_denominator(value: Any, *, optional: bool, code: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != {"available", "count", "sourceArtifactSha256"}:
        _fail(code)
    available = value["available"]
    if type(available) is not bool:
        _fail(code)
    if optional and not available:
        if value["count"] is not None or value["sourceArtifactSha256"] is not None:
            _fail(code)
        return dict(value)
    if not available:
        _fail(code)
    _require_int(value["count"], minimum=1, code=code)
    _require_hash(value["sourceArtifactSha256"], code)
    return dict(value)


def validate_teacher_workload_evidence(payload: Mapping[str, Any]) -> dict[str, Any]:
    if type(payload) is not dict:
        _fail("evidence_type_invalid")
    expected_keys = {
        "schemaVersion",
        "evidenceId",
        "fixtureId",
        "method",
        "scope",
        "lineage",
        "denominators",
        "workload",
        "boundaries",
        "evidenceSha256",
    }
    if set(payload) != expected_keys:
        _fail("evidence_schema_invalid")
    if payload["schemaVersion"] != EVIDENCE_SCHEMA_VERSION:
        _fail("evidence_version_invalid")
    _require_string(payload["fixtureId"], _FIXTURE_RE, "fixture_id_invalid")
    if payload["method"] != TEACHER_EDIT_METHOD:
        _fail("method_invalid")

    scope = payload["scope"]
    if type(scope) is not dict or set(scope) != {
        "jobId",
        "reviewerId",
        "reviewReportId",
        "reviewReportSha256",
        "baseCanonicalSha256",
    }:
        _fail("scope_invalid")
    _require_string(scope["jobId"], _JOB_RE, "scope_invalid")
    for key in ("reviewerId", "reviewReportId"):
        _require_string(scope[key], _ID_RE, "scope_invalid")
    for key in ("reviewReportSha256", "baseCanonicalSha256"):
        _require_hash(scope[key], "scope_invalid")

    lineage = payload["lineage"]
    if type(lineage) is not dict or set(lineage) != {
        "revisionCount",
        "headRevisionId",
        "headRevisionSha256",
        "revisionSha256s",
        "commandSha256s",
        "editedMeasureIds",
    }:
        _fail("lineage_invalid")
    revision_count = _require_int(lineage["revisionCount"], minimum=1, code="lineage_invalid")
    _require_string(lineage["headRevisionId"], _REVISION_ID_RE, "lineage_invalid")
    _require_hash(lineage["headRevisionSha256"], "lineage_invalid")
    for key in ("revisionSha256s", "commandSha256s"):
        values = lineage[key]
        if type(values) is not list or len(values) != revision_count or len(set(values)) != len(values):
            _fail("lineage_invalid")
        for value in values:
            _require_hash(value, "lineage_invalid")
    measures = lineage["editedMeasureIds"]
    if type(measures) is not list or not measures or len(set(measures)) != len(measures):
        _fail("lineage_invalid")
    for measure_id in measures:
        _require_string(measure_id, _ID_RE, "lineage_invalid")
    if lineage["headRevisionSha256"] != lineage["revisionSha256s"][-1]:
        _fail("lineage_head_mismatch")

    denominators = payload["denominators"]
    if type(denominators) is not dict or set(denominators) != {"measure", "page"}:
        _fail("denominator_invalid")
    measure = _validate_denominator(
        denominators["measure"], optional=False, code="measure_denominator_invalid"
    )
    page = _validate_denominator(
        denominators["page"], optional=True, code="page_denominator_invalid"
    )
    if measure["sourceArtifactSha256"] != scope["baseCanonicalSha256"]:
        _fail("measure_denominator_scope_mismatch")

    workload = payload["workload"]
    if type(workload) is not dict or set(workload) != {
        "editCount",
        "editsPerMeasure",
        "editsPerPage",
    }:
        _fail("workload_invalid")
    edit_count = _require_int(workload["editCount"], minimum=1, code="workload_invalid")
    if edit_count != revision_count:
        _fail("workload_revision_count_mismatch")
    if workload["editsPerMeasure"] != _ratio(edit_count, measure["count"]):
        _fail("measure_ratio_mismatch")
    expected_page_ratio = None if not page["available"] else _ratio(edit_count, page["count"])
    if workload["editsPerPage"] != expected_page_ratio:
        _fail("page_ratio_mismatch")

    if payload["boundaries"] != _BOUNDARIES:
        _fail("authority_boundary_invalid")
    expected_id = f"teacher_workload_{_sha(_evidence_body_without_id(payload))[:24]}"
    if payload["evidenceId"] != expected_id:
        _fail("evidence_id_mismatch")
    claimed_sha = _require_hash(payload["evidenceSha256"], "evidence_hash_invalid")
    body = {key: value for key, value in payload.items() if key != "evidenceSha256"}
    if not hmac.compare_digest(claimed_sha, _sha(body)):
        _fail("evidence_hash_mismatch")
    return json.loads(_canonical_json(payload).decode("utf-8"))


def build_teacher_workload_evidence(
    *,
    fixture_id: str,
    revisions: Iterable[Mapping[str, Any]],
    commands: Iterable[Mapping[str, Any]],
    measure_count: int,
    measure_count_source_sha256: str,
    page_count: int | None = None,
    page_count_source_sha256: str | None = None,
) -> dict[str, Any]:
    """Build read-only workload evidence from a complete immutable revision chain.

    One validated TeacherScoreRevision/ScoreEditCommand pair counts as one edit.
    Repeated edits to the same event or measure remain separate edits. Absence of
    revisions is not interpreted as zero edits because no completed-review proof
    exists in the current contracts.
    """

    _require_string(fixture_id, _FIXTURE_RE, "fixture_id_invalid")
    revision_items = [_validate_revision(item) for item in revisions]
    if not revision_items:
        _fail("empty_revision_history_unprovable")
    if len(revision_items) > 1_000_000:
        _fail("revision_history_too_large")

    command_by_id: dict[str, dict[str, Any]] = {}
    command_shas: set[str] = set()
    for payload in commands:
        try:
            command = validate_score_edit_command(payload)
        except Stage8ContractError as exc:
            raise TeacherWorkloadEvidenceError("command_invalid") from exc
        normalized = command.to_dict()
        if command.command_id in command_by_id or command.command_sha256 in command_shas:
            _fail("duplicate_or_replayed_command")
        command_by_id[command.command_id] = normalized
        command_shas.add(command.command_sha256)

    if len(command_by_id) != len(revision_items):
        _fail("command_revision_cardinality_mismatch")

    revision_ids: set[str] = set()
    revision_shas: set[str] = set()
    used_commands: set[str] = set()
    previous_revision_id: str | None = None
    previous_revision_sha: str | None = None
    previous_audit_sha: str | None = None
    scope: dict[str, str] | None = None
    ordered_command_shas: list[str] = []
    edited_measure_ids: set[str] = set()

    for revision in revision_items:
        revision_id = revision["revisionId"]
        revision_sha = revision["revisionSha256"]
        if revision_id in revision_ids or revision_sha in revision_shas:
            _fail("duplicate_or_replayed_revision")
        revision_ids.add(revision_id)
        revision_shas.add(revision_sha)

        if (
            revision["parentRevisionId"] != previous_revision_id
            or revision["parentRevisionSha256"] != previous_revision_sha
        ):
            _fail("revision_parent_chain_mismatch")
        if revision["previousAuditEventSha256"] != previous_audit_sha:
            _fail("revision_audit_chain_mismatch")

        command = command_by_id.get(revision["commandId"])
        if command is None or command["commandSha256"] != revision["commandSha256"]:
            _fail("revision_command_binding_mismatch")
        if command["commandId"] in used_commands:
            _fail("duplicate_or_replayed_command")
        used_commands.add(command["commandId"])

        checks = (
            (command["jobId"], revision["jobId"]),
            (command["reviewerId"], revision["reviewerId"]),
            (command["authorizationDecisionId"], revision["authorizationDecisionId"]),
            (command["reviewReportId"], revision["reviewReportId"]),
            (command["reviewReportSha256"], revision["reviewReportSha256"]),
            (command["baseCanonicalSha256"], revision["baseCanonicalSha256"]),
            (command["baseRevisionId"], revision["parentRevisionId"]),
            (command["baseRevisionSha256"], revision["parentRevisionSha256"]),
        )
        if any(actual != expected for actual, expected in checks):
            _fail("revision_command_scope_mismatch")

        current_scope = {
            "jobId": revision["jobId"],
            "reviewerId": revision["reviewerId"],
            "reviewReportId": revision["reviewReportId"],
            "reviewReportSha256": revision["reviewReportSha256"],
            "baseCanonicalSha256": revision["baseCanonicalSha256"],
        }
        if scope is None:
            scope = current_scope
        elif current_scope != scope:
            _fail("revision_scope_changed")

        ordered_command_shas.append(command["commandSha256"])
        edited_measure_ids.add(command["location"]["measureId"])
        previous_revision_id = revision_id
        previous_revision_sha = revision_sha
        previous_audit_sha = revision["auditEventSha256"]

    if used_commands != set(command_by_id):
        _fail("unreferenced_command_evidence")
    assert scope is not None

    measure_count = _require_int(measure_count, minimum=1, code="measure_denominator_invalid")
    measure_count_source_sha256 = _require_hash(
        measure_count_source_sha256, "measure_denominator_invalid"
    )
    if measure_count_source_sha256 != scope["baseCanonicalSha256"]:
        _fail("measure_denominator_scope_mismatch")

    if (page_count is None) != (page_count_source_sha256 is None):
        _fail("page_denominator_invalid")
    if page_count is None:
        page = {"available": False, "count": None, "sourceArtifactSha256": None}
    else:
        page = {
            "available": True,
            "count": _require_int(page_count, minimum=1, code="page_denominator_invalid"),
            "sourceArtifactSha256": _require_hash(
                page_count_source_sha256, "page_denominator_invalid"
            ),
        }

    edit_count = len(revision_items)
    evidence: dict[str, Any] = {
        "schemaVersion": EVIDENCE_SCHEMA_VERSION,
        "fixtureId": fixture_id,
        "method": TEACHER_EDIT_METHOD,
        "scope": scope,
        "lineage": {
            "revisionCount": edit_count,
            "headRevisionId": revision_items[-1]["revisionId"],
            "headRevisionSha256": revision_items[-1]["revisionSha256"],
            "revisionSha256s": [item["revisionSha256"] for item in revision_items],
            "commandSha256s": ordered_command_shas,
            "editedMeasureIds": sorted(edited_measure_ids),
        },
        "denominators": {
            "measure": {
                "available": True,
                "count": measure_count,
                "sourceArtifactSha256": measure_count_source_sha256,
            },
            "page": page,
        },
        "workload": {
            "editCount": edit_count,
            "editsPerMeasure": _ratio(edit_count, measure_count),
            "editsPerPage": None if page_count is None else _ratio(edit_count, page_count),
        },
        "boundaries": dict(_BOUNDARIES),
    }
    evidence["evidenceId"] = f"teacher_workload_{_sha(evidence)[:24]}"
    evidence["evidenceSha256"] = _sha(evidence)
    return validate_teacher_workload_evidence(evidence)


def project_teacher_workload_to_sm_poly_04(
    evidence: Mapping[str, Any], semantic_observation: Mapping[str, Any]
) -> dict[str, Any]:
    """Return a new SM-POLY-04 observation with workload only when v1 can represent it.

    SM-POLY-04 v1 requires both measure and page denominators when teacherEdits is
    available. Measure-only SM-POLY-13 evidence therefore remains valid evidence
    but is not forced into the older all-or-nothing semantic field.
    """

    validated = validate_teacher_workload_evidence(evidence)
    if type(semantic_observation) is not dict:
        _fail("semantic_observation_invalid")
    observation = json.loads(_canonical_json(semantic_observation).decode("utf-8"))
    semantic_metrics = observation.get("semanticMetrics")
    metric_order = ("pitch", "duration", "onset", "voice", "staff", "tie", "tuplet")
    if type(semantic_metrics) is dict and set(semantic_metrics) == set(metric_order):
        observation["semanticMetrics"] = {
            name: semantic_metrics[name]
            for name in metric_order
        }
    if observation.get("fixtureId") != validated["fixtureId"]:
        _fail("semantic_fixture_mismatch")
    engine = observation.get("engine")
    if type(engine) is not dict or engine.get("canonicalSha256") != validated["scope"]["baseCanonicalSha256"]:
        _fail("semantic_canonical_mismatch")
    existing = observation.get("teacherEdits")
    if type(existing) is not dict or existing.get("available") is not False or existing.get("method") != "UNAVAILABLE":
        _fail("semantic_teacher_edit_slot_not_empty")
    page = validated["denominators"]["page"]
    if not page["available"]:
        _fail("page_denominator_unavailable_for_sm_poly_04_v1")
    observation["teacherEdits"] = {
        "available": True,
        "method": TEACHER_EDIT_METHOD,
        "editCount": validated["workload"]["editCount"],
        "measureCount": validated["denominators"]["measure"]["count"],
        "pageCount": page["count"],
    }
    return observation


__all__ = [
    "EVIDENCE_SCHEMA_VERSION",
    "TEACHER_EDIT_METHOD",
    "TeacherWorkloadEvidenceError",
    "build_teacher_workload_evidence",
    "project_teacher_workload_to_sm_poly_04",
    "validate_teacher_workload_evidence",
]
