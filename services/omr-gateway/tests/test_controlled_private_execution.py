from __future__ import annotations
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import secrets, shutil, sys, tempfile, threading, unittest

SERVICE_ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SERVICE_ROOT/"src"))
import test_safe_upload_finalization as helpers
from scoremosaic_gateway.config import EngineEndpoint
from scoremosaic_gateway.controlled_private_execution import (
    CONNECT_TIMEOUT_SECONDS, RESPONSE_TIMEOUT_GRACE_SECONDS,
    ControlledPrivateExecutionError, PrivateExecutionHttpResponse,
    build_authenticated_execution_trigger_request,
    execute_controlled_private_engine_once, execution_trigger_credential_key,
)
from scoremosaic_gateway.controlled_private_network_dispatch import CONTROLLED_PRIVATE_NETWORK_DISPATCH_VERSION, ControlledPrivateNetworkDispatchResult
from scoremosaic_gateway.controlled_private_source_delivery import PrivateSourceHttpResponse, deliver_controlled_private_source_once
from scoremosaic_gateway.controlled_staging_dispatch_intent import persist_controlled_staging_dispatch_intent
from scoremosaic_gateway.controlled_staging_dispatching_transition import transition_controlled_staging_queued_to_dispatching
from scoremosaic_gateway.controlled_staging_job_lifecycle import run_controlled_staging_job_lifecycle
from scoremosaic_gateway.controlled_staging_queued_transition import queue_controlled_staging_run
from scoremosaic_gateway.controlled_staging_transition_state import transition_record_path
from scoremosaic_gateway.dispatch_identity import build_dispatch_identity
from scoremosaic_gateway.dispatch_input_capsule import build_dispatch_input_capsule
from scoremosaic_gateway.dispatch_target import APPROVED_ENGINE_ORIGINS
from scoremosaic_gateway.minimum_staging_vertical_slice import StagingUploadProvider, run_minimum_staging_vertical_slice
from scoremosaic_gateway.orchestration import ENGINE_NAMES, build_orchestration_plan
from scoremosaic_gateway.source_delivery import build_source_delivery_binding

class ControlledPrivateExecutionTests(unittest.TestCase):
    def setUp(self):
        fixture=helpers.SafeUploadFinalizationContractTests(methodName="runTest"); fixture.setUp()
        self.admission=fixture._admission(); self.session_policy=fixture.session_policy; self.source=helpers.PNG_1X1
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup); self.root=Path(self.temp.name)/"primary"; self.state_key=secrets.token_bytes(32)
        self.provider=StagingUploadProvider(self.root,state_integrity_key=self.state_key)
        self.minimum=run_minimum_staging_vertical_slice(admission=self.admission,session_policy=self.session_policy,payload=self.source,original_filename="scan.png",declared_media_type="image/png",observed_at_epoch_s=self.admission.evaluated_at_epoch_s,provider=self.provider)
        run_controlled_staging_job_lifecycle(minimum_slice=self.minimum,provider=self.provider)
        self.endpoint=EngineEndpoint("audiveris",APPROVED_ENGINE_ORIGINS["staging"]["audiveris"])
        queue_controlled_staging_run(minimum_slice=self.minimum,provider=self.provider,engine="audiveris")
        persist_controlled_staging_dispatch_intent(minimum_slice=self.minimum,provider=self.provider,endpoint=self.endpoint)
        state=transition_controlled_staging_queued_to_dispatching(minimum_slice=self.minimum,provider=self.provider,endpoint=self.endpoint); self.assertEqual((state.state,state.revision),("dispatching",2))
        b=self.minimum.binding
        self.plan=build_orchestration_plan(b.job_id,source_artifact_ref=b.source_artifact_ref,source_sha256=b.document_sha256,source_size_bytes=b.source_size_bytes,source_media_type=b.source_media_type,requested_engines=ENGINE_NAMES).as_dict()
        self.identity=build_dispatch_identity(self.plan,"audiveris"); self.capsule=build_dispatch_input_capsule(self.plan,self.identity,[self.source])
        self.dispatch=ControlledPrivateNetworkDispatchResult(version=CONTROLLED_PRIVATE_NETWORK_DISPATCH_VERSION,job_id=self.identity.job_id,engine="audiveris",run_id=self.identity.run_id,dispatch_identity_sha256=self.identity.identity_sha256,target_origin=self.endpoint.base_url,dispatching_revision=2,provisioning_http_status=201,dispatch_http_status=202,provisioning_attempt_count=1,dispatch_attempt_count=1,reconciliation_required_on_restart=True)
        self.now=1_800_700_000; self.source_generation="gen-stage5b3b-source"; self.source_secret=secrets.token_bytes(32); self.source_binding=build_source_delivery_binding(self.endpoint)
        self.source_result=deliver_controlled_private_source_once(provider=self.provider,endpoint=self.endpoint,capsule=self.capsule,dispatch_result=self.dispatch,generation_id=self.source_generation,credential_resolver=self._source_resolver,now_seconds=self.now,nonce="11"*16,transport=self._source_transport)
        self.execution_generation="gen-stage5b3b-execution"; self.execution_secret=secrets.token_bytes(32); self.resolver_calls=0

    def _source_resolver(self,key,generation):
        return self.source_secret if key==self.source_binding.credential_key and generation==self.source_generation else None

    def _source_transport(self,origin,path,headers,body,timeout):
        h=dict(headers); evidence={"version":"scoremosaic-source-delivery-v1","environment":"staging","engine":"audiveris","jobId":self.identity.job_id,"runId":self.identity.run_id,"dispatchIdentitySha256":self.identity.identity_sha256,"sourceArtifactId":self.identity.source_artifact_id,"sourceSizeBytes":len(body),"sourceSha256":sha256(body).hexdigest(),"sourceMediaType":h["x-scoremosaic-source-media-type"],"credentialGenerationId":self.source_generation,"timestamp":int(h["x-scoremosaic-source-timestamp"]),"nonceSha256":sha256(h["x-scoremosaic-source-nonce"].encode()).hexdigest(),"persistenceState":"written","authenticated":True,"trustedPlanConverged":True,"sourcePersisted":True,"engineExecutionAllowed":False,"retryAllowed":False}
        payload={"status":"accepted","kind":"source","evidence":evidence,"engineExecutionAllowed":False}
        return PrivateSourceHttpResponse(status=201,content_type="application/json; charset=utf-8",body=json.dumps(payload,sort_keys=True,separators=(",",":")).encode())

    def _resolver(self,key,generation):
        self.resolver_calls+=1
        return self.execution_secret if key==execution_trigger_credential_key("audiveris") and generation==self.execution_generation else None

    def _response(self,headers,body,*,result_return=False):
        h=dict(headers); p=json.loads(body); output=sha256(b"bounded-output-metadata").hexdigest()
        execution={"version":"scoremosaic-controlled-engine-execution-v1","environment":"staging","engine":"audiveris","jobId":self.identity.job_id,"runId":self.identity.run_id,"dispatchIdentitySha256":self.identity.identity_sha256,"sourceArtifactId":self.identity.source_artifact_id,"sourceSha256":self.capsule.source_sha256,"sourceMediaType":self.capsule.source_media_type,"candidateId":self.identity.candidate_id,"claimKey":"7"*64,"outputCount":1,"outputs":[{"sizeBytes":23,"sha256":output}],"executionAttemptCount":1,"engineExecutionPerformed":True,"automaticRetryAllowed":False,"restartReexecutionAllowed":False,"resultReturnAllowed":False,"resultPersistenceAllowed":False,"gatewayStateMutationAllowed":False,"reconciliationRequiredOnRestart":True}
        evidence={"version":"scoremosaic-authenticated-execution-trigger-v1","environment":"staging","engine":"audiveris","jobId":self.identity.job_id,"runId":self.identity.run_id,"dispatchIdentitySha256":self.identity.identity_sha256,"sourceArtifactId":self.identity.source_artifact_id,"sourceSha256":self.capsule.source_sha256,"candidateId":self.identity.candidate_id,"timeoutSeconds":p["timeoutSeconds"],"credentialGenerationId":self.execution_generation,"timestamp":int(h["x-scoremosaic-execution-timestamp"]),"nonceSha256":sha256(h["x-scoremosaic-execution-nonce"].encode()).hexdigest(),"payloadSha256":sha256(body).hexdigest(),"replayKey":"8"*64,"receiverAuthenticated":True,"engineExecutionPerformed":True,"retryAllowed":False,"resultReturnAllowed":False,"resultPersistenceAllowed":False,"gatewayStateMutationAllowed":False,"execution":execution}
        value={"status":"executed","kind":"execution","evidence":evidence,"engineExecutionPerformed":True,"resultReturnAllowed":result_return,"resultPersistenceAllowed":False}
        return PrivateExecutionHttpResponse(200,"application/json; charset=utf-8",json.dumps(value,sort_keys=True,separators=(",",":")).encode())

    def _success(self,origin,path,headers,body,connect_timeout,response_timeout):return self._response(headers,body)
    def _execute(self,**overrides):
        args=dict(minimum_slice=self.minimum,provider=self.provider,endpoint=self.endpoint,capsule=self.capsule,dispatch_result=self.dispatch,source_delivery_result=self.source_result,generation_id=self.execution_generation,credential_resolver=self._resolver,now_seconds=self.now,nonce="22"*16,transport=self._success); args.update(overrides)
        return execute_controlled_private_engine_once(**args)

    def test_one_shot_fixed_target_metadata_only(self):
        calls=[]
        def transport(*args):calls.append(args); return self._response(args[2],args[3])
        result=self._execute(transport=transport); self.assertEqual(len(calls),1); origin,path,headers,body,connect,response_timeout=calls[0]
        self.assertEqual((origin,path),(self.endpoint.base_url,"/internal/execute")); self.assertEqual(connect,CONNECT_TIMEOUT_SECONDS); self.assertEqual(response_timeout,self.plan["engineRuns"][0]["timeoutSeconds"]+RESPONSE_TIMEOUT_GRACE_SECONDS); self.assertNotIn(self.source,body)
        h=dict(headers); self.assertEqual(h["content-type"],"application/json"); self.assertEqual(int(h["content-length"]),len(body)); self.assertEqual(len(h["x-scoremosaic-execution-signature"]),64)
        self.assertTrue(result.engine_execution_performed); self.assertFalse(result.retry_allowed); self.assertFalse(result.result_return_allowed); self.assertFalse(result.result_persistence_allowed); self.assertNotIn("signature",json.dumps(result.as_safe_dict()).lower()); self.assertNotIn("22"*16,repr(result))

    def test_request_is_deterministic_ten_times_and_redacted(self):
        requests=[build_authenticated_execution_trigger_request(capsule=self.capsule,generation_id=self.execution_generation,credential_resolver=self._resolver,now_seconds=self.now,nonce="33"*16) for _ in range(10)]; first=requests[0]
        for item in requests[1:]:self.assertEqual((item.body,item.headers,item.payload_sha256,item.nonce_sha256),(first.body,first.headers,first.payload_sha256,first.nonce_sha256))
        self.assertNotIn("33"*16,repr(first)); self.assertNotIn(dict(first.headers)["x-scoremosaic-execution-signature"],repr(first)); self.assertFalse(first.as_safe_dict()["signatureExportAllowed"])

    def test_identity_and_ssrf_fail_before_credential_or_network(self):
        calls=[]; wrong=replace(self.source_result,source_sha256="f"*64)
        with self.assertRaises(ControlledPrivateExecutionError) as cm:self._execute(source_delivery_result=wrong,transport=lambda *a:calls.append(a))
        self.assertEqual(cm.exception.category,"staging_execution_source_evidence_invalid"); self.assertEqual((self.resolver_calls,calls),(0,[]))
        bad=EngineEndpoint("audiveris","http://169.254.169.254:80")
        with self.assertRaises(ControlledPrivateExecutionError) as cm:self._execute(endpoint=bad,transport=lambda *a:calls.append(a))
        self.assertEqual(cm.exception.category,"staging_execution_endpoint_invalid"); self.assertEqual((self.resolver_calls,calls),(0,[]))

    def test_missing_source_claim_or_dispatching_state_fails_before_credential(self):
        clone=Path(self.temp.name)/"missing-source"; shutil.copytree(self.root,clone); provider=StagingUploadProvider(clone,state_integrity_key=self.state_key); claims=list((clone/"state"/"source_delivery_claims").rglob("*.json")); self.assertEqual(len(claims),1); claims[0].unlink()
        with self.assertRaises(ControlledPrivateExecutionError) as cm:self._execute(provider=provider)
        self.assertEqual(cm.exception.category,"staging_execution_source_claim_invalid"); self.assertEqual(self.resolver_calls,0)
        path=transition_record_path(self.provider,job_id=self.identity.job_id,run_id=self.identity.run_id,revision=2); path.unlink()
        with self.assertRaises(ControlledPrivateExecutionError) as cm:self._execute()
        self.assertEqual(cm.exception.category,"staging_execution_durable_state_invalid"); self.assertEqual(self.resolver_calls,0)

    def test_transport_ambiguity_is_fenced_without_retry(self):
        calls=[]
        def failing(*args):calls.append(1); raise OSError("sensitive detail")
        with self.assertRaises(ControlledPrivateExecutionError) as cm:self._execute(transport=failing)
        self.assertEqual(cm.exception.category,"staging_execution_transport_failed"); self.assertNotIn("sensitive",str(cm.exception)); self.assertEqual(len(calls),1)
        with self.assertRaises(ControlledPrivateExecutionError) as cm:self._execute(transport=failing)
        self.assertEqual(cm.exception.category,"staging_execution_reconciliation_required"); self.assertEqual(len(calls),1)

    def test_redirect_and_result_return_escalation_are_rejected_and_fenced(self):
        for mode in ("redirect","result-return"):
            clone=Path(self.temp.name)/mode; shutil.copytree(self.root,clone); provider=StagingUploadProvider(clone,state_integrity_key=self.state_key); calls=[]
            def transport(origin,path,headers,body,connect,response_timeout):
                calls.append(1)
                if mode=="redirect":return PrivateExecutionHttpResponse(307,"application/json; charset=utf-8",b"{}","http://169.254.169.254/")
                return self._response(headers,body,result_return=True)
            with self.assertRaises(ControlledPrivateExecutionError):self._execute(provider=provider,transport=transport)
            with self.assertRaises(ControlledPrivateExecutionError) as cm:self._execute(provider=provider,transport=transport)
            self.assertEqual(cm.exception.category,"staging_execution_reconciliation_required"); self.assertEqual(len(calls),1)

    def test_concurrent_callers_have_exactly_one_network_winner(self):
        calls=[]; errors=[]; results=[]; lock=threading.Lock()
        def transport(origin,path,headers,body,connect,response_timeout):
            with lock:calls.append(1)
            return self._response(headers,body)
        def worker():
            try:results.append(self._execute(transport=transport))
            except ControlledPrivateExecutionError as exc:errors.append(exc.category)
        threads=[threading.Thread(target=worker) for _ in range(8)]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertEqual((len(results),len(calls)),(1,1)); self.assertEqual(errors.count("staging_execution_reconciliation_required"),7)

if __name__=="__main__":unittest.main()
