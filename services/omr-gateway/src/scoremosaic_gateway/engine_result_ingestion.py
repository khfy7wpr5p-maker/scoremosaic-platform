"""Stage 6 authenticated, bounded, deterministic engine-result ingestion.

This module starts after a result transport has delivered exact bytes and an
existing authenticated ``DispatchResultIdentity``. Engine output is evidence,
never authoritative score state. Persistence uses server-derived paths only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from hmac import compare_digest, new as hmac_new
import json
import re
import struct
from typing import Any, Callable, Mapping
import xml.etree.ElementTree as ET

from .artifact_lifecycle import (
    ArtifactLifecycleError,
    CandidateArtifactLifecycle,
    build_artifact_lifecycle,
    transition_artifact,
    transition_candidate,
)
from .dispatch_identity import (
    DispatchIdentityBinding,
    DispatchIdentityError,
    DispatchResultIdentity,
    build_dispatch_identity,
    require_dispatch_result_identity,
)
from .minimum_staging_vertical_slice import (
    MinimumStagingVerticalSliceError,
    StagingUploadProvider,
    _MAX_STATE_RECORD_BYTES,
    _decode_record,
)
from .orchestration import (
    ENGINE_NAMES,
    OrchestrationContractError,
    verify_orchestration_plan,
)
from .service_auth import EngineCredential

ENGINE_RESULT_FRAME_VERSION = "scoremosaic-engine-result-frame-v1"
ENGINE_RESULT_INGESTION_VERSION = "scoremosaic-engine-result-ingestion-v1"
CANDIDATE_PERSISTENCE_VERSION = "scoremosaic-candidate-persistence-v1"
PARTIAL_SUCCESS_VERSION = "scoremosaic-engine-partial-success-v1"

_FRAME_MAGIC = b"SMRES6V1"
_FRAME_HEADER = struct.Struct(">8sQQQ")
MAX_RAW_ENGINE_RESULT_BYTES = 64 * 1024 * 1024
MAX_MUSICXML_BYTES = 64 * 1024 * 1024
MAX_DIAGNOSTIC_BYTES = 64 * 1024
MAX_FRAME_BYTES = (
    _FRAME_HEADER.size
    + MAX_RAW_ENGINE_RESULT_BYTES
    + MAX_MUSICXML_BYTES
    + MAX_DIAGNOSTIC_BYTES
)
MAX_XML_ELEMENTS = 250_000
MAX_XML_DEPTH = 256
MAX_XML_ATTRIBUTE_COUNT = 64
MAX_XML_ATTRIBUTE_VALUE_LENGTH = 4096
MAX_XML_TEXT_LENGTH = 1_000_000
MAX_DIAGNOSTIC_DEPTH = 8
MAX_DIAGNOSTIC_COLLECTION_ITEMS = 1024
MAX_DIAGNOSTIC_STRING_LENGTH = 4096
MAX_DIAGNOSTIC_TOTAL_NODES = 4096

_PERSISTENCE_MAC_DOMAIN = b"scoremosaic-candidate-persistence-v1"
_PERSISTENCE_MAC_FIELD = "integrityMac"
_SHA_RE = re.compile(r"[0-9a-f]{64}\Z")
_JOB_RE = re.compile(r"job_[A-Za-z0-9_-]{8,80}\Z")
_RUN_RE = re.compile(r"run_[0-9a-f]{24}\Z")
_PLAN_RE = re.compile(r"plan_[0-9a-f]{24}\Z")
_ARTIFACT_RE = re.compile(r"artifact_[0-9a-f]{24}\Z")
_CANDIDATE_RE = re.compile(r"candidate_[0-9a-f]{24}\Z")
_SAFE_VERSION_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+:-]{0,127}\Z")
_FORBIDDEN_XML_MARKERS = (b"<!DOCTYPE", b"<!ENTITY", b"<?xml-stylesheet")
_ALLOWED_FAILURE_REASONS = {
    "engine_crash",
    "engine_timeout",
    "engine_nonzero_exit",
    "engine_result_missing",
    "engine_result_malformed",
    "engine_result_oversized",
    "engine_result_invalid_schema",
    "engine_unavailable",
}
_MEDIA_BY_KIND = {
    "raw_engine_result": "application/octet-stream",
    "musicxml": "application/vnd.recordare.musicxml+xml",
    "diagnostic": "application/json",
}
_MAX_BY_KIND = {
    "raw_engine_result": MAX_RAW_ENGINE_RESULT_BYTES,
    "musicxml": MAX_MUSICXML_BYTES,
    "diagnostic": MAX_DIAGNOSTIC_BYTES,
}


class EngineResultIngestionError(ValueError):
    """Stable fail-closed Stage 6 error category."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


def _matches(pattern: re.Pattern[str], value: object) -> bool:
    return type(value) is str and pattern.fullmatch(value) is not None


def _canonical_json(value: Any, category: str) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    except (TypeError, ValueError, OverflowError, UnicodeEncodeError):
        raise EngineResultIngestionError(category) from None


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            raise EngineResultIngestionError("engine_result_diagnostic_invalid")
        result[key] = value
    return result


def _require_bytes(
    value: object,
    *,
    maximum: int,
    category: str,
    empty_allowed: bool = False,
) -> bytes:
    if type(value) is not bytes:
        raise EngineResultIngestionError(category)
    if len(value) > maximum or (not empty_allowed and len(value) == 0):
        raise EngineResultIngestionError(category)
    return value


def _checked_sum(lengths: tuple[int, ...]) -> int:
    total = _FRAME_HEADER.size
    for value in lengths:
        if type(value) is not int or value < 0:
            raise EngineResultIngestionError("engine_result_frame_invalid")
        total += value
        if total > MAX_FRAME_BYTES:
            raise EngineResultIngestionError("engine_result_frame_oversized")
    return total


def build_engine_result_frame(
    *,
    raw_engine_result: bytes,
    musicxml: bytes,
    diagnostic: bytes,
) -> bytes:
    raw = _require_bytes(
        raw_engine_result,
        maximum=MAX_RAW_ENGINE_RESULT_BYTES,
        category="engine_result_raw_invalid",
    )
    xml = _require_bytes(
        musicxml,
        maximum=MAX_MUSICXML_BYTES,
        category="engine_result_musicxml_invalid",
    )
    diag = _require_bytes(
        diagnostic,
        maximum=MAX_DIAGNOSTIC_BYTES,
        category="engine_result_diagnostic_invalid",
    )
    expected = _checked_sum((len(raw), len(xml), len(diag)))
    frame = b"".join(
        (
            _FRAME_HEADER.pack(_FRAME_MAGIC, len(raw), len(xml), len(diag)),
            raw,
            xml,
            diag,
        )
    )
    if len(frame) != expected:
        raise EngineResultIngestionError("engine_result_frame_invalid")
    return frame


@dataclass(frozen=True, slots=True, repr=False)
class ParsedEngineResultFrame:
    raw_engine_result: bytes = field(repr=False)
    musicxml: bytes = field(repr=False)
    diagnostic: bytes = field(repr=False)

    def __post_init__(self) -> None:
        _require_bytes(
            self.raw_engine_result,
            maximum=MAX_RAW_ENGINE_RESULT_BYTES,
            category="engine_result_frame_invalid",
        )
        _require_bytes(
            self.musicxml,
            maximum=MAX_MUSICXML_BYTES,
            category="engine_result_frame_invalid",
        )
        _require_bytes(
            self.diagnostic,
            maximum=MAX_DIAGNOSTIC_BYTES,
            category="engine_result_frame_invalid",
        )

    def __repr__(self) -> str:
        return (
            "ParsedEngineResultFrame("
            f"rawBytes={len(self.raw_engine_result)!r}, "
            f"musicxmlBytes={len(self.musicxml)!r}, "
            f"diagnosticBytes={len(self.diagnostic)!r}, payloads=<redacted>)"
        )


def parse_engine_result_frame(payload: bytes) -> ParsedEngineResultFrame:
    body = _require_bytes(
        payload,
        maximum=MAX_FRAME_BYTES,
        category="engine_result_frame_invalid",
    )
    if len(body) < _FRAME_HEADER.size:
        raise EngineResultIngestionError("engine_result_frame_truncated")
    try:
        magic, raw_len, xml_len, diag_len = _FRAME_HEADER.unpack_from(body, 0)
    except struct.error:
        raise EngineResultIngestionError("engine_result_frame_invalid") from None
    if magic != _FRAME_MAGIC:
        raise EngineResultIngestionError("engine_result_frame_version_invalid")
    if raw_len > MAX_RAW_ENGINE_RESULT_BYTES:
        raise EngineResultIngestionError("engine_result_raw_oversized")
    if xml_len > MAX_MUSICXML_BYTES:
        raise EngineResultIngestionError("engine_result_musicxml_oversized")
    if diag_len > MAX_DIAGNOSTIC_BYTES:
        raise EngineResultIngestionError("engine_result_diagnostic_oversized")
    expected = _checked_sum((raw_len, xml_len, diag_len))
    if expected != len(body):
        raise EngineResultIngestionError(
            "engine_result_frame_truncated"
            if expected > len(body)
            else "engine_result_frame_trailing_data"
        )
    offset = _FRAME_HEADER.size
    raw_end = offset + raw_len
    xml_end = raw_end + xml_len
    return ParsedEngineResultFrame(
        raw_engine_result=body[offset:raw_end],
        musicxml=body[raw_end:xml_end],
        diagnostic=body[xml_end:],
    )


def _xml_local_name(tag: str) -> str:
    if type(tag) is not str:
        raise EngineResultIngestionError("engine_result_musicxml_invalid")
    return tag.rsplit("}", 1)[-1]


def _reject_forbidden_xml_constructs(body: bytes) -> None:
    """Scan the complete bounded document without allocating one full lowercase copy."""

    overlap = max(len(marker) for marker in _FORBIDDEN_XML_MARKERS) - 1
    carry = b""
    view = memoryview(body)
    for start in range(0, len(view), 64 * 1024):
        chunk = carry + view[start : start + 64 * 1024].tobytes()
        if any(marker in chunk for marker in _FORBIDDEN_XML_MARKERS):
            raise EngineResultIngestionError("engine_result_musicxml_unsafe_xml")
        carry = chunk[-overlap:] if overlap else b""


def _validate_musicxml_stream(document: bytes) -> str:
    body = _require_bytes(
        document,
        maximum=MAX_MUSICXML_BYTES,
        category="engine_result_musicxml_invalid",
    )
    _reject_forbidden_xml_constructs(body)
    parser = ET.XMLPullParser(events=("start", "end"))
    depth = 0
    element_count = 0
    root_name: str | None = None
    try:
        view = memoryview(body)
        for start in range(0, len(view), 64 * 1024):
            parser.feed(view[start : start + 64 * 1024].tobytes())
            for event, element in parser.read_events():
                if event == "start":
                    depth += 1
                    element_count += 1
                    if root_name is None:
                        root_name = _xml_local_name(element.tag)
                    if depth > MAX_XML_DEPTH or element_count > MAX_XML_ELEMENTS:
                        raise EngineResultIngestionError(
                            "engine_result_musicxml_complexity_exceeded"
                        )
                    if len(element.attrib) > MAX_XML_ATTRIBUTE_COUNT:
                        raise EngineResultIngestionError(
                            "engine_result_musicxml_complexity_exceeded"
                        )
                    for key, value in element.attrib.items():
                        if (
                            type(key) is not str
                            or type(value) is not str
                            or len(value) > MAX_XML_ATTRIBUTE_VALUE_LENGTH
                        ):
                            raise EngineResultIngestionError(
                                "engine_result_musicxml_complexity_exceeded"
                            )
                else:
                    if element.text is not None and len(element.text) > MAX_XML_TEXT_LENGTH:
                        raise EngineResultIngestionError(
                            "engine_result_musicxml_complexity_exceeded"
                        )
                    if element.tail is not None and len(element.tail) > MAX_XML_TEXT_LENGTH:
                        raise EngineResultIngestionError(
                            "engine_result_musicxml_complexity_exceeded"
                        )
                    element.clear()
                    depth -= 1
                    if depth < 0:
                        raise EngineResultIngestionError("engine_result_musicxml_invalid")
        parser.close()
    except EngineResultIngestionError:
        raise
    except (ET.ParseError, UnicodeError, ValueError, TypeError, MemoryError):
        raise EngineResultIngestionError("engine_result_musicxml_invalid") from None
    if depth != 0 or root_name not in {"score-partwise", "score-timewise"}:
        raise EngineResultIngestionError("engine_result_musicxml_schema_invalid")
    return root_name


def _validate_diagnostic_node(value: Any, *, depth: int, counter: list[int]) -> None:
    counter[0] += 1
    if counter[0] > MAX_DIAGNOSTIC_TOTAL_NODES or depth > MAX_DIAGNOSTIC_DEPTH:
        raise EngineResultIngestionError("engine_result_diagnostic_complexity_exceeded")
    if value is None or type(value) in {bool, int}:
        return
    if type(value) is float:
        raise EngineResultIngestionError("engine_result_diagnostic_invalid")
    if type(value) is str:
        if len(value) > MAX_DIAGNOSTIC_STRING_LENGTH:
            raise EngineResultIngestionError("engine_result_diagnostic_complexity_exceeded")
        return
    if type(value) is list:
        if len(value) > MAX_DIAGNOSTIC_COLLECTION_ITEMS:
            raise EngineResultIngestionError("engine_result_diagnostic_complexity_exceeded")
        for item in value:
            _validate_diagnostic_node(item, depth=depth + 1, counter=counter)
        return
    if type(value) is dict:
        if len(value) > MAX_DIAGNOSTIC_COLLECTION_ITEMS:
            raise EngineResultIngestionError("engine_result_diagnostic_complexity_exceeded")
        for key, item in value.items():
            if type(key) is not str or len(key) > MAX_DIAGNOSTIC_STRING_LENGTH:
                raise EngineResultIngestionError("engine_result_diagnostic_invalid")
            _validate_diagnostic_node(item, depth=depth + 1, counter=counter)
        return
    raise EngineResultIngestionError("engine_result_diagnostic_invalid")


def _normalize_diagnostic(document: bytes, engine: str) -> tuple[bytes, str | None, str | None]:
    body = _require_bytes(
        document,
        maximum=MAX_DIAGNOSTIC_BYTES,
        category="engine_result_diagnostic_invalid",
    )
    try:
        value = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except EngineResultIngestionError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError, RecursionError):
        raise EngineResultIngestionError("engine_result_diagnostic_invalid") from None
    if type(value) is not dict:
        raise EngineResultIngestionError("engine_result_diagnostic_schema_invalid")
    allowed = {"engine", "status", "engineVersion", "modelVersion", "warnings"}
    if set(value) - allowed or value.get("engine") != engine or value.get("status") != "success":
        raise EngineResultIngestionError("engine_result_diagnostic_schema_invalid")
    for key in ("engineVersion", "modelVersion"):
        item = value.get(key)
        if item is not None and (type(item) is not str or _SAFE_VERSION_RE.fullmatch(item) is None):
            raise EngineResultIngestionError("engine_result_diagnostic_schema_invalid")
    warnings = value.get("warnings", [])
    if type(warnings) is not list or len(warnings) > 64:
        raise EngineResultIngestionError("engine_result_diagnostic_schema_invalid")
    if any(type(item) is not str or len(item) > 256 for item in warnings):
        raise EngineResultIngestionError("engine_result_diagnostic_schema_invalid")
    normalized = {
        "engine": engine,
        "status": "success",
        "engineVersion": value.get("engineVersion"),
        "modelVersion": value.get("modelVersion"),
        "warnings": list(warnings),
    }
    _validate_diagnostic_node(normalized, depth=0, counter=[0])
    encoded = _canonical_json(normalized, "engine_result_diagnostic_invalid")
    if len(encoded) > MAX_DIAGNOSTIC_BYTES:
        raise EngineResultIngestionError("engine_result_diagnostic_oversized")
    return encoded, value.get("engineVersion"), value.get("modelVersion")


@dataclass(frozen=True, slots=True, repr=False)
class NormalizedEngineCandidate:
    version: str
    engine: str
    job_id: str
    run_id: str
    plan_id: str
    plan_sha256: str
    source_artifact_id: str
    source_sha256: str
    candidate_id: str
    candidate_namespace: str
    musicxml_artifact_id: str
    diagnostic_artifact_id: str
    dispatch_identity_sha256: str
    authenticated_result_sha256: str
    raw_engine_result: bytes = field(repr=False)
    musicxml: bytes = field(repr=False)
    diagnostic: bytes = field(repr=False)
    engine_version: str | None = None
    model_version: str | None = None

    def __post_init__(self) -> None:
        if (
            self.version != ENGINE_RESULT_INGESTION_VERSION
            or self.engine not in ENGINE_NAMES
            or not _matches(_JOB_RE, self.job_id)
            or not _matches(_RUN_RE, self.run_id)
            or not _matches(_PLAN_RE, self.plan_id)
            or not _matches(_SHA_RE, self.plan_sha256)
            or not _matches(_ARTIFACT_RE, self.source_artifact_id)
            or not _matches(_SHA_RE, self.source_sha256)
            or not _matches(_CANDIDATE_RE, self.candidate_id)
            or type(self.candidate_namespace) is not str
            or not _matches(_ARTIFACT_RE, self.musicxml_artifact_id)
            or not _matches(_ARTIFACT_RE, self.diagnostic_artifact_id)
            or not _matches(_SHA_RE, self.dispatch_identity_sha256)
            or not _matches(_SHA_RE, self.authenticated_result_sha256)
        ):
            raise EngineResultIngestionError("normalized_candidate_invalid")
        _require_bytes(self.raw_engine_result, maximum=MAX_RAW_ENGINE_RESULT_BYTES, category="normalized_candidate_invalid")
        _require_bytes(self.musicxml, maximum=MAX_MUSICXML_BYTES, category="normalized_candidate_invalid")
        _require_bytes(self.diagnostic, maximum=MAX_DIAGNOSTIC_BYTES, category="normalized_candidate_invalid")

    def __repr__(self) -> str:
        return (
            "NormalizedEngineCandidate("
            f"engine={self.engine!r}, job_id={self.job_id!r}, run_id={self.run_id!r}, "
            f"candidate_id={self.candidate_id!r}, candidate_sha256={self.candidate_sha256!r}, "
            "payloads=<redacted>)"
        )

    @property
    def raw_sha256(self) -> str:
        return sha256(self.raw_engine_result).hexdigest()

    @property
    def musicxml_sha256(self) -> str:
        return sha256(self.musicxml).hexdigest()

    @property
    def diagnostic_sha256(self) -> str:
        return sha256(self.diagnostic).hexdigest()

    @property
    def candidate_sha256(self) -> str:
        return sha256(
            _canonical_json(
                {
                    "version": self.version,
                    "engine": self.engine,
                    "jobId": self.job_id,
                    "runId": self.run_id,
                    "planId": self.plan_id,
                    "planSha256": self.plan_sha256,
                    "sourceArtifactId": self.source_artifact_id,
                    "sourceSha256": self.source_sha256,
                    "candidateId": self.candidate_id,
                    "candidateNamespace": self.candidate_namespace,
                    "musicxmlArtifactId": self.musicxml_artifact_id,
                    "diagnosticArtifactId": self.diagnostic_artifact_id,
                    "dispatchIdentitySha256": self.dispatch_identity_sha256,
                    "authenticatedResultSha256": self.authenticated_result_sha256,
                    "rawSha256": self.raw_sha256,
                    "rawBytes": len(self.raw_engine_result),
                    "musicxmlSha256": self.musicxml_sha256,
                    "musicxmlBytes": len(self.musicxml),
                    "diagnosticSha256": self.diagnostic_sha256,
                    "diagnosticBytes": len(self.diagnostic),
                    "engineVersion": self.engine_version,
                    "modelVersion": self.model_version,
                },
                "normalized_candidate_invalid",
            )
        ).hexdigest()

    def as_safe_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "engine": self.engine,
            "jobId": self.job_id,
            "runId": self.run_id,
            "planId": self.plan_id,
            "planSha256": self.plan_sha256,
            "sourceArtifactId": self.source_artifact_id,
            "sourceSha256": self.source_sha256,
            "candidateId": self.candidate_id,
            "candidateNamespace": self.candidate_namespace,
            "dispatchIdentitySha256": self.dispatch_identity_sha256,
            "authenticatedResultSha256": self.authenticated_result_sha256,
            "candidateSha256": self.candidate_sha256,
            "engineVersion": self.engine_version,
            "modelVersion": self.model_version,
            "artifacts": {
                "raw_engine_result": {"sha256": self.raw_sha256, "sizeBytes": len(self.raw_engine_result)},
                "musicxml": {"artifactId": self.musicxml_artifact_id, "sha256": self.musicxml_sha256, "sizeBytes": len(self.musicxml)},
                "diagnostic": {"artifactId": self.diagnostic_artifact_id, "sha256": self.diagnostic_sha256, "sizeBytes": len(self.diagnostic)},
            },
            "authoritativeScore": False,
            "candidateOnly": True,
        }


@dataclass(frozen=True, slots=True)
class EngineResultAdapter:
    engine: str

    def __post_init__(self) -> None:
        if self.engine not in ENGINE_NAMES:
            raise EngineResultIngestionError("engine_result_adapter_invalid")

    def normalize(
        self,
        *,
        credential: EngineCredential,
        expected_identity: DispatchIdentityBinding,
        result_identity: DispatchResultIdentity,
        result_payload: bytes,
    ) -> NormalizedEngineCandidate:
        if type(expected_identity) is not DispatchIdentityBinding:
            raise EngineResultIngestionError("engine_result_identity_invalid")
        if expected_identity.engine != self.engine:
            raise EngineResultIngestionError("engine_result_cross_engine_reuse")
        body = _require_bytes(result_payload, maximum=MAX_FRAME_BYTES, category="engine_result_payload_invalid")
        try:
            require_dispatch_result_identity(credential, expected_identity, result_identity, body)
        except DispatchIdentityError:
            raise EngineResultIngestionError("engine_result_authentication_failed") from None
        frame = parse_engine_result_frame(body)
        _validate_musicxml_stream(frame.musicxml)
        diagnostic, engine_version, model_version = _normalize_diagnostic(frame.diagnostic, self.engine)
        return NormalizedEngineCandidate(
            version=ENGINE_RESULT_INGESTION_VERSION,
            engine=self.engine,
            job_id=expected_identity.job_id,
            run_id=expected_identity.run_id,
            plan_id=expected_identity.plan_id,
            plan_sha256=expected_identity.plan_sha256,
            source_artifact_id=expected_identity.source_artifact_id,
            source_sha256=expected_identity.source_sha256,
            candidate_id=expected_identity.candidate_id,
            candidate_namespace=expected_identity.candidate_namespace,
            musicxml_artifact_id=expected_identity.musicxml_artifact_id,
            diagnostic_artifact_id=expected_identity.diagnostic_artifact_id,
            dispatch_identity_sha256=expected_identity.identity_sha256,
            authenticated_result_sha256=sha256(body).hexdigest(),
            raw_engine_result=frame.raw_engine_result,
            musicxml=frame.musicxml,
            diagnostic=diagnostic,
            engine_version=engine_version,
            model_version=model_version,
        )


class AudiverisResultAdapter(EngineResultAdapter):
    def __init__(self) -> None:
        super().__init__("audiveris")


class HomrResultAdapter(EngineResultAdapter):
    def __init__(self) -> None:
        super().__init__("homr")


class ClarityResultAdapter(EngineResultAdapter):
    def __init__(self) -> None:
        super().__init__("clarity")


ADAPTERS: Mapping[str, Callable[[], EngineResultAdapter]] = {
    "audiveris": AudiverisResultAdapter,
    "homr": HomrResultAdapter,
    "clarity": ClarityResultAdapter,
}


def ingest_authenticated_engine_result(
    *,
    credential: EngineCredential,
    expected_identity: DispatchIdentityBinding,
    result_identity: DispatchResultIdentity,
    result_payload: bytes,
) -> NormalizedEngineCandidate:
    if type(expected_identity) is not DispatchIdentityBinding:
        raise EngineResultIngestionError("engine_result_identity_invalid")
    factory = ADAPTERS.get(expected_identity.engine)
    if factory is None:
        raise EngineResultIngestionError("engine_result_adapter_invalid")
    return factory().normalize(
        credential=credential,
        expected_identity=expected_identity,
        result_identity=result_identity,
        result_payload=result_payload,
    )


def _provider_key(provider: StagingUploadProvider) -> bytes:
    key = getattr(provider, "_state_integrity_key", None)
    if type(key) is not bytes or len(key) != 32:
        raise EngineResultIngestionError("candidate_persistence_config_invalid")
    return key


def _candidate_record_path(provider: StagingUploadProvider, *, job_id: str, engine: str, candidate_id: str):
    return provider._root / "state" / "candidate_ingestion" / job_id / engine / f"{candidate_id}.json"


def _candidate_artifact_paths(provider: StagingUploadProvider, *, job_id: str, engine: str, candidate_id: str) -> dict[str, Any]:
    root = provider._root / "artifacts" / "candidates" / job_id / engine / candidate_id
    return {
        "raw_engine_result": root / "raw-engine-result.bin",
        "musicxml": root / "candidate.musicxml",
        "diagnostic": root / "diagnostic.json",
    }


def _persistence_mac(provider: StagingUploadProvider, record: dict[str, Any]) -> str:
    if _PERSISTENCE_MAC_FIELD in record:
        raise EngineResultIngestionError("candidate_persistence_state_invalid")
    return hmac_new(
        _provider_key(provider),
        b"\0".join((_PERSISTENCE_MAC_DOMAIN, _canonical_json(record, "candidate_persistence_state_invalid"))),
        sha256,
    ).hexdigest()


def _persist_exact_file(provider: StagingUploadProvider, path, payload: bytes, *, maximum: int) -> str:
    body = _require_bytes(payload, maximum=maximum, category="candidate_persistence_artifact_invalid")
    try:
        if provider._atomic_create(path, body):
            return "written"
        stored = provider._read_file_no_follow(path, max_bytes=maximum, overflow_category="staging_state_corrupt")
    except MinimumStagingVerticalSliceError:
        raise EngineResultIngestionError("candidate_persistence_state_invalid") from None
    if len(stored) != len(body) or not compare_digest(sha256(stored).digest(), sha256(body).digest()) or stored != body:
        raise EngineResultIngestionError("candidate_persistence_conflict")
    return "replay"


def _raw_artifact_id(plan: Mapping[str, Any], candidate_id: str) -> str:
    try:
        lifecycle = build_artifact_lifecycle(plan)
    except ArtifactLifecycleError:
        raise EngineResultIngestionError("candidate_persistence_lifecycle_invalid") from None
    for candidate in lifecycle.candidates:
        if candidate.candidate_id == candidate_id:
            return candidate.artifacts[0].artifact_id
    raise EngineResultIngestionError("candidate_persistence_identity_invalid")


@dataclass(frozen=True, slots=True)
class CandidatePersistenceResult:
    version: str
    engine: str
    job_id: str
    run_id: str
    candidate_id: str
    candidate_sha256: str
    record_sha256: str
    persistence_state: str

    def __post_init__(self) -> None:
        if (
            self.version != CANDIDATE_PERSISTENCE_VERSION
            or self.engine not in ENGINE_NAMES
            or not _matches(_JOB_RE, self.job_id)
            or not _matches(_RUN_RE, self.run_id)
            or not _matches(_CANDIDATE_RE, self.candidate_id)
            or not _matches(_SHA_RE, self.candidate_sha256)
            or not _matches(_SHA_RE, self.record_sha256)
            or self.persistence_state not in {"written", "replay"}
        ):
            raise EngineResultIngestionError("candidate_persistence_result_invalid")

    def as_safe_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "engine": self.engine,
            "jobId": self.job_id,
            "runId": self.run_id,
            "candidateId": self.candidate_id,
            "candidateSha256": self.candidate_sha256,
            "recordSha256": self.record_sha256,
            "persistenceState": self.persistence_state,
            "immutable": True,
            "overwriteAllowed": False,
            "authoritativeScore": False,
        }


def _candidate_record(plan: Mapping[str, Any], candidate: NormalizedEngineCandidate) -> dict[str, Any]:
    expected = build_dispatch_identity(plan, candidate.engine)
    checks = (
        (expected.job_id, candidate.job_id),
        (expected.run_id, candidate.run_id),
        (expected.plan_id, candidate.plan_id),
        (expected.plan_sha256, candidate.plan_sha256),
        (expected.source_artifact_id, candidate.source_artifact_id),
        (expected.source_sha256, candidate.source_sha256),
        (expected.candidate_id, candidate.candidate_id),
        (expected.candidate_namespace, candidate.candidate_namespace),
        (expected.musicxml_artifact_id, candidate.musicxml_artifact_id),
        (expected.diagnostic_artifact_id, candidate.diagnostic_artifact_id),
        (expected.identity_sha256, candidate.dispatch_identity_sha256),
    )
    if any(left != right for left, right in checks):
        raise EngineResultIngestionError("candidate_persistence_identity_invalid")
    return {
        "version": CANDIDATE_PERSISTENCE_VERSION,
        "jobId": candidate.job_id,
        "planId": candidate.plan_id,
        "planSha256": candidate.plan_sha256,
        "engine": candidate.engine,
        "runId": candidate.run_id,
        "dispatchIdentitySha256": candidate.dispatch_identity_sha256,
        "sourceArtifactId": candidate.source_artifact_id,
        "sourceSha256": candidate.source_sha256,
        "candidateId": candidate.candidate_id,
        "candidateNamespace": candidate.candidate_namespace,
        "candidateSha256": candidate.candidate_sha256,
        "authenticatedResultSha256": candidate.authenticated_result_sha256,
        "engineVersion": candidate.engine_version,
        "modelVersion": candidate.model_version,
        "artifacts": [
            {"kind": "raw_engine_result", "artifactId": _raw_artifact_id(plan, candidate.candidate_id), "sha256": candidate.raw_sha256, "sizeBytes": len(candidate.raw_engine_result), "mediaType": _MEDIA_BY_KIND["raw_engine_result"]},
            {"kind": "musicxml", "artifactId": candidate.musicxml_artifact_id, "sha256": candidate.musicxml_sha256, "sizeBytes": len(candidate.musicxml), "mediaType": _MEDIA_BY_KIND["musicxml"]},
            {"kind": "diagnostic", "artifactId": candidate.diagnostic_artifact_id, "sha256": candidate.diagnostic_sha256, "sizeBytes": len(candidate.diagnostic), "mediaType": _MEDIA_BY_KIND["diagnostic"]},
        ],
        "policies": {"immutable": True, "overwriteAllowed": False, "crossEngineWriteAllowed": False, "authoritativeScore": False, "candidateOnly": True},
    }


def _decode_verified_record(provider: StagingUploadProvider, raw: bytes) -> dict[str, Any]:
    sealed = _decode_record(raw)
    if type(sealed) is not dict or _PERSISTENCE_MAC_FIELD not in sealed:
        raise EngineResultIngestionError("candidate_persistence_state_invalid")
    if _canonical_json(sealed, "candidate_persistence_state_invalid") != raw:
        raise EngineResultIngestionError("candidate_persistence_state_invalid")
    observed = sealed.get(_PERSISTENCE_MAC_FIELD)
    record = dict(sealed)
    record.pop(_PERSISTENCE_MAC_FIELD, None)
    if type(observed) is not str or not compare_digest(observed, _persistence_mac(provider, record)):
        raise EngineResultIngestionError("candidate_persistence_state_invalid")
    return record


def _verified_artifact_metadata(record: Mapping[str, Any], identity: DispatchIdentityBinding) -> dict[str, dict[str, Any]]:
    artifacts = record.get("artifacts")
    if type(artifacts) is not list or len(artifacts) != 3:
        raise EngineResultIngestionError("candidate_persistence_state_invalid")
    by_kind: dict[str, dict[str, Any]] = {}
    for item in artifacts:
        if type(item) is not dict or type(item.get("kind")) is not str or item["kind"] in by_kind:
            raise EngineResultIngestionError("candidate_persistence_state_invalid")
        by_kind[item["kind"]] = item
    if set(by_kind) != set(_MEDIA_BY_KIND):
        raise EngineResultIngestionError("candidate_persistence_state_invalid")
    if by_kind["musicxml"].get("artifactId") != identity.musicxml_artifact_id or by_kind["diagnostic"].get("artifactId") != identity.diagnostic_artifact_id:
        raise EngineResultIngestionError("candidate_persistence_state_invalid")
    for kind, item in by_kind.items():
        if (
            not _matches(_ARTIFACT_RE, item.get("artifactId"))
            or not _matches(_SHA_RE, item.get("sha256"))
            or type(item.get("sizeBytes")) is not int
            or not 1 <= item["sizeBytes"] <= _MAX_BY_KIND[kind]
            or item.get("mediaType") != _MEDIA_BY_KIND[kind]
        ):
            raise EngineResultIngestionError("candidate_persistence_state_invalid")
    return by_kind


def _verify_persisted_artifacts(provider: StagingUploadProvider, record: Mapping[str, Any], identity: DispatchIdentityBinding) -> dict[str, bytes]:
    metadata = _verified_artifact_metadata(record, identity)
    paths = _candidate_artifact_paths(provider, job_id=identity.job_id, engine=identity.engine, candidate_id=identity.candidate_id)
    verified: dict[str, bytes] = {}
    for kind in ("raw_engine_result", "musicxml", "diagnostic"):
        item = metadata[kind]
        try:
            body = provider._read_file_no_follow(paths[kind], max_bytes=_MAX_BY_KIND[kind], overflow_category="staging_state_corrupt")
        except MinimumStagingVerticalSliceError:
            raise EngineResultIngestionError("candidate_persistence_artifact_invalid") from None
        if len(body) != item["sizeBytes"] or not compare_digest(sha256(body).hexdigest(), item["sha256"]):
            raise EngineResultIngestionError("candidate_persistence_artifact_invalid")
        verified[kind] = body
    return verified


def persist_normalized_candidate_once(
    *,
    provider: StagingUploadProvider,
    orchestration_plan: Mapping[str, Any],
    candidate: NormalizedEngineCandidate,
) -> CandidatePersistenceResult:
    if type(provider) is not StagingUploadProvider or type(candidate) is not NormalizedEngineCandidate:
        raise EngineResultIngestionError("candidate_persistence_input_invalid")
    try:
        verify_orchestration_plan(orchestration_plan)
        record = _candidate_record(orchestration_plan, candidate)
    except (OrchestrationContractError, DispatchIdentityError, ArtifactLifecycleError, TypeError, ValueError):
        raise EngineResultIngestionError("candidate_persistence_identity_invalid") from None
    paths = _candidate_artifact_paths(provider, job_id=candidate.job_id, engine=candidate.engine, candidate_id=candidate.candidate_id)
    _persist_exact_file(provider, paths["raw_engine_result"], candidate.raw_engine_result, maximum=MAX_RAW_ENGINE_RESULT_BYTES)
    _persist_exact_file(provider, paths["musicxml"], candidate.musicxml, maximum=MAX_MUSICXML_BYTES)
    _persist_exact_file(provider, paths["diagnostic"], candidate.diagnostic, maximum=MAX_DIAGNOSTIC_BYTES)
    sealed = dict(record)
    sealed[_PERSISTENCE_MAC_FIELD] = _persistence_mac(provider, record)
    payload = _canonical_json(sealed, "candidate_persistence_state_invalid")
    if len(payload) > _MAX_STATE_RECORD_BYTES:
        raise EngineResultIngestionError("candidate_persistence_state_invalid")
    path = _candidate_record_path(provider, job_id=candidate.job_id, engine=candidate.engine, candidate_id=candidate.candidate_id)
    try:
        if provider._atomic_create(path, payload):
            state = "written"
        else:
            stored_raw = provider._read_file_no_follow(path, max_bytes=_MAX_STATE_RECORD_BYTES, overflow_category="staging_state_corrupt")
            stored_record = _decode_verified_record(provider, stored_raw)
            if stored_record != record:
                raise EngineResultIngestionError("candidate_persistence_conflict")
            state = "replay"
    except EngineResultIngestionError:
        raise
    except MinimumStagingVerticalSliceError:
        raise EngineResultIngestionError("candidate_persistence_state_invalid") from None
    # Read-after-write/replay verification authenticates both record and actual bytes.
    verified_record = load_persisted_candidate_record(provider=provider, orchestration_plan=orchestration_plan, engine=candidate.engine)
    if verified_record != record:
        raise EngineResultIngestionError("candidate_persistence_state_invalid")
    record_sha = sha256(_canonical_json(record, "candidate_persistence_state_invalid")).hexdigest()
    return CandidatePersistenceResult(
        version=CANDIDATE_PERSISTENCE_VERSION,
        engine=candidate.engine,
        job_id=candidate.job_id,
        run_id=candidate.run_id,
        candidate_id=candidate.candidate_id,
        candidate_sha256=candidate.candidate_sha256,
        record_sha256=record_sha,
        persistence_state=state,
    )


def load_persisted_candidate_record(
    *,
    provider: StagingUploadProvider,
    orchestration_plan: Mapping[str, Any],
    engine: str,
) -> dict[str, Any]:
    if type(provider) is not StagingUploadProvider or engine not in ENGINE_NAMES:
        raise EngineResultIngestionError("candidate_persistence_input_invalid")
    try:
        identity = build_dispatch_identity(orchestration_plan, engine)
    except DispatchIdentityError:
        raise EngineResultIngestionError("candidate_persistence_plan_invalid") from None
    path = _candidate_record_path(provider, job_id=identity.job_id, engine=identity.engine, candidate_id=identity.candidate_id)
    try:
        raw = provider._read_file_no_follow(path, max_bytes=_MAX_STATE_RECORD_BYTES, overflow_category="staging_state_corrupt")
    except MinimumStagingVerticalSliceError:
        raise EngineResultIngestionError("candidate_persistence_missing") from None
    record = _decode_verified_record(provider, raw)
    if (
        record.get("version") != CANDIDATE_PERSISTENCE_VERSION
        or record.get("engine") != engine
        or record.get("jobId") != identity.job_id
        or record.get("runId") != identity.run_id
        or record.get("planId") != identity.plan_id
        or record.get("planSha256") != identity.plan_sha256
        or record.get("sourceArtifactId") != identity.source_artifact_id
        or record.get("sourceSha256") != identity.source_sha256
        or record.get("candidateId") != identity.candidate_id
        or record.get("candidateNamespace") != identity.candidate_namespace
        or record.get("dispatchIdentitySha256") != identity.identity_sha256
        or not _matches(_SHA_RE, record.get("candidateSha256"))
        or not _matches(_SHA_RE, record.get("authenticatedResultSha256"))
    ):
        raise EngineResultIngestionError("candidate_persistence_state_invalid")
    _verify_persisted_artifacts(provider, record, identity)
    return record


def load_persisted_candidate_musicxml(
    *, provider: StagingUploadProvider, orchestration_plan: Mapping[str, Any], engine: str
) -> bytes:
    record = load_persisted_candidate_record(provider=provider, orchestration_plan=orchestration_plan, engine=engine)
    identity = build_dispatch_identity(orchestration_plan, engine)
    return _verify_persisted_artifacts(provider, record, identity)["musicxml"]


@dataclass(frozen=True, slots=True)
class EngineIngestionOutcome:
    engine: str
    candidate_id: str
    status: str
    candidate_sha256: str | None
    reason_code: str | None

    def __post_init__(self) -> None:
        if self.engine not in ENGINE_NAMES or not _matches(_CANDIDATE_RE, self.candidate_id):
            raise EngineResultIngestionError("engine_outcome_invalid")
        if self.status == "success":
            if not _matches(_SHA_RE, self.candidate_sha256) or self.reason_code is not None:
                raise EngineResultIngestionError("engine_outcome_invalid")
        elif self.status == "failed":
            if self.candidate_sha256 is not None or self.reason_code not in _ALLOWED_FAILURE_REASONS:
                raise EngineResultIngestionError("engine_outcome_invalid")
        else:
            raise EngineResultIngestionError("engine_outcome_invalid")

    def as_safe_dict(self) -> dict[str, Any]:
        return {"engine": self.engine, "candidateId": self.candidate_id, "status": self.status, "candidateSha256": self.candidate_sha256, "reasonCode": self.reason_code}


def success_outcome(candidate: NormalizedEngineCandidate) -> EngineIngestionOutcome:
    if type(candidate) is not NormalizedEngineCandidate:
        raise EngineResultIngestionError("engine_outcome_invalid")
    return EngineIngestionOutcome(candidate.engine, candidate.candidate_id, "success", candidate.candidate_sha256, None)


def failure_outcome(*, engine: str, candidate_id: str, reason_code: str) -> EngineIngestionOutcome:
    return EngineIngestionOutcome(engine, candidate_id, "failed", None, reason_code)


@dataclass(frozen=True, slots=True)
class PartialSuccessSummary:
    version: str
    total_engine_count: int
    success_count: int
    failure_count: int
    status: str
    comparison_eligible: bool
    canonical_convergence_eligible: bool
    outcomes: tuple[EngineIngestionOutcome, ...]

    def __post_init__(self) -> None:
        if (
            self.version != PARTIAL_SUCCESS_VERSION
            or type(self.total_engine_count) is not int
            or not 1 <= self.total_engine_count <= len(ENGINE_NAMES)
            or type(self.success_count) is not int
            or type(self.failure_count) is not int
            or self.success_count + self.failure_count != self.total_engine_count
            or self.status != f"{self.success_count}_of_{self.total_engine_count}_success"
            or self.comparison_eligible is not (self.success_count >= 2)
            or self.canonical_convergence_eligible is not (self.success_count >= 2)
            or type(self.outcomes) is not tuple
            or len(self.outcomes) != self.total_engine_count
        ):
            raise EngineResultIngestionError("partial_success_summary_invalid")

    def as_safe_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "totalEngineCount": self.total_engine_count,
            "successCount": self.success_count,
            "failureCount": self.failure_count,
            "status": self.status,
            "comparisonEligible": self.comparison_eligible,
            "canonicalConvergenceEligible": self.canonical_convergence_eligible,
            "minimumSuccessfulCandidates": 2,
            "outcomes": [item.as_safe_dict() for item in self.outcomes],
            "engineFailureInvalidatesOtherCandidates": False,
        }


def summarize_partial_success(orchestration_plan: Mapping[str, Any], outcomes: tuple[EngineIngestionOutcome, ...]) -> PartialSuccessSummary:
    try:
        verify_orchestration_plan(orchestration_plan)
    except (OrchestrationContractError, TypeError, ValueError):
        raise EngineResultIngestionError("partial_success_plan_invalid") from None
    requested = tuple(orchestration_plan["requestedEngines"])
    if type(outcomes) is not tuple or len(outcomes) != len(requested):
        raise EngineResultIngestionError("partial_success_outcomes_invalid")
    by_engine: dict[str, EngineIngestionOutcome] = {}
    for outcome in outcomes:
        if type(outcome) is not EngineIngestionOutcome or outcome.engine in by_engine:
            raise EngineResultIngestionError("partial_success_outcomes_invalid")
        try:
            expected = build_dispatch_identity(orchestration_plan, outcome.engine)
        except DispatchIdentityError:
            raise EngineResultIngestionError("partial_success_outcomes_invalid") from None
        if outcome.candidate_id != expected.candidate_id:
            raise EngineResultIngestionError("partial_success_outcomes_invalid")
        by_engine[outcome.engine] = outcome
    if set(by_engine) != set(requested):
        raise EngineResultIngestionError("partial_success_outcomes_invalid")
    ordered = tuple(by_engine[engine] for engine in requested)
    success_count = sum(item.status == "success" for item in ordered)
    return PartialSuccessSummary(
        PARTIAL_SUCCESS_VERSION,
        len(ordered),
        success_count,
        len(ordered) - success_count,
        f"{success_count}_of_{len(ordered)}_success",
        success_count >= 2,
        success_count >= 2,
        ordered,
    )


def _build_lifecycle_from_verified_records(
    orchestration_plan: Mapping[str, Any],
    summary: PartialSuccessSummary,
    records: Mapping[str, Mapping[str, Any]],
) -> CandidateArtifactLifecycle:
    lifecycle = build_artifact_lifecycle(orchestration_plan)
    for outcome in summary.outcomes:
        candidate = next(item for item in lifecycle.candidates if item.engine == outcome.engine)
        if outcome.status == "success":
            record = records.get(outcome.engine)
            if type(record) is not dict or record.get("candidateSha256") != outcome.candidate_sha256:
                raise EngineResultIngestionError("candidate_lifecycle_record_invalid")
            artifacts = record.get("artifacts")
            if type(artifacts) is not list or len(artifacts) != 3:
                raise EngineResultIngestionError("candidate_lifecycle_record_invalid")
            by_kind = {item.get("kind"): item for item in artifacts if type(item) is dict}
            if set(by_kind) != set(_MEDIA_BY_KIND):
                raise EngineResultIngestionError("candidate_lifecycle_record_invalid")
            lifecycle = transition_candidate(lifecycle, candidate.candidate_id, "collecting")
            for artifact in candidate.artifacts:
                metadata = by_kind.get(artifact.kind)
                if type(metadata) is not dict or metadata.get("artifactId") != artifact.artifact_id:
                    raise EngineResultIngestionError("candidate_lifecycle_record_invalid")
                lifecycle = transition_artifact(lifecycle, artifact.artifact_id, "writing")
                lifecycle = transition_artifact(
                    lifecycle,
                    artifact.artifact_id,
                    "sealed",
                    sha256=metadata.get("sha256"),
                    size_bytes=metadata.get("sizeBytes"),
                    media_type=metadata.get("mediaType"),
                )
            lifecycle = transition_candidate(lifecycle, candidate.candidate_id, "sealed")
        else:
            reason = outcome.reason_code
            if reason is None:
                raise EngineResultIngestionError("candidate_lifecycle_failure_invalid")
            for artifact in candidate.artifacts:
                lifecycle = transition_artifact(lifecycle, artifact.artifact_id, "abandoned", reason_code=reason)
            lifecycle = transition_candidate(lifecycle, candidate.candidate_id, "failed", reason_code=reason)
    return lifecycle


def build_candidate_lifecycle_from_persistence(
    *,
    provider: StagingUploadProvider,
    orchestration_plan: Mapping[str, Any],
    outcomes: tuple[EngineIngestionOutcome, ...],
) -> CandidateArtifactLifecycle:
    """Build lifecycle only from records re-authenticated from the durable store."""

    summary = summarize_partial_success(orchestration_plan, outcomes)
    records: dict[str, Mapping[str, Any]] = {}
    for outcome in summary.outcomes:
        if outcome.status == "success":
            records[outcome.engine] = load_persisted_candidate_record(
                provider=provider,
                orchestration_plan=orchestration_plan,
                engine=outcome.engine,
            )
    try:
        return _build_lifecycle_from_verified_records(orchestration_plan, summary, records)
    except ArtifactLifecycleError:
        raise EngineResultIngestionError("candidate_lifecycle_invalid") from None
