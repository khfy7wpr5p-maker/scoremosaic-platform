from __future__ import annotations
from hashlib import sha256
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import secrets, sys, tempfile, threading, unittest

SERVICE_ROOT=Path(__file__).resolve().parents[1]
REPO_ROOT=SERVICE_ROOT.parents[1]
sys.path.insert(0,str(SERVICE_ROOT/"src")); sys.path.insert(0,str(REPO_ROOT/"services"/"omr-gateway"/"src"))
from scoremosaic_gateway.config import EngineEndpoint
from scoremosaic_gateway.controlled_staging_dispatch_wire import serialize_controlled_staging_dispatch_wire
from scoremosaic_gateway.credential_rotation import build_rotation_set, resolve_engine_credential_generation, sign_rotation_authenticated_request
from scoremosaic_gateway.dispatch_identity import build_dispatch_identity, dispatch_identity_payload
from scoremosaic_gateway.dispatch_input_capsule import build_dispatch_input_capsule
from scoremosaic_gateway.dispatch_target import APPROVED_ENGINE_ORIGINS, build_engine_dispatch_target
from scoremosaic_gateway.orchestration import build_orchestration_plan
from scoremosaic_gateway.service_auth import build_engine_auth_binding
from scoremosaic_gateway.source_delivery import build_source_delivery_binding, build_source_delivery_request, resolve_source_delivery_credential
from scoremosaic_gateway.trusted_plan_provisioning import TRUSTED_PLAN_PROVISIONING_PATH, build_trusted_plan_provisioning_binding, build_trusted_plan_provisioning_request, resolve_trusted_plan_provisioning_credential

if SERVICE_ROOT.name=="audiveris-service":
    from scoremosaic_audiveris.app import make_handler
    from scoremosaic_audiveris.authenticated_dispatch_receiver import ReceiverCredentialRotation
    from scoremosaic_audiveris.config import load_config
    from scoremosaic_audiveris.dispatch_acceptance import EngineDispatchAcceptanceStore, DispatchAcceptanceStoreError
    from scoremosaic_audiveris.receiver_authority import EngineReceiverAuthority
    from scoremosaic_audiveris.receiver_http import DISPATCH_PATH, PROVISIONING_SIGNATURE_HEADER, ReceiverHttpContext, handle_receiver_http_request, receiver_body_length
    from scoremosaic_audiveris.source_delivery import EngineSourceStore, SOURCE_DELIVERY_PATH, SourceDeliveryRotation
    ENGINE="audiveris"
elif SERVICE_ROOT.name=="homr-service":
    from scoremosaic_homr.app import make_handler
    from scoremosaic_homr.authenticated_dispatch_receiver import ReceiverCredentialRotation
    from scoremosaic_homr.config import load_config
    from scoremosaic_homr.dispatch_acceptance import EngineDispatchAcceptanceStore, DispatchAcceptanceStoreError
    from scoremosaic_homr.receiver_authority import EngineReceiverAuthority
    from scoremosaic_homr.receiver_http import DISPATCH_PATH, PROVISIONING_SIGNATURE_HEADER, ReceiverHttpContext, handle_receiver_http_request, receiver_body_length
    from scoremosaic_homr.source_delivery import EngineSourceStore, SOURCE_DELIVERY_PATH, SourceDeliveryRotation
    ENGINE="homr"
elif SERVICE_ROOT.name=="clarity-service":
    from scoremosaic_clarity.app import make_handler
    from scoremosaic_clarity.authenticated_dispatch_receiver import ReceiverCredentialRotation
    from scoremosaic_clarity.config import load_config
    from scoremosaic_clarity.dispatch_acceptance import EngineDispatchAcceptanceStore, DispatchAcceptanceStoreError
    from scoremosaic_clarity.receiver_authority import EngineReceiverAuthority
    from scoremosaic_clarity.receiver_http import DISPATCH_PATH, PROVISIONING_SIGNATURE_HEADER, ReceiverHttpContext, handle_receiver_http_request, receiver_body_length
    from scoremosaic_clarity.source_delivery import EngineSourceStore, SOURCE_DELIVERY_PATH, SourceDeliveryRotation
    ENGINE="clarity"
else: raise RuntimeError("unexpected engine service root")

class Stage5SourceHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup); root=Path(self.temp.name); self.now=1_800_500_000
        self.authority=EngineReceiverAuthority(root=root/"authority",integrity_key=secrets.token_bytes(32))
        self.acceptance=EngineDispatchAcceptanceStore(root=root/"dispatch-acceptance",integrity_key=secrets.token_bytes(32))
        self.source_store=EngineSourceStore(root=root/"sources",integrity_key=secrets.token_bytes(32))
        self.endpoint=EngineEndpoint(ENGINE,APPROVED_ENGINE_ORIGINS["staging"][ENGINE]); self.source=b"%PDF-1.4\n"+b"stage5a2"*64
        self.plan=build_orchestration_plan("job_stage5a2http01",source_artifact_ref="sources/job_stage5a2http01/source.pdf",source_sha256=sha256(self.source).hexdigest(),source_size_bytes=len(self.source),source_media_type="application/pdf").as_dict()
        self.identity=build_dispatch_identity(self.plan,ENGINE); self.capsule=build_dispatch_input_capsule(self.plan,self.identity,[self.source])
        self.prov_generation="gen-stage5a2-provision"; self.prov_secret=secrets.token_bytes(32); pb=build_trusted_plan_provisioning_binding(self.endpoint,environment="staging")
        pc=resolve_trusted_plan_provisioning_credential(pb,generation_id=self.prov_generation,resolver=lambda key,g: self.prov_secret if key==pb.credential_key and g==self.prov_generation else None)
        self.prov=build_trusted_plan_provisioning_request(capsule=self.capsule,credential=pc,issued_at=self.now,nonce="11"*16); self.pb=pb
        self.dispatch_generation="gen-stage5a2-dispatch"; self.dispatch_secret=secrets.token_bytes(32); db=build_engine_auth_binding(self.endpoint,"staging"); target=build_engine_dispatch_target(db,self.endpoint)
        dc=resolve_engine_credential_generation(db,self.dispatch_generation,lambda key,g: self.dispatch_secret if key==db.credential_key and g==self.dispatch_generation else None)
        rotation=build_rotation_set(current=dc,previous=None,rotation_started_at=self.now-1,previous_valid_until=None); body=dispatch_identity_payload(self.identity)
        signed=sign_rotation_authenticated_request(rotation,method=target.method,path=target.path,timestamp=self.now,nonce="22"*16,payload=body,now_seconds=self.now); self.dispatch_wire=serialize_controlled_staging_dispatch_wire(target=target,request=signed,payload=body); self.dispatch_body=body; self.db=db
        self.source_generation="gen-stage5a2-source"; self.source_secret=secrets.token_bytes(32); sb=build_source_delivery_binding(self.endpoint)
        sc=resolve_source_delivery_credential(sb,generation_id=self.source_generation,resolver=lambda key,g: self.source_secret if key==sb.credential_key and g==self.source_generation else None)
        self.source_request=build_source_delivery_request(capsule=self.capsule,credential=sc,timestamp=self.now,nonce="33"*16); self.sb=sb; self.source_resolver_calls=0
        def source_resolver(key,g):
            self.source_resolver_calls += 1
            return self.source_secret if key==self.sb.credential_key and g==self.source_generation else None
        self.context=ReceiverHttpContext(authority=self.authority,provisioning_credential_resolver=lambda key,g: self.prov_secret if key==self.pb.credential_key and g==self.prov_generation else None,dispatch_rotation=ReceiverCredentialRotation(current_generation_id=self.dispatch_generation,current_activated_at=self.now-1),dispatch_credential_resolver=lambda key,g: self.dispatch_secret if key==self.db.credential_key and g==self.dispatch_generation else None,now_seconds=lambda:self.now,dispatch_acceptance_store=self.acceptance,source_store=self.source_store,source_rotation=SourceDeliveryRotation(current_generation_id=self.source_generation,current_activated_at=self.now-1),source_credential_resolver=source_resolver)
    def source_headers(self): return (("Content-Type",self.source_request.source_media_type),("Content-Length",str(len(self.source_request.body))),*self.source_request.headers)
    def provision_headers(self): return (("Content-Type","application/json"),("Content-Length",str(len(self.prov.canonical_request_bytes))),(PROVISIONING_SIGNATURE_HEADER,self.prov.signature))
    def dispatch_headers(self): return (("Content-Type","application/json"),("Content-Length",str(len(self.dispatch_body))),*self.dispatch_wire.headers)
    def test_source_requires_authenticated_dispatch_before_secret_resolution(self):
        response=handle_receiver_http_request(method="POST",target=SOURCE_DELIVERY_PATH,headers=self.source_headers(),body=self.source_request.body,context=self.context)
        self.assertEqual(response.status,409); self.assertEqual(response.payload,{"error":"source_dispatch_not_accepted"}); self.assertEqual(self.source_resolver_calls,0)
    def test_real_http_provision_dispatch_then_source_persists_but_never_executes(self):
        server=ThreadingHTTPServer(("127.0.0.1",0),make_handler(load_config({}),receiver_context=self.context)); thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start(); self.addCleanup(thread.join,5); self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        host,port=server.server_address
        def post(path,body,headers):
            c=HTTPConnection(host,port,timeout=5); c.request("POST",path,body=body,headers=headers); r=c.getresponse(); payload=json.loads(r.read().decode()); status=r.status; c.close(); return status,payload
        status,_=post(TRUSTED_PLAN_PROVISIONING_PATH,self.prov.canonical_request_bytes,{"Content-Type":"application/json",PROVISIONING_SIGNATURE_HEADER:self.prov.signature}); self.assertEqual(status,201)
        status,payload=post(SOURCE_DELIVERY_PATH,self.source_request.body,{"Content-Type":self.source_request.source_media_type,**dict(self.source_request.headers)}); self.assertEqual(status,409); self.assertEqual(payload["error"],"source_dispatch_not_accepted")
        status,payload=post(DISPATCH_PATH,self.dispatch_body,{"Content-Type":"application/json",**dict(self.dispatch_wire.headers)}); self.assertEqual(status,202); self.assertFalse(payload["engineExecutionAllowed"])
        status,payload=post(SOURCE_DELIVERY_PATH,self.source_request.body,{"Content-Type":self.source_request.source_media_type,**dict(self.source_request.headers)}); self.assertEqual(status,201); self.assertEqual(payload["kind"],"source"); self.assertFalse(payload["engineExecutionAllowed"]); self.assertFalse(payload["evidence"]["engineExecutionAllowed"])
        stored=self.source_store.load(job_id=self.identity.job_id,run_id=self.identity.run_id); self.assertEqual(stored.source_bytes,self.source); self.assertEqual(stored.source_sha256,sha256(self.source).hexdigest())
        status,payload=post(SOURCE_DELIVERY_PATH,self.source_request.body,{"Content-Type":self.source_request.source_media_type,**dict(self.source_request.headers)}); self.assertEqual(status,200); self.assertEqual(payload["evidence"]["persistenceState"],"replay")
    def test_source_framing_is_exact_and_bounded(self):
        with self.assertRaises(Exception) as cm: receiver_body_length(method="POST",target=SOURCE_DELIVERY_PATH,headers=self.source_headers()+(("Transfer-Encoding","chunked"),))
        self.assertEqual(getattr(cm.exception,"category",None),"receiver_transfer_encoding_forbidden")
        wrong=(("Content-Type","image/png"),("Content-Length",str(len(self.source_request.body))),*self.source_request.headers)
        with self.assertRaises(Exception) as cm: receiver_body_length(method="POST",target=SOURCE_DELIVERY_PATH,headers=wrong)
        self.assertEqual(getattr(cm.exception,"category",None),"receiver_content_type_invalid")
        response=handle_receiver_http_request(method="POST",target=SOURCE_DELIVERY_PATH+"?x=1",headers=self.source_headers(),body=self.source_request.body,context=self.context); self.assertEqual(response.status,400)
        extra=self.source_headers()+(("x-scoremosaic-extra","x"),)
        response=handle_receiver_http_request(method="POST",target=SOURCE_DELIVERY_PATH,headers=extra,body=self.source_request.body,context=self.context); self.assertEqual(response.status,400)
    def test_source_route_is_fail_closed_without_stage5_context(self):
        legacy=ReceiverHttpContext(authority=self.authority,provisioning_credential_resolver=self.context.provisioning_credential_resolver,dispatch_rotation=self.context.dispatch_rotation,dispatch_credential_resolver=self.context.dispatch_credential_resolver,now_seconds=lambda:self.now)
        response=handle_receiver_http_request(method="POST",target=SOURCE_DELIVERY_PATH,headers=self.source_headers(),body=self.source_request.body,context=legacy); self.assertEqual(response.status,503)
    def test_dispatch_acceptance_store_detects_tamper_and_symlink(self):
        receipt=self.acceptance.publish(job_id=self.identity.job_id,run_id=self.identity.run_id,dispatch_identity_sha256=self.identity.identity_sha256); self.assertEqual(receipt.persistence_state,"written")
        replay=self.acceptance.publish(job_id=self.identity.job_id,run_id=self.identity.run_id,dispatch_identity_sha256=self.identity.identity_sha256); self.assertEqual(replay.persistence_state,"replay")
        path=Path(self.temp.name)/"dispatch-acceptance"/"accepted-dispatches"/f"{self.identity.job_id}.{self.identity.run_id}.json"; path.chmod(0o600); path.write_bytes(path.read_bytes()+b" ")
        with self.assertRaises(DispatchAcceptanceStoreError): self.acceptance.require(job_id=self.identity.job_id,run_id=self.identity.run_id,dispatch_identity_sha256=self.identity.identity_sha256)

if __name__=="__main__": unittest.main()
