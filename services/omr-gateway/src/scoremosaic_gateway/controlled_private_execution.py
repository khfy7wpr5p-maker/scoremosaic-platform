"""Authenticated one-shot Gateway -> engine execution boundary for Stage 5-B3b.

Execution is allowed only after exact capsule, authenticated dispatch evidence,
durable source-delivery evidence, and durable dispatching(2) state converge.
A create-once HMAC-sealed claim is published before network I/O. Any ambiguity
is reconciliation-only and never retried automatically. Result bytes are not
accepted or persisted here; Stage 6 owns result ingestion.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from hmac import compare_digest, new as hmac_new
from http.client import HTTPConnection, HTTPResponse
import json, re, socket
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from .config import EngineEndpoint
from .controlled_private_network_dispatch import ControlledPrivateNetworkDispatchResult
from .controlled_private_source_delivery import (
    CONTROLLED_PRIVATE_SOURCE_DELIVERY_VERSION,
    ControlledPrivateSourceDeliveryError,
    ControlledPrivateSourceDeliveryResult,
    _CLAIM_MAC_FIELD as _SOURCE_CLAIM_MAC_FIELD,
    _EXPECTED_BOUNDARIES as _SOURCE_BOUNDARIES,
    _canonical_json as _source_canonical_json,
    _claim_key as _source_claim_key,
    _claim_mac as _source_claim_mac,
    _claim_path as _source_claim_path,
)
from .controlled_staging_dispatching_transition import (
    ControlledStagingDispatchingTransitionError,
    recover_controlled_staging_dispatching_run,
)
from .dispatch_input_capsule import DispatchInputCapsule, DispatchInputCapsuleError, verify_dispatch_input_capsule
from .dispatch_target import APPROVED_ENGINE_ORIGINS
from .minimum_staging_vertical_slice import (
    MinimumStagingVerticalSliceError, MinimumStagingVerticalSliceResult,
    StagingUploadProvider, _MAX_STATE_RECORD_BYTES, _decode_record,
)
from .orchestration import MAX_ENGINE_TIMEOUT_SECONDS, MIN_ENGINE_TIMEOUT_SECONDS

CONTROLLED_PRIVATE_EXECUTION_VERSION="scoremosaic-controlled-private-execution-v1"
AUTHENTICATED_EXECUTION_TRIGGER_VERSION="scoremosaic-authenticated-execution-trigger-v1"
EXECUTION_TRIGGER_PATH="/internal/execute"
CALLER_SERVICE_IDENTITY="scoremosaic-omr-gateway"
MAX_REQUEST_BYTES=4096
MAX_RESPONSE_BYTES=16*1024
CONNECT_TIMEOUT_SECONDS=10
RESPONSE_TIMEOUT_GRACE_SECONDS=30
_SIGNATURE_DOMAIN=b"scoremosaic-authenticated-execution-trigger-v1"
_CLAIM_DOMAIN=b"scoremosaic-controlled-private-execution-claim-v1"
_CLAIM_MAC_FIELD="execution_trigger_claim_integrity_mac"
_AUDIENCES={"audiveris":"scoremosaic-audiveris-foundation","homr":"scoremosaic-homr-foundation","clarity":"scoremosaic-clarity-foundation"}
_GEN_RE=re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")
_NONCE_RE=re.compile(r"[0-9a-f]{32}\Z")
_SHA_RE=re.compile(r"[0-9a-f]{64}\Z")
_JOB_RE=re.compile(r"job_[A-Za-z0-9_-]{8,80}\Z")
_RUN_RE=re.compile(r"run_[0-9a-f]{24}\Z")
_ART_RE=re.compile(r"artifact_[0-9a-f]{24}\Z")
_CAND_RE=re.compile(r"candidate_[0-9a-f]{24}\Z")

class ControlledPrivateExecutionError(ValueError):
    def __init__(self,category:str)->None: self.category=category; super().__init__(category)

@dataclass(frozen=True,slots=True)
class PrivateExecutionHttpResponse:
    status:int; content_type:str; body:bytes; location:str|None=None
    def __post_init__(self)->None:
        if type(self.status) is not int or not 100<=self.status<=599 or type(self.content_type) is not str or type(self.body) is not bytes or len(self.body)>MAX_RESPONSE_BYTES or (self.location is not None and type(self.location) is not str):
            raise ControlledPrivateExecutionError("staging_execution_transport_response_invalid")

ExecutionTransport=Callable[[str,str,tuple[tuple[str,str],...],bytes,int,int],PrivateExecutionHttpResponse]

@dataclass(frozen=True,slots=True,repr=False)
class AuthenticatedExecutionTriggerRequest:
    engine:str; generation_id:str; timestamp:int; timeout_seconds:int
    nonce_sha256:str; payload_sha256:str
    body:bytes=field(repr=False); headers:tuple[tuple[str,str],...]=field(repr=False)
    def __post_init__(self)->None:
        if self.engine not in _AUDIENCES or _GEN_RE.fullmatch(self.generation_id) is None or type(self.timestamp) is not int or self.timestamp<0 or not MIN_ENGINE_TIMEOUT_SECONDS<=self.timeout_seconds<=MAX_ENGINE_TIMEOUT_SECONDS or _SHA_RE.fullmatch(self.nonce_sha256) is None or _SHA_RE.fullmatch(self.payload_sha256) is None or type(self.body) is not bytes or not 1<=len(self.body)<=MAX_REQUEST_BYTES or type(self.headers) is not tuple:
            raise ControlledPrivateExecutionError("staging_execution_request_invalid")
    def __repr__(self)->str:
        return f"AuthenticatedExecutionTriggerRequest(engine={self.engine!r}, generation_id={self.generation_id!r}, timestamp={self.timestamp!r}, timeout_seconds={self.timeout_seconds!r}, nonce_sha256={self.nonce_sha256!r}, payload_sha256={self.payload_sha256!r}, body=<redacted>, headers=<redacted>)"
    def as_safe_dict(self)->dict[str,object]:
        return {"version":AUTHENTICATED_EXECUTION_TRIGGER_VERSION,"environment":"staging","engine":self.engine,"credentialGenerationId":self.generation_id,"timestamp":self.timestamp,"timeoutSeconds":self.timeout_seconds,"nonceSha256":self.nonce_sha256,"payloadSha256":self.payload_sha256,"payloadBytes":len(self.body),"signaturePresent":True,"rawNonceExportAllowed":False,"signatureExportAllowed":False}

@dataclass(frozen=True,slots=True)
class ControlledPrivateExecutionResult:
    version:str; job_id:str; engine:str; run_id:str; dispatch_identity_sha256:str
    source_artifact_id:str; source_sha256:str; candidate_id:str; target_origin:str
    claim_key:str; http_status:int; execution_attempt_count:int; reconciliation_required_on_restart:bool
    def __post_init__(self)->None:
        expected=APPROVED_ENGINE_ORIGINS["staging"].get(self.engine) if type(self.engine) is str else None
        if self.version!=CONTROLLED_PRIVATE_EXECUTION_VERSION or expected is None or self.target_origin!=expected or _JOB_RE.fullmatch(self.job_id) is None or _RUN_RE.fullmatch(self.run_id) is None or _SHA_RE.fullmatch(self.dispatch_identity_sha256) is None or _ART_RE.fullmatch(self.source_artifact_id) is None or _SHA_RE.fullmatch(self.source_sha256) is None or _CAND_RE.fullmatch(self.candidate_id) is None or _SHA_RE.fullmatch(self.claim_key) is None or self.http_status!=200 or self.execution_attempt_count!=1 or self.reconciliation_required_on_restart is not True:
            raise ControlledPrivateExecutionError("staging_execution_result_invalid")
    @property
    def engine_execution_performed(self)->bool:return True
    @property
    def retry_allowed(self)->bool:return False
    @property
    def result_return_allowed(self)->bool:return False
    @property
    def result_persistence_allowed(self)->bool:return False
    @property
    def post_dispatch_job_mutation_allowed(self)->bool:return False
    def as_safe_dict(self)->dict[str,object]:
        return {"version":self.version,"environment":"staging","jobId":self.job_id,"engine":self.engine,"runId":self.run_id,"dispatchIdentitySha256":self.dispatch_identity_sha256,"sourceArtifactId":self.source_artifact_id,"sourceSha256":self.source_sha256,"candidateId":self.candidate_id,"targetOrigin":self.target_origin,"claimKey":self.claim_key,"httpStatus":200,"executionAttemptCount":1,"reconciliationRequiredOnRestart":True,"engineExecutionPerformed":True,"retryAllowed":False,"resultReturnAllowed":False,"resultPersistenceAllowed":False,"postDispatchJobMutationAllowed":False}

def _canonical(value:Any,category:str)->bytes:
    try:return json.dumps(value,ensure_ascii=True,allow_nan=False,sort_keys=True,separators=(",",":")).encode("ascii")
    except Exception:raise ControlledPrivateExecutionError(category) from None

def _pairs(pairs:list[tuple[str,Any]])->dict[str,Any]:
    out={}
    for key,value in pairs:
        if type(key) is not str or key in out:raise ControlledPrivateExecutionError("staging_execution_json_invalid")
        out[key]=value
    return out

def _endpoint(endpoint:object)->EngineEndpoint:
    if type(endpoint) is not EngineEndpoint:raise ControlledPrivateExecutionError("staging_execution_endpoint_invalid")
    expected=APPROVED_ENGINE_ORIGINS["staging"].get(endpoint.name)
    if expected is None or endpoint.base_url!=expected:raise ControlledPrivateExecutionError("staging_execution_endpoint_invalid")
    try:parsed=urlsplit(endpoint.base_url); port=parsed.port
    except ValueError:raise ControlledPrivateExecutionError("staging_execution_endpoint_invalid") from None
    if parsed.scheme!="http" or parsed.hostname is None or port is None or parsed.username is not None or parsed.password is not None or parsed.path not in {"","/"} or parsed.query or parsed.fragment:raise ControlledPrivateExecutionError("staging_execution_endpoint_invalid")
    return endpoint

def execution_trigger_credential_key(engine:str)->str:
    audience=_AUDIENCES.get(engine)
    if audience is None:raise ControlledPrivateExecutionError("staging_execution_engine_invalid")
    return ":".join((AUTHENTICATED_EXECUTION_TRIGGER_VERSION,"staging",CALLER_SERVICE_IDENTITY,engine,audience))

def _planned_timeout(capsule:DispatchInputCapsule)->int:
    try:plan=json.loads(capsule.canonical_plan_bytes.decode("ascii"),object_pairs_hook=_pairs,parse_constant=lambda _v:(_ for _ in ()).throw(ValueError()))
    except ControlledPrivateExecutionError:raise
    except Exception:raise ControlledPrivateExecutionError("staging_execution_plan_invalid") from None
    runs=plan.get("engineRuns") if type(plan) is dict else None
    matches=[x for x in runs if type(x) is dict and x.get("engine")==capsule.dispatch_identity.engine and x.get("runId")==capsule.dispatch_identity.run_id] if type(runs) is list else []
    if len(matches)!=1:raise ControlledPrivateExecutionError("staging_execution_plan_invalid")
    run=matches[0]; timeout=run.get("timeoutSeconds")
    if type(timeout) is not int or not MIN_ENGINE_TIMEOUT_SECONDS<=timeout<=MAX_ENGINE_TIMEOUT_SECONDS or run.get("candidateId")!=capsule.dispatch_identity.candidate_id or run.get("attemptLimit")!=1 or run.get("operation")!="transcribe":raise ControlledPrivateExecutionError("staging_execution_plan_invalid")
    return timeout

def _credential(resolver:Callable[[str,str],object],engine:str,generation:str)->bytes:
    if not callable(resolver) or type(generation) is not str or _GEN_RE.fullmatch(generation) is None:raise ControlledPrivateExecutionError("staging_execution_credential_invalid")
    try:raw=resolver(execution_trigger_credential_key(engine),generation)
    except Exception:raise ControlledPrivateExecutionError("staging_execution_credential_unavailable") from None
    if raw is None or type(raw) not in (bytes,bytearray,memoryview):raise ControlledPrivateExecutionError("staging_execution_credential_unavailable")
    try:size=raw.nbytes if type(raw) is memoryview else len(raw); secret=bytes(raw)
    except Exception:raise ControlledPrivateExecutionError("staging_execution_credential_unavailable") from None
    if not 32<=size<=512:raise ControlledPrivateExecutionError("staging_execution_credential_unavailable")
    return secret

def build_authenticated_execution_trigger_request(*,capsule:DispatchInputCapsule,generation_id:str,credential_resolver:Callable[[str,str],object],now_seconds:int,nonce:str)->AuthenticatedExecutionTriggerRequest:
    if type(capsule) is not DispatchInputCapsule or type(now_seconds) is not int or now_seconds<0 or type(nonce) is not str or _NONCE_RE.fullmatch(nonce) is None:raise ControlledPrivateExecutionError("staging_execution_request_invalid")
    try:verify_dispatch_input_capsule(capsule)
    except DispatchInputCapsuleError:raise ControlledPrivateExecutionError("staging_execution_capsule_invalid") from None
    i=capsule.dispatch_identity; timeout=_planned_timeout(capsule); secret=_credential(credential_resolver,i.engine,generation_id)
    body=_canonical({"version":AUTHENTICATED_EXECUTION_TRIGGER_VERSION,"environment":"staging","engine":i.engine,"jobId":i.job_id,"runId":i.run_id,"dispatchIdentitySha256":i.identity_sha256,"sourceArtifactId":i.source_artifact_id,"sourceSha256":capsule.source_sha256,"candidateId":i.candidate_id,"timeoutSeconds":timeout},"staging_execution_request_invalid")
    if not 1<=len(body)<=MAX_REQUEST_BYTES:raise ControlledPrivateExecutionError("staging_execution_request_invalid")
    audience=_AUDIENCES[i.engine]; key=execution_trigger_credential_key(i.engine)
    metadata=_canonical({"version":AUTHENTICATED_EXECUTION_TRIGGER_VERSION,"environment":"staging","callerIdentity":CALLER_SERVICE_IDENTITY,"engine":i.engine,"audienceIdentity":audience,"credentialKey":key,"method":"POST","path":EXECUTION_TRIGGER_PATH,"credentialGenerationId":generation_id,"timestamp":now_seconds,"nonce":nonce,"payloadBytes":len(body),"payloadSha256":sha256(body).hexdigest()},"staging_execution_request_invalid")
    signature=hmac_new(secret,b"\0".join((_SIGNATURE_DOMAIN,metadata,body)),sha256).hexdigest()
    headers=(("content-type","application/json"),("content-length",str(len(body))),("x-scoremosaic-execution-generation",generation_id),("x-scoremosaic-execution-timestamp",str(now_seconds)),("x-scoremosaic-execution-nonce",nonce),("x-scoremosaic-execution-signature",signature))
    return AuthenticatedExecutionTriggerRequest(i.engine,generation_id,now_seconds,timeout,sha256(nonce.encode("ascii")).hexdigest(),sha256(body).hexdigest(),body,headers)

def _verify_source_claim(provider:StagingUploadProvider,endpoint:EngineEndpoint,capsule:DispatchInputCapsule,result:ControlledPrivateSourceDeliveryResult)->None:
    i=capsule.dispatch_identity; key=_source_claim_key(capsule,endpoint)
    if result.claim_key!=key or result.job_id!=i.job_id or result.engine!=i.engine or result.run_id!=i.run_id or result.dispatch_identity_sha256!=i.identity_sha256 or result.source_artifact_id!=i.source_artifact_id or result.source_size_bytes!=capsule.source_size_bytes or result.source_sha256!=capsule.source_sha256 or result.source_media_type!=capsule.source_media_type or result.target_origin!=endpoint.base_url or result.http_status!=201 or result.source_attempt_count!=1:raise ControlledPrivateExecutionError("staging_execution_source_claim_invalid")
    record={"version":CONTROLLED_PRIVATE_SOURCE_DELIVERY_VERSION,"environment":"staging","claimKey":key,"jobId":i.job_id,"engine":i.engine,"runId":i.run_id,"dispatchIdentitySha256":i.identity_sha256,"sourceArtifactId":i.source_artifact_id,"sourceSizeBytes":capsule.source_size_bytes,"sourceSha256":capsule.source_sha256,"sourceMediaType":capsule.source_media_type,"targetOrigin":endpoint.base_url,"boundaries":dict(_SOURCE_BOUNDARIES)}
    try:
        raw=provider._read_file_no_follow(_source_claim_path(provider,key),max_bytes=_MAX_STATE_RECORD_BYTES,overflow_category="staging_state_corrupt"); stored=_decode_record(raw)
        if type(stored) is not dict or _SOURCE_CLAIM_MAC_FIELD not in stored or _source_canonical_json(stored)!=raw:raise ControlledPrivateExecutionError("staging_execution_source_claim_invalid")
        observed=stored.get(_SOURCE_CLAIM_MAC_FIELD); unsealed=dict(stored); unsealed.pop(_SOURCE_CLAIM_MAC_FIELD,None)
        if type(observed) is not str or not compare_digest(observed,_source_claim_mac(provider,unsealed)) or unsealed!=record:raise ControlledPrivateExecutionError("staging_execution_source_claim_invalid")
    except ControlledPrivateExecutionError:raise
    except (ControlledPrivateSourceDeliveryError,MinimumStagingVerticalSliceError):raise ControlledPrivateExecutionError("staging_execution_source_claim_invalid") from None

def _claim_key(capsule:DispatchInputCapsule,endpoint:EngineEndpoint,timeout:int)->str:
    i=capsule.dispatch_identity
    return sha256("\x1f".join((CONTROLLED_PRIVATE_EXECUTION_VERSION,i.job_id,i.run_id,i.identity_sha256,i.source_artifact_id,capsule.source_sha256,i.candidate_id,str(timeout),endpoint.base_url)).encode()).hexdigest()

def _claim_mac(provider:StagingUploadProvider,record:dict[str,Any])->str:
    key=getattr(provider,"_state_integrity_key",None)
    if type(key) is not bytes or len(key)!=32:raise ControlledPrivateExecutionError("staging_execution_state_invalid")
    return hmac_new(key,b"\0".join((_CLAIM_DOMAIN,_canonical(record,"staging_execution_state_invalid"))),sha256).hexdigest()

def _reserve_claim(provider:StagingUploadProvider,capsule:DispatchInputCapsule,endpoint:EngineEndpoint,timeout:int)->str:
    i=capsule.dispatch_identity; key=_claim_key(capsule,endpoint,timeout)
    record={"version":CONTROLLED_PRIVATE_EXECUTION_VERSION,"environment":"staging","claimKey":key,"jobId":i.job_id,"engine":i.engine,"runId":i.run_id,"dispatchIdentitySha256":i.identity_sha256,"sourceArtifactId":i.source_artifact_id,"sourceSha256":capsule.source_sha256,"candidateId":i.candidate_id,"timeoutSeconds":timeout,"targetOrigin":endpoint.base_url,"boundaries":{"automaticRetryAllowed":False,"restartReexecutionAllowed":False,"redirectAllowed":False,"proxyRoutingAllowed":False,"resultReturnAllowed":False,"resultPersistenceAllowed":False,"postDispatchJobMutationAllowed":False,"reconciliationRequired":True}}
    sealed=dict(record); sealed[_CLAIM_MAC_FIELD]=_claim_mac(provider,record); payload=_canonical(sealed,"staging_execution_state_invalid")
    path=provider._root/"state"/"execution_trigger_claims"/key[:2]/f"{key}.json"
    try:
        if provider._atomic_create(path,payload):return key
        raw=provider._read_file_no_follow(path,max_bytes=_MAX_STATE_RECORD_BYTES,overflow_category="staging_state_corrupt"); stored=_decode_record(raw)
    except MinimumStagingVerticalSliceError:raise ControlledPrivateExecutionError("staging_execution_state_invalid") from None
    if type(stored) is not dict or _CLAIM_MAC_FIELD not in stored or _canonical(stored,"staging_execution_state_invalid")!=raw:raise ControlledPrivateExecutionError("staging_execution_state_invalid")
    observed=stored.get(_CLAIM_MAC_FIELD); unsealed=dict(stored); unsealed.pop(_CLAIM_MAC_FIELD,None)
    if type(observed) is not str or not compare_digest(observed,_claim_mac(provider,unsealed)) or unsealed!=record:raise ControlledPrivateExecutionError("staging_execution_state_invalid")
    raise ControlledPrivateExecutionError("staging_execution_reconciliation_required")

def _default_post(origin:str,path:str,headers:tuple[tuple[str,str],...],body:bytes,connect_timeout:int,response_timeout:int)->PrivateExecutionHttpResponse:
    parsed=urlsplit(origin)
    if parsed.scheme!="http" or parsed.hostname is None or parsed.port is None or path!=EXECUTION_TRIGGER_PATH:raise ControlledPrivateExecutionError("staging_execution_transport_target_invalid")
    connection=HTTPConnection(parsed.hostname,parsed.port,timeout=connect_timeout)
    try:
        connection.connect()
        if connection.sock is None:raise OSError()
        connection.sock.settimeout(response_timeout); connection.request("POST",path,body=body,headers=dict(headers)); response:HTTPResponse=connection.getresponse(); raw=response.read(MAX_RESPONSE_BYTES+1)
        if len(raw)>MAX_RESPONSE_BYTES:raise ControlledPrivateExecutionError("staging_execution_response_too_large")
        return PrivateExecutionHttpResponse(int(response.status),response.getheader("Content-Type",""),raw,response.getheader("Location"))
    except ControlledPrivateExecutionError:raise
    except (TimeoutError,socket.timeout,OSError):raise ControlledPrivateExecutionError("staging_execution_transport_failed") from None
    except Exception:raise ControlledPrivateExecutionError("staging_execution_transport_failed") from None
    finally:
        try:connection.close()
        except Exception:pass

def _accepted(response:PrivateExecutionHttpResponse,capsule:DispatchInputCapsule,request:AuthenticatedExecutionTriggerRequest)->None:
    if 300<=response.status<=399 or response.location is not None:raise ControlledPrivateExecutionError("staging_execution_redirect_forbidden")
    if response.status!=200:raise ControlledPrivateExecutionError("staging_execution_receiver_rejected")
    if response.content_type!="application/json; charset=utf-8":raise ControlledPrivateExecutionError("staging_execution_response_invalid")
    try:value=json.loads(response.body.decode("ascii"),object_pairs_hook=_pairs,parse_constant=lambda _v:(_ for _ in ()).throw(ValueError()))
    except ControlledPrivateExecutionError:raise ControlledPrivateExecutionError("staging_execution_response_invalid") from None
    except Exception:raise ControlledPrivateExecutionError("staging_execution_response_invalid") from None
    if type(value) is not dict or set(value)!={"status","kind","evidence","engineExecutionPerformed","resultReturnAllowed","resultPersistenceAllowed"}:raise ControlledPrivateExecutionError("staging_execution_response_invalid")
    e=value.get("evidence"); i=capsule.dispatch_identity
    expected_e={"version","environment","engine","jobId","runId","dispatchIdentitySha256","sourceArtifactId","sourceSha256","candidateId","timeoutSeconds","credentialGenerationId","timestamp","nonceSha256","payloadSha256","replayKey","receiverAuthenticated","engineExecutionPerformed","retryAllowed","resultReturnAllowed","resultPersistenceAllowed","gatewayStateMutationAllowed","execution"}
    if value.get("status")!="executed" or value.get("kind")!="execution" or value.get("engineExecutionPerformed") is not True or value.get("resultReturnAllowed") is not False or value.get("resultPersistenceAllowed") is not False or type(e) is not dict or set(e)!=expected_e or e.get("version")!=AUTHENTICATED_EXECUTION_TRIGGER_VERSION or e.get("environment")!="staging" or e.get("engine")!=i.engine or e.get("jobId")!=i.job_id or e.get("runId")!=i.run_id or e.get("dispatchIdentitySha256")!=i.identity_sha256 or e.get("sourceArtifactId")!=i.source_artifact_id or e.get("sourceSha256")!=capsule.source_sha256 or e.get("candidateId")!=i.candidate_id or e.get("timeoutSeconds")!=request.timeout_seconds or e.get("credentialGenerationId")!=request.generation_id or e.get("timestamp")!=request.timestamp or e.get("nonceSha256")!=request.nonce_sha256 or e.get("payloadSha256")!=request.payload_sha256 or type(e.get("replayKey")) is not str or _SHA_RE.fullmatch(e["replayKey"]) is None or e.get("receiverAuthenticated") is not True or e.get("engineExecutionPerformed") is not True or e.get("retryAllowed") is not False or e.get("resultReturnAllowed") is not False or e.get("resultPersistenceAllowed") is not False or e.get("gatewayStateMutationAllowed") is not False:raise ControlledPrivateExecutionError("staging_execution_response_invalid")
    x=e.get("execution"); expected_x={"version","environment","engine","jobId","runId","dispatchIdentitySha256","sourceArtifactId","sourceSha256","sourceMediaType","candidateId","claimKey","outputCount","outputs","executionAttemptCount","engineExecutionPerformed","automaticRetryAllowed","restartReexecutionAllowed","resultReturnAllowed","resultPersistenceAllowed","gatewayStateMutationAllowed","reconciliationRequiredOnRestart"}
    if type(x) is not dict or set(x)!=expected_x or x.get("version")!="scoremosaic-controlled-engine-execution-v1" or x.get("environment")!="staging" or x.get("engine")!=i.engine or x.get("jobId")!=i.job_id or x.get("runId")!=i.run_id or x.get("dispatchIdentitySha256")!=i.identity_sha256 or x.get("sourceArtifactId")!=i.source_artifact_id or x.get("sourceSha256")!=capsule.source_sha256 or x.get("sourceMediaType")!=capsule.source_media_type or x.get("candidateId")!=i.candidate_id or type(x.get("claimKey")) is not str or _SHA_RE.fullmatch(x["claimKey"]) is None or x.get("executionAttemptCount")!=1 or x.get("engineExecutionPerformed") is not True or x.get("automaticRetryAllowed") is not False or x.get("restartReexecutionAllowed") is not False or x.get("resultReturnAllowed") is not False or x.get("resultPersistenceAllowed") is not False or x.get("gatewayStateMutationAllowed") is not False or x.get("reconciliationRequiredOnRestart") is not True:raise ControlledPrivateExecutionError("staging_execution_response_invalid")
    outputs=x.get("outputs")
    if type(outputs) is not list or not 1<=len(outputs)<=16 or x.get("outputCount")!=len(outputs):raise ControlledPrivateExecutionError("staging_execution_response_invalid")
    for o in outputs:
        if type(o) is not dict or set(o)!={"sizeBytes","sha256"} or type(o.get("sizeBytes")) is not int or not 1<=o["sizeBytes"]<=64*1024*1024 or type(o.get("sha256")) is not str or _SHA_RE.fullmatch(o["sha256"]) is None:raise ControlledPrivateExecutionError("staging_execution_response_invalid")

def execute_controlled_private_engine_once(*,minimum_slice:MinimumStagingVerticalSliceResult,provider:StagingUploadProvider,endpoint:EngineEndpoint,capsule:DispatchInputCapsule,dispatch_result:ControlledPrivateNetworkDispatchResult,source_delivery_result:ControlledPrivateSourceDeliveryResult,generation_id:str,credential_resolver:Callable[[str,str],object],now_seconds:int,nonce:str,transport:ExecutionTransport=_default_post)->ControlledPrivateExecutionResult:
    if type(minimum_slice) is not MinimumStagingVerticalSliceResult or type(provider) is not StagingUploadProvider or type(dispatch_result) is not ControlledPrivateNetworkDispatchResult or type(source_delivery_result) is not ControlledPrivateSourceDeliveryResult or type(now_seconds) is not int or now_seconds<0 or type(nonce) is not str or _NONCE_RE.fullmatch(nonce) is None or not callable(transport):raise ControlledPrivateExecutionError("staging_execution_input_invalid")
    checked=_endpoint(endpoint)
    if type(capsule) is not DispatchInputCapsule:raise ControlledPrivateExecutionError("staging_execution_capsule_invalid")
    try:verify_dispatch_input_capsule(capsule)
    except DispatchInputCapsuleError:raise ControlledPrivateExecutionError("staging_execution_capsule_invalid") from None
    i=capsule.dispatch_identity
    if i.engine!=checked.name:raise ControlledPrivateExecutionError("staging_execution_capsule_invalid")
    if dispatch_result.job_id!=i.job_id or dispatch_result.engine!=i.engine or dispatch_result.run_id!=i.run_id or dispatch_result.dispatch_identity_sha256!=i.identity_sha256 or dispatch_result.target_origin!=checked.base_url or dispatch_result.network_dispatch_performed is not True or dispatch_result.receiver_authenticated is not True or dispatch_result.trusted_plan_provisioned is not True or dispatch_result.retry_allowed is not False:raise ControlledPrivateExecutionError("staging_execution_dispatch_evidence_invalid")
    if source_delivery_result.job_id!=i.job_id or source_delivery_result.engine!=i.engine or source_delivery_result.run_id!=i.run_id or source_delivery_result.dispatch_identity_sha256!=i.identity_sha256 or source_delivery_result.source_artifact_id!=i.source_artifact_id or source_delivery_result.source_size_bytes!=capsule.source_size_bytes or source_delivery_result.source_sha256!=capsule.source_sha256 or source_delivery_result.source_media_type!=capsule.source_media_type or source_delivery_result.target_origin!=checked.base_url or source_delivery_result.source_persisted is not True or source_delivery_result.retry_allowed is not False:raise ControlledPrivateExecutionError("staging_execution_source_evidence_invalid")
    _verify_source_claim(provider,checked,capsule,source_delivery_result)
    timeout=_planned_timeout(capsule)
    try:recovery=recover_controlled_staging_dispatching_run(minimum_slice=minimum_slice,provider=provider,endpoint=checked)
    except ControlledStagingDispatchingTransitionError:raise ControlledPrivateExecutionError("staging_execution_durable_state_invalid") from None
    if recovery.state!="dispatching" or recovery.revision!=2 or recovery.disposition!="reconciliation_required" or recovery.reconciliation_required is not True or recovery.retry_allowed or recovery.network_dispatch_allowed or recovery.automatic_execution_allowed or recovery.state_mutation_allowed:raise ControlledPrivateExecutionError("staging_execution_durable_state_invalid")
    request=build_authenticated_execution_trigger_request(capsule=capsule,generation_id=generation_id,credential_resolver=credential_resolver,now_seconds=now_seconds,nonce=nonce)
    if request.timeout_seconds!=timeout:raise ControlledPrivateExecutionError("staging_execution_request_invalid")
    claim=_reserve_claim(provider,capsule,checked,timeout); response_timeout=timeout+RESPONSE_TIMEOUT_GRACE_SECONDS
    try:response=transport(checked.base_url,EXECUTION_TRIGGER_PATH,request.headers,request.body,CONNECT_TIMEOUT_SECONDS,response_timeout)
    except ControlledPrivateExecutionError:raise
    except Exception:raise ControlledPrivateExecutionError("staging_execution_transport_failed") from None
    if type(response) is not PrivateExecutionHttpResponse:raise ControlledPrivateExecutionError("staging_execution_transport_response_invalid")
    _accepted(response,capsule,request)
    return ControlledPrivateExecutionResult(CONTROLLED_PRIVATE_EXECUTION_VERSION,i.job_id,i.engine,i.run_id,i.identity_sha256,i.source_artifact_id,capsule.source_sha256,i.candidate_id,checked.base_url,claim,200,1,True)
