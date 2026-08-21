from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
from pathlib import Path
import secrets
import sys
import tempfile
import threading
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

import test_safe_upload_finalization as helpers
from scoremosaic_gateway.config import EngineEndpoint
from scoremosaic_gateway.controlled_private_network_dispatch import (
    ControlledPrivateNetworkDispatchError,
    PrivateControlHttpResponse,
    dispatch_controlled_private_network_once,
)
from scoremosaic_gateway.controlled_staging_dispatch_intent import (
    persist_controlled_staging_dispatch_intent,
)
from scoremosaic_gateway.controlled_staging_dispatch_wire import (
    serialize_controlled_staging_dispatch_wire,
)
from scoremosaic_gateway.controlled_staging_dispatching_transition import (
    recover_controlled_staging_dispatching_run,
)
from scoremosaic_gateway.controlled_staging_transition_state import transition_record_path
from scoremosaic_gateway.controlled_staging_job_lifecycle import (
    run_controlled_staging_job_lifecycle,
)
from scoremosaic_gateway.controlled_staging_queued_transition import (
    queue_controlled_staging_run,
)
from scoremosaic_gateway.credential_rotation import (
    build_rotation_set,
    resolve_engine_credential_generation,
    sign_rotation_authenticated_request,
)
from scoremosaic_gateway.dispatch_identity import (
    build_dispatch_identity,
    dispatch_identity_payload,
)
from scoremosaic_gateway.dispatch_input_capsule import build_dispatch_input_capsule
from scoremosaic_gateway.dispatch_target import (
    APPROVED_ENGINE_ORIGINS,
    build_engine_dispatch_target,
)
from scoremosaic_gateway.minimum_staging_vertical_slice import (
    StagingUploadProvider,
    run_minimum_staging_vertical_slice,
)
from scoremosaic_gateway.orchestration import ENGINE_NAMES, build_orchestration_plan
from scoremosaic_gateway.service_auth import build_engine_auth_binding
from scoremosaic_gateway.trusted_plan_provisioning import (
    build_trusted_plan_provisioning_binding,
    build_trusted_plan_provisioning_request,
    resolve_trusted_plan_provisioning_credential,
)


class ControlledPrivateNetworkDispatchTests(unittest.TestCase):
    def setUp(self) -> None:
        fixture = helpers.SafeUploadFinalizationContractTests(methodName="runTest")
        fixture.setUp()
        self.admission = fixture._admission()
        self.session_policy = fixture.session_policy
        self.source = helpers.PNG_1X1

        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.provider = StagingUploadProvider(
            self.root,
            state_integrity_key=secrets.token_bytes(32),
        )
        self.minimum_slice = run_minimum_staging_vertical_slice(
            admission=self.admission,
            session_policy=self.session_policy,
            payload=self.source,
            original_filename="scan.png",
            declared_media_type="image/png",
            observed_at_epoch_s=self.admission.evaluated_at_epoch_s,
            provider=self.provider,
        )
        run_controlled_staging_job_lifecycle(
            minimum_slice=self.minimum_slice,
            provider=self.provider,
        )

        self.endpoint = EngineEndpoint(
            "audiveris",
            APPROVED_ENGINE_ORIGINS["staging"]["audiveris"],
        )
        self.queued = queue_controlled_staging_run(
            minimum_slice=self.minimum_slice,
            provider=self.provider,
            engine=self.endpoint.name,
        )
        self.intent = persist_controlled_staging_dispatch_intent(
            minimum_slice=self.minimum_slice,
            provider=self.provider,
            endpoint=self.endpoint,
        )

        binding = self.minimum_slice.binding
        self.plan = build_orchestration_plan(
            binding.job_id,
            source_artifact_ref=binding.source_artifact_ref,
            source_sha256=binding.document_sha256,
            source_size_bytes=binding.source_size_bytes,
            source_media_type=binding.source_media_type,
            requested_engines=ENGINE_NAMES,
        ).as_dict()
        self.identity = build_dispatch_identity(self.plan, self.endpoint.name)
        self.capsule = build_dispatch_input_capsule(
            self.plan,
            self.identity,
            [self.source],
        )

        self.now = 1_800_500_000
        self.provisioning_secret = secrets.token_bytes(32)
        self.provisioning_generation = "gen-stage4d-provision"
        provisioning_binding = build_trusted_plan_provisioning_binding(
            self.endpoint,
            environment="staging",
        )
        provisioning_credential = resolve_trusted_plan_provisioning_credential(
            provisioning_binding,
            generation_id=self.provisioning_generation,
            resolver=lambda key, generation: (
                self.provisioning_secret
                if key == provisioning_binding.credential_key
                and generation == self.provisioning_generation
                else None
            ),
        )
        self.provisioning_credential = provisioning_credential
        self.provisioning_request = self._provisioning_request(self.now)

        self.dispatch_secret = secrets.token_bytes(32)
        self.dispatch_generation = "gen-stage4d-dispatch"
        dispatch_binding = build_engine_auth_binding(self.endpoint, "staging")
        dispatch_credential = resolve_engine_credential_generation(
            dispatch_binding,
            self.dispatch_generation,
            lambda key, generation: (
                self.dispatch_secret
                if key == dispatch_binding.credential_key
                and generation == self.dispatch_generation
                else None
            ),
        )
        rotation = build_rotation_set(
            current=dispatch_credential,
            previous=None,
            rotation_started_at=self.now - 1,
            previous_valid_until=None,
        )
        target = build_engine_dispatch_target(dispatch_binding, self.endpoint)
        body = dispatch_identity_payload(self.identity)
        signed = sign_rotation_authenticated_request(
            rotation,
            method=target.method,
            path=target.path,
            timestamp=self.now,
            nonce="22" * 16,
            payload=body,
            now_seconds=self.now,
        )
        self.dispatch_wire = serialize_controlled_staging_dispatch_wire(
            target=target,
            request=signed,
            payload=body,
        )

    def _provisioning_request(self, issued_at: int):
        return build_trusted_plan_provisioning_request(
            capsule=self.capsule,
            credential=self.provisioning_credential,
            issued_at=issued_at,
            nonce="11" * 16,
        )

    def _accepted(self, kind: str) -> bytes:
        if kind == "trusted_plan":
            evidence = {
                "version": "scoremosaic-trusted-plan-provisioning-v1",
                "engine": self.identity.engine,
                "environment": "staging",
                "jobId": self.identity.job_id,
                "runId": self.identity.run_id,
                "credentialGenerationId": self.provisioning_generation,
                "issuedAt": self.now,
                "requestSha256": "1" * 64,
                "canonicalPlanSha256": self.capsule.canonical_plan_sha256,
                "nonceSha256": "2" * 64,
                "persistenceState": "written",
                "authenticated": True,
                "credentialExportAllowed": False,
                "rawPlanExportAllowed": False,
                "networkProvisioningAllowed": False,
                "networkDispatchAllowed": False,
                "retryAllowed": False,
                "jobStateMutationAllowed": False,
                "engineExecutionAllowed": False,
            }
        else:
            evidence = {
                "engine": self.identity.engine,
                "environment": "staging",
                "jobId": self.identity.job_id,
                "runId": self.identity.run_id,
                "dispatchIdentitySha256": self.identity.identity_sha256,
                "credentialGenerationId": self.dispatch_generation,
                "requestTimestamp": self.now,
                "requestNonceSha256": "3" * 64,
                "payloadSha256": self.identity.identity_sha256,
                "replayReservationKey": "4" * 64,
                "replayExpiresAt": self.now + 420,
                "receiverAuthenticated": True,
                "trustedPlanConverged": True,
                "replayReserved": True,
                "engineExecutionAllowed": False,
                "retryAllowed": False,
                "sourceAccessAllowed": False,
                "jobStateMutationAllowed": False,
            }
        payload = {
            "status": "accepted",
            "kind": kind,
            "evidence": evidence,
            "engineExecutionAllowed": False,
        }
        return json.dumps(
            payload,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")

    def _transport(self, calls: list[tuple]):
        lock = threading.Lock()

        def transport(origin, path, headers, body, timeout):
            with lock:
                calls.append((origin, path, headers, body, timeout))
            if path == "/internal/trusted-plan":
                return PrivateControlHttpResponse(
                    status=201,
                    content_type="application/json; charset=utf-8",
                    body=self._accepted("trusted_plan"),
                )
            if path == "/internal/transcribe":
                return PrivateControlHttpResponse(
                    status=202,
                    content_type="application/json; charset=utf-8",
                    body=self._accepted("dispatch"),
                )
            raise AssertionError(path)

        return transport

    def _dispatch(self, *, transport, now=None, endpoint=None, provisioning=None, wire=None):
        return dispatch_controlled_private_network_once(
            minimum_slice=self.minimum_slice,
            provider=self.provider,
            endpoint=self.endpoint if endpoint is None else endpoint,
            capsule=self.capsule,
            provisioning_request=(
                self.provisioning_request if provisioning is None else provisioning
            ),
            dispatch_wire=self.dispatch_wire if wire is None else wire,
            now_seconds=self.now if now is None else now,
            timeout_seconds=7,
            transport=transport,
        )

    def test_one_shot_provision_then_dispatch_is_fixed_private_and_non_executable(self) -> None:
        calls: list[tuple] = []
        result = self._dispatch(transport=self._transport(calls))

        self.assertEqual(len(calls), 2)
        self.assertEqual(
            [call[1] for call in calls],
            ["/internal/trusted-plan", "/internal/transcribe"],
        )
        for origin, path, headers, body, timeout in calls:
            self.assertEqual(origin, APPROVED_ENGINE_ORIGINS["staging"]["audiveris"])
            self.assertIn(path, {"/internal/trusted-plan", "/internal/transcribe"})
            self.assertEqual(timeout, 7)
            self.assertNotEqual(body, self.source)
            self.assertNotIn(self.source, body)
            self.assertIn(("content-type", "application/json"), headers)

        self.assertEqual((result.provisioning_attempt_count, result.dispatch_attempt_count), (1, 1))
        self.assertTrue(result.network_dispatch_performed)
        self.assertTrue(result.trusted_plan_provisioned)
        self.assertTrue(result.receiver_authenticated)
        self.assertFalse(result.source_transfer_allowed)
        self.assertFalse(result.engine_execution_allowed)
        self.assertFalse(result.result_persistence_allowed)
        self.assertFalse(result.retry_allowed)
        self.assertFalse(result.redirect_allowed)
        self.assertFalse(result.post_dispatch_job_mutation_allowed)
        self.assertTrue(result.reconciliation_required_on_restart)

        recovery = recover_controlled_staging_dispatching_run(
            minimum_slice=self.minimum_slice,
            provider=self.provider,
            endpoint=self.endpoint,
        )
        self.assertEqual((recovery.state, recovery.revision), ("dispatching", 2))
        self.assertTrue(recovery.reconciliation_required)
        self.assertFalse(recovery.retry_allowed)
        self.assertFalse(recovery.network_dispatch_allowed)
        self.assertFalse(recovery.automatic_execution_allowed)

    def test_arbitrary_origin_fails_before_revision_two_or_network(self) -> None:
        calls: list[tuple] = []
        malicious = EngineEndpoint("audiveris", "http://169.254.169.254:80")
        with self.assertRaises(ControlledPrivateNetworkDispatchError) as ctx:
            self._dispatch(
                transport=self._transport(calls),
                endpoint=malicious,
            )
        self.assertEqual(ctx.exception.category, "staging_private_dispatch_endpoint_invalid")
        self.assertEqual(calls, [])
        rev2 = transition_record_path(
            self.provider,
            job_id=self.queued.job_id,
            run_id=self.queued.run_id,
            revision=2,
        )
        self.assertFalse(rev2.exists())

    def test_redirect_is_forbidden_and_restart_never_resends(self) -> None:
        calls: list[tuple] = []

        def redirect(origin, path, headers, body, timeout):
            calls.append((origin, path))
            return PrivateControlHttpResponse(
                status=307,
                content_type="text/plain",
                body=b"",
                location="http://attacker.invalid/",
            )

        with self.assertRaises(ControlledPrivateNetworkDispatchError) as ctx:
            self._dispatch(transport=redirect)
        self.assertEqual(ctx.exception.category, "staging_private_dispatch_redirect_forbidden")
        self.assertEqual(len(calls), 1)

        with self.assertRaises(ControlledPrivateNetworkDispatchError) as retry_ctx:
            self._dispatch(transport=redirect)
        self.assertEqual(
            retry_ctx.exception.category,
            "staging_private_dispatch_reconciliation_required",
        )
        self.assertEqual(len(calls), 1)

    def test_transport_exception_is_bounded_and_retry_makes_zero_more_calls(self) -> None:
        calls = 0
        sensitive = "TOKEN_DO_NOT_LEAK /private/socket/path"

        def broken(origin, path, headers, body, timeout):
            nonlocal calls
            calls += 1
            raise RuntimeError(sensitive)

        with self.assertRaises(ControlledPrivateNetworkDispatchError) as ctx:
            self._dispatch(transport=broken)
        self.assertEqual(ctx.exception.category, "staging_private_dispatch_transport_failed")
        self.assertNotIn(sensitive, str(ctx.exception))
        self.assertEqual(calls, 1)

        with self.assertRaises(ControlledPrivateNetworkDispatchError) as retry_ctx:
            self._dispatch(transport=broken)
        self.assertEqual(
            retry_ctx.exception.category,
            "staging_private_dispatch_reconciliation_required",
        )
        self.assertEqual(calls, 1)

    def test_receiver_execution_claim_or_malformed_json_fails_closed(self) -> None:
        calls: list[tuple] = []

        def malicious_response(origin, path, headers, body, timeout):
            calls.append((origin, path))
            if path == "/internal/trusted-plan":
                return PrivateControlHttpResponse(
                    201,
                    "application/json; charset=utf-8",
                    self._accepted("trusted_plan"),
                )
            payload = json.loads(self._accepted("dispatch").decode("ascii"))
            payload["engineExecutionAllowed"] = True
            return PrivateControlHttpResponse(
                202,
                "application/json; charset=utf-8",
                json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("ascii"),
            )

        with self.assertRaises(ControlledPrivateNetworkDispatchError) as ctx:
            self._dispatch(transport=malicious_response)
        self.assertEqual(ctx.exception.category, "staging_private_dispatch_response_invalid")
        self.assertEqual(len(calls), 2)

    def test_stale_dispatch_wire_fails_before_revision_two_and_network(self) -> None:
        calls: list[tuple] = []
        future_now = self.now + 121
        fresh_provisioning = self._provisioning_request(future_now)
        with self.assertRaises(ControlledPrivateNetworkDispatchError) as ctx:
            self._dispatch(
                transport=self._transport(calls),
                now=future_now,
                provisioning=fresh_provisioning,
            )
        self.assertEqual(ctx.exception.category, "staging_private_dispatch_wire_invalid")
        self.assertEqual(calls, [])

    def test_tampered_dispatch_body_fails_before_network(self) -> None:
        calls: list[tuple] = []
        tampered = replace(self.dispatch_wire, body=self.dispatch_wire.body + b" ")
        with self.assertRaises(ControlledPrivateNetworkDispatchError):
            self._dispatch(transport=self._transport(calls), wire=tampered)
        self.assertEqual(calls, [])

    def test_concurrent_calls_have_one_network_winner_and_no_duplicate_send(self) -> None:
        calls: list[tuple] = []
        transport = self._transport(calls)

        def attempt():
            try:
                result = self._dispatch(transport=transport)
                return ("accepted", result.dispatch_http_status)
            except ControlledPrivateNetworkDispatchError as exc:
                return ("rejected", exc.category)

        with ThreadPoolExecutor(max_workers=8) as pool:
            observed = list(pool.map(lambda _index: attempt(), range(8)))

        accepted = [item for item in observed if item[0] == "accepted"]
        rejected = [item for item in observed if item[0] == "rejected"]
        self.assertEqual(len(accepted), 1, observed)
        self.assertEqual(len(rejected), 7, observed)
        self.assertTrue(
            all(
                item[1] == "staging_private_dispatch_reconciliation_required"
                for item in rejected
            ),
            observed,
        )
        self.assertEqual(len(calls), 2, calls)
        self.assertEqual(
            [call[1] for call in calls],
            ["/internal/trusted-plan", "/internal/transcribe"],
        )


if __name__ == "__main__":
    unittest.main()
