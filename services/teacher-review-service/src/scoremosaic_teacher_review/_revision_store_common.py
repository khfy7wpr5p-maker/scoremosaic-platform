from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import hmac
import json
import re
from typing import Any, Mapping

STORE_SCHEMA_VERSION = "scoremosaic-teacher-revision-store-v1"
SCOPE_PURPOSE = b"scoremosaic/teacher-review/revision-store/scope/v1\x00"
RECORD_PURPOSE = b"scoremosaic/teacher-review/revision-store/record/v1\x00"
HEAD_PURPOSE = b"scoremosaic/teacher-review/revision-store/head/v1\x00"

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")
_JOB_RE = re.compile(r"^job_[A-Za-z0-9_-]{8,80}$")
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_REVISION_RE = re.compile(r"^rev_[0-9a-f]{32}$")
_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class DurableRevisionStoreError(ValueError):
    """Fail-closed durable Teacher Review store error with a stable category."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


def fail(category: str) -> None:
    raise DurableRevisionStoreError(category)


def canonical_json(value: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError):
        fail("revision_store_non_canonical_value")


def require_id(value: Any, category: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 200
        or _ID_RE.fullmatch(value) is None
    ):
        fail(category)
    return value


def require_job(value: Any, category: str) -> str:
    if not isinstance(value, str) or _JOB_RE.fullmatch(value) is None:
        fail(category)
    return value


def require_hash(value: Any, category: str) -> str:
    if not isinstance(value, str) or _HASH_RE.fullmatch(value) is None:
        fail(category)
    return value


def require_nullable_hash(value: Any, category: str) -> str | None:
    if value is None:
        return None
    return require_hash(value, category)


def require_nullable_revision_id(value: Any, category: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or _REVISION_RE.fullmatch(value) is None:
        fail(category)
    return value


def require_parent_pair(
    revision_id: Any,
    revision_sha256: Any,
    category: str,
) -> tuple[str | None, str | None]:
    normalized_id = require_nullable_revision_id(revision_id, category)
    normalized_sha = require_nullable_hash(revision_sha256, category)
    if (normalized_id is None) != (normalized_sha is None):
        fail(category)
    return normalized_id, normalized_sha


def require_timestamp(value: Any, category: str) -> str:
    if not isinstance(value, str) or _TIMESTAMP_RE.fullmatch(value) is None:
        fail(category)
    return value


def hmac_hex(key: bytes, purpose: bytes, body: bytes) -> str:
    return hmac.new(key, purpose + body, sha256).hexdigest()


@dataclass(frozen=True)
class RevisionScope:
    tenant_id: str
    job_id: str
    review_report_id: str
    review_report_sha256: str
    base_canonical_sha256: str

    def __post_init__(self) -> None:
        require_id(self.tenant_id, "revision_store_tenant_invalid")
        require_job(self.job_id, "revision_store_job_invalid")
        require_id(self.review_report_id, "revision_store_report_invalid")
        require_hash(self.review_report_sha256, "revision_store_report_hash_invalid")
        require_hash(self.base_canonical_sha256, "revision_store_canonical_hash_invalid")

    @classmethod
    def create(cls, **kwargs: str) -> "RevisionScope":
        return cls(**kwargs)

    def body(self) -> dict[str, str]:
        return {
            "tenantId": self.tenant_id,
            "jobId": self.job_id,
            "reviewReportId": self.review_report_id,
            "reviewReportSha256": self.review_report_sha256,
            "baseCanonicalSha256": self.base_canonical_sha256,
        }

    @property
    def scope_id(self) -> str:
        return sha256(canonical_json(self.body())).hexdigest()


@dataclass(frozen=True)
class DurableRevisionHead:
    revision_id: str
    revision_sha256: str
    audit_event_sha256: str
    sequence: int


@dataclass(frozen=True)
class AppendRevisionResult:
    applied: bool
    idempotent_replay: bool
    head: DurableRevisionHead
