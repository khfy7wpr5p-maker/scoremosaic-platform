# ScoreMosaic Architecture Consistency Report

Current architecture state contract: `contracts/architecture-current-state-v1.json`

## Scope

This audit compares the current Stage 5-11 repository truth against the documents that present current architecture or roadmap state:

- `README.md`
- `docs/architecture.md`
- `docs/architecture-stage5-7-current.md`
- `docs/architecture-stage8-current.md`
- `docs/architecture-stage9-11-current.md`
- `docs/st-omr-architecture-contract-v1.md`
- `docs/teacher-review-score-editor-architecture-contract.md`
- `docs/roadmap.md`
- `docs/security-boundaries.md`

Historical gate/stage documents remain evidence for their original boundary and are not rewritten merely because later stages exist.

## Incompatibilities found

### A-001 — dispatch/execution activation contradiction

**Severity:** high documentation risk  
**Before:** main architecture/README/security language described Gateway orchestration/execution as wholly disabled while the authoritative Stage 5-7 addendum already proved bounded authenticated private controlled-staging dispatch/execution.

**Resolution:** all current documents now distinguish:

```text
controlled-staging private dispatch/execution = implemented
public/production orchestration = locked
```

### A-002 — stale Stage 8 future boundary

**Severity:** medium  
**Before:** Stage 5-7 still described the first Stage 8 implementation as future work.

**Resolution:** Stage 5-7 now records Stage 8 as completed repository scope and points to the Stage 8 current addendum.

### A-003 — Stage 8 stop-boundary ambiguity

**Severity:** high documentation risk  
**Before:** Stage 8 stated that autonomous repository-only development stops there, conflicting with the actual later Stage 9-11 repository merges.

**Resolution:** the stop rule is now scoped correctly to the **external production publication effect**. Repository-only Stage 9-11 work is explicitly compatible because it did not execute publication.

### A-004 — Teacher Review foundation document stale

**Severity:** medium  
**Before:** the Teacher Review architecture contract described the editor as future-only and unimplemented.

**Resolution:** it is now classified as the historical TR-0A foundation plus current Stage 8-11 alignment. Repository revision/validation/approval/publication-preparation foundations are acknowledged while live production API/write/persistence remains locked.

### A-005 — roadmap behind repository state

**Severity:** high planning risk  
**Before:** roadmap entries still marked controlled runtime, Teacher Review revisions/RBAC and approval/publication work as not started/in progress despite later completed stages.

**Resolution:** roadmap is synchronized through Stage 11 and separates repository-complete work from live/production activation.

### A-006 — ST-OMR long-term target versus current Stage 7 contract

**Severity:** high architectural migration risk  
**Before:** ST-OMR was only described as a future fourth independent candidate engine; the architecture did not explain how a future ST-OMR-primary/only strategy could coexist with the current Stage 7 `>=2 Canonical candidates` rule.

**Resolution:** current truth remains Audiveris/HOMR/Clarity with `>=2` Canonical candidates. ST-OMR-primary/only is defined as an optional versioned migration requiring shadow/teacher-gold/no-regression/abstention/deterministic-validation evidence. Existing engines cannot be removed by implication.

### A-007 — missing Stage 9-11 current addendum

**Severity:** medium  
**Before:** current architecture had dedicated Stage 5-7 and Stage 8 addenda but no consolidated Stage 9-11 current-state document.

**Resolution:** `docs/architecture-stage9-11-current.md` is now the current addendum for production-foundation, disconnected UI and typed local application boundaries.

## Current consistency rules

The CI consistency test enforces:

1. Stage 5-11 status vocabulary is exact and closed.
2. Current Stage 7 engine set remains Audiveris/HOMR/Clarity.
3. Stage 7 minimum Canonical candidate count remains 2.
4. ST-OMR is not integrated into current Gateway by documentation implication.
5. ST-OMR-only migration requires explicit evidence and a versioned Stage 7 migration.
6. Production provider/network/database/object-storage/identity/secrets/public API/public traffic locks remain false.
7. Teacher Review production write/approval persistence/publication execution locks remain false.
8. Browser networking/persistence/production reads/server write/playback remain false.
9. Every current architecture document binds to `contracts/architecture-current-state-v1.json`.
10. Known stale phrases cannot silently return.

## Result

```text
Current architecture contradictions found: 7
Resolved in architecture-sync branch: 7
Known unresolved current-document contradiction: 0
Production activation performed: 0
Security boundary weakened: 0
```

Executable CI evidence is required before this result can be treated as complete.
