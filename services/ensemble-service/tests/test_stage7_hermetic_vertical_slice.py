from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import secrets
import sys
import tempfile
import unittest

TEST_FILE = Path(__file__).resolve()
ENSEMBLE_ROOT = TEST_FILE.parents[1]
REPO_ROOT = TEST_FILE.parents[3]
GATEWAY_ROOT = REPO_ROOT / "services" / "omr-gateway"
sys.path.insert(0, str(ENSEMBLE_ROOT / "src"))
sys.path.insert(0, str(GATEWAY_ROOT / "src"))
sys.path.insert(0, str(GATEWAY_ROOT / "tests"))

import test_safe_upload_finalization as upload_helpers

from scoremosaic_ensemble.convergence import converge_verified_candidates
from scoremosaic_gateway.candidate_convergence_handoff import (
    load_verified_candidate_handoffs,
)
from scoremosaic_gateway.config import EngineEndpoint
from scoremosaic_gateway.controlled_private_execution import (
    PrivateExecutionHttpResponse,
    execute_controlled_private_engine_once,
    execution_trigger_credential_key,
)
from scoremosaic_gateway.controlled_private_network_dispatch import (
    PrivateControlHttpResponse,
    dispatch_controlled_private_network_once,
)
from scoremosaic_gateway.controlled_private_source_delivery import (
    PrivateSourceHttpResponse,
    deliver_controlled_private_source_once,
)
from scoremosaic_gateway.controlled_staging_dispatch_intent import (
    persist_controlled_staging_dispatch_intent,
)
from scoremosaic_gateway.controlled_staging_dispatch_wire import (
    serialize_controlled_staging_dispatch_wire,
)
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
    build_dispatch_result_identity,
    dispatch_identity_payload,
)
from scoremosaic_gateway.dispatch_input_capsule import build_dispatch_input_capsule
from scoremosaic_gateway.dispatch_target import (
    APPROVED_ENGINE_ORIGINS,
    build_engine_dispatch_target,
)
from scoremosaic_gateway.engine_result_ingestion import (
    build_engine_result_frame,
    failure_outcome,
    ingest_authenticated_engine_result,
    persist_normalized_candidate_once,
    success_outcome,
)
from scoremosaic_gateway.minimum_staging_vertical_slice import (
    StagingUploadProvider,
    run_minimum_staging_vertical_slice,
)
from scoremosaic_gateway.orchestration import ENGINE_NAMES, build_orchestration_plan
from scoremosaic_gateway.service_auth import (
    EngineCredential,
    MIN_CREDENTIAL_BYTES,
    build_engine_auth_binding,
)
from scoremosaic_gateway.source_delivery import build_source_delivery_binding
from scoremosaic_gateway.trusted_plan_provisioning import (
    build_trusted_plan_provisioning_binding,
    build_trusted_plan_provisioning_request,
    resolve_trusted_plan_provisioning_credential,
)

MUSICXML = b'''<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0">
 <part-list><score-part id="P1"><part-name>Music</part-name></score-part></part-list>
 <part id="P1"><measure number="1"><attributes><divisions>1</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes><note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><type>whole</type></note></measure></part>
</score-partwise>'''


class Stage7HermeticVerticalSliceTests(unittest.TestCase):
    """Compose real Stage 5-7 repository contracts with hermetic remote fixtures.

    Network and engine processes are not live here. Fixed transport functions act
    only as the remote boundary while the Gateway dispatch/signing, durable state,
    source delivery, one-shot execution fence, result authentication, candidate
    persistence, Stage 7 handoff, Canonical normalization and comparator are real
    repository implementations.
    """

    def setUp(self) -> None:
        fixture = upload_helpers.SafeUploadFinalizationContractTests(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.admission = fixture._admission()
        self.session_policy = fixture.session_policy
        self.source = upload_helpers.PNG_1X1

        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.provider = StagingUploadProvider(
            Path(self.temp.name) / "state",
            state_integrity_key=secrets.token_bytes(32),
        )
        self.minimum = run_minimum_staging_vertical_slice(
            admission=self.admission,
            session_policy=self.session_policy,
            payload=self.source,
            original_filename="score.png",
            declared_media_type="image/png",
            observed_at_epoch_s=self.admission.evaluated_at_epoch_s,
            provider=self.provider,
        )
        run_controlled_staging_job_lifecycle(
            minimum_slice=self.minimum,
            provider=self.provider,
        )
        binding = self.minimum.binding
        self.plan = build_orchestration_plan(
            binding.job_id,
            source_artifact_ref=binding.source_artifact_ref,
            source_sha256=binding.document_sha256,
            source_size_bytes=binding.source_size_bytes,
            source_media_type=binding.source_media_type,
            requested_engines=ENGINE_NAMES,
        ).as_dict()
        self.now = 1_800_900_000

    @staticmethod
    def _canonical(value: dict) -> bytes:
        return json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")

    @staticmethod
    def _diagnostic(engine: str) -> bytes:
        return Stage7HermeticVerticalSliceTests._canonical(
            {
                "engine": engine,
                "engineVersion": "hermetic-1",
                "modelVersion": "hermetic-model-1",
                "status": "success",
                "warnings": [],
            }
        )

    def _control_response(self, *, kind: str, identity, capsule, provision_generation: str, dispatch_generation: str):
        if kind == "trusted_plan":
            evidence = {
                "version": "scoremosaic-trusted-plan-provisioning-v1",
                "engine": identity.engine,
                "environment": "staging",
                "jobId": identity.job_id,
                "runId": identity.run_id,
                "credentialGenerationId": provision_generation,
                "issuedAt": self.now,
                "requestSha256": "1" * 64,
                "canonicalPlanSha256": capsule.canonical_plan_sha256,
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
            status = 201
        else:
            evidence = {
                "engine": identity.engine,
                "environment": "staging",
                "jobId": identity.job_id,
                "runId": identity.run_id,
                "dispatchIdentitySha256": identity.identity_sha256,
                "credentialGenerationId": dispatch_generation,
                "requestTimestamp": self.now,
                "requestNonceSha256": "3" * 64,
                "payloadSha256": identity.identity_sha256,
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
            status = 202
        body = self._canonical(
            {
                "status": "accepted",
                "kind": kind,
                "evidence": evidence,
                "engineExecutionAllowed": False,
            }
        )
        return PrivateControlHttpResponse(
            status=status,
            content_type="application/json; charset=utf-8",
            body=body,
        )

    def _source_response(self, *, identity, generation: str, headers, body: bytes):
        values = dict(headers)
        evidence = {
            "version": "scoremosaic-source-delivery-v1",
            "environment": "staging",
            "engine": identity.engine,
            "jobId": identity.job_id,
            "runId": identity.run_id,
            "dispatchIdentitySha256": identity.identity_sha256,
            "sourceArtifactId": identity.source_artifact_id,
            "sourceSizeBytes": len(body),
            "sourceSha256": sha256(body).hexdigest(),
            "sourceMediaType": values["x-scoremosaic-source-media-type"],
            "credentialGenerationId": generation,
            "timestamp": int(values["x-scoremosaic-source-timestamp"]),
            "nonceSha256": sha256(
                values["x-scoremosaic-source-nonce"].encode("ascii")
            ).hexdigest(),
            "persistenceState": "written",
            "authenticated": True,
            "trustedPlanConverged": True,
            "sourcePersisted": True,
            "engineExecutionAllowed": False,
            "retryAllowed": False,
        }
        return PrivateSourceHttpResponse(
            status=201,
            content_type="application/json; charset=utf-8",
            body=self._canonical(
                {
                    "status": "accepted",
                    "kind": "source",
                    "evidence": evidence,
                    "engineExecutionAllowed": False,
                }
            ),
        )

    def _execution_response(self, *, identity, capsule, generation: str, headers, body: bytes):
        values = dict(headers)
        request = json.loads(body)
        output_sha = sha256(b"hermetic-engine-output-metadata").hexdigest()
        execution = {
            "version": "scoremosaic-controlled-engine-execution-v1",
            "environment": "staging",
            "engine": identity.engine,
            "jobId": identity.job_id,
            "runId": identity.run_id,
            "dispatchIdentitySha256": identity.identity_sha256,
            "sourceArtifactId": identity.source_artifact_id,
            "sourceSha256": capsule.source_sha256,
            "sourceMediaType": capsule.source_media_type,
            "candidateId": identity.candidate_id,
            "claimKey": "7" * 64,
            "outputCount": 1,
            "outputs": [{"sizeBytes": 31, "sha256": output_sha}],
            "executionAttemptCount": 1,
            "engineExecutionPerformed": True,
            "automaticRetryAllowed": False,
            "restartReexecutionAllowed": False,
            "resultReturnAllowed": False,
            "resultPersistenceAllowed": False,
            "gatewayStateMutationAllowed": False,
            "reconciliationRequiredOnRestart": True,
        }
        evidence = {
            "version": "scoremosaic-authenticated-execution-trigger-v1",
            "environment": "staging",
            "engine": identity.engine,
            "jobId": identity.job_id,
            "runId": identity.run_id,
            "dispatchIdentitySha256": identity.identity_sha256,
            "sourceArtifactId": identity.source_artifact_id,
            "sourceSha256": capsule.source_sha256,
            "candidateId": identity.candidate_id,
            "timeoutSeconds": request["timeoutSeconds"],
            "credentialGenerationId": generation,
            "timestamp": int(values["x-scoremosaic-execution-timestamp"]),
            "nonceSha256": sha256(
                values["x-scoremosaic-execution-nonce"].encode("ascii")
            ).hexdigest(),
            "payloadSha256": sha256(body).hexdigest(),
            "replayKey": "8" * 64,
            "receiverAuthenticated": True,
            "engineExecutionPerformed": True,
            "retryAllowed": False,
            "resultReturnAllowed": False,
            "resultPersistenceAllowed": False,
            "gatewayStateMutationAllowed": False,
            "execution": execution,
        }
        return PrivateExecutionHttpResponse(
            200,
            "application/json; charset=utf-8",
            self._canonical(
                {
                    "status": "executed",
                    "kind": "execution",
                    "evidence": evidence,
                    "engineExecutionPerformed": True,
                    "resultReturnAllowed": False,
                    "resultPersistenceAllowed": False,
                }
            ),
        )

    def _run_one_engine(self, engine: str, nonce_digit: str):
        endpoint = EngineEndpoint(engine, APPROVED_ENGINE_ORIGINS["staging"][engine])
        queue_controlled_staging_run(
            minimum_slice=self.minimum,
            provider=self.provider,
            engine=engine,
        )
        persist_controlled_staging_dispatch_intent(
            minimum_slice=self.minimum,
            provider=self.provider,
            endpoint=endpoint,
        )

        identity = build_dispatch_identity(self.plan, engine)
        capsule = build_dispatch_input_capsule(self.plan, identity, [self.source])
        self.assertEqual(capsule.source_sha256, sha256(self.source).hexdigest())

        provision_generation = f"gen-stage7-provision-{engine}"
        provision_secret = secrets.token_bytes(32)
        provision_binding = build_trusted_plan_provisioning_binding(
            endpoint,
            environment="staging",
        )
        provision_credential = resolve_trusted_plan_provisioning_credential(
            provision_binding,
            generation_id=provision_generation,
            resolver=lambda key, generation: (
                provision_secret
                if key == provision_binding.credential_key
                and generation == provision_generation
                else None
            ),
        )
        provisioning_request = build_trusted_plan_provisioning_request(
            capsule=capsule,
            credential=provision_credential,
            issued_at=self.now,
            nonce=nonce_digit * 32,
        )

        dispatch_generation = f"gen-stage7-dispatch-{engine}"
        dispatch_secret = secrets.token_bytes(32)
        dispatch_binding = build_engine_auth_binding(endpoint, "staging")
        dispatch_credential = resolve_engine_credential_generation(
            dispatch_binding,
            dispatch_generation,
            lambda key, generation: (
                dispatch_secret
                if key == dispatch_binding.credential_key
                and generation == dispatch_generation
                else None
            ),
        )
        rotation = build_rotation_set(
            current=dispatch_credential,
            previous=None,
            rotation_started_at=self.now - 1,
            previous_valid_until=None,
        )
        target = build_engine_dispatch_target(dispatch_binding, endpoint)
        dispatch_body = dispatch_identity_payload(identity)
        signed = sign_rotation_authenticated_request(
            rotation,
            method=target.method,
            path=target.path,
            timestamp=self.now,
            nonce=(str((int(nonce_digit) + 1) % 10) * 32),
            payload=dispatch_body,
            now_seconds=self.now,
        )
        dispatch_wire = serialize_controlled_staging_dispatch_wire(
            target=target,
            request=signed,
            payload=dispatch_body,
        )

        control_calls: list[str] = []

        def control_transport(origin, path, headers, body, timeout):
            self.assertEqual(origin, endpoint.base_url)
            self.assertEqual(timeout, 7)
            control_calls.append(path)
            if path == "/internal/trusted-plan":
                return self._control_response(
                    kind="trusted_plan",
                    identity=identity,
                    capsule=capsule,
                    provision_generation=provision_generation,
                    dispatch_generation=dispatch_generation,
                )
            if path == "/internal/transcribe":
                return self._control_response(
                    kind="dispatch",
                    identity=identity,
                    capsule=capsule,
                    provision_generation=provision_generation,
                    dispatch_generation=dispatch_generation,
                )
            raise AssertionError(path)

        dispatch_result = dispatch_controlled_private_network_once(
            minimum_slice=self.minimum,
            provider=self.provider,
            endpoint=endpoint,
            capsule=capsule,
            provisioning_request=provisioning_request,
            dispatch_wire=dispatch_wire,
            now_seconds=self.now,
            timeout_seconds=7,
            transport=control_transport,
        )
        self.assertEqual(
            control_calls,
            ["/internal/trusted-plan", "/internal/transcribe"],
        )
        self.assertTrue(dispatch_result.network_dispatch_performed)
        self.assertTrue(dispatch_result.receiver_authenticated)
        self.assertFalse(dispatch_result.retry_allowed)

        source_generation = f"gen-stage7-source-{engine}"
        source_secret = secrets.token_bytes(32)
        source_binding = build_source_delivery_binding(endpoint)
        source_calls = 0

        def source_transport(origin, path, headers, body, timeout):
            nonlocal source_calls
            source_calls += 1
            self.assertEqual((origin, path), (endpoint.base_url, "/internal/source"))
            self.assertEqual(body, self.source)
            return self._source_response(
                identity=identity,
                generation=source_generation,
                headers=headers,
                body=body,
            )

        source_result = deliver_controlled_private_source_once(
            provider=self.provider,
            endpoint=endpoint,
            capsule=capsule,
            dispatch_result=dispatch_result,
            generation_id=source_generation,
            credential_resolver=lambda key, generation: (
                source_secret
                if key == source_binding.credential_key
                and generation == source_generation
                else None
            ),
            now_seconds=self.now,
            nonce=(str((int(nonce_digit) + 2) % 10) * 32),
            transport=source_transport,
        )
        self.assertEqual(source_calls, 1)
        self.assertTrue(source_result.source_persisted)
        self.assertFalse(source_result.retry_allowed)

        execution_generation = f"gen-stage7-execution-{engine}"
        execution_secret = secrets.token_bytes(32)
        execution_calls = 0

        def execution_transport(origin, path, headers, body, connect_timeout, response_timeout):
            nonlocal execution_calls
            execution_calls += 1
            self.assertEqual((origin, path), (endpoint.base_url, "/internal/execute"))
            self.assertGreaterEqual(response_timeout, 30)
            return self._execution_response(
                identity=identity,
                capsule=capsule,
                generation=execution_generation,
                headers=headers,
                body=body,
            )

        execution_result = execute_controlled_private_engine_once(
            minimum_slice=self.minimum,
            provider=self.provider,
            endpoint=endpoint,
            capsule=capsule,
            dispatch_result=dispatch_result,
            source_delivery_result=source_result,
            generation_id=execution_generation,
            credential_resolver=lambda key, generation: (
                execution_secret
                if key == execution_trigger_credential_key(engine)
                and generation == execution_generation
                else None
            ),
            now_seconds=self.now,
            nonce=(str((int(nonce_digit) + 3) % 10) * 32),
            transport=execution_transport,
        )
        self.assertEqual(execution_calls, 1)
        self.assertTrue(execution_result.engine_execution_performed)
        self.assertFalse(execution_result.retry_allowed)
        self.assertFalse(execution_result.result_return_allowed)

        result_frame = build_engine_result_frame(
            raw_engine_result=f"hermetic-raw-{engine}".encode("ascii"),
            musicxml=MUSICXML,
            diagnostic=self._diagnostic(engine),
        )
        result_credential = EngineCredential(
            binding=build_engine_auth_binding(endpoint, "staging"),
            _secret=(engine.encode("ascii") + b"R" * 64)[:MIN_CREDENTIAL_BYTES],
        )
        result_identity = build_dispatch_result_identity(
            result_credential,
            identity,
            result_frame,
        )
        candidate = ingest_authenticated_engine_result(
            credential=result_credential,
            expected_identity=identity,
            result_identity=result_identity,
            result_payload=result_frame,
        )
        persistence = persist_normalized_candidate_once(
            provider=self.provider,
            orchestration_plan=self.plan,
            candidate=candidate,
        )
        self.assertEqual(persistence.persistence_state, "written")
        return candidate

    def test_immutable_source_to_neutral_comparator_vertical_slice(self) -> None:
        successful = [
            self._run_one_engine(ENGINE_NAMES[0], "1"),
            self._run_one_engine(ENGINE_NAMES[1], "5"),
        ]
        failed_engine = ENGINE_NAMES[2]
        outcomes = (
            success_outcome(successful[0]),
            success_outcome(successful[1]),
            failure_outcome(
                engine=failed_engine,
                candidate_id=build_dispatch_identity(
                    self.plan,
                    failed_engine,
                ).candidate_id,
                reason_code="engine_unavailable",
            ),
        )
        handoffs = load_verified_candidate_handoffs(
            provider=self.provider,
            orchestration_plan=self.plan,
            outcomes=outcomes,
        )
        payloads = tuple(item.to_ensemble_payload() for item in handoffs)
        result = converge_verified_candidates(payloads)

        self.assertEqual(result.status, "comparison_ready")
        self.assertEqual(result.admission.accepted_candidate_count, 2)
        self.assertEqual(result.admission.rejected_candidate_count, 0)
        self.assertIsNotNone(result.admission.comparison)
        self.assertTrue(result.admission.comparison.identical)
        self.assertIsNotNone(result.comparison_report)
        self.assertFalse(result.as_safe_dict()["boundaries"]["authoritativeScore"])
        self.assertFalse(result.as_safe_dict()["boundaries"]["winnerSelection"])
        self.assertEqual(
            self.minimum.binding.document_sha256,
            sha256(self.source).hexdigest(),
        )

        baseline = result.as_safe_dict()
        for _ in range(10):
            repeated = converge_verified_candidates(tuple(reversed(payloads)))
            self.assertEqual(repeated.as_safe_dict(), baseline)
            self.assertEqual(repeated.result_sha256, result.result_sha256)


if __name__ == "__main__":
    unittest.main()
