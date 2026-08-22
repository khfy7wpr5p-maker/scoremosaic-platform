"""SQLite-backed append-only Stage 8 revision-store foundation.

The adapter is intentionally private and transport-free. It provides durable,
restart-safe evidence and atomic expected-parent semantics without enabling the
production durable-store flag or any Teacher Review write API.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from types import MappingProxyType
from typing import Any, Mapping

from .contracts import Stage8ContractError, TeacherScoreRevision
from ._materialization import MaterializedEdit, RevisionValidationReport, restore_teacher_state


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
        _fail("REVISION_STORE_NON_CANONICAL_VALUE")


def _sha(value: Any) -> str:
    return sha256(_canonical_json(value)).hexdigest()


def _clone(value: Any) -> Any:
    try:
        return json.loads(_canonical_json(value).decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        _fail("REVISION_STORE_NON_CANONICAL_VALUE")


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _verify_revision_record(record: Mapping[str, Any]) -> dict[str, Any]:
    payload = _clone(record)
    required = {
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
    if set(payload) != required:
        _fail("REVISION_STORE_REVISION_SCHEMA_INVALID")
    revision_id = payload.pop("revisionId")
    claimed_sha = payload.pop("revisionSha256")
    actual_sha = _sha(payload)
    if claimed_sha != actual_sha or revision_id != f"rev_{actual_sha[:32]}":
        _fail("REVISION_STORE_REVISION_HASH_MISMATCH")
    if payload["status"] != "draft" or payload["immutable"] is not True:
        _fail("REVISION_STORE_REVISION_STATE_INVALID")
    if payload["approvalEligible"] is not False or payload["publicationEligible"] is not False:
        _fail("REVISION_STORE_REVISION_STATE_INVALID")
    audit_body = {
        "actorId": payload["reviewerId"],
        "authorizationDecisionId": payload["authorizationDecisionId"],
        "commandSha256": payload["commandSha256"],
        "resultingMusicalStateSha256": payload["resultingMusicalStateSha256"],
        "previousAuditEventSha256": payload["previousAuditEventSha256"],
        "createdAt": payload["createdAt"],
    }
    if _sha(audit_body) != payload["auditEventSha256"]:
        _fail("REVISION_STORE_AUDIT_HASH_MISMATCH")
    return {**payload, "revisionId": revision_id, "revisionSha256": claimed_sha}


def _verify_validation_record(record: Mapping[str, Any], expected_state_sha256: str) -> dict[str, Any]:
    payload = _clone(record)
    if set(payload) != {
        "schemaVersion",
        "musicalStateSha256",
        "blockingIssueCount",
        "unresolvedIssueCount",
        "issues",
        "validationReportSha256",
    }:
        _fail("REVISION_STORE_VALIDATION_SCHEMA_INVALID")
    claimed = payload.pop("validationReportSha256")
    if _sha(payload) != claimed:
        _fail("REVISION_STORE_VALIDATION_HASH_MISMATCH")
    if payload["musicalStateSha256"] != expected_state_sha256:
        _fail("REVISION_STORE_STATE_VALIDATION_MISMATCH")
    return {**payload, "validationReportSha256": claimed}


@dataclass(frozen=True)
class AppendResult:
    revision_id: str
    revision_sha256: str
    already_present: bool


@dataclass(frozen=True)
class StoredRevisionHead:
    job_id: str
    revision: Mapping[str, Any]
    score: Mapping[str, Any]
    validation: RevisionValidationReport

    def restore_state(self):
        return restore_teacher_state(
            base_canonical_sha256=self.revision["baseCanonicalSha256"],
            revision_id=self.revision["revisionId"],
            revision_sha256=self.revision["revisionSha256"],
            score_payload=self.score,
            expected_musical_state_sha256=self.revision["resultingMusicalStateSha256"],
        )


class SqliteRevisionStore:
    """Append-only revision evidence with atomic expected-parent compare/append."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)
        if not self._db_path or self._db_path == ":memory:":
            _fail("REVISION_STORE_PATH_INVALID")
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path, timeout=10.0, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    def _initialize(self) -> None:
        connection = self._connect()
        try:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = FULL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS teacher_revisions (
                    revision_id TEXT PRIMARY KEY,
                    revision_sha256 TEXT NOT NULL UNIQUE,
                    job_id TEXT NOT NULL,
                    command_id TEXT NOT NULL,
                    command_sha256 TEXT NOT NULL,
                    base_canonical_sha256 TEXT NOT NULL,
                    parent_revision_id TEXT,
                    parent_revision_sha256 TEXT,
                    resulting_state_sha256 TEXT NOT NULL,
                    validation_report_sha256 TEXT NOT NULL,
                    audit_event_sha256 TEXT NOT NULL,
                    revision_json BLOB NOT NULL,
                    state_json BLOB NOT NULL,
                    validation_json BLOB NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(job_id, command_sha256),
                    CHECK ((parent_revision_id IS NULL) = (parent_revision_sha256 IS NULL))
                );

                CREATE TABLE IF NOT EXISTS teacher_revision_heads (
                    job_id TEXT PRIMARY KEY,
                    revision_id TEXT NOT NULL,
                    revision_sha256 TEXT NOT NULL,
                    base_canonical_sha256 TEXT NOT NULL,
                    resulting_state_sha256 TEXT NOT NULL,
                    audit_event_sha256 TEXT NOT NULL,
                    FOREIGN KEY(revision_id) REFERENCES teacher_revisions(revision_id)
                );
                """
            )
        finally:
            connection.close()

    def append(
        self,
        *,
        revision: TeacherScoreRevision,
        materialized: MaterializedEdit,
        expected_parent_revision_id: str | None,
        expected_parent_revision_sha256: str | None,
    ) -> AppendResult:
        if not isinstance(revision, TeacherScoreRevision):
            _fail("REVISION_STORE_REVISION_TYPE_INVALID")
        if not isinstance(materialized, MaterializedEdit):
            _fail("REVISION_STORE_MATERIALIZATION_TYPE_INVALID")
        if (expected_parent_revision_id is None) != (expected_parent_revision_sha256 is None):
            _fail("REVISION_STORE_EXPECTED_PARENT_INVALID")

        record = _verify_revision_record(revision.record)
        validation = _verify_validation_record(
            materialized.validation.record, materialized.musical_state_sha256
        )
        state = materialized.score_dict()
        if _sha(state) != materialized.musical_state_sha256:
            _fail("REVISION_STORE_STATE_HASH_MISMATCH")

        checks = (
            (record["parentRevisionId"], expected_parent_revision_id, "REVISION_STORE_PARENT_MISMATCH"),
            (record["parentRevisionSha256"], expected_parent_revision_sha256, "REVISION_STORE_PARENT_MISMATCH"),
            (record["resultingMusicalStateSha256"], materialized.musical_state_sha256, "REVISION_STORE_STATE_HASH_MISMATCH"),
            (record["validationReportSha256"], validation["validationReportSha256"], "REVISION_STORE_VALIDATION_HASH_MISMATCH"),
            (record["blockingIssueCount"], validation["blockingIssueCount"], "REVISION_STORE_VALIDATION_COUNT_MISMATCH"),
            (record["unresolvedIssueCount"], validation["unresolvedIssueCount"], "REVISION_STORE_VALIDATION_COUNT_MISMATCH"),
        )
        for actual, expected, code in checks:
            if actual != expected:
                _fail(code)

        revision_bytes = _canonical_json(record)
        state_bytes = _canonical_json(state)
        validation_bytes = _canonical_json(validation)

        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")

            existing = connection.execute(
                """
                SELECT revision_id, revision_sha256, revision_json, state_json, validation_json
                FROM teacher_revisions
                WHERE job_id = ? AND command_sha256 = ?
                """,
                (record["jobId"], record["commandSha256"]),
            ).fetchone()
            if existing is not None:
                if (
                    existing["revision_id"] == record["revisionId"]
                    and existing["revision_sha256"] == record["revisionSha256"]
                    and bytes(existing["revision_json"]) == revision_bytes
                    and bytes(existing["state_json"]) == state_bytes
                    and bytes(existing["validation_json"]) == validation_bytes
                ):
                    connection.execute("COMMIT")
                    return AppendResult(
                        revision_id=record["revisionId"],
                        revision_sha256=record["revisionSha256"],
                        already_present=True,
                    )
                _fail("REVISION_STORE_IDEMPOTENCY_CONFLICT")

            head = connection.execute(
                """
                SELECT revision_id, revision_sha256
                FROM teacher_revision_heads
                WHERE job_id = ?
                """,
                (record["jobId"],),
            ).fetchone()
            if head is None:
                if expected_parent_revision_id is not None:
                    _fail("REVISION_STORE_STALE_PARENT")
                if record["previousAuditEventSha256"] is not None:
                    _fail("REVISION_STORE_AUDIT_PARENT_MISMATCH")
            else:
                head_full = connection.execute(
                    """
                    SELECT base_canonical_sha256, audit_event_sha256
                    FROM teacher_revision_heads
                    WHERE job_id = ?
                    """,
                    (record["jobId"],),
                ).fetchone()
                if (
                    head["revision_id"] != expected_parent_revision_id
                    or head["revision_sha256"] != expected_parent_revision_sha256
                ):
                    _fail("REVISION_STORE_STALE_PARENT")
                if record["baseCanonicalSha256"] != head_full["base_canonical_sha256"]:
                    _fail("REVISION_STORE_BASE_CANONICAL_MISMATCH")
                if record["previousAuditEventSha256"] != head_full["audit_event_sha256"]:
                    _fail("REVISION_STORE_AUDIT_PARENT_MISMATCH")

            connection.execute(
                """
                INSERT INTO teacher_revisions (
                    revision_id, revision_sha256, job_id, command_id, command_sha256,
                    base_canonical_sha256, parent_revision_id, parent_revision_sha256,
                    resulting_state_sha256, validation_report_sha256, audit_event_sha256,
                    revision_json, state_json, validation_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record["revisionId"],
                    record["revisionSha256"],
                    record["jobId"],
                    record["commandId"],
                    record["commandSha256"],
                    record["baseCanonicalSha256"],
                    record["parentRevisionId"],
                    record["parentRevisionSha256"],
                    record["resultingMusicalStateSha256"],
                    record["validationReportSha256"],
                    record["auditEventSha256"],
                    revision_bytes,
                    state_bytes,
                    validation_bytes,
                    record["createdAt"],
                ),
            )

            if head is None:
                connection.execute(
                    """
                    INSERT INTO teacher_revision_heads (
                        job_id, revision_id, revision_sha256, base_canonical_sha256,
                        resulting_state_sha256, audit_event_sha256
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record["jobId"],
                        record["revisionId"],
                        record["revisionSha256"],
                        record["baseCanonicalSha256"],
                        record["resultingMusicalStateSha256"],
                        record["auditEventSha256"],
                    ),
                )
            else:
                cursor = connection.execute(
                    """
                    UPDATE teacher_revision_heads
                    SET revision_id = ?, revision_sha256 = ?, base_canonical_sha256 = ?,
                        resulting_state_sha256 = ?, audit_event_sha256 = ?
                    WHERE job_id = ? AND revision_id = ? AND revision_sha256 = ?
                    """,
                    (
                        record["revisionId"],
                        record["revisionSha256"],
                        record["baseCanonicalSha256"],
                        record["resultingMusicalStateSha256"],
                        record["auditEventSha256"],
                        record["jobId"],
                        expected_parent_revision_id,
                        expected_parent_revision_sha256,
                    ),
                )
                if cursor.rowcount != 1:
                    _fail("REVISION_STORE_STALE_PARENT")

            connection.execute("COMMIT")
            return AppendResult(
                revision_id=record["revisionId"],
                revision_sha256=record["revisionSha256"],
                already_present=False,
            )
        except Stage8ContractError:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        except sqlite3.IntegrityError:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise Stage8ContractError("REVISION_STORE_INTEGRITY_CONFLICT") from None
        except sqlite3.Error:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise Stage8ContractError("REVISION_STORE_PROVIDER_FAILURE") from None
        finally:
            connection.close()

    def load_head(self, job_id: str) -> StoredRevisionHead | None:
        if not isinstance(job_id, str) or not job_id:
            _fail("REVISION_STORE_JOB_ID_INVALID")
        connection = self._connect()
        try:
            head_row = connection.execute(
                """
                SELECT
                    revision_id, revision_sha256, base_canonical_sha256,
                    resulting_state_sha256, audit_event_sha256
                FROM teacher_revision_heads
                WHERE job_id = ?
                """,
                (job_id,),
            ).fetchone()
            if head_row is None:
                return None
            rows = connection.execute(
                """
                SELECT revision_json, state_json, validation_json
                FROM teacher_revisions
                WHERE job_id = ?
                """,
                (job_id,),
            ).fetchall()
        except sqlite3.Error:
            raise Stage8ContractError("REVISION_STORE_PROVIDER_FAILURE") from None
        finally:
            connection.close()

        records: dict[str, tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = {}
        try:
            for row in rows:
                revision_raw = json.loads(bytes(row["revision_json"]).decode("utf-8"))
                state_raw = json.loads(bytes(row["state_json"]).decode("utf-8"))
                validation_raw = json.loads(bytes(row["validation_json"]).decode("utf-8"))
                revision = _verify_revision_record(revision_raw)
                if revision["jobId"] != job_id:
                    _fail("REVISION_STORE_JOB_CORRUPTION_DETECTED")
                if _sha(state_raw) != revision["resultingMusicalStateSha256"]:
                    _fail("REVISION_STORE_STATE_CORRUPTION_DETECTED")
                validation = _verify_validation_record(
                    validation_raw, revision["resultingMusicalStateSha256"]
                )
                if validation["validationReportSha256"] != revision["validationReportSha256"]:
                    _fail("REVISION_STORE_VALIDATION_CORRUPTION_DETECTED")
                if revision["revisionId"] in records:
                    _fail("REVISION_STORE_DUPLICATE_REVISION_DETECTED")
                records[revision["revisionId"]] = (revision, state_raw, validation)
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
            _fail("REVISION_STORE_CORRUPTION_DETECTED")

        head_id = head_row["revision_id"]
        if head_id not in records:
            _fail("REVISION_STORE_HEAD_CORRUPTION_DETECTED")
        head_revision, head_state, head_validation = records[head_id]
        if (
            head_revision["revisionSha256"] != head_row["revision_sha256"]
            or head_revision["baseCanonicalSha256"] != head_row["base_canonical_sha256"]
            or head_revision["resultingMusicalStateSha256"] != head_row["resulting_state_sha256"]
            or head_revision["auditEventSha256"] != head_row["audit_event_sha256"]
        ):
            _fail("REVISION_STORE_HEAD_CORRUPTION_DETECTED")

        seen: set[str] = set()
        current = head_revision
        while True:
            current_id = current["revisionId"]
            if current_id in seen:
                _fail("REVISION_STORE_CHAIN_CYCLE_DETECTED")
            seen.add(current_id)
            parent_id = current["parentRevisionId"]
            parent_sha = current["parentRevisionSha256"]
            previous_audit = current["previousAuditEventSha256"]
            if parent_id is None:
                if parent_sha is not None or previous_audit is not None:
                    _fail("REVISION_STORE_CHAIN_CORRUPTION_DETECTED")
                break
            parent_entry = records.get(parent_id)
            if parent_entry is None:
                _fail("REVISION_STORE_CHAIN_PARENT_MISSING")
            parent = parent_entry[0]
            if (
                parent["revisionSha256"] != parent_sha
                or parent["auditEventSha256"] != previous_audit
                or parent["baseCanonicalSha256"] != current["baseCanonicalSha256"]
            ):
                _fail("REVISION_STORE_CHAIN_CORRUPTION_DETECTED")
            current = parent

        if len(seen) != len(records):
            _fail("REVISION_STORE_ORPHAN_REVISION_DETECTED")

        return StoredRevisionHead(
            job_id=job_id,
            revision=_freeze(head_revision),
            score=_freeze(head_state),
            validation=RevisionValidationReport(_freeze(head_validation)),
        )
