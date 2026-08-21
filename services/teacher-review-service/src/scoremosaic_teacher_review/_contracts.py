from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import hmac
import json
import re
from types import MappingProxyType
from typing import Any, Mapping


AUTHZ_VERSION = "scoremosaic-review-authz-v1"
COMMAND_VERSION = "scoremosaic-score-edit-command-v1"
REVISION_VERSION = "scoremosaic-teacher-score-revision-v1"
AUTHZ_PURPOSE = b"scoremosaic/teacher-review/authorization/v1\x00"

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")
_JOB_RE = re.compile(r"^job_[A-Za-z0-9_-]{8,80}$")
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_ISSUE_RE = re.compile(r"^issue_[A-Za-z0-9_-]{6,80}$")
_ALLOWED_ACTIONS = frozenset({"revision:read", "revision:propose"})
_ALLOWED_OPERATIONS = frozenset(
    {
        "set_pitch",
        "set_effective_duration",
        "set_written_type",
        "set_dots",
        "set_staff_voice",
        "set_time_signature",
        "set_tab",
        "remove_event",
    }
)
_ALLOWED_COMMAND_KEYS = frozenset(
    {
        "schemaVersion",
        "commandId",
        "jobId",
        "reviewerId",
        "authorizationDecisionId",
        "reviewReportId",
        "reviewReportSha256",
        "baseCanonicalSha256",
        "baseRevisionId",
        "baseRevisionSha256",
        "issueId",
        "location",
        "operation",
        "oldValueSha256",
        "reason",
        "commandSha256",
    }
)
_ALLOWED_LOCATION_KEYS = frozenset(
    {"partId", "measureId", "eventId", "staff", "voice", "onset"}
)
_ALLOWED_ONSET_KEYS = frozenset({"numerator", "denominator"})
_ALLOWED_OPERATION_KEYS = frozenset({"type", "value"})


class Stage8ContractError(ValueError):
    """Fail-closed Stage 8 contract violation with a stable public code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _fail(code: str) -> None:
    raise Stage8ContractError(code)


def _require_exact_keys(mapping: Mapping[str, Any], allowed: frozenset[str], code: str) -> None:
    if set(mapping) != set(allowed):
        _fail(code)


def _require_string(value: Any, *, code: str, max_length: int = 200, pattern: re.Pattern[str] | None = None) -> str:
    if not isinstance(value, str) or not value or len(value) > max_length:
        _fail(code)
    if pattern is not None and pattern.fullmatch(value) is None:
        _fail(code)
    return value


def _require_hash(value: Any, code: str) -> str:
    return _require_string(value, code=code, max_length=64, pattern=_HASH_RE)


def _require_nullable_hash(value: Any, code: str) -> str | None:
    if value is None:
        return None
    return _require_hash(value, code)


def _require_nullable_id(value: Any, code: str) -> str | None:
    if value is None:
        return None
    return _require_string(value, code=code, pattern=_ID_RE)


def _require_int(value: Any, *, code: str, minimum: int | None = None, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(code)
    if minimum is not None and value < minimum:
        _fail(code)
    if maximum is not None and value > maximum:
        _fail(code)
    return value


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError):
        _fail("NON_CANONICAL_VALUE")


def _sha256_mapping(value: Mapping[str, Any]) -> str:
    return sha256(_canonical_json(value)).hexdigest()


def _normalize_parent(parent_id: Any, parent_sha256: Any, *, code: str) -> tuple[str | None, str | None]:
    normalized_id = _require_nullable_id(parent_id, code)
    normalized_sha = _require_nullable_hash(parent_sha256, code)
    if (normalized_id is None) != (normalized_sha is None):
        _fail(code)
    return normalized_id, normalized_sha


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


def _immutable_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    # JSON round-trip removes caller-owned aliases; recursive freezing prevents nested mutation.
    cloned = json.loads(_canonical_json(value).decode("utf-8"))
    return _deep_freeze(cloned)


@dataclass(frozen=True)
class ReviewAuthorizationGrant:
    decision_id: str
    reviewer_id: str
    tenant_id: str
    job_id: str
    review_report_id: str
    review_report_sha256: str
    canonical_score_sha256: str
    parent_revision_id: str | None
    parent_revision_sha256: str | None
    allowed_actions: tuple[str, ...]
    grant_sha256: str
    signature_hex: str = field(repr=False)

    def safe_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": AUTHZ_VERSION,
            "decisionId": self.decision_id,
            "reviewerId": self.reviewer_id,
            "tenantId": self.tenant_id,
            "jobId": self.job_id,
            "reviewReportId": self.review_report_id,
            "reviewReportSha256": self.review_report_sha256,
            "canonicalScoreSha256": self.canonical_score_sha256,
            "parentRevisionId": self.parent_revision_id,
            "parentRevisionSha256": self.parent_revision_sha256,
            "allowedActions": list(self.allowed_actions),
            "grantSha256": self.grant_sha256,
            "signature": "<redacted>",
        }


@dataclass(frozen=True)
class VerifiedReviewAuthorization:
    decision_id: str
    reviewer_id: str
    tenant_id: str
    job_id: str
    review_report_id: str
    review_report_sha256: str
    canonical_score_sha256: str
    parent_revision_id: str | None
    parent_revision_sha256: str | None
    allowed_actions: tuple[str, ...]
    grant_sha256: str


@dataclass(frozen=True)
class ScoreEditCommand:
    command_id: str
    job_id: str
    reviewer_id: str
    authorization_decision_id: str
    review_report_id: str
    review_report_sha256: str
    base_canonical_sha256: str
    base_revision_id: str | None
    base_revision_sha256: str | None
    issue_id: str | None
    location: Mapping[str, Any]
    operation: Mapping[str, Any]
    old_value_sha256: str
    reason: str | None
    command_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": COMMAND_VERSION,
            "commandId": self.command_id,
            "jobId": self.job_id,
            "reviewerId": self.reviewer_id,
            "authorizationDecisionId": self.authorization_decision_id,
            "reviewReportId": self.review_report_id,
            "reviewReportSha256": self.review_report_sha256,
            "baseCanonicalSha256": self.base_canonical_sha256,
            "baseRevisionId": self.base_revision_id,
            "baseRevisionSha256": self.base_revision_sha256,
            "issueId": self.issue_id,
            "location": _deep_thaw(self.location),
            "operation": _deep_thaw(self.operation),
            "oldValueSha256": self.old_value_sha256,
            "reason": self.reason,
            "commandSha256": self.command_sha256,
        }


@dataclass(frozen=True)
class TeacherScoreRevision:
    record: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return _deep_thaw(self.record)


def issue_authorization_grant(
    *,
    decision_id: str,
    reviewer_id: str,
    tenant_id: str,
    job_id: str,
    review_report_id: str,
    review_report_sha256: str,
    canonical_score_sha256: str,
    parent_revision_id: str | None,
    parent_revision_sha256: str | None,
    allowed_actions: tuple[str, ...],
    signing_key: bytes,
) -> ReviewAuthorizationGrant:
    if not isinstance(signing_key, bytes) or len(signing_key) < 32:
        _fail("AUTHZ_KEY_INVALID")
    decision_id = _require_string(decision_id, code="AUTHZ_DECISION_ID_INVALID", pattern=_ID_RE)
    reviewer_id = _require_string(reviewer_id, code="AUTHZ_REVIEWER_ID_INVALID", pattern=_ID_RE)
    tenant_id = _require_string(tenant_id, code="AUTHZ_TENANT_ID_INVALID", pattern=_ID_RE)
    job_id = _require_string(job_id, code="AUTHZ_JOB_ID_INVALID", pattern=_JOB_RE)
    review_report_id = _require_string(review_report_id, code="AUTHZ_REPORT_ID_INVALID", pattern=_ID_RE)
    review_report_sha256 = _require_hash(review_report_sha256, "AUTHZ_REPORT_HASH_INVALID")
    canonical_score_sha256 = _require_hash(canonical_score_sha256, "AUTHZ_CANONICAL_HASH_INVALID")
    parent_revision_id, parent_revision_sha256 = _normalize_parent(
        parent_revision_id, parent_revision_sha256, code="AUTHZ_PARENT_INVALID"
    )
    if not isinstance(allowed_actions, tuple) or not allowed_actions:
        _fail("AUTHZ_ACTIONS_INVALID")
    if any(action not in _ALLOWED_ACTIONS for action in allowed_actions):
        _fail("AUTHZ_ACTIONS_INVALID")
    normalized_actions = tuple(sorted(set(allowed_actions)))
    if len(normalized_actions) != len(allowed_actions):
        _fail("AUTHZ_ACTIONS_INVALID")

    body = {
        "schemaVersion": AUTHZ_VERSION,
        "decisionId": decision_id,
        "reviewerId": reviewer_id,
        "tenantId": tenant_id,
        "jobId": job_id,
        "reviewReportId": review_report_id,
        "reviewReportSha256": review_report_sha256,
        "canonicalScoreSha256": canonical_score_sha256,
        "parentRevisionId": parent_revision_id,
        "parentRevisionSha256": parent_revision_sha256,
        "allowedActions": list(normalized_actions),
    }
    grant_sha256 = _sha256_mapping(body)
    signature_hex = hmac.new(signing_key, AUTHZ_PURPOSE + _canonical_json(body), sha256).hexdigest()
    return ReviewAuthorizationGrant(
        decision_id=decision_id,
        reviewer_id=reviewer_id,
        tenant_id=tenant_id,
        job_id=job_id,
        review_report_id=review_report_id,
        review_report_sha256=review_report_sha256,
        canonical_score_sha256=canonical_score_sha256,
        parent_revision_id=parent_revision_id,
        parent_revision_sha256=parent_revision_sha256,
        allowed_actions=normalized_actions,
        grant_sha256=grant_sha256,
        signature_hex=signature_hex,
    )


def verify_authorization_grant(
    grant: ReviewAuthorizationGrant,
    *,
    signing_key: bytes,
    required_action: str,
    expected_job_id: str,
    expected_reviewer_id: str,
    expected_review_report_id: str,
    expected_review_report_sha256: str,
    expected_canonical_score_sha256: str,
    expected_parent_revision_id: str | None,
    expected_parent_revision_sha256: str | None,
) -> VerifiedReviewAuthorization:
    if not isinstance(grant, ReviewAuthorizationGrant):
        _fail("AUTHZ_GRANT_TYPE_INVALID")
    if not isinstance(signing_key, bytes) or len(signing_key) < 32:
        _fail("AUTHZ_KEY_INVALID")
    if required_action not in _ALLOWED_ACTIONS:
        _fail("AUTHZ_REQUIRED_ACTION_INVALID")

    expected_parent_revision_id, expected_parent_revision_sha256 = _normalize_parent(
        expected_parent_revision_id,
        expected_parent_revision_sha256,
        code="AUTHZ_EXPECTED_PARENT_INVALID",
    )
    body = {
        "schemaVersion": AUTHZ_VERSION,
        "decisionId": grant.decision_id,
        "reviewerId": grant.reviewer_id,
        "tenantId": grant.tenant_id,
        "jobId": grant.job_id,
        "reviewReportId": grant.review_report_id,
        "reviewReportSha256": grant.review_report_sha256,
        "canonicalScoreSha256": grant.canonical_score_sha256,
        "parentRevisionId": grant.parent_revision_id,
        "parentRevisionSha256": grant.parent_revision_sha256,
        "allowedActions": list(grant.allowed_actions),
    }
    expected_grant_sha = _sha256_mapping(body)
    if not hmac.compare_digest(grant.grant_sha256, expected_grant_sha):
        _fail("AUTHZ_GRANT_HASH_MISMATCH")
    expected_signature = hmac.new(signing_key, AUTHZ_PURPOSE + _canonical_json(body), sha256).hexdigest()
    if not hmac.compare_digest(grant.signature_hex, expected_signature):
        _fail("AUTHZ_SIGNATURE_INVALID")

    expected = (
        (grant.job_id, expected_job_id, "AUTHZ_JOB_MISMATCH"),
        (grant.reviewer_id, expected_reviewer_id, "AUTHZ_REVIEWER_MISMATCH"),
        (grant.review_report_id, expected_review_report_id, "AUTHZ_REPORT_MISMATCH"),
        (grant.review_report_sha256, expected_review_report_sha256, "AUTHZ_REPORT_HASH_MISMATCH"),
        (grant.canonical_score_sha256, expected_canonical_score_sha256, "AUTHZ_CANONICAL_HASH_MISMATCH"),
        (grant.parent_revision_id, expected_parent_revision_id, "AUTHZ_STALE_PARENT"),
        (grant.parent_revision_sha256, expected_parent_revision_sha256, "AUTHZ_STALE_PARENT"),
    )
    for actual, wanted, code in expected:
        if actual != wanted:
            _fail(code)
    if required_action not in grant.allowed_actions:
        _fail("AUTHZ_ACTION_DENIED")

    return VerifiedReviewAuthorization(
        decision_id=grant.decision_id,
        reviewer_id=grant.reviewer_id,
        tenant_id=grant.tenant_id,
        job_id=grant.job_id,
        review_report_id=grant.review_report_id,
        review_report_sha256=grant.review_report_sha256,
        canonical_score_sha256=grant.canonical_score_sha256,
        parent_revision_id=grant.parent_revision_id,
        parent_revision_sha256=grant.parent_revision_sha256,
        allowed_actions=grant.allowed_actions,
        grant_sha256=grant.grant_sha256,
    )


def _validate_rational(value: Any, code: str) -> dict[str, int]:
    if not isinstance(value, Mapping):
        _fail(code)
    _require_exact_keys(value, _ALLOWED_ONSET_KEYS, code)
    numerator = _require_int(value["numerator"], code=code)
    denominator = _require_int(value["denominator"], code=code, minimum=1, maximum=1_000_000)
    return {"numerator": numerator, "denominator": denominator}


def _validate_location(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail("COMMAND_LOCATION_INVALID")
    _require_exact_keys(value, _ALLOWED_LOCATION_KEYS, "COMMAND_LOCATION_INVALID")
    return {
        "partId": _require_string(value["partId"], code="COMMAND_LOCATION_INVALID", pattern=_ID_RE),
        "measureId": _require_string(value["measureId"], code="COMMAND_LOCATION_INVALID", pattern=_ID_RE),
        "eventId": _require_string(value["eventId"], code="COMMAND_LOCATION_INVALID", pattern=_ID_RE),
        "staff": _require_int(value["staff"], code="COMMAND_LOCATION_INVALID", minimum=1, maximum=128),
        "voice": _require_string(value["voice"], code="COMMAND_LOCATION_INVALID", max_length=40),
        "onset": _validate_rational(value["onset"], "COMMAND_LOCATION_INVALID"),
    }


def _validate_operation(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail("COMMAND_OPERATION_INVALID")
    _require_exact_keys(value, _ALLOWED_OPERATION_KEYS, "COMMAND_OPERATION_INVALID")
    op_type = value["type"]
    if op_type not in _ALLOWED_OPERATIONS:
        _fail("COMMAND_OPERATION_NOT_ALLOWED")
    new_value = value["value"]

    if op_type == "set_pitch":
        if not isinstance(new_value, Mapping) or set(new_value) != {"step", "alter", "octave"}:
            _fail("COMMAND_VALUE_INVALID")
        step = new_value["step"]
        if step not in {"A", "B", "C", "D", "E", "F", "G"}:
            _fail("COMMAND_VALUE_INVALID")
        normalized = {
            "step": step,
            "alter": _validate_rational(new_value["alter"], "COMMAND_VALUE_INVALID"),
            "octave": _require_int(new_value["octave"], code="COMMAND_VALUE_INVALID", minimum=-2, maximum=12),
        }
    elif op_type == "set_effective_duration":
        normalized = _validate_rational(new_value, "COMMAND_VALUE_INVALID")
        if normalized["numerator"] < 0:
            _fail("COMMAND_VALUE_INVALID")
    elif op_type == "set_written_type":
        normalized = _require_string(new_value, code="COMMAND_VALUE_INVALID", max_length=40)
    elif op_type == "set_dots":
        normalized = _require_int(new_value, code="COMMAND_VALUE_INVALID", minimum=0, maximum=8)
    elif op_type == "set_staff_voice":
        if not isinstance(new_value, Mapping) or set(new_value) != {"staff", "voice"}:
            _fail("COMMAND_VALUE_INVALID")
        normalized = {
            "staff": _require_int(new_value["staff"], code="COMMAND_VALUE_INVALID", minimum=1, maximum=128),
            "voice": _require_string(new_value["voice"], code="COMMAND_VALUE_INVALID", max_length=40),
        }
    elif op_type == "set_time_signature":
        if not isinstance(new_value, Mapping) or set(new_value) != {"beats", "beatType"}:
            _fail("COMMAND_VALUE_INVALID")
        beats = _require_string(new_value["beats"], code="COMMAND_VALUE_INVALID", max_length=40)
        if re.fullmatch(r"^[1-9][0-9]*(\+[1-9][0-9]*)*$", beats) is None:
            _fail("COMMAND_VALUE_INVALID")
        normalized = {
            "beats": beats,
            "beatType": _require_int(new_value["beatType"], code="COMMAND_VALUE_INVALID", minimum=1, maximum=1024),
        }
    elif op_type == "set_tab":
        if not isinstance(new_value, Mapping) or set(new_value) != {"string", "fret"}:
            _fail("COMMAND_VALUE_INVALID")
        normalized = {
            "string": _require_int(new_value["string"], code="COMMAND_VALUE_INVALID", minimum=1, maximum=24),
            "fret": _require_int(new_value["fret"], code="COMMAND_VALUE_INVALID", minimum=0, maximum=96),
        }
    else:
        if new_value is not None:
            _fail("COMMAND_VALUE_INVALID")
        normalized = None

    return {"type": op_type, "value": normalized}


def validate_score_edit_command(payload: Mapping[str, Any]) -> ScoreEditCommand:
    if not isinstance(payload, Mapping):
        _fail("COMMAND_TYPE_INVALID")
    _require_exact_keys(payload, _ALLOWED_COMMAND_KEYS, "COMMAND_SCHEMA_CLOSED")
    if payload["schemaVersion"] != COMMAND_VERSION:
        _fail("COMMAND_VERSION_INVALID")

    command_id = _require_string(payload["commandId"], code="COMMAND_ID_INVALID", pattern=_ID_RE)
    job_id = _require_string(payload["jobId"], code="COMMAND_JOB_ID_INVALID", pattern=_JOB_RE)
    reviewer_id = _require_string(payload["reviewerId"], code="COMMAND_REVIEWER_ID_INVALID", pattern=_ID_RE)
    authorization_decision_id = _require_string(payload["authorizationDecisionId"], code="COMMAND_AUTHZ_ID_INVALID", pattern=_ID_RE)
    review_report_id = _require_string(payload["reviewReportId"], code="COMMAND_REPORT_ID_INVALID", pattern=_ID_RE)
    review_report_sha256 = _require_hash(payload["reviewReportSha256"], "COMMAND_REPORT_HASH_INVALID")
    base_canonical_sha256 = _require_hash(payload["baseCanonicalSha256"], "COMMAND_CANONICAL_HASH_INVALID")
    base_revision_id, base_revision_sha256 = _normalize_parent(payload["baseRevisionId"], payload["baseRevisionSha256"], code="COMMAND_PARENT_INVALID")
    issue_id = payload["issueId"]
    if issue_id is not None:
        issue_id = _require_string(issue_id, code="COMMAND_ISSUE_ID_INVALID", max_length=86, pattern=_ISSUE_RE)
    location = _validate_location(payload["location"])
    operation = _validate_operation(payload["operation"])
    old_value_sha256 = _require_hash(payload["oldValueSha256"], "COMMAND_OLD_VALUE_HASH_INVALID")
    reason = payload["reason"]
    if reason is not None:
        reason = _require_string(reason, code="COMMAND_REASON_INVALID", max_length=2000)

    body = {
        "schemaVersion": COMMAND_VERSION,
        "commandId": command_id,
        "jobId": job_id,
        "reviewerId": reviewer_id,
        "authorizationDecisionId": authorization_decision_id,
        "reviewReportId": review_report_id,
        "reviewReportSha256": review_report_sha256,
        "baseCanonicalSha256": base_canonical_sha256,
        "baseRevisionId": base_revision_id,
        "baseRevisionSha256": base_revision_sha256,
        "issueId": issue_id,
        "location": location,
        "operation": operation,
        "oldValueSha256": old_value_sha256,
        "reason": reason,
    }
    expected_sha = _sha256_mapping(body)
    command_sha256 = _require_hash(payload["commandSha256"], "COMMAND_HASH_INVALID")
    if not hmac.compare_digest(command_sha256, expected_sha):
        _fail("COMMAND_HASH_MISMATCH")

    return ScoreEditCommand(
        command_id=command_id,
        job_id=job_id,
        reviewer_id=reviewer_id,
        authorization_decision_id=authorization_decision_id,
        review_report_id=review_report_id,
        review_report_sha256=review_report_sha256,
        base_canonical_sha256=base_canonical_sha256,
        base_revision_id=base_revision_id,
        base_revision_sha256=base_revision_sha256,
        issue_id=issue_id,
        location=_immutable_mapping(location),
        operation=_immutable_mapping(operation),
        old_value_sha256=old_value_sha256,
        reason=reason,
        command_sha256=command_sha256,
    )


def build_score_edit_command(payload_without_hash: Mapping[str, Any]) -> ScoreEditCommand:
    if not isinstance(payload_without_hash, Mapping) or "commandSha256" in payload_without_hash:
        _fail("COMMAND_BUILD_INPUT_INVALID")
    candidate = dict(payload_without_hash)
    candidate["commandSha256"] = "0" * 64
    try:
        validate_score_edit_command(candidate)
    except Stage8ContractError as exc:
        if exc.code != "COMMAND_HASH_MISMATCH":
            raise
    body = {key: value for key, value in candidate.items() if key != "commandSha256"}
    candidate["commandSha256"] = _sha256_mapping(body)
    return validate_score_edit_command(candidate)


def assert_authorized_command(
    authorization: VerifiedReviewAuthorization,
    command: ScoreEditCommand,
    *,
    current_parent_revision_id: str | None,
    current_parent_revision_sha256: str | None,
) -> None:
    if not isinstance(authorization, VerifiedReviewAuthorization):
        _fail("COMMAND_AUTHZ_TYPE_INVALID")
    if not isinstance(command, ScoreEditCommand):
        _fail("COMMAND_TYPE_INVALID")
    current_parent_revision_id, current_parent_revision_sha256 = _normalize_parent(current_parent_revision_id, current_parent_revision_sha256, code="CURRENT_PARENT_INVALID")
    checks = (
        (command.authorization_decision_id, authorization.decision_id, "COMMAND_AUTHZ_MISMATCH"),
        (command.job_id, authorization.job_id, "COMMAND_JOB_MISMATCH"),
        (command.reviewer_id, authorization.reviewer_id, "COMMAND_REVIEWER_MISMATCH"),
        (command.review_report_id, authorization.review_report_id, "COMMAND_REPORT_MISMATCH"),
        (command.review_report_sha256, authorization.review_report_sha256, "COMMAND_REPORT_HASH_MISMATCH"),
        (command.base_canonical_sha256, authorization.canonical_score_sha256, "COMMAND_CANONICAL_HASH_MISMATCH"),
        (command.base_revision_id, authorization.parent_revision_id, "COMMAND_STALE_PARENT"),
        (command.base_revision_sha256, authorization.parent_revision_sha256, "COMMAND_STALE_PARENT"),
        (command.base_revision_id, current_parent_revision_id, "COMMAND_STALE_PARENT"),
        (command.base_revision_sha256, current_parent_revision_sha256, "COMMAND_STALE_PARENT"),
    )
    for actual, expected, code in checks:
        if actual != expected:
            _fail(code)
    if "revision:propose" not in authorization.allowed_actions:
        _fail("COMMAND_ACTION_DENIED")


def build_teacher_score_revision(
    *,
    authorization: VerifiedReviewAuthorization,
    command: ScoreEditCommand,
    current_parent_revision_id: str | None,
    current_parent_revision_sha256: str | None,
    resulting_musical_state_sha256: str,
    validation_report_sha256: str,
    blocking_issue_count: int,
    unresolved_issue_count: int,
    created_at: str,
    previous_audit_event_sha256: str | None,
) -> TeacherScoreRevision:
    assert_authorized_command(
        authorization,
        command,
        current_parent_revision_id=current_parent_revision_id,
        current_parent_revision_sha256=current_parent_revision_sha256,
    )
    resulting_musical_state_sha256 = _require_hash(resulting_musical_state_sha256, "REVISION_RESULT_HASH_INVALID")
    validation_report_sha256 = _require_hash(validation_report_sha256, "REVISION_VALIDATION_HASH_INVALID")
    blocking_issue_count = _require_int(blocking_issue_count, code="REVISION_BLOCKING_COUNT_INVALID", minimum=0, maximum=1_000_000)
    unresolved_issue_count = _require_int(unresolved_issue_count, code="REVISION_UNRESOLVED_COUNT_INVALID", minimum=0, maximum=1_000_000)
    created_at = _require_string(created_at, code="REVISION_CREATED_AT_INVALID", max_length=64)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", created_at) is None:
        _fail("REVISION_CREATED_AT_INVALID")
    previous_audit_event_sha256 = _require_nullable_hash(previous_audit_event_sha256, "REVISION_AUDIT_PARENT_INVALID")

    provenance = {
        "jobId": command.job_id,
        "reviewerId": command.reviewer_id,
        "tenantId": authorization.tenant_id,
        "authorizationDecisionId": authorization.decision_id,
        "authorizationGrantSha256": authorization.grant_sha256,
        "reviewReportId": command.review_report_id,
        "reviewReportSha256": command.review_report_sha256,
        "baseCanonicalSha256": command.base_canonical_sha256,
        "parentRevisionId": command.base_revision_id,
        "parentRevisionSha256": command.base_revision_sha256,
        "commandId": command.command_id,
        "commandSha256": command.command_sha256,
        "resultingMusicalStateSha256": resulting_musical_state_sha256,
        "validationReportSha256": validation_report_sha256,
        "blockingIssueCount": blocking_issue_count,
        "unresolvedIssueCount": unresolved_issue_count,
        "createdAt": created_at,
        "previousAuditEventSha256": previous_audit_event_sha256,
        "status": "draft",
        "immutable": True,
        "approvalEligible": False,
        "publicationEligible": False,
    }
    audit_body = {
        "actorId": authorization.reviewer_id,
        "authorizationDecisionId": authorization.decision_id,
        "commandSha256": command.command_sha256,
        "resultingMusicalStateSha256": resulting_musical_state_sha256,
        "previousAuditEventSha256": previous_audit_event_sha256,
        "createdAt": created_at,
    }
    audit_event_sha256 = _sha256_mapping(audit_body)
    revision_body = {
        "schemaVersion": REVISION_VERSION,
        **provenance,
        "auditEventSha256": audit_event_sha256,
    }
    revision_sha256 = _sha256_mapping(revision_body)
    record = {
        **revision_body,
        "revisionId": f"rev_{revision_sha256[:32]}",
        "revisionSha256": revision_sha256,
    }
    return TeacherScoreRevision(_immutable_mapping(record))
