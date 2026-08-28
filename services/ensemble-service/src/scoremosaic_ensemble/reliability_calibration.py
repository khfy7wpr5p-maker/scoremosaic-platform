"""Research-only engine reliability calibration evidence for polyphonic OMR."""
from __future__ import annotations
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
import json, re
from typing import Any, Iterable, Mapping

OBSERVATION_SCHEMA_VERSION="scoremosaic-engine-reliability-observation-v1"
REPORT_SCHEMA_VERSION="scoremosaic-engine-reliability-report-v1"
BINNING_METHOD="FIXED_10_BIN_BASIS_POINTS_V1"
BRIER_METHOD="BINARY_BRIER_EXACT_RATIONAL_V1"
ECE_METHOD="FIXED_BIN_ECE_EXACT_RATIONAL_V1"
CORRECTNESS_METHOD="TEACHER_GOLD_BINARY_CORRECTNESS_V1"
CONFIDENCE_SCALE="CORRECTNESS_CONFIDENCE_BASIS_POINTS_V1"
CURRENT_ENGINES=("audiveris","homr","clarity")
TARGET_CATEGORIES=("parse","structuralValidity","pitch","duration","onset","voice","staff","tie","tuplet","measureConsistency","relationCorrectness")
SOURCE_QUALITY_SEVERITIES=("LOW","MODERATE","HIGH","SEVERE","UNAVAILABLE")
CONFIDENCE_SOURCES=("ENGINE_NATIVE_REPORTED","IMPORTED_BENCHMARK_TELEMETRY","REPOSITORY_RESEARCH_FIXTURE")
MAX_OBSERVATIONS=100_000; MAX_GROUPS=2_048; MAX_CONTEXT_SLICES=8_192
_SHA_RE=re.compile(r"[0-9a-f]{64}\Z"); _OBS_RE=re.compile(r"reliability_obs_[0-9a-f]{24}\Z"); _REPORT_RE=re.compile(r"reliability_report_[0-9a-f]{24}\Z")
_FIXTURE_RE=re.compile(r"poly_fixture_[A-Za-z0-9_-]{8,96}\Z"); _ID_RE=re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z"); _VER_RE=re.compile(r"[A-Za-z0-9][A-Za-z0-9._+:-]{0,127}\Z")
_BOUNDARIES={"researchOnly":True,"readOnly":True,"confidenceRewriting":False,"recalibratedProbabilityOutput":False,"engineRanking":False,"winnerSelection":False,"selectivePrediction":False,"productionThreshold":False,"productionDecisionAuthority":False,"automaticMerge":False,"automaticCorrection":False,"teacherAuthorityOverride":False,"stage7EvidenceMutation":False,"stage7QuorumChange":False,"stOmrIntegration":False}

class ReliabilityCalibrationError(ValueError):
    def __init__(self, category:str): self.category=category; super().__init__(category)

def _canonical_json(value:Any)->bytes:
    try: return json.dumps(value,ensure_ascii=True,allow_nan=False,sort_keys=True,separators=(",",":")).encode("ascii")
    except (TypeError,ValueError,OverflowError,UnicodeEncodeError): raise ReliabilityCalibrationError("non_canonical_json") from None

def _exact(v:object, keys:set[str], err:str)->Mapping[str,Any]:
    if type(v) is not dict or set(v)!=keys: raise ReliabilityCalibrationError(err)
    return v

def _match(rx:re.Pattern[str],v:object)->bool: return type(v) is str and rx.fullmatch(v) is not None

def _frac(v:Fraction)->dict[str,int]: return {"numerator":v.numerator,"denominator":v.denominator}

def _check_frac(v:object,err:str,unit=False):
    x=_exact(v,{"numerator","denominator"},err); n=x["numerator"]; d=x["denominator"]
    if type(n) is not int or type(d) is not int or d<=0: raise ReliabilityCalibrationError(err)
    f=Fraction(n,d)
    if (f.numerator,f.denominator)!=(n,d) or (unit and not 0<=f<=1): raise ReliabilityCalibrationError(err)

def _no_complexity(): return {"available":False,"profileId":None,"profileSha256":None,"voiceCount":None,"maxSimultaneousVoiceCount":None,"multiStaffPresent":None,"tupletPresent":None,"overlapDensityBasisPoints":None}
def _no_quality(): return {"available":False,"profileId":None,"profileSha256":None,"severity":None,"maxDegradationRiskBasisPoints":None}

def _check_complexity(v:object):
    keys=set(_no_complexity()); x=_exact(v,keys,"complexity_context_invalid")
    if type(x["available"]) is not bool: raise ReliabilityCalibrationError("complexity_context_invalid")
    if not x["available"]:
        if any(x[k] is not None for k in keys-{"available"}): raise ReliabilityCalibrationError("complexity_context_invalid")
        return
    if not (type(x["profileId"]) is str and re.fullmatch(r"complexity_[0-9a-f]{24}",x["profileId"]) and _match(_SHA_RE,x["profileSha256"])): raise ReliabilityCalibrationError("complexity_context_invalid")
    if type(x["voiceCount"]) is not int or not 0<=x["voiceCount"]<=512: raise ReliabilityCalibrationError("complexity_context_invalid")
    m=x["maxSimultaneousVoiceCount"]
    if m is not None and (type(m) is not int or not 0<=m<=512): raise ReliabilityCalibrationError("complexity_context_invalid")
    ms=x["multiStaffPresent"]
    if ms is not None and type(ms) is not bool: raise ReliabilityCalibrationError("complexity_context_invalid")
    if type(x["tupletPresent"]) is not bool: raise ReliabilityCalibrationError("complexity_context_invalid")
    o=x["overlapDensityBasisPoints"]
    if type(o) is not int or not 0<=o<=10_000: raise ReliabilityCalibrationError("complexity_context_invalid")

def _check_quality(v:object):
    keys=set(_no_quality()); x=_exact(v,keys,"source_quality_context_invalid")
    if type(x["available"]) is not bool: raise ReliabilityCalibrationError("source_quality_context_invalid")
    if not x["available"]:
        if any(x[k] is not None for k in keys-{"available"}): raise ReliabilityCalibrationError("source_quality_context_invalid")
        return
    if not (type(x["profileId"]) is str and re.fullmatch(r"source_quality_[0-9a-f]{24}",x["profileId"]) and _match(_SHA_RE,x["profileSha256"])): raise ReliabilityCalibrationError("source_quality_context_invalid")
    if x["severity"] not in SOURCE_QUALITY_SEVERITIES: raise ReliabilityCalibrationError("source_quality_context_invalid")
    r=x["maxDegradationRiskBasisPoints"]
    if r is not None and (type(r) is not int or not 0<=r<=10_000): raise ReliabilityCalibrationError("source_quality_context_invalid")
    if (x["severity"]=="UNAVAILABLE")!=(r is None): raise ReliabilityCalibrationError("source_quality_context_invalid")

def validate_reliability_observation(payload:Mapping[str,Any])->dict[str,Any]:
    keys={"schemaVersion","observationId","fixtureId","target","engine","confidence","context","provenance","boundaries","observationSha256"}; x=_exact(payload,keys,"reliability_observation_schema_invalid")
    if x["schemaVersion"]!=OBSERVATION_SCHEMA_VERSION or not _match(_OBS_RE,x["observationId"]) or not _match(_FIXTURE_RE,x["fixtureId"]): raise ReliabilityCalibrationError("reliability_observation_schema_invalid")
    t=_exact(x["target"],{"category","targetUnitId","correct","method"},"reliability_target_invalid")
    if t["category"] not in TARGET_CATEGORIES or not _match(_ID_RE,t["targetUnitId"]) or type(t["correct"]) is not bool or t["method"]!=CORRECTNESS_METHOD: raise ReliabilityCalibrationError("reliability_target_invalid")
    e=_exact(x["engine"],{"name","engineVersion","modelVersion"},"reliability_engine_invalid")
    if e["name"] not in CURRENT_ENGINES or not _match(_VER_RE,e["engineVersion"]) or not _match(_VER_RE,e["modelVersion"]): raise ReliabilityCalibrationError("reliability_engine_invalid")
    c=_exact(x["confidence"],{"available","basisPoints","evidenceSource","methodVersion","scale","scope","calibratedInput"},"confidence_evidence_invalid")
    if type(c["available"]) is not bool: raise ReliabilityCalibrationError("confidence_evidence_invalid")
    if c["available"]:
        if type(c["basisPoints"]) is not int or not 0<=c["basisPoints"]<=10_000 or c["evidenceSource"] not in CONFIDENCE_SOURCES or not _match(_VER_RE,c["methodVersion"]) or c["scale"]!=CONFIDENCE_SCALE or c["scope"]!="TARGET_UNIT_CORRECTNESS" or c["calibratedInput"] is not False: raise ReliabilityCalibrationError("confidence_evidence_invalid")
    elif any(c[k] is not None for k in c if k!="available"): raise ReliabilityCalibrationError("confidence_evidence_invalid")
    ctx=_exact(x["context"],{"complexity","sourceQuality"},"reliability_context_invalid"); _check_complexity(ctx["complexity"]); _check_quality(ctx["sourceQuality"])
    p=_exact(x["provenance"],{"teacherGoldReferenceSha256","semanticEvidenceSha256","contextBindingMethodVersion"},"reliability_provenance_invalid")
    if not _match(_SHA_RE,p["teacherGoldReferenceSha256"]) or not _match(_SHA_RE,p["semanticEvidenceSha256"]) or not _match(_VER_RE,p["contextBindingMethodVersion"]): raise ReliabilityCalibrationError("reliability_provenance_invalid")
    b=_exact(x["boundaries"],set(_BOUNDARIES),"authority_boundary_invalid")
    if any(b[k] is not v for k,v in _BOUNDARIES.items()): raise ReliabilityCalibrationError("authority_boundary_invalid")
    if not _match(_SHA_RE,x["observationSha256"]): raise ReliabilityCalibrationError("reliability_observation_hash_invalid")
    h=deepcopy(dict(x)); h.pop("observationSha256")
    if x["observationSha256"]!=sha256(_canonical_json(h)).hexdigest(): raise ReliabilityCalibrationError("reliability_observation_hash_invalid")
    ident=deepcopy(dict(x)); ident.pop("observationId"); ident.pop("observationSha256")
    if x["observationId"]!="reliability_obs_"+sha256(_canonical_json(ident)).hexdigest()[:24]: raise ReliabilityCalibrationError("reliability_observation_id_mismatch")
    return deepcopy(dict(x))

def complexity_context_from_profile(profile:Mapping[str,Any])->dict[str,Any]:
    from .polyphony_complexity import validate_polyphony_complexity_profile
    p=validate_polyphony_complexity_profile(profile); d=p["dimensions"]
    def val(section,name):
        m=d[section][name]; return m["value"] if m["available"] else None
    out={"available":True,"profileId":p["profileId"],"profileSha256":p["profileSha256"],"voiceCount":val("voiceComplexity","voiceCount"),"maxSimultaneousVoiceCount":val("voiceComplexity","maxSimultaneousVoiceCount"),"multiStaffPresent":val("staffComplexity","multiStaffPresent"),"tupletPresent":val("tupletComplexity","tupletPresent"),"overlapDensityBasisPoints":val("overlapComplexity","overlapDensity")}
    _check_complexity(out); return out

def source_quality_context_from_profile(profile:Mapping[str,Any])->dict[str,Any]:
    from .source_quality import validate_source_quality_profile
    p=validate_source_quality_profile(profile); d=p["derivedState"]
    out={"available":True,"profileId":p["profileId"],"profileSha256":p["profileSha256"],"severity":d["severity"],"maxDegradationRiskBasisPoints":d["maxDegradationRiskBasisPoints"]}; _check_quality(out); return out

def build_reliability_observation(*,fixture_id:str,target_category:str,target_unit_id:str,correct:bool,engine:str,engine_version:str,model_version:str,confidence_basis_points:int|None,confidence_evidence_source:str|None,confidence_method_version:str|None,teacher_gold_reference_sha256:str,semantic_evidence_sha256:str,context_binding_method_version:str,complexity:Mapping[str,Any]|None=None,source_quality:Mapping[str,Any]|None=None)->dict[str,Any]:
    avail=confidence_basis_points is not None
    if not avail and (confidence_evidence_source is not None or confidence_method_version is not None): raise ReliabilityCalibrationError("confidence_evidence_invalid")
    c={"available":False,"basisPoints":None,"evidenceSource":None,"methodVersion":None,"scale":None,"scope":None,"calibratedInput":None}
    if avail: c={"available":True,"basisPoints":confidence_basis_points,"evidenceSource":confidence_evidence_source,"methodVersion":confidence_method_version,"scale":CONFIDENCE_SCALE,"scope":"TARGET_UNIT_CORRECTNESS","calibratedInput":False}
    x={"schemaVersion":OBSERVATION_SCHEMA_VERSION,"observationId":"placeholder","fixtureId":fixture_id,"target":{"category":target_category,"targetUnitId":target_unit_id,"correct":correct,"method":CORRECTNESS_METHOD},"engine":{"name":engine,"engineVersion":engine_version,"modelVersion":model_version},"confidence":c,"context":{"complexity":deepcopy(dict(complexity)) if complexity is not None else _no_complexity(),"sourceQuality":deepcopy(dict(source_quality)) if source_quality is not None else _no_quality()},"provenance":{"teacherGoldReferenceSha256":teacher_gold_reference_sha256,"semanticEvidenceSha256":semantic_evidence_sha256,"contextBindingMethodVersion":context_binding_method_version},"boundaries":deepcopy(_BOUNDARIES)}
    ident=deepcopy(x); ident.pop("observationId"); x["observationId"]="reliability_obs_"+sha256(_canonical_json(ident)).hexdigest()[:24]; x["observationSha256"]=sha256(_canonical_json(x)).hexdigest(); return validate_reliability_observation(x)

def _bin(bp:int)->int: return min(9,bp//1000)
def _metrics(items:list[Mapping[str,Any]])->dict[str,Any]:
    n=len(items)
    if not n: raise ReliabilityCalibrationError("empty_calibration_group")
    correct=sum(i["target"]["correct"] for i in items); conf=sum(i["confidence"]["basisPoints"] for i in items)
    bnum=sum((10_000-i["confidence"]["basisPoints"])**2 if i["target"]["correct"] else i["confidence"]["basisPoints"]**2 for i in items)
    bins=[]; ece_num=0
    for k in range(10):
        bucket=[i for i in items if _bin(i["confidence"]["basisPoints"])==k]; lo=k*1000; hi=10_000 if k==9 else (k+1)*1000-1
        if not bucket: bins.append({"index":k,"lowerInclusiveBasisPoints":lo,"upperInclusiveBasisPoints":hi,"observationCount":0,"correctCount":0,"empiricalAccuracy":None,"meanReportedConfidenceBasisPoints":None,"absoluteCalibrationGap":None}); continue
        bn=len(bucket); bc=sum(i["target"]["correct"] for i in bucket); bs=sum(i["confidence"]["basisPoints"] for i in bucket); delta=abs(bc*10_000-bs); ece_num+=delta
        bins.append({"index":k,"lowerInclusiveBasisPoints":lo,"upperInclusiveBasisPoints":hi,"observationCount":bn,"correctCount":bc,"empiricalAccuracy":_frac(Fraction(bc,bn)),"meanReportedConfidenceBasisPoints":_frac(Fraction(bs,bn)),"absoluteCalibrationGap":_frac(Fraction(delta,bn*10_000))})
    return {"observationCount":n,"correctCount":correct,"empiricalAccuracy":_frac(Fraction(correct,n)),"meanReportedConfidenceBasisPoints":_frac(Fraction(conf,n)),"brierScore":_frac(Fraction(bnum,n*100_000_000)),"expectedCalibrationError":_frac(Fraction(ece_num,n*10_000)),"reliabilityBins":bins}

def _overlap_band(v:int)->str:
    return "ZERO" if v==0 else "LOW_NONZERO" if v<2500 else "MODERATE" if v<5000 else "HIGH" if v<7500 else "VERY_HIGH"
def _slice_values(i:Mapping[str,Any])->list[tuple[str,str]]:
    out=[]; c=i["context"]["complexity"]
    if c["available"]:
        out += [("voiceCount",str(c["voiceCount"])),("tupletPresent","true" if c["tupletPresent"] else "false"),("overlapDensityBand",_overlap_band(c["overlapDensityBasisPoints"]))]
        if c["multiStaffPresent"] is not None: out.append(("multiStaffPresent","true" if c["multiStaffPresent"] else "false"))
        if c["maxSimultaneousVoiceCount"] is not None: out.append(("maxSimultaneousVoiceCount",str(c["maxSimultaneousVoiceCount"])))
    q=i["context"]["sourceQuality"]
    if q["available"]: out.append(("sourceQualitySeverity",q["severity"]))
    return out

def build_reliability_report(observations:Iterable[Mapping[str,Any]])->dict[str,Any]:
    items=[validate_reliability_observation(i) for i in observations]
    if len(items)>MAX_OBSERVATIONS: raise ReliabilityCalibrationError("observation_limit_exceeded")
    ids=set(); units=set()
    for i in items:
        if i["observationId"] in ids: raise ReliabilityCalibrationError("duplicate_reliability_observation")
        ids.add(i["observationId"]); c=i["confidence"]; key=(i["fixtureId"],i["engine"]["name"],i["engine"]["engineVersion"],i["engine"]["modelVersion"],i["target"]["category"],i["target"]["targetUnitId"],c["evidenceSource"],c["methodVersion"])
        if key in units: raise ReliabilityCalibrationError("duplicate_reliability_target_unit")
        units.add(key)
    eligible=[i for i in items if i["confidence"]["available"]]; grouped={}
    for i in eligible: grouped.setdefault((i["engine"]["name"],i["target"]["category"],i["confidence"]["methodVersion"]),[]).append(i)
    if len(grouped)>MAX_GROUPS: raise ReliabilityCalibrationError("group_limit_exceeded")
    order=lambda k:(CURRENT_ENGINES.index(k[0]),k[1],k[2])
    groups=[]
    for k in sorted(grouped,key=order):
        g=grouped[k]; groups.append({"engine":k[0],"category":k[1],"confidenceMethodVersion":k[2],**_metrics(g),"contextCoverage":{"complexityObservationCount":sum(i["context"]["complexity"]["available"] for i in g),"sourceQualityObservationCount":sum(i["context"]["sourceQuality"]["available"] for i in g)}})
    sm={}
    for i in eligible:
        base=(i["engine"]["name"],i["target"]["category"],i["confidence"]["methodVersion"])
        for d,v in _slice_values(i): sm.setdefault(base+(d,v),[]).append(i)
    if len(sm)>MAX_CONTEXT_SLICES: raise ReliabilityCalibrationError("context_slice_limit_exceeded")
    slices=[]
    for k in sorted(sm,key=lambda x:(CURRENT_ENGINES.index(x[0]),x[1],x[2],x[3],x[4])):
        m=_metrics(sm[k]); m.pop("reliabilityBins"); slices.append({"engine":k[0],"category":k[1],"confidenceMethodVersion":k[2],"dimension":k[3],"value":k[4],**m})
    x={"schemaVersion":REPORT_SCHEMA_VERSION,"reportId":"placeholder","method":{"binning":BINNING_METHOD,"brier":BRIER_METHOD,"expectedCalibrationError":ECE_METHOD,"fittedCalibrationModel":None,"recalibratedProbability":None},"observationCount":len(items),"eligibleObservationCount":len(eligible),"observationSetSha256":sha256(_canonical_json(sorted(i["observationSha256"] for i in items))).hexdigest(),"groups":groups,"contextSlices":slices,"boundaries":deepcopy(_BOUNDARIES)}
    ident=deepcopy(x); ident.pop("reportId"); x["reportId"]="reliability_report_"+sha256(_canonical_json(ident)).hexdigest()[:24]; x["reportSha256"]=sha256(_canonical_json(x)).hexdigest(); return validate_reliability_report(x)

def _check_metric(x:Mapping[str,Any],bins=False):
    if type(x["observationCount"]) is not int or x["observationCount"]<=0 or type(x["correctCount"]) is not int or not 0<=x["correctCount"]<=x["observationCount"]: raise ReliabilityCalibrationError("calibration_metric_invalid")
    _check_frac(x["empiricalAccuracy"],"calibration_metric_invalid",True); _check_frac(x["meanReportedConfidenceBasisPoints"],"calibration_metric_invalid"); _check_frac(x["brierScore"],"calibration_metric_invalid",True); _check_frac(x["expectedCalibrationError"],"calibration_metric_invalid",True)
    mean=Fraction(x["meanReportedConfidenceBasisPoints"]["numerator"],x["meanReportedConfidenceBasisPoints"]["denominator"])
    if not 0<=mean<=10_000: raise ReliabilityCalibrationError("calibration_metric_invalid")
    if bins:
        bs=x["reliabilityBins"]
        if type(bs) is not list or len(bs)!=10: raise ReliabilityCalibrationError("reliability_bins_invalid")
        total=right=0
        keys={"index","lowerInclusiveBasisPoints","upperInclusiveBasisPoints","observationCount","correctCount","empiricalAccuracy","meanReportedConfidenceBasisPoints","absoluteCalibrationGap"}
        for k,b0 in enumerate(bs):
            b=_exact(b0,keys,"reliability_bins_invalid"); lo=k*1000; hi=10_000 if k==9 else (k+1)*1000-1
            if b["index"]!=k or b["lowerInclusiveBasisPoints"]!=lo or b["upperInclusiveBasisPoints"]!=hi or type(b["observationCount"]) is not int or type(b["correctCount"]) is not int or b["observationCount"]<0 or not 0<=b["correctCount"]<=b["observationCount"]: raise ReliabilityCalibrationError("reliability_bins_invalid")
            total+=b["observationCount"]; right+=b["correctCount"]
            vals=(b["empiricalAccuracy"],b["meanReportedConfidenceBasisPoints"],b["absoluteCalibrationGap"])
            if b["observationCount"]==0:
                if any(v is not None for v in vals): raise ReliabilityCalibrationError("reliability_bins_invalid")
            else:
                _check_frac(vals[0],"reliability_bins_invalid",True); _check_frac(vals[1],"reliability_bins_invalid"); _check_frac(vals[2],"reliability_bins_invalid",True)
        if total!=x["observationCount"] or right!=x["correctCount"]: raise ReliabilityCalibrationError("reliability_bins_invalid")

def validate_reliability_report(payload:Mapping[str,Any])->dict[str,Any]:
    keys={"schemaVersion","reportId","method","observationCount","eligibleObservationCount","observationSetSha256","groups","contextSlices","boundaries","reportSha256"}; x=_exact(payload,keys,"reliability_report_schema_invalid")
    if x["schemaVersion"]!=REPORT_SCHEMA_VERSION or not _match(_REPORT_RE,x["reportId"]): raise ReliabilityCalibrationError("reliability_report_schema_invalid")
    m=_exact(x["method"],{"binning","brier","expectedCalibrationError","fittedCalibrationModel","recalibratedProbability"},"reliability_report_method_invalid")
    if m!={"binning":BINNING_METHOD,"brier":BRIER_METHOD,"expectedCalibrationError":ECE_METHOD,"fittedCalibrationModel":None,"recalibratedProbability":None}: raise ReliabilityCalibrationError("reliability_report_method_invalid")
    if type(x["observationCount"]) is not int or not 0<=x["observationCount"]<=MAX_OBSERVATIONS or type(x["eligibleObservationCount"]) is not int or not 0<=x["eligibleObservationCount"]<=x["observationCount"] or not _match(_SHA_RE,x["observationSetSha256"]) or type(x["groups"]) is not list or len(x["groups"])>MAX_GROUPS or type(x["contextSlices"]) is not list or len(x["contextSlices"])>MAX_CONTEXT_SLICES: raise ReliabilityCalibrationError("reliability_report_counts_invalid")
    gkeys={"engine","category","confidenceMethodVersion","observationCount","correctCount","empiricalAccuracy","meanReportedConfidenceBasisPoints","brierScore","expectedCalibrationError","reliabilityBins","contextCoverage"}; total=0; seen=set()
    for g0 in x["groups"]:
        g=_exact(g0,gkeys,"reliability_group_invalid"); k=(g["engine"],g["category"],g["confidenceMethodVersion"])
        if g["engine"] not in CURRENT_ENGINES or g["category"] not in TARGET_CATEGORIES or not _match(_VER_RE,g["confidenceMethodVersion"]) or k in seen: raise ReliabilityCalibrationError("reliability_group_invalid")
        seen.add(k); _check_metric(g,True); cov=_exact(g["contextCoverage"],{"complexityObservationCount","sourceQualityObservationCount"},"context_coverage_invalid")
        if any(type(v) is not int or not 0<=v<=g["observationCount"] for v in cov.values()): raise ReliabilityCalibrationError("context_coverage_invalid")
        total+=g["observationCount"]
    if total!=x["eligibleObservationCount"]: raise ReliabilityCalibrationError("eligible_group_count_mismatch")
    skeys={"engine","category","confidenceMethodVersion","dimension","value","observationCount","correctCount","empiricalAccuracy","meanReportedConfidenceBasisPoints","brierScore","expectedCalibrationError"}; seen=set()
    for s0 in x["contextSlices"]:
        s=_exact(s0,skeys,"context_slice_invalid"); k=(s["engine"],s["category"],s["confidenceMethodVersion"],s["dimension"],s["value"])
        if s["engine"] not in CURRENT_ENGINES or s["category"] not in TARGET_CATEGORIES or not _match(_VER_RE,s["confidenceMethodVersion"]) or not _match(_ID_RE,s["dimension"]) or not _match(_ID_RE,s["value"]) or k in seen: raise ReliabilityCalibrationError("context_slice_invalid")
        seen.add(k); _check_metric(s,False)
    b=_exact(x["boundaries"],set(_BOUNDARIES),"authority_boundary_invalid")
    if any(b[k] is not v for k,v in _BOUNDARIES.items()): raise ReliabilityCalibrationError("authority_boundary_invalid")
    if not _match(_SHA_RE,x["reportSha256"]): raise ReliabilityCalibrationError("reliability_report_hash_invalid")
    h=deepcopy(dict(x)); h.pop("reportSha256")
    if x["reportSha256"]!=sha256(_canonical_json(h)).hexdigest(): raise ReliabilityCalibrationError("reliability_report_hash_invalid")
    ident=deepcopy(dict(x)); ident.pop("reportId"); ident.pop("reportSha256")
    if x["reportId"]!="reliability_report_"+sha256(_canonical_json(ident)).hexdigest()[:24]: raise ReliabilityCalibrationError("reliability_report_id_mismatch")
    return deepcopy(dict(x))

def validate_reliability_report_against_observations(payload:Mapping[str,Any],observations:Iterable[Mapping[str,Any]])->dict[str,Any]:
    x=validate_reliability_report(payload); items=[validate_reliability_observation(i) for i in observations]; sh=sha256(_canonical_json(sorted(i["observationSha256"] for i in items))).hexdigest()
    if x["observationSetSha256"]!=sh: raise ReliabilityCalibrationError("observation_set_mismatch")
    if x!=build_reliability_report(items): raise ReliabilityCalibrationError("reliability_report_recompute_mismatch")
    return x
