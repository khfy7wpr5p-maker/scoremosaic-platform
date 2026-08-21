"""Non-executable bounded input capsule for authenticated engine dispatch.

The capsule carries exactly three pieces of untrusted transport content:

* one already-derived C.2-C dispatch identity,
* one exact canonical deterministic orchestration-plan JSON payload,
* one exact immutable PDF/JPEG/PNG source byte sequence.

This module only validates and freezes evidence. It never resolves credentials,
reserves replay state, mutates job state, opens a filesystem path, performs
network I/O, or invokes an engine runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
from typing import Any, Iterable, Mapping

from .dispatch_identity import (
    DispatchIdentityBinding,
    DispatchIdentityError,
    build_dispatch_identity,
    dispatch_identity_payload,
)
from .orchestration import (
    MAX_SOURCE_BYTES,
    OrchestrationContractError,
    verify_orchestration_plan,
)
from .safe_intake import (
    SafeIntakeMediaTypeError,
    SafeIntakeSignatureError,
    verify_signature_media_type,
)

DISPATCH_INPUT_CAPSULE_VERSION = "scoremosaic-dispatch-input-capsule-v1"
MAX_CAPSULE_PLAN_BYTES = 64 * 1024
MAX_CAPSULE_SOURCE_CHUNK_BYTES = 1024 * 1024
MAX_CAPSULE_SOURCE_CHUNKS = 16_384


class DispatchInputCapsuleError(ValueError):
    """Fail-closed bounded capsule validation failure."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


def _canonical_json_bytes(payload: Any) -> bytes:
    try:
        return json.dumps(
            payload,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    except (TypeError, ValueError, OverflowError, UnicodeEncodeError):
        raise DispatchInputCapsuleError("capsule_plan_json_invalid") from None


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            raise DispatchInputCapsuleError("capsule_plan_json_invalid")
        result[key] = value
    return result


def _decode_canonical_plan(plan_bytes: bytes) -> tuple[dict[str, Any], str]:
    if type(plan_bytes) is not bytes:
        raise DispatchInputCapsuleError("capsule_plan_bytes_invalid")
    if not plan_bytes or len(plan_bytes) > MAX_CAPSULE_PLAN_BYTES:
        raise DispatchInputCapsuleError("capsule_plan_size_invalid")
    try:
        plan_text = plan_bytes.decode("ascii")
        decoded = json.loads(plan_text, object_pairs_hook=_reject_duplicate_pairs)
    except DispatchInputCapsuleError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        raise DispatchInputCapsuleError("capsule_plan_json_invalid") from None
    if type(decoded) is not dict:
        raise DispatchInputCapsuleError("capsule_plan_json_invalid")

    canonical = _canonical_json_bytes(decoded)
    if not hmac.compare_digest(plan_bytes, canonical):
        raise DispatchInputCapsuleError("capsule_plan_not_canonical")
    try:
        verify_orchestration_plan(decoded)
    except (OrchestrationContractError, TypeError, ValueError, KeyError):
        raise DispatchInputCapsuleError("capsule_plan_contract_invalid") from None
    return decoded, hashlib.sha256(canonical).hexdigest()


def canonical_orchestration_plan_bytes(plan: Mapping[str, Any]) -> bytes:
    """Return the exact canonical bytes of one verified deterministic plan."""

    if not isinstance(plan, Mapping):
        raise DispatchInputCapsuleError("capsule_plan_invalid")
    try:
        snapshot = json.loads(
            _canonical_json_bytes(dict(plan)).decode("ascii"),
            object_pairs_hook=_reject_duplicate_pairs,
        )
        verify_orchestration_plan(snapshot)
    except DispatchInputCapsuleError:
        raise
    except (OrchestrationContractError, TypeError, ValueError, KeyError, json.JSONDecodeError):
        raise DispatchInputCapsuleError("capsule_plan_contract_invalid") from None
    canonical = _canonical_json_bytes(snapshot)
    if not canonical or len(canonical) > MAX_CAPSULE_PLAN_BYTES:
        raise DispatchInputCapsuleError("capsule_plan_size_invalid")
    return canonical


def _collect_source_chunks(
    chunks: Iterable[bytes],
    *,
    expected_size: int,
) -> bytes:
    if type(expected_size) is not int or not 1 <= expected_size <= MAX_SOURCE_BYTES:
        raise DispatchInputCapsuleError("capsule_source_size_invalid")
    try:
        iterator = iter(chunks)
    except TypeError:
        raise DispatchInputCapsuleError("capsule_source_stream_invalid") from None

    collected = bytearray()
    chunk_count = 0
    for chunk in iterator:
        chunk_count += 1
        if chunk_count > MAX_CAPSULE_SOURCE_CHUNKS:
            raise DispatchInputCapsuleError("capsule_source_stream_invalid")
        if type(chunk) is not bytes or not chunk:
            raise DispatchInputCapsuleError("capsule_source_chunk_invalid")
        if len(chunk) > MAX_CAPSULE_SOURCE_CHUNK_BYTES:
            raise DispatchInputCapsuleError("capsule_source_chunk_too_large")
        if len(collected) + len(chunk) > expected_size:
            raise DispatchInputCapsuleError("capsule_source_size_mismatch")
        collected.extend(chunk)

    if len(collected) != expected_size:
        raise DispatchInputCapsuleError("capsule_source_size_mismatch")
    return bytes(collected)


def _require_identity_convergence(
    plan: Mapping[str, Any],
    identity: DispatchIdentityBinding,
) -> None:
    if type(identity) is not DispatchIdentityBinding:
        raise DispatchInputCapsuleError("capsule_dispatch_identity_invalid")
    try:
        expected = build_dispatch_identity(plan, identity.engine)
        observed_payload = dispatch_identity_payload(identity)
        expected_payload = dispatch_identity_payload(expected)
    except (DispatchIdentityError, TypeError, ValueError, KeyError):
        raise DispatchInputCapsuleError("capsule_dispatch_identity_invalid") from None
    if identity != expected or not hmac.compare_digest(observed_payload, expected_payload):
        raise DispatchInputCapsuleError("capsule_dispatch_identity_mismatch")


def _require_source_convergence(
    plan: Mapping[str, Any],
    identity: DispatchIdentityBinding,
    source_bytes: bytes,
) -> tuple[int, str, str]:
    if type(source_bytes) is not bytes or not source_bytes:
        raise DispatchInputCapsuleError("capsule_source_bytes_invalid")
    if len(source_bytes) > MAX_SOURCE_BYTES:
        raise DispatchInputCapsuleError("capsule_source_size_invalid")

    source = plan.get("sourceArtifact")
    if type(source) is not dict:
        raise DispatchInputCapsuleError("capsule_plan_contract_invalid")
    expected_size = source.get("sizeBytes")
    expected_sha256 = source.get("sha256")
    expected_media_type = source.get("mediaType")

    if (
        type(expected_size) is not int
        or expected_size != len(source_bytes)
        or identity.source_size_bytes != len(source_bytes)
    ):
        raise DispatchInputCapsuleError("capsule_source_size_mismatch")

    observed_sha256 = hashlib.sha256(source_bytes).hexdigest()
    if (
        type(expected_sha256) is not str
        or not hmac.compare_digest(observed_sha256, expected_sha256)
        or not hmac.compare_digest(observed_sha256, identity.source_sha256)
    ):
        raise DispatchInputCapsuleError("capsule_source_sha256_mismatch")

    if (
        type(expected_media_type) is not str
        or identity.source_media_type != expected_media_type
    ):
        raise DispatchInputCapsuleError("capsule_source_media_type_mismatch")
    try:
        signature = verify_signature_media_type(source_bytes, expected_media_type)
    except (SafeIntakeMediaTypeError, SafeIntakeSignatureError, TypeError):
        raise DispatchInputCapsuleError("capsule_source_media_type_mismatch") from None
    if signature.media_type != expected_media_type:
        raise DispatchInputCapsuleError("capsule_source_media_type_mismatch")

    return len(source_bytes), observed_sha256, expected_media_type


@dataclass(frozen=True, slots=True, repr=False)
class DispatchInputCapsule:
    """Immutable verified transport evidence with no execution authority."""

    version: str
    dispatch_identity: DispatchIdentityBinding
    canonical_plan_bytes: bytes
    canonical_plan_sha256: str
    source_bytes: bytes
    source_size_bytes: int
    source_sha256: str
    source_media_type: str

    def __repr__(self) -> str:
        return (
            "DispatchInputCapsule("
            f"version={self.version!r}, engine={self.dispatch_identity.engine!r}, "
            f"job_id={self.dispatch_identity.job_id!r}, "
            f"run_id={self.dispatch_identity.run_id!r}, "
            f"canonical_plan_sha256={self.canonical_plan_sha256!r}, "
            f"source_size_bytes={self.source_size_bytes!r}, "
            f"source_sha256={self.source_sha256!r}, "
            f"source_media_type={self.source_media_type!r}, "
            "canonical_plan_bytes=<redacted>, source_bytes=<redacted>)"
        )

    @property
    def credential_access_allowed(self) -> bool:
        return False

    @property
    def replay_side_effect_allowed(self) -> bool:
        return False

    @property
    def state_mutation_allowed(self) -> bool:
        return False

    @property
    def network_dispatch_allowed(self) -> bool:
        return False

    @property
    def engine_execution_allowed(self) -> bool:
        return False

    def as_safe_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "dispatchIdentity": self.dispatch_identity.as_safe_dict(),
            "canonicalPlanSha256": self.canonical_plan_sha256,
            "canonicalPlanBytes": len(self.canonical_plan_bytes),
            "sourceSizeBytes": self.source_size_bytes,
            "sourceSha256": self.source_sha256,
            "sourceMediaType": self.source_media_type,
            "credentialAccessAllowed": False,
            "replaySideEffectAllowed": False,
            "stateMutationAllowed": False,
            "networkDispatchAllowed": False,
            "engineExecutionAllowed": False,
        }


def verify_dispatch_input_capsule(capsule: DispatchInputCapsule) -> dict[str, Any]:
    """Revalidate all untrusted capsule content without causing side effects."""

    if type(capsule) is not DispatchInputCapsule:
        raise DispatchInputCapsuleError("capsule_invalid")
    if capsule.version != DISPATCH_INPUT_CAPSULE_VERSION:
        raise DispatchInputCapsuleError("capsule_version_invalid")

    plan, canonical_sha256 = _decode_canonical_plan(capsule.canonical_plan_bytes)
    if not hmac.compare_digest(canonical_sha256, capsule.canonical_plan_sha256):
        raise DispatchInputCapsuleError("capsule_plan_sha256_mismatch")
    _require_identity_convergence(plan, capsule.dispatch_identity)
    source_size, source_sha256, source_media_type = _require_source_convergence(
        plan,
        capsule.dispatch_identity,
        capsule.source_bytes,
    )
    if (
        capsule.source_size_bytes != source_size
        or not hmac.compare_digest(capsule.source_sha256, source_sha256)
        or capsule.source_media_type != source_media_type
    ):
        raise DispatchInputCapsuleError("capsule_source_metadata_mismatch")
    return plan


def build_dispatch_input_capsule(
    orchestration_plan: Mapping[str, Any],
    dispatch_identity: DispatchIdentityBinding,
    source_chunks: Iterable[bytes],
) -> DispatchInputCapsule:
    """Freeze exact canonical plan and source bytes into verified evidence.

    The source iterator is bounded by both the plan-declared exact size and the
    global source limit. No callback, replay reservation, filesystem write,
    network request, credential resolver, or execution hook is accepted here.
    """

    plan_bytes = canonical_orchestration_plan_bytes(orchestration_plan)
    plan, canonical_sha256 = _decode_canonical_plan(plan_bytes)
    _require_identity_convergence(plan, dispatch_identity)
    expected_size = dispatch_identity.source_size_bytes
    source_bytes = _collect_source_chunks(source_chunks, expected_size=expected_size)
    source_size, source_sha256, source_media_type = _require_source_convergence(
        plan,
        dispatch_identity,
        source_bytes,
    )
    capsule = DispatchInputCapsule(
        version=DISPATCH_INPUT_CAPSULE_VERSION,
        dispatch_identity=dispatch_identity,
        canonical_plan_bytes=plan_bytes,
        canonical_plan_sha256=canonical_sha256,
        source_bytes=source_bytes,
        source_size_bytes=source_size,
        source_sha256=source_sha256,
        source_media_type=source_media_type,
    )
    verify_dispatch_input_capsule(capsule)
    return capsule
