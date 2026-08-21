# ScoreMosaic Stage 5-7 Current Architecture

Status: **authoritative current-activation addendum for Stage 5-7**  
Base: Stage 7 convergence merge `d07d31e32dcddb01a2c683e36822d9184be27f6c`

This document supersedes older activation-state statements in `docs/architecture.md` where they say engine dispatch, candidate persistence, or Stage 7 convergence are entirely disabled. The older document remains useful for Gate B-E foundation history; this addendum records the current Stage 5-7 runtime and contract truth.

## Current trust chain

```text
untrusted external document
  -> Safe Intake B.1-B.6
  -> immutable source + source/job binding
  -> deterministic orchestration plan
  -> durable planned(0) -> queued(1)
  -> authenticated dispatch capsule
  -> atomic queued(1) -> dispatching(2)
  -> authenticated fixed-destination private dispatch
  -> authenticated immutable source delivery
  -> one-shot authenticated engine execution trigger
  -> bounded engine execution boundary
  -> authenticated result identity
  -> bounded engine-specific result adapter
  -> immutable HMAC-sealed candidate persistence
  -> Stage 7 verified candidate handoff
  -> independent Ensemble handoff verification
  -> Candidate Safety composition
  -> deterministic Canonical Score admission
  -> neutral Ensemble Comparator
  -> deterministic comparison report
  -> decomposed bounded evidence
```

Engine/AI output is evidence throughout this chain. It never mutates authoritative score state directly.

## Stage 5 current state

Stage 5 is complete at controlled-staging/integration level.

- Dispatch Input Capsule is bounded, deterministic and source/plan/identity bound.
- Engine receiver authentication is fail-closed.
- `queued(1) -> dispatching(2)` and competing cancellation use exactly-one-winner durable revision semantics.
- Private dispatch uses exact allowlisted origins, fixed method/path, bounded timeouts, no redirects, no caller-selected host and no automatic retry after ambiguous remote execution.
- Source delivery and execution use purpose-separated credentials.
- Execution requires verified source-delivery evidence plus exact durable `dispatching(2)` state.
- Restart after ambiguous execution requires reconciliation; it never silently re-executes.

Production activation is not implied. Private networking is never considered authentication.

## Stage 6 current state

Stage 6 is complete at authenticated ingestion/persistence integration level.

- Audiveris, HOMR and Clarity each have an explicit engine-bound result adapter.
- Result identity is authenticated before parsing.
- Result framing, MusicXML and diagnostic payloads are bounded and fail closed.
- Candidate identity is bound to job, run, plan, source and engine.
- Candidate artifacts are written create-once under server-derived paths.
- Persistence records are HMAC sealed; replay revalidates both record integrity and actual artifact bytes.
- Candidate lifecycle reconstruction is allowed only from re-authenticated durable persistence.
- 3/3, 2/3, 1/3 and 0/3 partial-success semantics are deterministic; at least two authenticated successful candidates are required for comparison eligibility.

A persisted candidate is still not an authoritative score.

## Stage 7 current state

Stage 7 convergence is complete at repository contract/hermetic-integration level.

- Gateway reopens Stage 6 persistence and re-verifies artifact bytes before handoff.
- Stage 6 candidate hash is recomputed from persisted content metadata instead of trusting a stored claim alone.
- Ensemble accepts only a closed, versioned, independently hash-verified handoff.
- All admitted candidates must converge on the same job, plan and source identity.
- Candidate input order is normalized deterministically by engine identity.
- Existing Canonical normalization rules remain unchanged and fail closed per candidate.
- At least two Canonical candidates are required for comparison.
- Comparator and comparison report remain neutral and read-only.
- Evidence is decomposed into agreement, structural consistency, musical consistency, visual confidence availability, source-quality availability and localization-reliability availability. No opaque confidence score grants authority.

The hermetic vertical slice composes the real repository contracts from immutable intake through Stage 5, Stage 6 and Stage 7. Remote transports and engine outputs are controlled fixtures in that test. It does **not** prove live HOMR/Clarity/Audiveris production model execution.

## Candidate Safety composition

The three engine services currently carry byte-identical `candidate-safety-v1` implementations. The Stage 7 acceptance CI guards against silent policy drift between them.

The effective Stage 7 safety composition is:

1. engine-local Candidate Safety v1 for real engine-produced MusicXML/MXL;
2. Stage 6 authenticated result lineage before parsing;
3. Stage 6 bounded XML/result validation and immutable persistence;
4. Stage 7 persistence and handoff re-verification;
5. Canonical structural and musical bounds.

Current Stage 6 candidate contracts do not contain page-coordinate/bbox evidence. Stage 7 therefore marks localization/bbox confidence unavailable rather than inventing coordinates or confidence.

## Durable-state and rollback boundary

Durable revision-2 `dispatching` records, cancellation records, execution fences and Stage 6 immutable candidate records are security state. Older code must not delete, rewrite, ignore or reinterpret them to regain execution authority.

Unknown remote execution after restart remains reconciliation-only. Candidate persistence is create-once; conflicting bytes never overwrite existing state.

## Network/runtime truth

Current repository evidence proves controlled-staging contracts and hermetic integration. It does not prove:

- production credential provisioning;
- production TLS/service-mesh policy;
- live production HOMR/Clarity/Audiveris binaries/models;
- live result-return transport from engines into Stage 6;
- authenticated Gateway-to-Ensemble production transport;
- public API routes.

Those capabilities remain locked until separately activated and validated.

## UI readiness

The machine-readable readiness contract is `contracts/stage7-ui-readiness.json`.

Stage 7 result: **UI_READY_WITH_LOCKED_FEATURES**.

Contract-first read-only/mock UI work may begin safely. A real backend-connected public UI must remain locked until authenticated public read APIs, production durable providers, live result transport and the Stage 8 Teacher Review mutation/approval contracts exist.

## Stage 8 boundary

The first Stage 8 implementation should define immutable `TeacherScoreRevision` identity/provenance and bounded edit operations before any writable editor or approval route is enabled. Optimistic concurrency, deterministic musical validation, authorization/resource scope, append-only audit evidence and approval/publication barriers are mandatory before UI mutation authority.
