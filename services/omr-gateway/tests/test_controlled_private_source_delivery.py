from __future__ import annotations
from hashlib import sha256
import json
from pathlib import Path
import secrets, tempfile, threading, unittest
from scoremosaic_gateway.config import EngineEndpoint
from scoremosaic_gateway.controlled_private_network_dispatch import CONTROLLED_PRIVATE_NETWORK_DISPATCH_VERSION, ControlledPrivateNetworkDispatchResult
from scoremosaic_gateway.controlled_private_source_delivery import ControlledPrivateSourceDeliveryError, PrivateSourceHttpResponse, deliver_controlled_private_source_once
from scoremosaic_gateway.dispatch_identity import build_dispatch_identity
from scoremosaic_gateway.dispatch_input_capsule import build_dispatch_input_capsule
from scoremosaic_gateway.dispatch_target import APPROVED_ENGINE_ORIGINS
from scoremosaic_gateway.minimum_staging_vertical_slice import StagingUploadProvider
from scoremosaic_gateway.orchestration import build_orchestration_plan
from scoremosaic_gateway.source_delivery import build_source_delivery_binding

class ControlledPrivateSourceDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.provider=StagingUploadProvider(Path(self.temp.name)/"staging",state_integrity_key=secrets.token_bytes(32)); self.now=1_800_600_000; self.engine="audiveris"; self.endpoint=EngineEndpoint(self.engine,APPROVED_ENGINE_ORIGINS["staging"][self.engine])
        self.source=b"%PDF-1.4\n"+b"stage5a2-gateway"*64
        self.plan=build_orchestration_plan("job_stage5a2gateway01",source_artifact_ref="sources/job_stage5a2gateway01/source.pdf",source_sha256=sha256(self.source).hexdigest(),source_size_bytes=len(self.source),source_media_type="application/pdf").as_dict(); self.identity=build_dispatch_identity(self.plan,self.engine); self.capsule=build_dispatch_input_capsule(self.plan,self.identity,[self.source])
        self.dispatch_result=ControlledPrivateNetworkDispatchResult(version=CONTROLLED_PRIVATE_NETWORK_DISPATCH_VERSION,job_id=self.identity.job_id,engine=self.engine,run_id=self.identity.run_id,dispatch_identity_sha256=self.identity.identity_sha256,target_origin=self.endpoint.base_url,dispatching_revision=2,provisioning_http_status=201,dispatch_http_status=202,provisioning_attempt_count=1,dispatch_attempt_count=1,reconciliation_required_on_restart=True)
        self.generation="gen-stage5a2-source"; self.secret=secrets.token_bytes(32); self.binding=build_source_delivery_binding(self.endpoint); self.resolver_calls=0
    def resolver(self,key,generation):
        self.resolver_calls += 1
        return self.secret if key==self.binding.credential_key and generation==self.generation else None
    @staticmethod
    def accepted_response(headers):
        values=dict(headers); body_sha=values["x-scoremosaic-source-sha256"]
        evidence={"version":"scoremosaic-source-delivery-v1","environment":"staging","engine":"audiveris","jobId":values["x-scoremosaic-source-job"],"runId":values["x-scoremosaic-source-run"],"dispatchIdentitySha256":values["x-scoremosaic-source-dispatch-sha256"],"sourceArtifactId":values["x-scoremosaic-source-artifact"],"sourceSizeBytes":int(values["x-scoremosaic-source-bytes"]),"sourceSha256":body_sha,"sourceMediaType":values["x-scoremosaic-source-media-type"],"credentialGenerationId":values["x-scoremosaic-source-generation"],"timestamp":int(values["x-scoremosaic-source-timestamp"]),"nonceSha256":sha256(values["x-scoremosaic-source-nonce"].encode()).hexdigest(),"persistenceState":"written","authenticated":True,"trustedPlanConverged":True,"sourcePersisted":True,"engineExecutionAllowed":False,"retryAllowed":False}
        payload={"status":"accepted","kind":"source","evidence":evidence,"engineExecutionAllowed":False}
        return PrivateSourceHttpResponse(status=201,content_type="application/json; charset=utf-8",body=json.dumps(payload,sort_keys=True,separators=(",",":")).encode())
    def test_successful_source_delivery_is_one_shot_and_non_executable(self):
        calls=[]
        def transport(origin,path,headers,body,timeout):
            calls.append((origin,path,headers,body,timeout)); return self.accepted_response(headers)
        result=deliver_controlled_private_source_once(provider=self.provider,endpoint=self.endpoint,capsule=self.capsule,dispatch_result=self.dispatch_result,generation_id=self.generation,credential_resolver=self.resolver,now_seconds=self.now,nonce="44"*16,transport=transport)
        self.assertEqual(len(calls),1); self.assertEqual(calls[0][0],self.endpoint.base_url); self.assertEqual(calls[0][1],"/internal/source"); self.assertEqual(calls[0][3],self.source); self.assertTrue(result.network_source_delivery_performed); self.assertTrue(result.source_persisted); self.assertFalse(result.engine_execution_allowed); self.assertFalse(result.retry_allowed); self.assertFalse(result.result_persistence_allowed); self.assertFalse(result.post_dispatch_job_mutation_allowed)
    def test_dispatch_evidence_and_ssrf_fail_before_credential_or_network(self):
        calls=[]
        wrong=ControlledPrivateNetworkDispatchResult(version=CONTROLLED_PRIVATE_NETWORK_DISPATCH_VERSION,job_id=self.identity.job_id,engine=self.engine,run_id="run_"+"f"*24,dispatch_identity_sha256=self.identity.identity_sha256,target_origin=self.endpoint.base_url,dispatching_revision=2,provisioning_http_status=201,dispatch_http_status=202,provisioning_attempt_count=1,dispatch_attempt_count=1,reconciliation_required_on_restart=True)
        with self.assertRaises(ControlledPrivateSourceDeliveryError): deliver_controlled_private_source_once(provider=self.provider,endpoint=self.endpoint,capsule=self.capsule,dispatch_result=wrong,generation_id=self.generation,credential_resolver=self.resolver,now_seconds=self.now,nonce="55"*16,transport=lambda *args: calls.append(args))
        self.assertEqual(self.resolver_calls,0); self.assertEqual(calls,[])
        bad=EngineEndpoint(self.engine,"http://169.254.169.254:80")
        with self.assertRaises(ControlledPrivateSourceDeliveryError): deliver_controlled_private_source_once(provider=self.provider,endpoint=bad,capsule=self.capsule,dispatch_result=self.dispatch_result,generation_id=self.generation,credential_resolver=self.resolver,now_seconds=self.now,nonce="55"*16,transport=lambda *args: calls.append(args))
        self.assertEqual(self.resolver_calls,0); self.assertEqual(calls,[])
    def test_transport_ambiguity_writes_fence_and_restart_resends_zero(self):
        calls=[]
        def failing(*args): calls.append(args); raise OSError("sensitive transport detail")
        with self.assertRaises(ControlledPrivateSourceDeliveryError) as cm: deliver_controlled_private_source_once(provider=self.provider,endpoint=self.endpoint,capsule=self.capsule,dispatch_result=self.dispatch_result,generation_id=self.generation,credential_resolver=self.resolver,now_seconds=self.now,nonce="66"*16,transport=failing)
        self.assertEqual(cm.exception.category,"staging_source_transport_failed"); self.assertEqual(len(calls),1); self.assertNotIn("sensitive",str(cm.exception))
        with self.assertRaises(ControlledPrivateSourceDeliveryError) as cm: deliver_controlled_private_source_once(provider=self.provider,endpoint=self.endpoint,capsule=self.capsule,dispatch_result=self.dispatch_result,generation_id=self.generation,credential_resolver=self.resolver,now_seconds=self.now,nonce="66"*16,transport=failing)
        self.assertEqual(cm.exception.category,"staging_source_reconciliation_required"); self.assertEqual(len(calls),1)
    def test_redirect_or_malicious_execution_response_is_never_retried(self):
        for mode in ("redirect","execution"):
            root=Path(self.temp.name)/mode; provider=StagingUploadProvider(root,state_integrity_key=secrets.token_bytes(32)); calls=[]
            def transport(origin,path,headers,body,timeout):
                calls.append(1)
                if mode=="redirect": return PrivateSourceHttpResponse(status=307,content_type="application/json; charset=utf-8",body=b"{}",location="http://169.254.169.254/")
                response=self.accepted_response(headers); value=json.loads(response.body); value["engineExecutionAllowed"]=True
                return PrivateSourceHttpResponse(status=201,content_type=response.content_type,body=json.dumps(value,sort_keys=True,separators=(",",":")).encode())
            with self.assertRaises(ControlledPrivateSourceDeliveryError): deliver_controlled_private_source_once(provider=provider,endpoint=self.endpoint,capsule=self.capsule,dispatch_result=self.dispatch_result,generation_id=self.generation,credential_resolver=self.resolver,now_seconds=self.now,nonce=("77" if mode=="redirect" else "88")*16,transport=transport)
            with self.assertRaises(ControlledPrivateSourceDeliveryError) as cm: deliver_controlled_private_source_once(provider=provider,endpoint=self.endpoint,capsule=self.capsule,dispatch_result=self.dispatch_result,generation_id=self.generation,credential_resolver=self.resolver,now_seconds=self.now,nonce=("77" if mode=="redirect" else "88")*16,transport=transport)
            self.assertEqual(cm.exception.category,"staging_source_reconciliation_required"); self.assertEqual(len(calls),1)
    def test_concurrent_callers_have_exactly_one_network_winner(self):
        calls=[]; lock=threading.Lock(); errors=[]; results=[]
        def transport(origin,path,headers,body,timeout):
            with lock: calls.append(1)
            return self.accepted_response(headers)
        def worker():
            try: results.append(deliver_controlled_private_source_once(provider=self.provider,endpoint=self.endpoint,capsule=self.capsule,dispatch_result=self.dispatch_result,generation_id=self.generation,credential_resolver=self.resolver,now_seconds=self.now,nonce="99"*16,transport=transport))
            except ControlledPrivateSourceDeliveryError as exc: errors.append(exc.category)
        threads=[threading.Thread(target=worker) for _ in range(8)]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertEqual(len(results),1); self.assertEqual(len(calls),1); self.assertEqual(errors.count("staging_source_reconciliation_required"),7)

if __name__=="__main__": unittest.main()
