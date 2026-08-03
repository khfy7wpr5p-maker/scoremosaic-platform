"""Immutable job and engine-run records for future orchestration."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import Iterable

ENGINE_NAMES = ("audiveris", "homr", "clarity")
_JOB_ID_PATTERN = re.compile(r"^job_[A-Za-z0-9_-]{8,80}$")


class ModelError(ValueError):
    """Raised when a future gateway job plan is invalid."""


@dataclass(frozen=True, slots=True)
class EngineRunRecord:
    run_id: str
    engine: str
    status: str
    candidate_key: str


@dataclass(frozen=True, slots=True)
class GatewayJobRecord:
    job_id: str
    status: str
    requested_engines: tuple[str, ...]
    engine_runs: tuple[EngineRunRecord, ...]


def _run_suffix(job_id: str, engine: str) -> str:
    digest = hashlib.sha256(f"{job_id}:{engine}".encode("utf-8")).hexdigest()
    return digest[:24]


def build_job_record(
    job_id: str,
    requested_engines: Iterable[str] = ENGINE_NAMES,
) -> GatewayJobRecord:
    """Build an in-memory plan only; this does not queue or execute a job."""

    if not _JOB_ID_PATTERN.fullmatch(job_id):
        raise ModelError("job_id does not match the OMR job contract")

    engines = tuple(requested_engines)
    if not engines:
        raise ModelError("at least one engine is required")
    if len(set(engines)) != len(engines):
        raise ModelError("requested engines must be unique")
    unsupported = sorted(set(engines) - set(ENGINE_NAMES))
    if unsupported:
        raise ModelError(f"unsupported engines: {', '.join(unsupported)}")

    runs = tuple(
        EngineRunRecord(
            run_id=f"run_{_run_suffix(job_id, engine)}",
            engine=engine,
            status="queued",
            candidate_key=f"candidates/{job_id}/{engine}",
        )
        for engine in engines
    )

    return GatewayJobRecord(
        job_id=job_id,
        status="queued",
        requested_engines=engines,
        engine_runs=runs,
    )
