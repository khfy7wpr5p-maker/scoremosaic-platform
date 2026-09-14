# ScoreMosaic Architecture Consistency Report

Current architecture state contract: `contracts/architecture-current-state-v1.json`  
Current research/evaluation addendum: `docs/architecture-research-evidence-current.md`

## Scope

This audit compares current Stage 5-11 authority truth plus merged unnumbered integration/research workstreams through main commit `dfd8b8607607383fd1e250ce704e97af84a5101b` against the documents that present current architecture or roadmap state:

- `README.md`
- `docs/architecture.md`
- `docs/architecture-stage5-7-current.md`
- `docs/architecture-stage8-current.md`
- `docs/architecture-stage9-11-current.md`
- `docs/architecture-research-evidence-current.md`
- `docs/st-omr-architecture-contract-v1.md`
- `docs/teacher-review-score-editor-architecture-contract.md`
- `docs/roadmap.md`
- `docs/security-boundaries.md`

Historical gate/stage documents remain evidence for their original boundary and are not rewritten merely because later work exists.

## Previously resolved incompatibilities

### A-001 — dispatch/execution activation contradiction

Resolved by distinguishing controlled-staging private dispatch/execution from public/production orchestration.

### A-002 — stale Stage 8 future boundary

Resolved by recording Stage 8 repository completion in current Stage 5-7 documentation.

### A-003 — Stage 8 stop-boundary ambiguity

Resolved by scoping the stop rule to external production/publication effects rather than repository-only later work.

### A-004 — Teacher Review foundation document stale

Resolved by classifying the older Teacher Review architecture as historical foundation plus current Stage 8-11 alignment.

### A-005 — roadmap behind repository state

Resolved for Stage 5-11 and the initial UI/API/security workstreams.

### A-006 — ST-OMR long-term target versus current Stage 7 contract

Resolved by preserving the Audiveris/HOMR/Clarity `>=2` Canonical candidate contract and requiring a versioned evidence-backed migration for any ST-OMR-primary/only future.

### A-007 — missing Stage 9-11 current addendum

Resolved by `docs/architecture-stage9-11-current.md`.

## New drift found in the 2026-09-14 audit

### A-008 — post-baseline research evidence chain absent from current architecture summary

**Severity:** high planning/documentation risk  
**Before:** the current-state contract and main architecture still emphasized the older Stage 11-F baseline even though SM-POLY-02/03/04/05/06/07/08/09/11 had merged.

**Resolution:**

- add `docs/architecture-research-evidence-current.md`;
- add machine-readable `polyphonicResearchEvidence` to `contracts/architecture-current-state-v1.json`;
- synchronize `docs/architecture.md`, `docs/architecture-stage5-7-current.md` and `docs/roadmap.md`;
- keep Stage 7 production engine set/quorum and all production authority unchanged.

The synchronized state distinguishes evidence-infrastructure readiness from real evidence readiness:

```text
teacherGoldHarnessReady=true
teacherGoldRegistrySufficientlyPopulated=false
minimumResearchBenchmarkReady=false
stOmrShadowEvidenceContractReady=true
realWorldShadowBenchmarkComplete=false
directCrossArtifactJoinValidated=false
selectivePredictionAuthorized=false
```

### A-009 — Real Score Intake / H7-D / Score Discovery integrations missing from machine-readable current-state summary

**Severity:** medium-high architecture drift risk  
**Before:** merged repository capabilities existed in contracts/code/docs but were not represented in the central architecture-current-state contract.

**Resolution:** the current-state contract now records three explicit unnumbered workstreams:

- Real Score Intake v1/v1.1 → pinned Score Editor Core projection;
- H7-C/H7-D ST-Orchestration non-authoritative preview evidence;
- SD-4B disconnected Score Discovery consumer/handoff boundary.

All activation locks remain explicit: no live upload, no automatic correction, no H7-E production inference, no direct browser engine call, no live Score Discovery Gateway networking, no production import.

### A-010 — roadmap did not identify the actual post-SM-POLY-11 next gate

**Severity:** high planning risk  
**Before:** the roadmap still prioritized broad ST-OMR training/evaluation but did not record the named next research owner already declared by SM-POLY-04 and SM-POLY-11.

**Resolution:** roadmap priority now begins with:

```text
1. SM-POLY-13 Teacher Review workload instrumentation
2. populate/qualify real Teacher-Gold evidence
3. versioned direct cross-artifact join
4. selective prediction / abstention research
5. versioned ST-OMR promotion decision gate
```

`TEACHER_REVISION_COMMAND_COUNT_V1` is the fixed next method. No number is invented for the cross-artifact join or selective-prediction packages. Repository searches found no current SM-POLY-10 or SM-POLY-12 definition.

## Current consistency rules

Current architecture must preserve these rules:

1. Stage 5-11 status vocabulary remains exact and closed.
2. Current Stage 7 engine set remains Audiveris/HOMR/Clarity.
3. Stage 7 minimum Canonical candidate count remains 2.
4. ST-OMR is not integrated into current Gateway by implication.
5. ST-OMR-only migration requires explicit real evidence and a versioned Stage 7 migration.
6. SM-POLY research packages remain descriptive/research-only unless a later gate explicitly changes authority.
7. Convergence Evidence Vector v2 does not claim direct cross-artifact identity equivalence.
8. Teacher-Gold harness readiness must not be reported as corpus/benchmark readiness.
9. H7-D authenticated staging is not H7-E production authorization.
10. Real Score Intake/Core projection does not grant live upload/persistence/automatic correction authority.
11. Score Discovery handoff remains `discovery-handoff-only` and must pass Safe Intake.
12. Production provider/network/database/object-storage/identity/secrets/public API/public traffic locks remain false.
13. Teacher Review production write/approval persistence/publication execution locks remain false.
14. Browser networking/persistence/production reads/server write/playback remain false except the separately verified static fixture-preview traffic itself.
15. Downstream music applications cannot become upstream score authority.
16. Missing research package numbers cannot be inferred or assigned by documentation.

## Result

```text
Historical current-document contradictions previously resolved: 7
New architecture/documentation drift found in this audit: 3
New drift resolved on docs/architecture-sync-2026-09-14: 3
Known unresolved current-document contradiction after this sync: 0
Stage 7 authority change: 0
Production activation performed: 0
Security boundary weakened: 0
```

Executable CI evidence is still required before the branch is merge-ready. The architecture update itself is documentation/state synchronization only and must not be interpreted as runtime authorization.
