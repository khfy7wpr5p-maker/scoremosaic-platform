"""One-shot private source transfer for Stage 5-A2.

The Gateway may send source bytes only after a successful Stage 4-D authenticated
dispatch result. A durable create-once claim is published before network I/O; any
restart or repeated invocation after that claim performs zero network operations
and requires reconciliation. No engine execution, result persistence, retry, or
post-dispatch job mutation is enabled here.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from hmac import compare_digest, new as hmac_new
from http.client import HTTPConnection, HTTPResponse
import json, re, socket
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit
from .config import EngineEndpoint
from .controlled_private_network_dispatch import ControlledPrivateNetworkDispatchResult
from .dispatch_input_capsule import DispatchInputCapsule, DispatchInputCapsuleError, verify_dispatch_input_capsule
from .dispatch_target import APPROVED_ENGINE_ORIGINS
from .minimum_staging_vertical_slice import MinimumStagingVerticalSliceError, StagingUploadProvider, _MAX_STATE_RECORD_BYTES, _decode_record
from .source_delivery import SOURCE_DELIVERY_MAX_FUTURE_SKEW_SECONDS, SOURCE_DELIVERY_MAX_AGE_SECONDS, SOURCE_DELIVERY_PATH, SourceDeliveryError, build_source_delivery_binding, build_source_delivery_request, resolve_source_delivery_credential

CONTROLLED_PRIVATE_SOURCE_DELIVERY_VERSION="scoremosaic-controlled-private-source-delivery-v1"
MAX_SOURCE_RESPONSE_BYTES=16*1024
MIN_TIMEOUT_SECONDS=1
MAX_TIMEOUT_SECONDS=30
EXPECTED_RESPONSE_CONTENT_TYPE="application/json; charset=utf-8"
_CLAIM_DOMAIN=b"scoremosaic-controlled-private-source-delivery-claim-v1"
_CLAIM_MAC_FIELD="source_delivery_claim_integrity_mac"
_SHA256_RE=re.compile(r"[0-9a-f]{64}\Z")
_EXPECTED_BOUNDARIES={"automaticRetryAllowed":False,"restartResendAllowed":False,"redirectAllowed":False,"proxyRoutingAllowed":False,"engineExecutionAllowed":False,"resultPersistenceAllowed":False,"postDispatchJobMutationAllowed":False,"reconciliationRequired":True}

class ControlledPrivateSourceDeliveryError(ValueError):
    def __init__(self,category:str)->None: self.category=category; super().__init__(category)

@dataclass(frozen=True,slots=True)
class PrivateSourceHttpResponse:
    status:int; content_type:str; body:bytes; location:str|None=None
    def __post_init__(self)->None:
        if type(self.status) is not int or not 100<=self.status<=599 or type(self.content_type) is not str or type(self.body) is not bytes or len(self.body)>MAX_SOURCE_RESPONSE_BYTES or (self.location is not None and type(self.location) is not str): raise ControlledPrivateSourceDeliveryError("staging_source_transport_response_invalid")

SourceTransport=Callable[[str,str,tuple[tuple[str,str],...],bytes,int],PrivateSourceHttpResponse]

@dataclass(frozen=True,slots=True)
class ControlledPrivateSourceDeliveryResult:
    version:str; job_id:str; engine:str; run_id:str; dispatch_identity_sha256:str; source_artifact_id:str; source_size_bytes:int; source_sha256:str; source_media_type:str; target_origin:str; claim_key:str; http_status:int; source_attempt_count:int; reconciliation_required_on_restart:bool
    def __post_init__(self)->None:
        expected=APPROVED_ENGINE_ORIGINS["staging"].get(self.engine) if type(self.engine) is str else None
        if self.version!=CONTROLLED_PRIVATE_SOURCE_DELIVERY_VERSION or expected is None or self.target_origin!=expected or type(self.job_id) is not str or type(self.run_id) is not str or _SHA256_RE.fullmatch(self.dispatch_identity_sha256) is None or type(self.source_artifact_id) is not str or type(self.source_size_bytes) is not int or self.source_size_bytes<1 or _SHA256_RE.fullmatch(self.source_sha256) is None or type(self.source_media_type) is not str or _SHA256_RE.fullmatch(self.claim_key) is None or self.http_status!=201 or self.source_attempt_count!=1 or self.reconciliation_required_on_restart is not True: raise ControlledPrivateSourceDeliveryError("staging_source_result_invalid")
    @property
    def network_source_delivery_performed(self)->bool: return True
    @property
    def source_persisted(self)->bool: return True
    @property
    def engine_execution_allowed(self)->bool: return False
    @property
    def retry_allowed(self)->bool: return False
    @property
    def result_persistence_allowed(self)->bool: return False
    @property
    def post_dispatch_job_mutation_allowed(self)->bool: return False
    def as_safe_dict(self)->dict[str,object]:
        return {"version":self.version,"environment":"staging","jobId":self.job_id,"engine":self.engine,"runId":self.run_id,"dispatchIdentitySha256":self.dispatch_identity_sha256,"sourceArtifactId":self.source_artifact_id,"sourceSizeBytes":self.source_size_bytes,"sourceSha256":self.source_sha256,"sourceMediaType":self.source_media_type,"targetOrigin":self.target_origin,"claimKey":self.claim_key,"httpStatus":self.http_status,"sourceAttemptCount":1,"reconciliationRequiredOnRestart":True,"networkSourceDeliveryPerformed":True,"sourcePersisted":True,"engineExecutionAllowed":False,"retryAllowed":False,"resultPersistenceAllowed":False,"postDispatchJobMutationAllowed":False}

def _canonical_json(value:dict[str,Any])->bytes:
    try: return json.dumps(value,ensure_ascii=True,allow_nan=False,sort_keys=True,separators=(",",":")).encode("ascii")
    except Exception: raise ControlledPrivateSourceDeliveryError("staging_source_state_invalid") from None

def _strict_pairs(pairs:list[tuple[str,Any]])->dict[str,Any]:
    out={}
    for key,value in pairs:
        if type(key) is not str or key in out: raise ControlledPrivateSourceDeliveryError("staging_source_response_invalid")
        out[key]=value
    return out

def _strict_json(raw:bytes)->dict[str,Any]:
    if type(raw) is not bytes or not raw or len(raw)>MAX_SOURCE_RESPONSE_BYTES: raise ControlledPrivateSourceDeliveryError("staging_source_response_invalid")
    try: value=json.loads(raw.decode("utf-8"),object_pairs_hook=_strict_pairs,parse_constant=lambda _v: (_ for _ in ()).throw(ValueError()))
    except ControlledPrivateSourceDeliveryError: raise
    except Exception: raise ControlledPrivateSourceDeliveryError("staging_source_response_invalid") from None
    if type(value) is not dict: raise ControlledPrivateSourceDeliveryError("staging_source_response_invalid")
    return value

def _endpoint(endpoint:object)->EngineEndpoint:
    if type(endpoint) is not EngineEndpoint: raise ControlledPrivateSourceDeliveryError("staging_source_endpoint_invalid")
    expected=APPROVED_ENGINE_ORIGINS["staging"].get(endpoint.name)
    if expected is None or endpoint.base_url!=expected: raise ControlledPrivateSourceDeliveryError("staging_source_endpoint_invalid")
    try: parsed=urlsplit(endpoint.base_url); port=parsed.port
    except ValueError: raise ControlledPrivateSourceDeliveryError("staging_source_endpoint_invalid") from None
    if parsed.scheme!="http" or parsed.hostname is None or port is None or parsed.username is not None or parsed.password is not None or parsed.path not in {"","/"} or parsed.query or parsed.fragment: raise ControlledPrivateSourceDeliveryError("staging_source_endpoint_invalid")
    return endpoint

def _claim_key(capsule:DispatchInputCapsule,endpoint:EngineEndpoint)->str:
    i=capsule.dispatch_identity
    material="\x1f".join((CONTROLLED_PRIVATE_SOURCE_DELIVERY_VERSION,i.job_id,i.run_id,i.identity_sha256,i.source_artifact_id,capsule.source_sha256,str(capsule.source_size_bytes),capsule.source_media_type,endpoint.base_url)).encode("utf-8")
    return sha256(material).hexdigest()

def _claim_path(provider:StagingUploadProvider,key:str)->Path:
    return provider._root/"state"/"source_delivery_claims"/key[:2]/f"{key}.json"

def _claim_mac(provider:StagingUploadProvider,record:dict[str,Any])->str:
    key=getattr(provider,"_state_integrity_key",None)
    if type(key) is not bytes or len(key)!=32: raise ControlledPrivateSourceDeliveryError("staging_source_state_invalid")
    return hmac_new(key,b"\0".join((_CLAIM_DOMAIN,_canonical_json(record))),sha256).hexdigest()

def _reserve_claim(provider:StagingUploadProvider,capsule:DispatchInputCapsule,endpoint:EngineEndpoint)->str:
    key=_claim_key(capsule,endpoint); i=capsule.dispatch_identity
    record={"version":CONTROLLED_PRIVATE_SOURCE_DELIVERY_VERSION,"environment":"staging","claimKey":key,"jobId":i.job_id,"engine":i.engine,"runId":i.run_id,"dispatchIdentitySha256":i.identity_sha256,"sourceArtifactId":i.source_artifact_id,"sourceSizeBytes":capsule.source_size_bytes,"sourceSha256":capsule.source_sha256,"sourceMediaType":capsule.source_media_type,"targetOrigin":endpoint.base_url,"boundaries":dict(_EXPECTED_BOUNDARIES)}
    sealed=dict(record); sealed[_CLAIM_MAC_FIELD]=_claim_mac(provider,record); payload=_canonical_json(sealed)
    if len(payload)>_MAX_STATE_RECORD_BYTES: raise ControlledPrivateSourceDeliveryError("staging_source_state_invalid")
    path=_claim_path(provider,key)
    try:
        created=provider._atomic_create(path,payload)
        if created: return key
        raw=provider._read_file_no_follow(path,max_bytes=_MAX_STATE_RECORD_BYTES,overflow_category="staging_state_corrupt")
        stored=_decode_record(raw)
    except MinimumStagingVerticalSliceError: raise ControlledPrivateSourceDeliveryError("staging_source_state_invalid") from None
    if type(stored) is not dict or _CLAIM_MAC_FIELD not in stored or _canonical_json(stored)!=raw: raise ControlledPrivateSourceDeliveryError("staging_source_state_invalid")
    observed=stored.get(_CLAIM_MAC_FIELD); raw_record=dict(stored); raw_record.pop(_CLAIM_MAC_FIELD,None)
    if type(observed) is not str or not compare_digest(observed,_claim_mac(provider,raw_record)) or raw_record!=record: raise ControlledPrivateSourceDeliveryError("staging_source_state_invalid")
    raise ControlledPrivateSourceDeliveryError("staging_source_reconciliation_required")

def _default_post(origin:str,path:str,headers:tuple[tuple[str,str],...],body:bytes,timeout:int)->PrivateSourceHttpResponse:
    parsed=urlsplit(origin)
    if parsed.scheme!="http" or parsed.hostname is None or parsed.port is None or path!=SOURCE_DELIVERY_PATH: raise ControlledPrivateSourceDeliveryError("staging_source_transport_target_invalid")
    connection=HTTPConnection(parsed.hostname,parsed.port,timeout=timeout)
    try:
        connection.request("POST",path,body=body,headers=dict(headers)); response:HTTPResponse=connection.getresponse(); response_body=response.read(MAX_SOURCE_RESPONSE_BYTES+1)
        if len(response_body)>MAX_SOURCE_RESPONSE_BYTES: raise ControlledPrivateSourceDeliveryError("staging_source_response_too_large")
        return PrivateSourceHttpResponse(status=int(response.status),content_type=response.getheader("Content-Type",""),body=response_body,location=response.getheader("Location"))
    except ControlledPrivateSourceDeliveryError: raise
    except (TimeoutError,socket.timeout,OSError): raise ControlledPrivateSourceDeliveryError("staging_source_transport_failed") from None
    except Exception: raise ControlledPrivateSourceDeliveryError("staging_source_transport_failed") from None
    finally:
        try: connection.close()
        except Exception: pass

def _accepted(response:PrivateSourceHttpResponse,request)->None:
    if 300<=response.status<=399 or response.location is not None: raise ControlledPrivateSourceDeliveryError("staging_source_redirect_forbidden")
    if response.status!=201: raise ControlledPrivateSourceDeliveryError("staging_source_receiver_rejected")
    if response.content_type!=EXPECTED_RESPONSE_CONTENT_TYPE: raise ControlledPrivateSourceDeliveryError("staging_source_response_invalid")
    value=_strict_json(response.body); evidence=value.get("evidence")
    expected_keys={"version","environment","engine","jobId","runId","dispatchIdentitySha256","sourceArtifactId","sourceSizeBytes","sourceSha256","sourceMediaType","credentialGenerationId","timestamp","nonceSha256","persistenceState","authenticated","trustedPlanConverged","sourcePersisted","engineExecutionAllowed","retryAllowed"}
    if set(value)!={"status","kind","evidence","engineExecutionAllowed"} or value.get("status")!="accepted" or value.get("kind")!="source" or value.get("engineExecutionAllowed") is not False or type(evidence) is not dict or set(evidence)!=expected_keys: raise ControlledPrivateSourceDeliveryError("staging_source_response_invalid")
    if evidence.get("version")!="scoremosaic-source-delivery-v1" or evidence.get("environment")!="staging" or evidence.get("engine")!=request.engine or evidence.get("jobId")!=request.job_id or evidence.get("runId")!=request.run_id or evidence.get("dispatchIdentitySha256")!=request.dispatch_identity_sha256 or evidence.get("sourceArtifactId")!=request.source_artifact_id or evidence.get("sourceSizeBytes")!=request.source_size_bytes or evidence.get("sourceSha256")!=request.source_sha256 or evidence.get("sourceMediaType")!=request.source_media_type or evidence.get("credentialGenerationId")!=request.credential_generation_id or evidence.get("timestamp")!=request.timestamp or evidence.get("nonceSha256")!=request.nonce_sha256 or evidence.get("persistenceState")!="written" or evidence.get("authenticated") is not True or evidence.get("trustedPlanConverged") is not True or evidence.get("sourcePersisted") is not True or evidence.get("engineExecutionAllowed") is not False or evidence.get("retryAllowed") is not False: raise ControlledPrivateSourceDeliveryError("staging_source_response_invalid")

def deliver_controlled_private_source_once(*,provider:StagingUploadProvider,endpoint:EngineEndpoint,capsule:DispatchInputCapsule,dispatch_result:ControlledPrivateNetworkDispatchResult,generation_id:str,credential_resolver:Callable[[str,str],object],now_seconds:int,nonce:str,timeout_seconds:int=10,transport:SourceTransport=_default_post)->ControlledPrivateSourceDeliveryResult:
    if type(provider) is not StagingUploadProvider or type(dispatch_result) is not ControlledPrivateNetworkDispatchResult or type(now_seconds) is not int or now_seconds<0 or type(timeout_seconds) is not int or not MIN_TIMEOUT_SECONDS<=timeout_seconds<=MAX_TIMEOUT_SECONDS or not callable(credential_resolver) or not callable(transport): raise ControlledPrivateSourceDeliveryError("staging_source_input_invalid")
    checked_endpoint=_endpoint(endpoint)
    if type(capsule) is not DispatchInputCapsule: raise ControlledPrivateSourceDeliveryError("staging_source_capsule_invalid")
    try: verify_dispatch_input_capsule(capsule)
    except DispatchInputCapsuleError: raise ControlledPrivateSourceDeliveryError("staging_source_capsule_invalid") from None
    i=capsule.dispatch_identity
    if dispatch_result.job_id!=i.job_id or dispatch_result.engine!=i.engine or dispatch_result.run_id!=i.run_id or dispatch_result.dispatch_identity_sha256!=i.identity_sha256 or dispatch_result.target_origin!=checked_endpoint.base_url or dispatch_result.network_dispatch_performed is not True or dispatch_result.receiver_authenticated is not True or dispatch_result.trusted_plan_provisioned is not True or dispatch_result.engine_execution_allowed is not False or dispatch_result.retry_allowed is not False: raise ControlledPrivateSourceDeliveryError("staging_source_dispatch_evidence_invalid")
    try:
        binding=build_source_delivery_binding(checked_endpoint); credential=resolve_source_delivery_credential(binding,generation_id=generation_id,resolver=credential_resolver); request=build_source_delivery_request(capsule=capsule,credential=credential,timestamp=now_seconds,nonce=nonce)
    except SourceDeliveryError: raise ControlledPrivateSourceDeliveryError("staging_source_request_invalid") from None
    if request.timestamp>now_seconds+SOURCE_DELIVERY_MAX_FUTURE_SKEW_SECONDS or now_seconds-request.timestamp>SOURCE_DELIVERY_MAX_AGE_SECONDS: raise ControlledPrivateSourceDeliveryError("staging_source_request_invalid")
    claim_key=_reserve_claim(provider,capsule,checked_endpoint)
    headers=(("content-type",request.source_media_type),("content-length",str(len(request.body))),*request.headers)
    try: response=transport(checked_endpoint.base_url,SOURCE_DELIVERY_PATH,headers,request.body,timeout_seconds)
    except ControlledPrivateSourceDeliveryError: raise
    except Exception: raise ControlledPrivateSourceDeliveryError("staging_source_transport_failed") from None
    if type(response) is not PrivateSourceHttpResponse: raise ControlledPrivateSourceDeliveryError("staging_source_transport_response_invalid")
    _accepted(response,request)
    return ControlledPrivateSourceDeliveryResult(version=CONTROLLED_PRIVATE_SOURCE_DELIVERY_VERSION,job_id=i.job_id,engine=i.engine,run_id=i.run_id,dispatch_identity_sha256=i.identity_sha256,source_artifact_id=i.source_artifact_id,source_size_bytes=capsule.source_size_bytes,source_sha256=capsule.source_sha256,source_media_type=capsule.source_media_type,target_origin=checked_endpoint.base_url,claim_key=claim_key,http_status=response.status,source_attempt_count=1,reconciliation_required_on_restart=True)
