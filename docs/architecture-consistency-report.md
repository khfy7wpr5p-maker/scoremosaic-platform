# ScoreMosaic Architecture Consistency Report

Current architecture state contract: `contracts/architecture-current-state-v1.json`  
Current research/evaluation addendum: `docs/architecture-research-evidence-current.md`

## Scope

This audit compares current Stage 5-11 authority truth plus unnumbered integration/research workstreams through the verified main base `b26e6c512edc88f9215bfe1b97199d309adf9f7c` and the SM-POLY-13 repository package against the documents that present current architecture or roadmap state:

- `README.md`
- `docs/architecture.md`
- `docs/architecture-stage5-7-current.md`
- `docs/architecture-stage8-current.md`
- `docs/architecture-stage9-11-current.md`
- `docs/architecture-research-evidence-current.md`
- `docs/sm-poly-13-teacher-review-workload.md`
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

### A-008 — post-baseline research evidence chain absent from current architecture summary

Resolved by adding the research/evaluation addendum and machine-readable `polyphonicResearchEvidence`, while preserving Stage 7 authority.

### A-009 — Real Score Intake / H7-D / Score Discovery integrations missing from machine-readable current-state summary

Resolved by recording those unnumbered workstreams and their explicit activation locks.

### A-010 — roadmap did not identify the actual post-SM-POLY-11 next gate

Resolved by naming SM-POLY-13 and method `TEACHER_REVISION_COMMAND_COUNT_V1` without inventing SM-POLY-10/12 or later package numbers.

## New SM-POLY-13 consistency finding

### A-011 — teacher-workload vocabulary existed but no deterministic derivation contract existed

**Severity:** high research-validity risk  
**Before:** SM-POLY-04 could represent teacher-edit counts, but the repository had no exact, tamper-checked method for deriving those values from Teacher Review history. Treating revision count, unique event count, changed-measure count or inferred page count as equivalent would have produced ambiguous metrics.

**Resolution:** SM-POLY-13 adds a separately versioned read-only evidence contract and extractor with these fixed rules:

```text
method = TEACHER_REVISION_COMMAND_COUNT_V1
one validated TeacherScoreRevision/ScoreEditCommand pair = one edit
empty history != proven zero edits
measure denominator must bind edited Canonical SHA
page denominator is optional and never inferred from command location
duplicate/replayed/tampered lineage = reject
```

SM-POLY-13 validates exact command SHA, revision SHA, audit SHA, parent/audit chain, command↔revision scope and duplicate/replay invariants. Its SM-POLY-04 adapter requires exact fixture + Canonical binding and both denominators before populating the older all-or-nothing `teacherEdits` field.

The synchronized research locks remain:

```text
teacherWorkloadEvidenceReady=true
teacherGoldRegistrySufficientlyPopulated=false
minimumResearchBenchmarkReady=false
realWorldShadowBenchmarkComplete=false
directCrossArtifactJoinValidated=false
selectivePredictionAuthorized=false
productionDecisionAuthorityGranted=false
```

The next priority is now:

```text
POPULATE_AND_QUALIFY_REAL_TEACHER_GOLD_EVIDENCE
  -> versioned direct cross-artifact join
  -> selective prediction / abstention research
  -> versioned ST-OMR promotion decision gate
```

No package number is assigned to the latter work until its own contract/PR exists.

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
9. SM-POLY-13 workload evidence must come from exact immutable revision/command lineage; page workload cannot be guessed.
10. H7-D authenticated staging is not H7-E production authorization.
11. Real Score Intake/Core projection does not grant live upload/persistence/automatic correction authority.
12. Score Discovery handoff remains `discovery-handoff-only` and must pass Safe Intake.
13. Production provider/network/database/object-storage/identity/secrets/public API/public traffic locks remain false.
14. Teacher Review production write/approval persistence/publication execution locks remain false.
15. Browser networking/persistence/production reads/server write/playback remain false except the separately verified static fixture-preview traffic itself.
16. Downstream music applications cannot become upstream score authority.
17. Missing research package numbers cannot be inferred or assigned by documentation.

## Result

```text
Historical current-document contradictions previously resolved: 10
New SM-POLY-13 research-validity drift found: 1
New SM-POLY-13 drift resolved on feature/sm-poly-13-teacher-review-workload: 1
Known unresolved current-document contradiction after this sync: 0
Stage 7 authority change: 0
Teacher Review authority change: 0
Production activation performed: 0
Security boundary weakened: 0
```

Executable CI evidence is required before the branch is merge-ready. The SM-POLY-13 package is a read-only research/evaluation derivation and must not be interpreted as runtime authorization.
