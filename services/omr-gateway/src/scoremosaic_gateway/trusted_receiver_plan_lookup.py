"""Provider-neutral trusted orchestration-plan lookup for a future receiver.

A live engine receiver cannot treat the signed dispatch body as plan authority.
This contract therefore extracts only a tightly bounded *untrusted lookup hint*
from the canonical C.2-C dispatch-identity payload, asks a caller-supplied
read-only trusted provider for the exact orchestration plan, independently
verifies that plan with the existing deterministic orchestration contract, and
finally requires that the trusted plan reproduces the complete received body
byte-for-byte for the expected engine run.

The hint is never authority. Provider selection, persistence, HTTP routing,
credential resolution, authentication, replay reservation, job-state mutation,
network dispatch, and engine execution are deliberately outside this slice.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from hashlib import sha256
import json
import re
from typing import Any, Callable, Mapping

from .dispatch_identity import (
    DISPATCH_IDENTITY_CONTRACT_VERSION,
    MAX_DISPATCH_IDENTITY_PAYLOAD_BYTES,
    DispatchIdentityError,
    build_dispatch_identity,
    dispatch_identity_payload,
)
from .orchestration import ENGINE_NAMES, OrchestrationContractError, verify_orchestration_plan


TRUSTED_RECEIVER_PLAN_LOOKUP_VERSION = "scoremosaic-trusted-receiver-plan-lookup-v1"
_JOB_ID_RE = re.compile(r"job_[A-Za-z0-9_-]{8,80}\Z")
_PLAN_ID_RE = re.compile(r"plan_[0-9a-f]{24}\Z")
_RUN_ID_RE = re.compile(r"run_[0-9a-f]{24}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_EXPECTED_BODY_KEYS = frozenset(
    {"version", "planId", "planSha256", "jobId", "sourceArtifact", "engineRun"}
)
_EXPECTED_ENGINE_RUN_KEYS = frozenset(
    {"runId", "engine", "candidateId", "candidateNamespace", "expectedArtifacts"}
)
_TRUSTED_RESOLUTION_SEAL = object()


class TrustedReceiverPlanLookupError(ValueError):
    """Stable fail-closed category for trusted receiver-plan lookup."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


def _canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    except (TypeError, ValueError, OverflowError, UnicodeEncodeError):
        raise TrustedReceiverPlanLookupError("receiver_plan_payload_invalid") from None


def _duplicate_rejecting_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            raise TrustedReceiverPlanLookupError("receiver_plan_payload_invalid")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise TrustedReceiverPlanLookupError("receiver_plan_payload_invalid")


def _require_payload(value: object) -> bytes:
    if (
        type(value) is not bytes
        or not value
        or len(value) > MAX_DISPATCH_IDENTITY_PAYLOAD_BYTES
    ):
        raise TrustedReceiverPlanLookupError("receiver_plan_payload_invalid")
    return value


def _parse_canonical_payload(payload: bytes) -> dict[str, Any]:
    try:
        text = payload.decode("ascii")
    except UnicodeDecodeError:
        raise TrustedReceiverPlanLookupError("receiver_plan_payload_invalid") from None
    try:
        value = json.loads(
            text,
            object_pairs_hook=_duplicate_rejecting_object,
            parse_constant=_reject_json_constant,
        )
    except TrustedReceiverPlanLookupError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError):
        raise TrustedReceiverPlanLookupError("receiver_plan_payload_invalid") from None
    if type(value) is not dict:
        raise TrustedReceiverPlanLookupError("receiver_plan_payload_invalid")
    if _canonical_json_bytes(value) != payload:
        raise TrustedReceiverPlanLookupError("receiver_plan_payload_not_canonical")
    return value


def _require_pattern(value: object, pattern: re.Pattern[str], category: str) -> str:
    if type(value) is not str or pattern.fullmatch(value) is None:
        raise TrustedReceiverPlanLookupError(category)
    return value


def _require_engine(value: object) -> str:
    if type(value) is not str or value not in ENGINE_NAMES:
        raise TrustedReceiverPlanLookupError("receiver_plan_engine_invalid")
    return value


@dataclass(frozen=True, slots=True)
class ReceiverPlanLookupHint:
    """Untrusted bounded keys extracted from the received identity body."""

    version: str
    plan_id: str
    plan_sha256: str
    job_id: str
    run_id: str
    engine: str
    body_sha256: str
    body_bytes: int

    def __post_init__(self) -> None:
        if (
            type(self.version) is not str
            or self.version != TRUSTED_RECEIVER_PLAN_LOOKUP_VERSION
            or type(self.plan_id) is not str
            or _PLAN_ID_RE.fullmatch(self.plan_id) is None
            or type(self.plan_sha256) is not str
            or _SHA256_RE.fullmatch(self.plan_sha256) is None
            or type(self.job_id) is not str
            or _JOB_ID_RE.fullmatch(self.job_id) is None
            or type(self.run_id) is not str
            or _RUN_ID_RE.fullmatch(self.run_id) is None
            or type(self.engine) is not str
            or self.engine not in ENGINE_NAMES
            or type(self.body_sha256) is not str
            or _SHA256_RE.fullmatch(self.body_sha256) is None
            or type(self.body_bytes) is not int
            or not 1 <= self.body_bytes <= MAX_DISPATCH_IDENTITY_PAYLOAD_BYTES
        ):
            raise TrustedReceiverPlanLookupError("receiver_plan_hint_invalid")

    @property
    def trusted(self) -> bool:
        return False

    @property
    def authorization_allowed(self) -> bool:
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
            "planId": self.plan_id,
            "planSha256": self.plan_sha256,
            "jobId": self.job_id,
            "runId": self.run_id,
            "engine": self.engine,
            "bodySha256": self.body_sha256,
            "bodyBytes": self.body_bytes,
            "trusted": False,
            "authorizationAllowed": False,
            "networkDispatchAllowed": False,
            "engineExecutionAllowed": False,
        }


TrustedReceiverPlanResolver = Callable[[ReceiverPlanLookupHint], Mapping[str, Any] | None]


@dataclass(frozen=True, slots=True)
class TrustedReceiverPlanResolution:
    """Sealed result proving a trusted provider plan exactly reproduces the body."""

    version: str
    hint: ReceiverPlanLookupHint
    plan_id: str
    plan_sha256: str
    job_id: str
    run_id: str
    engine: str
    dispatch_identity_sha256: str
    canonical_plan_sha256: str
    _canonical_plan_json: bytes = field(repr=False)
    _seal: object = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._seal is not _TRUSTED_RESOLUTION_SEAL:
            raise TrustedReceiverPlanLookupError("trusted_receiver_plan_result_invalid")
        if (
            type(self.version) is not str
            or self.version != TRUSTED_RECEIVER_PLAN_LOOKUP_VERSION
            or type(self.hint) is not ReceiverPlanLookupHint
            or type(self.plan_id) is not str
            or _PLAN_ID_RE.fullmatch(self.plan_id) is None
            or type(self.plan_sha256) is not str
            or _SHA256_RE.fullmatch(self.plan_sha256) is None
            or type(self.job_id) is not str
            or _JOB_ID_RE.fullmatch(self.job_id) is None
            or type(self.run_id) is not str
            or _RUN_ID_RE.fullmatch(self.run_id) is None
            or type(self.engine) is not str
            or self.engine not in ENGINE_NAMES
            or type(self.dispatch_identity_sha256) is not str
            or _SHA256_RE.fullmatch(self.dispatch_identity_sha256) is None
            or type(self.canonical_plan_sha256) is not str
            or _SHA256_RE.fullmatch(self.canonical_plan_sha256) is None
            or type(self._canonical_plan_json) is not bytes
            or not self._canonical_plan_json
            or self.plan_id != self.hint.plan_id
            or self.plan_sha256 != self.hint.plan_sha256
            or self.job_id != self.hint.job_id
            or self.run_id != self.hint.run_id
            or self.engine != self.hint.engine
        ):
            raise TrustedReceiverPlanLookupError("trusted_receiver_plan_result_invalid")

    @property
    def trusted_plan_resolved(self) -> bool:
        return True

    @property
    def receiver_authentication_passed(self) -> bool:
        return False

    @property
    def network_dispatch_allowed(self) -> bool:
        return False

    @property
    def job_state_mutation_allowed(self) -> bool:
        return False

    @property
    def engine_execution_allowed(self) -> bool:
        return False

    def plan_mapping(self) -> dict[str, Any]:
        """Return a fresh detached copy of the already-verified trusted plan."""

        try:
            value = json.loads(self._canonical_plan_json.decode("ascii"))
        except Exception:
            raise TrustedReceiverPlanLookupError(
                "trusted_receiver_plan_result_invalid"
            ) from None
        if type(value) is not dict:
            raise TrustedReceiverPlanLookupError("trusted_receiver_plan_result_invalid")
        return value

    def as_safe_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "planId": self.plan_id,
            "planSha256": self.plan_sha256,
            "jobId": self.job_id,
            "runId": self.run_id,
            "engine": self.engine,
            "dispatchIdentitySha256": self.dispatch_identity_sha256,
            "canonicalPlanSha256": self.canonical_plan_sha256,
            "trustedPlanResolved": True,
            "receiverAuthenticationPassed": False,
            "networkDispatchAllowed": False,
            "jobStateMutationAllowed": False,
            "engineExecutionAllowed": False,
        }


def parse_receiver_plan_lookup_hint(payload: bytes) -> ReceiverPlanLookupHint:
    """Extract bounded untrusted lookup keys from exact canonical identity bytes."""

    body = _require_payload(payload)
    value = _parse_canonical_payload(body)
    if frozenset(value) != _EXPECTED_BODY_KEYS:
        raise TrustedReceiverPlanLookupError("receiver_plan_payload_shape_invalid")
    if value.get("version") != DISPATCH_IDENTITY_CONTRACT_VERSION:
        raise TrustedReceiverPlanLookupError("receiver_plan_identity_version_invalid")

    engine_run = value.get("engineRun")
    if type(engine_run) is not dict or frozenset(engine_run) != _EXPECTED_ENGINE_RUN_KEYS:
        raise TrustedReceiverPlanLookupError("receiver_plan_payload_shape_invalid")

    return ReceiverPlanLookupHint(
        version=TRUSTED_RECEIVER_PLAN_LOOKUP_VERSION,
        plan_id=_require_pattern(
            value.get("planId"),
            _PLAN_ID_RE,
            "receiver_plan_id_invalid",
        ),
        plan_sha256=_require_pattern(
            value.get("planSha256"),
            _SHA256_RE,
            "receiver_plan_sha256_invalid",
        ),
        job_id=_require_pattern(
            value.get("jobId"),
            _JOB_ID_RE,
            "receiver_plan_job_id_invalid",
        ),
        run_id=_require_pattern(
            engine_run.get("runId"),
            _RUN_ID_RE,
            "receiver_plan_run_id_invalid",
        ),
        engine=_require_engine(engine_run.get("engine")),
        body_sha256=sha256(body).hexdigest(),
        body_bytes=len(body),
    )


def _snapshot_provider_plan(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TrustedReceiverPlanLookupError("trusted_receiver_plan_invalid")
    try:
        snapshot = deepcopy(dict(value))
    except Exception:
        raise TrustedReceiverPlanLookupError("trusted_receiver_plan_invalid") from None
    if type(snapshot) is not dict:
        raise TrustedReceiverPlanLookupError("trusted_receiver_plan_invalid")
    return snapshot


def resolve_trusted_receiver_plan(
    *,
    payload: bytes,
    expected_engine: str,
    resolver: TrustedReceiverPlanResolver,
) -> TrustedReceiverPlanResolution:
    """Resolve a trusted plan and require it to reproduce the complete body."""

    body = _require_payload(payload)
    engine = _require_engine(expected_engine)
    hint = parse_receiver_plan_lookup_hint(body)
    if hint.engine != engine:
        raise TrustedReceiverPlanLookupError("receiver_plan_engine_mismatch")
    if not callable(resolver):
        raise TrustedReceiverPlanLookupError("trusted_receiver_plan_resolver_invalid")

    try:
        observed = resolver(hint)
    except Exception:
        raise TrustedReceiverPlanLookupError("trusted_receiver_plan_unavailable") from None
    if observed is None:
        raise TrustedReceiverPlanLookupError("trusted_receiver_plan_unavailable")

    plan = _snapshot_provider_plan(observed)
    try:
        verify_orchestration_plan(plan)
        identity = build_dispatch_identity(plan, engine)
        expected_body = dispatch_identity_payload(identity)
    except (OrchestrationContractError, DispatchIdentityError, TypeError, ValueError, KeyError):
        raise TrustedReceiverPlanLookupError("trusted_receiver_plan_invalid") from None

    if (
        plan.get("planId") != hint.plan_id
        or plan.get("planSha256") != hint.plan_sha256
        or plan.get("jobId") != hint.job_id
        or identity.plan_id != hint.plan_id
        or identity.plan_sha256 != hint.plan_sha256
        or identity.job_id != hint.job_id
        or identity.run_id != hint.run_id
        or identity.engine != hint.engine
        or expected_body != body
        or identity.identity_sha256 != hint.body_sha256
    ):
        raise TrustedReceiverPlanLookupError("trusted_receiver_plan_mismatch")

    canonical_plan_json = _canonical_json_bytes(plan)
    return TrustedReceiverPlanResolution(
        version=TRUSTED_RECEIVER_PLAN_LOOKUP_VERSION,
        hint=hint,
        plan_id=identity.plan_id,
        plan_sha256=identity.plan_sha256,
        job_id=identity.job_id,
        run_id=identity.run_id,
        engine=identity.engine,
        dispatch_identity_sha256=identity.identity_sha256,
        canonical_plan_sha256=sha256(canonical_plan_json).hexdigest(),
        _canonical_plan_json=canonical_plan_json,
        _seal=_TRUSTED_RESOLUTION_SEAL,
    )
