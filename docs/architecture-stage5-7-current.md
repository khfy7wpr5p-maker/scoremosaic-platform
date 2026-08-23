# ScoreMosaic Stage 5-7 Current Architecture

Status: **authoritative current-activation addendum for Stage 5-7**, synchronized through Stage 11-F  
Current architecture state contract: `contracts/architecture-current-state-v1.json`

This document remains authoritative for Stage 5-7 behavior. Later-stage status is summarized only to prevent stale boundary statements; detailed Stage 8 and Stage 9-11 truth lives in their current addenda.

## Current trust chain through Stage 7

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

This is controlled staging evidence, not production/public activation. Private networking is never considered authentication.

## Stage 6 current state

Stage 6 is complete at authenticated ingestion/persistence integration level.

- Audiveris, HOMR and Clarity each have explicit engine-bound result adapters.
- Result identity is authenticated before parsing.
- Result framing, MusicXML and diagnostics are bounded and fail closed.
- Candidate identity is bound to job, run, plan, source and engine.
- Candidate artifacts are create-once under server-derived paths.
- Persistence records are HMAC sealed and replay revalidates record integrity and artifact bytes.
- 3/3, 2/3, 1/3 and 0/3 partial-success semantics are deterministic.
- At least two authenticated successful candidates are required for comparison eligibility.

A persisted candidate is still not an authoritative score.

## Stage 7 current state

Stage 7 convergence is complete at repository contract/hermetic-integration level.

- Gateway reopens Stage 6 persistence and re-verifies artifact bytes before handoff.
- Stage 6 candidate hash is recomputed from persisted content metadata.
- Ensemble accepts only a closed, versioned, independently hash-verified handoff.
- All admitted candidates converge on the same job, plan and source identity.
- Candidate input order is deterministic by engine identity.
- Canonical normalization remains fail-closed per candidate.
- At least two Canonical candidates are required for comparison.
- Comparator/report are neutral and read-only.
- Evidence is decomposed; no opaque confidence score grants authority.

The hermetic vertical slice uses controlled transports/fixtures and does **not** prove live HOMR/Clarity/Audiveris production model execution.

Historical Stage 7 readiness remains **UI_READY_WITH_LOCKED_FEATURES**. That result permitted contract-first/read-only UI work while keeping live backend integration locked; Stage 10 and Stage 11 later implemented only repository-local disconnected UI/application layers under that constraint.

## Current OMR set and ST-OMR migration boundary

The authoritative Stage 7 v1 engine set remains:

```text
Audiveris
HOMR
Clarity
```

ST-OMR is not currently part of this quorum. Any future ST-OMR-primary or ST-OMR-only path requires a versioned migration instead of silently weakening the `>=2` Stage 7 rule. Required evidence includes shadow comparison, teacher-gold evaluation, category-stratified no-regression results, calibrated abstention, deterministic musical validation and rollback. Existing engines may later be retired from production only after those gates pass; they may remain offline benchmark/reference engines.

## Candidate Safety composition

The effective Stage 7 safety composition is:

1. engine-local Candidate Safety v1;
2. Stage 6 authenticated result lineage before parsing;
3. Stage 6 bounded result validation and immutable persistence;
4. Stage 7 persistence/handoff re-verification;
5. Canonical structural and musical bounds.

Current Stage 6 candidate contracts do not contain page-coordinate/bbox evidence, so Stage 7 marks localization evidence unavailable rather than inventing it.

## Durable-state and rollback boundary

Durable `dispatching` records, cancellation records, execution fences and Stage 6 immutable candidate records are security state. Older code must not delete, rewrite, ignore or reinterpret them to regain authority.

Unknown remote execution after restart remains reconciliation-only. Candidate persistence is create-once and conflicting bytes never overwrite existing state.

## Network/runtime truth

Current repository evidence proves controlled-staging execution and hermetic Stage 5-7 integration. It does **not** prove:

- production credential provisioning;
- production TLS/service-mesh policy;
- public API routes;
- production Gateway-to-Ensemble transport;
- production provider-backed persistence;
- production traffic readiness.

Those capabilities remain locked behind later production gates.

## Later stages now completed in repository scope

The former “future Stage 8” boundary is no longer current. Repository-only work has since completed:

- **Stage 8:** immutable Teacher Review, including `TeacherScoreRevision`, approval and non-executing publication-handoff preparation;
- **Stage 9:** production-foundation contracts, with external provisioning still deferred;
- **Stage 10:** disconnected product UI experience;
- **Stage 11:** typed local UI/application contracts and integration, with live API still locked.

See `docs/architecture-stage8-current.md` and `docs/architecture-stage9-11-current.md`.
