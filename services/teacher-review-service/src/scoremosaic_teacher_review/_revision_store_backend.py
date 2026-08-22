from __future__ import annotations

from hashlib import sha256
import hmac
import json
import os
from pathlib import Path
import sqlite3
import stat
from typing import Any

from ._revision_store_common import (
    DurableRevisionHead,
    DurableRevisionStoreError,
    HEAD_PURPOSE,
    RECORD_PURPOSE,
    RevisionScope,
    SCOPE_PURPOSE,
    STORE_SCHEMA_VERSION,
    canonical_json,
    fail,
    hmac_hex,
    require_hash,
    require_nullable_revision_id,
)


class SqliteRevisionBackend:
    def __init__(self, root: Path, signing_key: bytes) -> None:
        if not isinstance(root, Path) or not root.is_absolute():
            fail("revision_store_root_invalid")
        if not isinstance(signing_key, bytes) or len(signing_key) < 32:
            fail("revision_store_key_invalid")
        self._root = root
        self._key = bytes(signing_key)
        self._db_path = root / "teacher-review-revisions.sqlite3"
        self._initialize()

    def _initialize(self) -> None:
        try:
            self._root.mkdir(parents=True, mode=0o700, exist_ok=True)
            root_stat = self._root.lstat()
            os.chmod(self._root, 0o700)
        except OSError:
            fail("revision_store_root_invalid")
        if not stat.S_ISDIR(root_stat.st_mode) or stat.S_ISLNK(root_stat.st_mode):
            fail("revision_store_root_invalid")
        try:
            db_stat = self._db_path.lstat()
        except FileNotFoundError:
            db_stat = None
        except OSError:
            fail("revision_store_database_invalid")
        if db_stat is not None and (
            stat.S_ISLNK(db_stat.st_mode) or not stat.S_ISREG(db_stat.st_mode)
        ):
            fail("revision_store_database_invalid")

        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS store_meta ("
                "singleton INTEGER PRIMARY KEY CHECK(singleton=1), schema_version TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS revision_scopes ("
                "scope_id TEXT PRIMARY KEY, scope_json BLOB NOT NULL, scope_hmac TEXT NOT NULL)"
            )
            connection.execute("""
                CREATE TABLE IF NOT EXISTS revision_records (
                    scope_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    revision_id TEXT NOT NULL,
                    revision_sha256 TEXT NOT NULL,
                    parent_revision_id TEXT,
                    parent_revision_sha256 TEXT,
                    audit_event_sha256 TEXT NOT NULL,
                    record_json BLOB NOT NULL,
                    record_hmac TEXT NOT NULL,
                    PRIMARY KEY(scope_id, revision_sha256),
                    UNIQUE(scope_id, revision_id),
                    UNIQUE(scope_id, sequence),
                    FOREIGN KEY(scope_id) REFERENCES revision_scopes(scope_id)
                )
            """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS revision_heads (
                    scope_id TEXT PRIMARY KEY,
                    revision_id TEXT NOT NULL,
                    revision_sha256 TEXT NOT NULL,
                    audit_event_sha256 TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    head_hmac TEXT NOT NULL,
                    FOREIGN KEY(scope_id) REFERENCES revision_scopes(scope_id)
                )
            """)
            row = connection.execute(
                "SELECT schema_version FROM store_meta WHERE singleton=1"
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO store_meta(singleton, schema_version) VALUES(1, ?)",
                    (STORE_SCHEMA_VERSION,),
                )
            elif row[0] != STORE_SCHEMA_VERSION:
                fail("revision_store_schema_mismatch")
            connection.commit()
        except DurableRevisionStoreError:
            connection.rollback()
            raise
        except sqlite3.Error:
            connection.rollback()
            fail("revision_store_database_invalid")
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        try:
            connection = sqlite3.connect(
                self._db_path,
                timeout=10.0,
                isolation_level=None,
                check_same_thread=False,
            )
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=10000")
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA trusted_schema=OFF")
            return connection
        except sqlite3.Error:
            fail("revision_store_database_invalid")

    def _seal_scope(self, scope: RevisionScope) -> tuple[bytes, str]:
        body = canonical_json(scope.body())
        return body, hmac_hex(self._key, SCOPE_PURPOSE, body)

    def _ensure_scope(self, connection: sqlite3.Connection, scope: RevisionScope) -> None:
        body, signature = self._seal_scope(scope)
        row = connection.execute(
            "SELECT scope_json, scope_hmac FROM revision_scopes WHERE scope_id=?",
            (scope.scope_id,),
        ).fetchone()
        if row is None:
            connection.execute(
                "INSERT INTO revision_scopes(scope_id, scope_json, scope_hmac) VALUES(?, ?, ?)",
                (scope.scope_id, body, signature),
            )
            return
        if (
            not hmac.compare_digest(bytes(row[0]), body)
            or not isinstance(row[1], str)
            or not hmac.compare_digest(row[1], signature)
        ):
            fail("revision_store_scope_tampered")

    def _existing_scope(self, connection: sqlite3.Connection, scope: RevisionScope) -> bool:
        body, signature = self._seal_scope(scope)
        row = connection.execute(
            "SELECT scope_json, scope_hmac FROM revision_scopes WHERE scope_id=?",
            (scope.scope_id,),
        ).fetchone()
        if row is None:
            return False
        if (
            not hmac.compare_digest(bytes(row[0]), body)
            or not isinstance(row[1], str)
            or not hmac.compare_digest(row[1], signature)
        ):
            fail("revision_store_scope_tampered")
        return True

    def _head_body(
        self,
        scope: RevisionScope,
        *,
        revision_id: str,
        revision_sha256: str,
        audit_event_sha256: str,
        sequence: int,
    ) -> bytes:
        return canonical_json({
            "schemaVersion": STORE_SCHEMA_VERSION,
            "scopeId": scope.scope_id,
            "revisionId": revision_id,
            "revisionSha256": revision_sha256,
            "auditEventSha256": audit_event_sha256,
            "sequence": sequence,
        })

    def _read_head(
        self, connection: sqlite3.Connection, scope: RevisionScope
    ) -> DurableRevisionHead | None:
        row = connection.execute(
            "SELECT revision_id, revision_sha256, audit_event_sha256, sequence, head_hmac "
            "FROM revision_heads WHERE scope_id=?",
            (scope.scope_id,),
        ).fetchone()
        if row is None:
            return None
        revision_id = require_nullable_revision_id(row[0], "revision_store_head_invalid")
        revision_sha256 = require_hash(row[1], "revision_store_head_invalid")
        audit_sha = require_hash(row[2], "revision_store_head_invalid")
        sequence = row[3]
        if revision_id is None or isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
            fail("revision_store_head_invalid")
        expected_hmac = hmac_hex(
            self._key,
            HEAD_PURPOSE,
            self._head_body(
                scope,
                revision_id=revision_id,
                revision_sha256=revision_sha256,
                audit_event_sha256=audit_sha,
                sequence=sequence,
            ),
        )
        if not isinstance(row[4], str) or not hmac.compare_digest(row[4], expected_hmac):
            fail("revision_store_head_tampered")
        return DurableRevisionHead(revision_id, revision_sha256, audit_sha, sequence)

    def _record_hmac(
        self,
        scope: RevisionScope,
        *,
        sequence: int,
        revision_id: str,
        revision_sha256: str,
        record_json: bytes,
    ) -> str:
        return hmac_hex(
            self._key,
            RECORD_PURPOSE,
            canonical_json({
                "schemaVersion": STORE_SCHEMA_VERSION,
                "scopeId": scope.scope_id,
                "sequence": sequence,
                "revisionId": revision_id,
                "revisionSha256": revision_sha256,
                "recordSha256": sha256(record_json).hexdigest(),
            }),
        )

    def _verify_record_row(self, scope: RevisionScope, row: tuple[Any, ...]) -> dict[str, Any]:
        sequence, revision_id, revision_sha256, record_json, record_hmac = row
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
            fail("revision_store_record_invalid")
        record_json = bytes(record_json)
        expected = self._record_hmac(
            scope,
            sequence=sequence,
            revision_id=revision_id,
            revision_sha256=revision_sha256,
            record_json=record_json,
        )
        if not isinstance(record_hmac, str) or not hmac.compare_digest(record_hmac, expected):
            fail("revision_store_record_tampered")
        try:
            decoded = json.loads(record_json.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            fail("revision_store_record_invalid")
        if (
            not isinstance(decoded, dict)
            or decoded.get("revisionId") != revision_id
            or decoded.get("revisionSha256") != revision_sha256
            or canonical_json(decoded) != record_json
        ):
            fail("revision_store_record_tampered")
        return decoded

    def _load_record(
        self, connection: sqlite3.Connection, scope: RevisionScope, revision_sha256: str
    ) -> dict[str, Any]:
        revision_sha256 = require_hash(
            revision_sha256, "revision_store_revision_identity_invalid"
        )
        row = connection.execute(
            "SELECT sequence, revision_id, revision_sha256, record_json, record_hmac "
            "FROM revision_records WHERE scope_id=? AND revision_sha256=?",
            (scope.scope_id, revision_sha256),
        ).fetchone()
        if row is None:
            fail("revision_store_record_missing")
        return self._verify_record_row(scope, row)
