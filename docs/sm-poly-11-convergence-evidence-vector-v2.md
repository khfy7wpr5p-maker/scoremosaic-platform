# SM-POLY-11 — Convergence Evidence Vector v2

Status: **research-only evidence integration**  
Production behavior change: **none**

## Purpose

SM-POLY-11 introduces a deterministic, SHA-pinned Convergence Evidence Vector v2 that can place an existing Stage 7 convergence result beside research evidence produced by SM-POLY-04 through SM-POLY-09 without changing production convergence authority.

The vector answers one bounded question: **which immutable upstream evidence artifacts are present in this research evidence context beside this exact Stage 7 result?** It does not answer which engine is best, which artifact belongs to the same fixture unless the upstream artifact itself proves that relationship, which candidate should win, or whether MusicXML should be merged or corrected.

## Evidence families

The v2 vector has one opaque artifact-set slot for each upstream evidence family:

- SM-POLY-04 semantic metric reports;
- SM-POLY-05 visual/BBox evidence sidecars;
- SM-POLY-06 source-quality profiles;
- SM-POLY-07 polyphony-complexity profiles;
- SM-POLY-08 reliability-calibration reports;
- SM-POLY-09 ST-OMR shadow reports.

The vector does **not** relabel those artifacts by engine, category, fixture, Teacher-Gold reference, or source document. Upstream identity remains defined and validated inside the upstream artifact itself. This matters because SM-POLY-04 and SM-POLY-08 reports can aggregate multiple observations/engine groups, while SM-POLY-05/06/07/09 carry their own provenance at different granularities.

The current production-engine set remains exactly:

```text
audiveris
homr
clarity
```

ST-OMR remains a separately identified shadow engine and is not added to the production candidate set.

## Stage 7 reference

The vector binds the exact existing Stage 7 `resultSha256` under `scoremosaic-stage7-convergence-v1`. The Stage 7 result already content-binds its candidate inputs, including shared job/plan/source identity. SM-POLY-11 does not duplicate or weaken those Stage 7 checks.

The Stage 7 reference method is frozen to:

```text
STAGE7_RESULT_SHA256_REFERENCE_V1
```

The Stage 7 reference is explicitly non-authoritative inside this research package.

## Evidence context, not identity equivalence

The evidence context method is fixed to:

```text
OPAQUE_UPSTREAM_ARTIFACT_SET_CONTEXT_V1
```

It fixes:

```text
directFixtureBindingClaimed=false
crossArtifactIdentityMatchClaimed=false
```

This prevents a SHA reference alone from being interpreted as proof that a multi-fixture benchmark report, a page sidecar, a source-quality profile, a complexity profile and a Stage 7 run all describe the same granular target. Any future direct cross-artifact join must validate the relevant upstream payloads and introduce a separately versioned binding method.

## Reference-only integration

SM-POLY-11 does not copy or reinterpret upstream metric values. Every available evidence-family slot uses the single frozen method:

```text
SHA256_ARTIFACT_SET_REFERENCE_V1
```

Each slot binds:

- explicit availability;
- exact upstream schema version;
- the frozen binding-method version;
- a sorted unique set of immutable artifact SHA-256 values;
- a deterministic SHA-256 of that artifact set.

Callers cannot provide a custom provenance-method label in v2. A new method requires a new versioned contract rather than silently changing v2 semantics.

Unavailable evidence is a first-class state. An unavailable slot must have null schema/method/set hash and an empty artifact set. Hidden values in an unavailable slot fail closed.

## Determinism

The vector uses canonical JSON, a content-derived `vectorId`, and `vectorSha256`. Validation recomputes:

- evidence-set hashes;
- available evidence-family count;
- vector identity;
- vector SHA-256;
- frozen binding methods;
- evidence-context non-equivalence claims;
- fixed authority boundaries.

Changing the Stage 7 result reference or any evidence artifact changes the vector identity.

## No aggregate score

V2 intentionally fixes these derived fields to null:

```text
aggregateConfidenceScore = null
engineRanking = null
winner = null
```

Reliability evidence, source quality, visual localization, semantic metrics, complexity, and ST-OMR shadow evidence remain separate evidence families. V2 does not invent a weighting formula, cross-artifact identity match, engine-specific attribution outside upstream artifacts, or selective-prediction threshold.

## Authority boundaries

Every vector fixes:

```text
researchOnly=true
readOnly=true
descriptiveEvidenceOnly=true
upstreamEvidenceReinterpreted=false
crossArtifactIdentityMatchClaimed=false
stage7EvidenceMutation=false
stage7QuorumContribution=false
stage7QuorumChange=false
productionDecisionAuthority=false
engineRanking=false
winnerSelection=false
singleAggregateScore=false
confidenceUsedAsAuthority=false
automaticMerge=false
automaticCorrection=false
teacherAuthorityOverride=false
stOmrProductionPromotion=false
gatewayIntegration=false
```

Therefore SM-POLY-11 does **not**:

- modify `convergence.py` or the Stage 7 production execution path;
- change the current `>=2` Canonical-candidate rule;
- add ST-OMR to Gateway or Stage 7 quorum;
- rank Audiveris/HOMR/Clarity/ST-OMR;
- claim that opaque upstream artifacts refer to the same fixture/source/Teacher-Gold target;
- relabel upstream evidence by engine/category;
- allow caller-defined provenance method labels in v2;
- choose a winning candidate;
- generate an overall confidence score;
- merge or repair MusicXML;
- write Teacher Review state;
- authorize publication or production promotion.

## Files

- `contracts/convergence-evidence-vector-v2.schema.json`
- `services/ensemble-service/src/scoremosaic_ensemble/convergence_evidence_v2.py`
- `services/ensemble-service/tests/test_convergence_evidence_v2.py`
- `.github/workflows/sm-poly-11-convergence-evidence-v2-ci.yml`
- `docs/sm-poly-11-convergence-evidence-vector-v2.md`

## Next gate

SM-POLY-11 is an evidence-context integration layer, not an authority layer. A later stage may introduce a directly validated cross-artifact join or evaluate whether an evidence family is sufficiently calibrated for selective prediction/abstention, but either change requires separate explicit authorization and must not silently modify Stage 7 production behavior.

SM-POLY-13 remains the planned owner for Teacher Review workload instrumentation (`TEACHER_REVISION_COMMAND_COUNT_V1`).
