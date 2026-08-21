"""Controlled one-shot private network dispatch for Stage 4-D.

This is the first Gateway boundary permitted to perform network I/O for one
already-prepared controlled-staging dispatch. It deliberately transfers only
control-plane JSON: the authenticated trusted-plan provisioning request followed
by the authenticated C.2-C dispatch identity. Source bytes are never sent and no
engine execution, result persistence, retry, redirect, proxy routing, or
post-dispatch job mutation is authorized.

Security ordering is conservative:
1. Re-validate capsule, provisioning request, signed wire, fixed allowlisted
   endpoint, and freshness without side effects.
2. Atomically publish durable dispatching revision 2. This is the crash/retry
   fence: any existing revision-2 dispatching record is reconciliation-only and
   causes zero network calls.
3. Send the provisioning request exactly once to the fixed private origin.
4. Only after a strict 201 accepted/non-executable response, send the dispatch
   request exactly once to the fixed /internal/transcribe target.
5. Require strict bounded 202 accepted/non-executable evidence.

Any transport ambiguity leaves the durable run in dispatching(2); callers must
reconcile and must not automatically retry this function.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from http.client import HTTPConnection, HTTPResponse
import json
import socket
from typing import Any, Callable, Sequence
from urllib.parse import urlsplit

from .authenticated_request import MAX_FUTURE_SKEW_SECONDS, MAX_REQUEST_AGE_SECONDS
from .config import EngineEndpoint
from .controlled_staging_dispatch_wire import (
    ControlledStagingDispatchWireError,
    ControlledStagingDispatchWireRequest,
    parse_controlled_staging_dispatch_wire,
)
from .controlled_staging_dispatching_transition import (
    ControlledStagingDispatchingTransitionError,
    transition_controlled_staging_queued_to_dispatching,
)
from .dispatch_identity import DispatchIdentityError, dispatch_identity_payload
from .dispatch_input_capsule import (
    DispatchInputCapsule,
    DispatchInputCapsuleError,
    verify_dispatch_input_capsule,
)
from .dispatch_target import (
    APPROVED_ENGINE_ORIGINS,
    DISPATCH_METHOD,
    DISPATCH_PATH,
    DispatchTargetError,
    build_engine_dispatch_target,
)
from .minimum_staging_vertical_slice import (
    MinimumStagingVerticalSliceResult,
    StagingUploadProvider,
)
from .service_auth import ServiceAuthError, build_engine_auth_binding
from .trusted_plan_provisioning import (
    MAX_PROVISIONING_AGE_SECONDS,
    TRUSTED_PLAN_PROVISIONING_ALGORITHM,
    TRUSTED_PLAN_PROVISIONING_METHOD,
    TRUSTED_PLAN_PROVISIONING_PATH,
    TRUSTED_PLAN_PROVISIONING_VERSION,
    TrustedPlanProvisioningError,
    TrustedPlanProvisioningRequest,
    build_trusted_plan_provisioning_binding,
)

CONTROLLED_PRIVATE_NETWORK_DISPATCH_VERSION = (
    "scoremosaic-controlled-private-network-dispatch-v1"
)
MAX_CONTROL_RESPONSE_BYTES = 16 * 1024
MIN_CONTROL_TIMEOUT_SECONDS = 1
MAX_CONTROL_TIMEOUT_SECONDS = 30
EXPECTED_RESPONSE_CONTENT_TYPE = "application/json; charset=utf-8"
PROVISIONING_SIGNATURE_HEADER = "x-scoremosaic-provisioning-signature"


class ControlledPrivateNetworkDispatchError(ValueError):
    """Bounded Stage 4-D failure category."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


@dataclass(frozen=True, slots=True)
class PrivateControlHttpResponse:
    """Bounded transport result; no redirect following is represented."""

    status: int
    content_type: str
    body: bytes
    location: str | None = None

    def __post_init__(self) -> None:
        if (
            type(self.status) is not int
            or not 100 <= self.status <= 599
            or type(self.content_type) is not str
            or type(self.body) is not bytes
            or len(self.body) > MAX_CONTROL_RESPONSE_BYTES
            or (self.location is not None and type(self.location) is not str)
        ):
            raise ControlledPrivateNetworkDispatchError(
                "staging_private_dispatch_transport_response_invalid"
            )


PrivateControlTransport = Callable[
    [str, str, tuple[tuple[str, str], ...], bytes, int],
    PrivateControlHttpResponse,
]


@dataclass(frozen=True, slots=True)
class ControlledPrivateNetworkDispatchResult:
    version: str
    job_id: str
    engine: str
    run_id: str
    dispatch_identity_sha256: str
    target_origin: str
    dispatching_revision: int
    provisioning_http_status: int
    dispatch_http_status: int
    provisioning_attempt_count: int
    dispatch_attempt_count: int
    reconciliation_required_on_restart: bool

    def __post_init__(self) -> None:
        expected_origin = (
            APPROVED_ENGINE_ORIGINS["staging"].get(self.engine)
            if type(self.engine) is str
            else None
        )
        if (
            self.version != CONTROLLED_PRIVATE_NETWORK_DISPATCH_VERSION
            or type(self.job_id) is not str
            or type(self.engine) is not str
            or expected_origin is None
            or self.target_origin != expected_origin
            or type(self.run_id) is not str
            or type(self.dispatch_identity_sha256) is not str
            or len(self.dispatch_identity_sha256) != 64
            or self.dispatching_revision != 2
            or self.provisioning_http_status != 201
            or self.dispatch_http_status != 202
            or self.provisioning_attempt_count != 1
            or self.dispatch_attempt_count != 1
            or self.reconciliation_required_on_restart is not True
        ):
            raise ControlledPrivateNetworkDispatchError(
                "staging_private_dispatch_result_invalid"
            )

    @property
    def network_dispatch_performed(self) -> bool:
        return True

    @property
    def trusted_plan_provisioned(self) -> bool:
        return True

    @property
    def receiver_authenticated(self) -> bool:
        return True

    @property
    def source_transfer_allowed(self) -> bool:
        return False

    @property
    def engine_execution_allowed(self) -> bool:
        return False

    @property
    def result_persistence_allowed(self) -> bool:
        return False

    @property
    def retry_allowed(self) -> bool:
        return False

    @property
    def redirect_allowed(self) -> bool:
        return False

    @property
    def post_dispatch_job_mutation_allowed(self) -> bool:
        return False

    def as_safe_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "environment": "staging",
            "jobId": self.job_id,
            "engine": self.engine,
            "runId": self.run_id,
            "dispatchIdentitySha256": self.dispatch_identity_sha256,
            "targetOrigin": self.target_origin,
            "dispatchingRevision": self.dispatching_revision,
            "provisioningHttpStatus": self.provisioning_http_status,
            "dispatchHttpStatus": self.dispatch_http_status,
            "provisioningAttemptCount": self.provisioning_attempt_count,
            "dispatchAttemptCount": self.dispatch_attempt_count,
            "reconciliationRequiredOnRestart": True,
            "networkDispatchPerformed": True,
            "trustedPlanProvisioned": True,
            "receiverAuthenticated": True,
            "sourceTransferAllowed": False,
            "engineExecutionAllowed": False,
            "resultPersistenceAllowed": False,
            "retryAllowed": False,
            "redirectAllowed": False,
            "postDispatchJobMutationAllowed": False,
        }


def _strict_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            raise ControlledPrivateNetworkDispatchError(
                "staging_private_dispatch_response_invalid"
            )
        result[key] = value
    return result


def _strict_json(raw: bytes) -> dict[str, Any]:
    if type(raw) is not bytes or not raw or len(raw) > MAX_CONTROL_RESPONSE_BYTES:
        raise ControlledPrivateNetworkDispatchError(
            "staging_private_dispatch_response_invalid"
        )
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_strict_pairs,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except ControlledPrivateNetworkDispatchError:
        raise
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
        TypeError,
        RecursionError,
    ):
        raise ControlledPrivateNetworkDispatchError(
            "staging_private_dispatch_response_invalid"
        ) from None
    if type(value) is not dict:
        raise ControlledPrivateNetworkDispatchError(
            "staging_private_dispatch_response_invalid"
        )
    return value


def _require_timeout(value: object) -> int:
    if (
        type(value) is not int
        or not MIN_CONTROL_TIMEOUT_SECONDS <= value <= MAX_CONTROL_TIMEOUT_SECONDS
    ):
        raise ControlledPrivateNetworkDispatchError(
            "staging_private_dispatch_timeout_invalid"
        )
    return value


def _require_now(value: object) -> int:
    if type(value) is not int or value < 0:
        raise ControlledPrivateNetworkDispatchError(
            "staging_private_dispatch_time_invalid"
        )
    return value


def _require_endpoint(endpoint: object) -> EngineEndpoint:
    if type(endpoint) is not EngineEndpoint:
        raise ControlledPrivateNetworkDispatchError(
            "staging_private_dispatch_endpoint_invalid"
        )
    expected = APPROVED_ENGINE_ORIGINS["staging"].get(endpoint.name)
    if expected is None or endpoint.base_url != expected:
        raise ControlledPrivateNetworkDispatchError(
            "staging_private_dispatch_endpoint_invalid"
        )
    try:
        parsed = urlsplit(endpoint.base_url)
        port = parsed.port
    except ValueError:
        raise ControlledPrivateNetworkDispatchError(
            "staging_private_dispatch_endpoint_invalid"
        ) from None
    if (
        parsed.scheme != "http"
        or parsed.hostname is None
        or port is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ControlledPrivateNetworkDispatchError(
            "staging_private_dispatch_endpoint_invalid"
        )
    return endpoint


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    except (TypeError, ValueError, OverflowError, UnicodeEncodeError):
        raise ControlledPrivateNetworkDispatchError(
            "staging_private_dispatch_provisioning_invalid"
        ) from None


def _decode_provisioning_body(
    request: TrustedPlanProvisioningRequest,
    *,
    endpoint: EngineEndpoint,
    capsule: DispatchInputCapsule,
    now_seconds: int,
) -> None:
    if type(request) is not TrustedPlanProvisioningRequest:
        raise ControlledPrivateNetworkDispatchError(
            "staging_private_dispatch_provisioning_invalid"
        )
    if (
        request.engine != endpoint.name
        or request.job_id != capsule.dispatch_identity.job_id
        or request.run_id != capsule.dispatch_identity.run_id
        or request.canonical_plan_sha256 != capsule.canonical_plan_sha256
        or request.issued_at > now_seconds
        or now_seconds - request.issued_at > MAX_PROVISIONING_AGE_SECONDS
    ):
        raise ControlledPrivateNetworkDispatchError(
            "staging_private_dispatch_provisioning_invalid"
        )
    try:
        body = json.loads(
            request.canonical_request_bytes.decode("ascii"),
            object_pairs_hook=_strict_pairs,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except ControlledPrivateNetworkDispatchError:
        raise ControlledPrivateNetworkDispatchError(
            "staging_private_dispatch_provisioning_invalid"
        ) from None
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
        TypeError,
        RecursionError,
    ):
        raise ControlledPrivateNetworkDispatchError(
            "staging_private_dispatch_provisioning_invalid"
        ) from None
    if type(body) is not dict or _canonical_json(body) != request.canonical_request_bytes:
        raise ControlledPrivateNetworkDispatchError(
            "staging_private_dispatch_provisioning_invalid"
        )
    try:
        binding = build_trusted_plan_provisioning_binding(
            endpoint,
            environment="staging",
        )
    except TrustedPlanProvisioningError:
        raise ControlledPrivateNetworkDispatchError(
            "staging_private_dispatch_provisioning_invalid"
        ) from None
    expected_public = {
        "version": TRUSTED_PLAN_PROVISIONING_VERSION,
        "algorithm": TRUSTED_PLAN_PROVISIONING_ALGORITHM,
        "environment": "staging",
        "callerIdentity": binding.caller_identity,
        "engine": endpoint.name,
        "audienceIdentity": binding.audience_identity,
        "credentialKey": binding.credential_key,
        "origin": binding.origin,
        "method": TRUSTED_PLAN_PROVISIONING_METHOD,
        "path": TRUSTED_PLAN_PROVISIONING_PATH,
        "jobId": capsule.dispatch_identity.job_id,
        "runId": capsule.dispatch_identity.run_id,
        "orchestrationPlanId": capsule.dispatch_identity.plan_id,
        "orchestrationPlanSha256": capsule.dispatch_identity.plan_sha256,
        "canonicalPlanSha256": capsule.canonical_plan_sha256,
        "canonicalPlanBytes": len(capsule.canonical_plan_bytes),
    }
    expected_keys = set(expected_public) | {
        "credentialGenerationId",
        "issuedAt",
        "nonce",
        "canonicalPlanB64",
    }
    if set(body) != expected_keys:
        raise ControlledPrivateNetworkDispatchError(
            "staging_private_dispatch_provisioning_invalid"
        )
    if (
        body.get("credentialGenerationId") != request.credential_generation_id
        or body.get("issuedAt") != request.issued_at
    ):
        raise ControlledPrivateNetworkDispatchError(
            "staging_private_dispatch_provisioning_invalid"
        )
    for key, expected in expected_public.items():
        if body.get(key) != expected:
            raise ControlledPrivateNetworkDispatchError(
                "staging_private_dispatch_provisioning_invalid"
            )
    encoded = body.get("canonicalPlanB64")
    if type(encoded) is not str:
        raise ControlledPrivateNetworkDispatchError(
            "staging_private_dispatch_provisioning_invalid"
        )
    try:
        decoded = base64.b64decode(encoded.encode("ascii"), validate=True)
    except (UnicodeEncodeError, ValueError):
        raise ControlledPrivateNetworkDispatchError(
            "staging_private_dispatch_provisioning_invalid"
        ) from None
    if decoded != capsule.canonical_plan_bytes:
        raise ControlledPrivateNetworkDispatchError(
            "staging_private_dispatch_provisioning_invalid"
        )


def _validate_dispatch_wire(
    wire: ControlledStagingDispatchWireRequest,
    *,
    endpoint: EngineEndpoint,
    capsule: DispatchInputCapsule,
    now_seconds: int,
):
    if type(wire) is not ControlledStagingDispatchWireRequest:
        raise ControlledPrivateNetworkDispatchError(
            "staging_private_dispatch_wire_invalid"
        )
    identity = capsule.dispatch_identity
    try:
        expected_body = dispatch_identity_payload(identity)
        binding = build_engine_auth_binding(endpoint, "staging")
        target = build_engine_dispatch_target(binding, endpoint)
        parsed = parse_controlled_staging_dispatch_wire(
            target=target,
            headers=wire.headers,
            body=wire.body,
            observed_method=target.method,
            observed_path=target.path,
        )
    except (
        DispatchIdentityError,
        ServiceAuthError,
        DispatchTargetError,
        ControlledStagingDispatchWireError,
    ):
        raise ControlledPrivateNetworkDispatchError(
            "staging_private_dispatch_wire_invalid"
        ) from None
    if (
        wire.body != expected_body
        or parsed.envelope.engine != identity.engine
        or parsed.envelope.payload_sha256 != identity.identity_sha256
        or parsed.envelope.timestamp > now_seconds + MAX_FUTURE_SKEW_SECONDS
        or now_seconds - parsed.envelope.timestamp > MAX_REQUEST_AGE_SECONDS
    ):
        raise ControlledPrivateNetworkDispatchError(
            "staging_private_dispatch_wire_invalid"
        )
    return target


def _exact_headers(
    pairs: Sequence[tuple[str, str]],
) -> tuple[tuple[str, str], ...]:
    if type(pairs) not in {tuple, list}:
        raise ControlledPrivateNetworkDispatchError(
            "staging_private_dispatch_headers_invalid"
        )
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for pair in pairs:
        if type(pair) is not tuple or len(pair) != 2:
            raise ControlledPrivateNetworkDispatchError(
                "staging_private_dispatch_headers_invalid"
            )
        name, value = pair
        if type(name) is not str or type(value) is not str:
            raise ControlledPrivateNetworkDispatchError(
                "staging_private_dispatch_headers_invalid"
            )
        lowered = name.lower()
        if (
            lowered in seen
            or name != name.strip()
            or value != value.strip()
            or not name
            or any(ord(char) < 0x20 or ord(char) == 0x7F for char in name + value)
        ):
            raise ControlledPrivateNetworkDispatchError(
                "staging_private_dispatch_headers_invalid"
            )
        seen.add(lowered)
        result.append((lowered, value))
    return tuple(result)


def _default_private_post(
    origin: str,
    path: str,
    headers: tuple[tuple[str, str], ...],
    body: bytes,
    timeout_seconds: int,
) -> PrivateControlHttpResponse:
    """Perform exactly one direct HTTP POST; no proxy or redirect layer exists."""

    parsed = urlsplit(origin)
    if (
        parsed.scheme != "http"
        or parsed.hostname is None
        or parsed.port is None
        or path not in {TRUSTED_PLAN_PROVISIONING_PATH, DISPATCH_PATH}
        or not path.startswith("/")
        or "?" in path
        or "#" in path
    ):
        raise ControlledPrivateNetworkDispatchError(
            "staging_private_dispatch_transport_target_invalid"
        )
    connection = HTTPConnection(parsed.hostname, parsed.port, timeout=timeout_seconds)
    try:
        connection.request(
            "POST",
            path,
            body=body,
            headers=dict(headers),
        )
        response: HTTPResponse = connection.getresponse()
        response_body = response.read(MAX_CONTROL_RESPONSE_BYTES + 1)
        if len(response_body) > MAX_CONTROL_RESPONSE_BYTES:
            raise ControlledPrivateNetworkDispatchError(
                "staging_private_dispatch_response_too_large"
            )
        return PrivateControlHttpResponse(
            status=int(response.status),
            content_type=response.getheader("Content-Type", ""),
            body=response_body,
            location=response.getheader("Location"),
        )
    except ControlledPrivateNetworkDispatchError:
        raise
    except (TimeoutError, socket.timeout, OSError):
        raise ControlledPrivateNetworkDispatchError(
            "staging_private_dispatch_transport_failed"
        ) from None
    except Exception:
        raise ControlledPrivateNetworkDispatchError(
            "staging_private_dispatch_transport_failed"
        ) from None
    finally:
        try:
            connection.close()
        except Exception:
            pass


def _send_once(
    transport: PrivateControlTransport,
    *,
    origin: str,
    path: str,
    headers: tuple[tuple[str, str], ...],
    body: bytes,
    timeout_seconds: int,
) -> PrivateControlHttpResponse:
    if not callable(transport):
        raise ControlledPrivateNetworkDispatchError(
            "staging_private_dispatch_transport_invalid"
        )
    try:
        response = transport(origin, path, headers, body, timeout_seconds)
    except ControlledPrivateNetworkDispatchError:
        raise
    except Exception:
        raise ControlledPrivateNetworkDispatchError(
            "staging_private_dispatch_transport_failed"
        ) from None
    if type(response) is not PrivateControlHttpResponse:
        raise ControlledPrivateNetworkDispatchError(
            "staging_private_dispatch_transport_response_invalid"
        )
    if 300 <= response.status <= 399 or response.location is not None:
        raise ControlledPrivateNetworkDispatchError(
            "staging_private_dispatch_redirect_forbidden"
        )
    return response


def _accepted_response(
    response: PrivateControlHttpResponse,
    *,
    expected_status: int,
    expected_kind: str,
    capsule: DispatchInputCapsule,
) -> dict[str, Any]:
    if response.status != expected_status:
        raise ControlledPrivateNetworkDispatchError(
            "staging_private_dispatch_receiver_rejected"
        )
    if response.content_type != EXPECTED_RESPONSE_CONTENT_TYPE:
        raise ControlledPrivateNetworkDispatchError(
            "staging_private_dispatch_response_invalid"
        )
    value = _strict_json(response.body)
    if set(value) != {"status", "kind", "evidence", "engineExecutionAllowed"}:
        raise ControlledPrivateNetworkDispatchError(
            "staging_private_dispatch_response_invalid"
        )
    evidence = value.get("evidence")
    identity = capsule.dispatch_identity
    if (
        value.get("status") != "accepted"
        or value.get("kind") != expected_kind
        or value.get("engineExecutionAllowed") is not False
        or type(evidence) is not dict
        or evidence.get("engine") != identity.engine
        or evidence.get("jobId") != identity.job_id
        or evidence.get("runId") != identity.run_id
        or evidence.get("engineExecutionAllowed") is not False
        or evidence.get("retryAllowed") is not False
    ):
        raise ControlledPrivateNetworkDispatchError(
            "staging_private_dispatch_response_invalid"
        )
    if expected_kind == "dispatch":
        if (
            evidence.get("dispatchIdentitySha256") != identity.identity_sha256
            or evidence.get("receiverAuthenticated") is not True
            or evidence.get("trustedPlanConverged") is not True
            or evidence.get("replayReserved") is not True
            or evidence.get("sourceAccessAllowed") is not False
            or evidence.get("jobStateMutationAllowed") is not False
        ):
            raise ControlledPrivateNetworkDispatchError(
                "staging_private_dispatch_response_invalid"
            )
    elif expected_kind == "trusted_plan":
        if (
            evidence.get("canonicalPlanSha256") != capsule.canonical_plan_sha256
            or evidence.get("authenticated") is not True
            or evidence.get("persistenceState") != "written"
            or evidence.get("rawPlanExportAllowed") is not False
            or evidence.get("jobStateMutationAllowed") is not False
        ):
            raise ControlledPrivateNetworkDispatchError(
                "staging_private_dispatch_response_invalid"
            )
    return value


def dispatch_controlled_private_network_once(
    *,
    minimum_slice: MinimumStagingVerticalSliceResult,
    provider: StagingUploadProvider,
    endpoint: EngineEndpoint,
    capsule: DispatchInputCapsule,
    provisioning_request: TrustedPlanProvisioningRequest,
    dispatch_wire: ControlledStagingDispatchWireRequest,
    now_seconds: int,
    timeout_seconds: int = 10,
    transport: PrivateControlTransport = _default_private_post,
) -> ControlledPrivateNetworkDispatchResult:
    """Provision + dispatch exactly once after durable dispatching(2) publication.

    If revision 2 already exists, this function performs zero network operations.
    Any network failure after a newly-written revision 2 is intentionally left for
    reconciliation; automatic retry would risk duplicate receiver side effects.
    """

    if type(minimum_slice) is not MinimumStagingVerticalSliceResult:
        raise ControlledPrivateNetworkDispatchError(
            "staging_private_dispatch_input_invalid"
        )
    if type(provider) is not StagingUploadProvider:
        raise ControlledPrivateNetworkDispatchError(
            "staging_private_dispatch_input_invalid"
        )
    checked_endpoint = _require_endpoint(endpoint)
    checked_now = _require_now(now_seconds)
    checked_timeout = _require_timeout(timeout_seconds)
    if type(capsule) is not DispatchInputCapsule:
        raise ControlledPrivateNetworkDispatchError(
            "staging_private_dispatch_capsule_invalid"
        )
    try:
        verify_dispatch_input_capsule(capsule)
    except DispatchInputCapsuleError:
        raise ControlledPrivateNetworkDispatchError(
            "staging_private_dispatch_capsule_invalid"
        ) from None
    identity = capsule.dispatch_identity
    if identity.engine != checked_endpoint.name:
        raise ControlledPrivateNetworkDispatchError(
            "staging_private_dispatch_capsule_invalid"
        )

    _decode_provisioning_body(
        provisioning_request,
        endpoint=checked_endpoint,
        capsule=capsule,
        now_seconds=checked_now,
    )
    target = _validate_dispatch_wire(
        dispatch_wire,
        endpoint=checked_endpoint,
        capsule=capsule,
        now_seconds=checked_now,
    )
    if (
        target.origin != checked_endpoint.base_url
        or target.method != DISPATCH_METHOD
        or target.path != DISPATCH_PATH
    ):
        raise ControlledPrivateNetworkDispatchError(
            "staging_private_dispatch_target_invalid"
        )

    provisioning_headers = _exact_headers(
        (
            ("content-type", "application/json"),
            ("content-length", str(len(provisioning_request.canonical_request_bytes))),
            (PROVISIONING_SIGNATURE_HEADER, provisioning_request.signature),
        )
    )
    dispatch_headers = _exact_headers(
        (
            ("content-type", "application/json"),
            ("content-length", str(len(dispatch_wire.body))),
            *dispatch_wire.headers,
        )
    )

    try:
        dispatching = transition_controlled_staging_queued_to_dispatching(
            minimum_slice=minimum_slice,
            provider=provider,
            endpoint=checked_endpoint,
        )
    except ControlledStagingDispatchingTransitionError as exc:
        raise ControlledPrivateNetworkDispatchError(exc.category) from None
    if (
        dispatching.job_id != identity.job_id
        or dispatching.engine != identity.engine
        or dispatching.run_id != identity.run_id
        or dispatching.dispatch_identity_sha256 != identity.identity_sha256
        or dispatching.state != "dispatching"
        or dispatching.revision != 2
        or dispatching.reconciliation_required is not True
    ):
        raise ControlledPrivateNetworkDispatchError(
            "staging_private_dispatch_dispatching_invalid"
        )
    if dispatching.persistence_state != "written":
        raise ControlledPrivateNetworkDispatchError(
            "staging_private_dispatch_reconciliation_required"
        )

    provision_response = _send_once(
        transport,
        origin=target.origin,
        path=TRUSTED_PLAN_PROVISIONING_PATH,
        headers=provisioning_headers,
        body=provisioning_request.canonical_request_bytes,
        timeout_seconds=checked_timeout,
    )
    _accepted_response(
        provision_response,
        expected_status=201,
        expected_kind="trusted_plan",
        capsule=capsule,
    )

    dispatch_response = _send_once(
        transport,
        origin=target.origin,
        path=target.path,
        headers=dispatch_headers,
        body=dispatch_wire.body,
        timeout_seconds=checked_timeout,
    )
    _accepted_response(
        dispatch_response,
        expected_status=202,
        expected_kind="dispatch",
        capsule=capsule,
    )

    return ControlledPrivateNetworkDispatchResult(
        version=CONTROLLED_PRIVATE_NETWORK_DISPATCH_VERSION,
        job_id=identity.job_id,
        engine=identity.engine,
        run_id=identity.run_id,
        dispatch_identity_sha256=identity.identity_sha256,
        target_origin=target.origin,
        dispatching_revision=dispatching.revision,
        provisioning_http_status=provision_response.status,
        dispatch_http_status=dispatch_response.status,
        provisioning_attempt_count=1,
        dispatch_attempt_count=1,
        reconciliation_required_on_restart=True,
    )
