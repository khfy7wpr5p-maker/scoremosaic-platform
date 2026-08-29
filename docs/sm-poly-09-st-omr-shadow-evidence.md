# SM-POLY-09 — ST-OMR Shadow Candidate Evidence

Status: **research-only shadow evidence**  
Production behavior change: **none**

## Purpose

SM-POLY-09 introduces a versioned evidence path for evaluating ST-OMR beside the current ScoreMosaic OMR baseline without adding ST-OMR to Gateway, Stage 6 production candidate handling, or the Stage 7 quorum.

The stage answers one bounded question: **how does a provenance-pinned ST-OMR candidate perform against verified Teacher-Gold evidence while the current Audiveris/HOMR/Clarity benchmark remains independently pinned?**

It does not select a winner or promote ST-OMR.

## Shadow observation

Each observation binds:

`Teacher-Gold reference SHA`
→ `source document SHA`
→ `prepared immutable page-set SHA`
→ `job/run identity`
→ `ST-OMR engine version`
→ `model version`
→ `model manifest SHA`
→ `model artifact SHA`
→ `training code commit`
→ `candidate artifact SHA`
→ optional Canonical SHA
→ category evidence.

The semantic categories remain aligned with the SM-POLY-04 vocabulary:

- parse;
- structural validity;
- pitch;
- duration;
- onset;
- voice;
- staff;
- tie;
- tuplet;
- measure consistency;
- relation correctness.

Metric evidence is retained as exact integer `correct/total` counts. Missing evidence is explicitly unavailable rather than silently converted to zero.

A parse failure may not contain Canonical, structural, or semantic success evidence.

## Model and run provenance

ST-OMR shadow evidence requires a model-manifest SHA, model-artifact SHA, exact training-code commit, and source/job/run binding. The manifest is evidence only; the existing `st-omr-model-manifest-v1` contract still does not authorize deployment.

Changing the model, run, source binding, or candidate changes the deterministic observation identity and SHA.

## Current-engine baseline binding

A shadow report requires immutable benchmark report SHA references for the complete current engine set:

- `audiveris`
- `homr`
- `clarity`

The baseline method is explicitly versioned. SM-POLY-09 does not copy those engines into the ST-OMR contract, alter their current SM-POLY-04 semantics, or calculate a cross-engine ranking. The existing benchmark reports remain the source of their detailed metrics; the shadow report binds their exact identities beside the ST-OMR category evidence.

## Determinism and fail-closed validation

Observations and reports have content-derived IDs and SHA-256 hashes. Validators recompute both. Reports bind the sorted observation-hash set and can be fully rebuilt with `validate_shadow_report_against_observations()` so a rehashed forged aggregate still fails.

Duplicate ST-OMR run evidence is rejected. A report accepts at most 10,000 observations.

## Context

Optional SM-POLY-07 complexity and SM-POLY-06 source-quality profile IDs/SHAs may be attached as immutable conditioning context. They do not change scores, confidence, or authority.

SM-POLY-08 remains unchanged: its v1 engine set is still Audiveris/HOMR/Clarity. ST-OMR confidence calibration is not smuggled into that frozen contract. A later explicit shadow-reliability extension may consume SM-POLY-09 evidence if raw ST-OMR confidence with adequate provenance becomes available.

## Authority boundaries

Every observation/report fixes these states:

```text
researchOnly=true
shadowOnly=true
readOnly=true
productionEligible=false
gatewayIntegration=false
stage7QuorumContribution=false
stage7EvidenceMutation=false
engineRanking=false
winnerSelection=false
automaticMerge=false
automaticCorrection=false
teacherAuthorityOverride=false
productionDecisionAuthority=false
```

Therefore SM-POLY-09 does **not**:

- add ST-OMR to the Gateway;
- add ST-OMR to the Stage 7 quorum;
- change the current `>=2` Canonical-candidate rule;
- rank Audiveris/HOMR/Clarity/ST-OMR;
- select a winner;
- merge or repair MusicXML;
- write Teacher Review state;
- authorize model promotion;
- activate a production ST-OMR runtime.

## Files

- `contracts/st-omr-shadow-observation-v1.schema.json`
- `contracts/st-omr-shadow-report-v1.schema.json`
- `services/ensemble-service/src/scoremosaic_ensemble/st_omr_shadow.py`
- `services/ensemble-service/tests/test_st_omr_shadow.py`
- `.github/workflows/sm-poly-09-st-omr-shadow-evidence-ci.yml`
- `docs/sm-poly-09-st-omr-shadow-evidence.md`

## Next gate

SM-POLY-09 produces evidence only. Any future ST-OMR PRIMARY gate requires a separate explicit authorization and real-world evidence review. SM-POLY-11 may later consume versioned evidence through Convergence Evidence Vector v2, but it must not silently turn shadow evidence into Stage 7 authority.
