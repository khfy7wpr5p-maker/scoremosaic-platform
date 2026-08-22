from __future__ import annotations

import hmac
import sqlite3
from pathlib import Path
import stat
from typing import Any, Callable

from .contracts import TeacherScoreRevision
from ._revision_store_backend import SqliteRevisionBackend
from ._revision_store_common import (
    AppendRevisionResult,
    DurableRevisionHead,
    DurableRevisionStoreError,
    HEAD_PURPOSE,
    RevisionScope,
    fail,
    hmac_hex,
    require_parent_pair,
)
from ._revision_store_validation import validate_revision_for_store


class DurableRevisionStore(SqliteRevisionBackend):
    """Controlled durable append-only Teacher Review revision store.

    This class is a repository-owned persistence foundation, not a public API and
    not a production activation. Each append is one SQLite FULL-synchronous
    transaction. `BEGIN IMMEDIATE` provides a single writer linearization point;
    the exact parent revision acts as an optimistic-concurrency precondition.
    """

    def __init__(
        self,
        root: Path,
        *,
        signing_key: bytes,
        _fault_injector: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(root, signing_key)
        self._fault_injector = _fault_injector

    def __repr__(self) -> str:
        return (
            f"DurableRevisionStore(root={self._root!r}, "
            f"signing_key=<redacted>, schema={self._schema_version!r})"
        )

    @property
    def _schema_version(self) -> str:
        from ._revision_store_common import STORE_SCHEMA_VERSION

        return STORE_SCHEMA_VERSION

    def _connect(self) -> sqlite3.Connection:
        """Open SQLite only while the private root/database identities remain safe."""

        try:
            root_stat = self._root.lstat()
        except OSError:
            fail("revision_store_root_invalid")
        if not stat.S_ISDIR(root_stat.st_mode) or stat.S_ISLNK(root_stat.st_mode):
            fail("revision_store_root_invalid")
        root_identity = (root_stat.st_dev, root_stat.st_ino)
        retained_root_identity = getattr(self, "_root_identity", None)
        if retained_root_identity is not None and root_identity != retained_root_identity:
            fail("revision_store_root_substituted")

        try:
            pre_db_stat = self._db_path.lstat()
        except FileNotFoundError:
            pre_db_stat = None
        except OSError:
            fail("revision_store_database_invalid")
        if pre_db_stat is not None and (
            stat.S_ISLNK(pre_db_stat.st_mode) or not stat.S_ISREG(pre_db_stat.st_mode)
        ):
            fail("revision_store_database_invalid")
        pre_db_identity = (
            None
            if pre_db_stat is None
            else (pre_db_stat.st_dev, pre_db_stat.st_ino)
        )

        connection = super()._connect()
        try:
            post_root_stat = self._root.lstat()
            post_db_stat = self._db_path.lstat()
        except OSError:
            connection.close()
            fail("revision_store_database_invalid")
        if (
            not stat.S_ISDIR(post_root_stat.st_mode)
            or stat.S_ISLNK(post_root_stat.st_mode)
            or not stat.S_ISREG(post_db_stat.st_mode)
            or stat.S_ISLNK(post_db_stat.st_mode)
        ):
            connection.close()
            fail("revision_store_database_invalid")
        post_root_identity = (post_root_stat.st_dev, post_root_stat.st_ino)
        post_db_identity = (post_db_stat.st_dev, post_db_stat.st_ino)
        if post_root_identity != root_identity:
            connection.close()
            fail("revision_store_root_substituted")
        if pre_db_identity is not None and post_db_identity != pre_db_identity:
            connection.close()
            fail("revision_store_database_substituted")
        if retained_root_identity is None:
            self._root_identity = root_identity
        return connection

    def _fault(self, point: str) -> None:
        if self._fault_injector is not None:
            self._fault_injector(point)

    def _raw_revision_identity(
        self, revision: TeacherScoreRevision
    ) -> tuple[str, str, str | None]:
        if not isinstance(revision, TeacherScoreRevision):
            fail("revision_store_revision_type_invalid")
        record = revision.to_dict()
        try:
            revision_id = record["revisionId"]
            revision_sha256 = record["revisionSha256"]
            previous_audit = record["previousAuditEventSha256"]
        except (KeyError, TypeError):
            fail("revision_store_revision_schema_invalid")
        if not isinstance(revision_id, str) or not isinstance(revision_sha256, str):
            fail("revision_store_revision_identity_invalid")
        return revision_id, revision_sha256, previous_audit

    def _validate_loaded_record(
        self,
        scope: RevisionScope,
        record: dict[str, Any],
        *,
        expected_parent_revision_id: str | None,
        expected_parent_revision_sha256: str | None,
        expected_previous_audit_event_sha256: str | None,
    ) -> dict[str, Any]:
        validated, _ = validate_revision_for_store(
            scope,
            TeacherScoreRevision(record),
            expected_parent_revision_id=expected_parent_revision_id,
            expected_parent_revision_sha256=expected_parent_revision_sha256,
            expected_previous_audit_event_sha256=expected_previous_audit_event_sha256,
        )
        return validated

    def append_revision(
        self,
        scope: RevisionScope,
        revision: TeacherScoreRevision,
        *,
        expected_parent_revision_id: str | None,
        expected_parent_revision_sha256: str | None,
    ) -> AppendRevisionResult:
        if not isinstance(scope, RevisionScope):
            fail("revision_store_scope_type_invalid")
        expected_parent_revision_id, expected_parent_revision_sha256 = require_parent_pair(
            expected_parent_revision_id,
            expected_parent_revision_sha256,
            "revision_store_expected_parent_invalid",
        )
        raw_revision_id, raw_revision_sha256, raw_previous_audit = self._raw_revision_identity(
            revision
        )

        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure_scope(connection, scope)
            head = self._read_head(connection, scope)

            # An exact replay is idempotent only while the same revision remains
            # the current head. Replaying an older historical revision must not
            # rewind or otherwise regain mutation authority.
            if (
                head is not None
                and head.revision_id == raw_revision_id
                and head.revision_sha256 == raw_revision_sha256
            ):
                record, record_json = validate_revision_for_store(
                    scope,
                    revision,
                    expected_parent_revision_id=expected_parent_revision_id,
                    expected_parent_revision_sha256=expected_parent_revision_sha256,
                    expected_previous_audit_event_sha256=raw_previous_audit,
                )
                persisted = self._load_record(connection, scope, raw_revision_sha256)
                from ._revision_store_common import canonical_json

                if not hmac.compare_digest(canonical_json(persisted), record_json):
                    fail("revision_store_replay_conflict")
                connection.commit()
                return AppendRevisionResult(
                    applied=False,
                    idempotent_replay=True,
                    head=head,
                )

            current_parent_id = head.revision_id if head is not None else None
            current_parent_sha = head.revision_sha256 if head is not None else None
            if (
                current_parent_id != expected_parent_revision_id
                or current_parent_sha != expected_parent_revision_sha256
            ):
                fail("revision_store_stale_parent")

            expected_previous_audit = head.audit_event_sha256 if head is not None else None
            record, record_json = validate_revision_for_store(
                scope,
                revision,
                expected_parent_revision_id=expected_parent_revision_id,
                expected_parent_revision_sha256=expected_parent_revision_sha256,
                expected_previous_audit_event_sha256=expected_previous_audit,
            )
            sequence = 1 if head is None else head.sequence + 1
            record_hmac = self._record_hmac(
                scope,
                sequence=sequence,
                revision_id=record["revisionId"],
                revision_sha256=record["revisionSha256"],
                record_json=record_json,
            )
            try:
                connection.execute(
                    "INSERT INTO revision_records("
                    "scope_id, sequence, revision_id, revision_sha256, "
                    "parent_revision_id, parent_revision_sha256, audit_event_sha256, "
                    "record_json, record_hmac) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        scope.scope_id,
                        sequence,
                        record["revisionId"],
                        record["revisionSha256"],
                        record["parentRevisionId"],
                        record["parentRevisionSha256"],
                        record["auditEventSha256"],
                        record_json,
                        record_hmac,
                    ),
                )
            except sqlite3.IntegrityError:
                fail("revision_store_append_conflict")

            self._fault("after_record_insert_before_head")
            head_body = self._head_body(
                scope,
                revision_id=record["revisionId"],
                revision_sha256=record["revisionSha256"],
                audit_event_sha256=record["auditEventSha256"],
                sequence=sequence,
            )
            head_hmac = hmac_hex(self._key, HEAD_PURPOSE, head_body)

            if head is None:
                try:
                    connection.execute(
                        "INSERT INTO revision_heads("
                        "scope_id, revision_id, revision_sha256, audit_event_sha256, sequence, head_hmac"
                        ") VALUES(?, ?, ?, ?, ?, ?)",
                        (
                            scope.scope_id,
                            record["revisionId"],
                            record["revisionSha256"],
                            record["auditEventSha256"],
                            sequence,
                            head_hmac,
                        ),
                    )
                except sqlite3.IntegrityError:
                    fail("revision_store_stale_parent")
            else:
                cursor = connection.execute(
                    "UPDATE revision_heads SET revision_id=?, revision_sha256=?, "
                    "audit_event_sha256=?, sequence=?, head_hmac=? "
                    "WHERE scope_id=? AND revision_id=? AND revision_sha256=? "
                    "AND sequence=?",
                    (
                        record["revisionId"],
                        record["revisionSha256"],
                        record["auditEventSha256"],
                        sequence,
                        head_hmac,
                        scope.scope_id,
                        head.revision_id,
                        head.revision_sha256,
                        head.sequence,
                    ),
                )
                if cursor.rowcount != 1:
                    fail("revision_store_stale_parent")

            self._fault("after_head_update_before_commit")
            connection.commit()
            return AppendRevisionResult(
                applied=True,
                idempotent_replay=False,
                head=DurableRevisionHead(
                    record["revisionId"],
                    record["revisionSha256"],
                    record["auditEventSha256"],
                    sequence,
                ),
            )
        except DurableRevisionStoreError:
            connection.rollback()
            raise
        except sqlite3.Error:
            connection.rollback()
            fail("revision_store_database_invalid")
        except BaseException:
            # Fault-injection tests intentionally raise non-store exceptions here.
            # SQLite rollback is still mandatory before propagating them.
            connection.rollback()
            raise
        finally:
            connection.close()

    def load_head(self, scope: RevisionScope) -> DurableRevisionHead | None:
        history = self.load_history(scope)
        if not history:
            return None
        last = history[-1]
        return DurableRevisionHead(
            last["revisionId"],
            last["revisionSha256"],
            last["auditEventSha256"],
            len(history),
        )

    def load_revision(
        self, scope: RevisionScope, revision_sha256: str
    ) -> dict[str, Any]:
        if not isinstance(scope, RevisionScope):
            fail("revision_store_scope_type_invalid")
        connection = self._connect()
        try:
            if not self._existing_scope(connection, scope):
                fail("revision_store_record_missing")
            record = self._load_record(connection, scope, revision_sha256)
            return self._validate_loaded_record(
                scope,
                record,
                expected_parent_revision_id=record.get("parentRevisionId"),
                expected_parent_revision_sha256=record.get("parentRevisionSha256"),
                expected_previous_audit_event_sha256=record.get("previousAuditEventSha256"),
            )
        except sqlite3.Error:
            fail("revision_store_database_invalid")
        finally:
            connection.close()

    def load_history(self, scope: RevisionScope) -> tuple[dict[str, Any], ...]:
        if not isinstance(scope, RevisionScope):
            fail("revision_store_scope_type_invalid")
        connection = self._connect()
        try:
            if not self._existing_scope(connection, scope):
                return ()
            rows = connection.execute(
                "SELECT sequence, revision_id, revision_sha256, record_json, record_hmac "
                "FROM revision_records WHERE scope_id=? ORDER BY sequence ASC",
                (scope.scope_id,),
            ).fetchall()
            head = self._read_head(connection, scope)
            if not rows:
                if head is not None:
                    fail("revision_store_history_head_mismatch")
                return ()
            if head is None:
                fail("revision_store_history_head_mismatch")

            records: list[dict[str, Any]] = []
            previous_id: str | None = None
            previous_sha: str | None = None
            previous_audit: str | None = None
            for expected_sequence, row in enumerate(rows, start=1):
                if row[0] != expected_sequence:
                    fail("revision_store_history_sequence_mismatch")
                record = self._verify_record_row(scope, row)
                record = self._validate_loaded_record(
                    scope,
                    record,
                    expected_parent_revision_id=previous_id,
                    expected_parent_revision_sha256=previous_sha,
                    expected_previous_audit_event_sha256=previous_audit,
                )
                records.append(record)
                previous_id = record["revisionId"]
                previous_sha = record["revisionSha256"]
                previous_audit = record["auditEventSha256"]

            if (
                head.sequence != len(records)
                or head.revision_id != previous_id
                or head.revision_sha256 != previous_sha
                or head.audit_event_sha256 != previous_audit
            ):
                fail("revision_store_history_head_mismatch")
            return tuple(records)
        except sqlite3.Error:
            fail("revision_store_database_invalid")
        finally:
            connection.close()


__all__ = [
    "AppendRevisionResult",
    "DurableRevisionHead",
    "DurableRevisionStore",
    "DurableRevisionStoreError",
    "RevisionScope",
]
