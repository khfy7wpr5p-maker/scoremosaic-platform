# ScoreMosaic Stage 8 Current Architecture

Status: **Stage 8-A through Stage 8-H merged; Stage 8-I rational read-only timeline foundation in review**.

Current Stage 8-H main: `d89bc5ac7075898e27b7b5cc363041c9d8b5df1f`.

## Current trust chain

```text
Stage 7 immutable read-only evidence
  -> Review Report + exact Canonical SHA-256
  -> HMAC-sealed reviewer/tenant/resource authorization
  -> closed bounded ScoreEditCommand
  -> exact parent + stable musical location
  -> old-value SHA-256 precondition
  -> deterministic Canonical-derived review musical state
  -> one bounded typed edit
  -> deterministic post-edit validation evidence
  -> immutable draft TeacherScoreRevision
  -> append-only audit identity
  -> controlled durable revision scope
  -> atomic exact-parent append
  -> HMAC-sealed revision record + head
  -> restart/recovery re-verification
  -> revision:read authorization + exact base/revision snapshot
  -> independently revalidated Stage 7 comparison evidence
  -> bounded deterministic read-only projection/focus
  -> local fail-closed read-only browser adapter
  -> exact revision/state revalidation
  -> deterministic corrected MusicXML bytes
  -> generated-XML structural safety validation
  -> provenance-safe Canonical re-normalization
  -> editable-musical semantic round-trip equality
  -> immutable draft corrected-artifact evidence
  -> fresh durable head + revision:propose authorization
  -> closed hashed write-request envelope
  -> exact current-state + old-value/location validation
  -> provider-neutral idempotency reservation
  -> immutable exact-parent revision append
  -> disconnected local typed BrowserEditIntent
  -> exact-current revision:read timeline authorization
  -> recomputed validation equality with immutable revision evidence
  -> exact rational event/beat/simultaneity cursor timeline
  -> [LOCKED] audio/playback execution
  -> [LOCKED] live Gate E transport/server resolution
  -> [LOCKED] live/public write API and browser mutation
  -> [LOCKED] exact revision/artifact approval
  -> [LOCKED] publication
```

Teacher Review never mutates source artifacts, engine candidates, Stage 7 Canonical artifacts, or Ensemble evidence in place. Teacher work forms a separate immutable lineage.

## Stage 8-A — merged

Purpose-separated HMAC reviewer authorization, exact tenant/job/reviewer/report/Canonical/parent scope, sealed-grant re-verification, closed edit commands, deterministic immutable draft revisions, stale-parent protection, append-only audit identity, and no approval/publication authority.

## Stage 8-B — merged

Controlled append-only durable revision storage with purpose-separated HMAC integrity, exact-parent optimistic concurrency, exact replay convergence, synchronous record/head transactions, crash rollback/restart verification, filesystem substitution defenses, and fail-closed scope/key/tamper behavior.

`production-durable-store-enabled=false` remains locked. Full-store rollback detection still needs a separately durable anti-rollback authority.

## Stage 8-C — merged

Deterministic Canonical-derived review state, frozen typed edit allowlist, exact part/measure/event/staff/voice/onset targeting, old-value SHA preconditions, deterministic state/validation hashes, and visible musical validation without silent repair.

## Stage 8-D — merged

Exact `revision:read` authorization, exact base/revision snapshot binding, independent Stage 7 report revalidation, bounded deterministic pagination/focus, data minimization, and read-only/non-authoritative capabilities. No HTTP route.

## Stage 8-E — merged

Disconnected read-only browser workspace with `connect-src 'none'`, no browser storage/forms/navigation/dynamic HTML injection, keyboard issue navigation, explicit absent-event evidence, and disabled mutation/approval/publication/playback controls.

## Stage 8-F — merged

Exact revision/state corrected-MusicXML derivative, bounded deterministic generation, independent structural safety validation, explicit `teacher-review` Canonical provenance, editable-musical semantic round-trip equality, and immutable draft corrected-artifact evidence.

Production corrected-artifact persistence/transport remains locked.

## Stage 8-G — merged

Server-authorized in-process write foundation:

- fresh durable head before caller request parsing;
- sealed `revision:propose` authorization against exact current scope/parent;
- closed hashed request envelope around one existing ScoreEditCommand;
- exact current-state binding;
- Stage 8-C as the only edit/location/old-value musical validator;
- provider-neutral exact request idempotency;
- exact-parent CAS append and concurrent duplicate convergence;
- no raw XML/arbitrary patches;
- no live route activation.

`write-api-enabled=false` and `public-api-enabled=false` remain locked.

## Stage 8-H — merged

Disconnected structured BrowserEditIntent composer:

- consumes only Stage 8-D read-only projections;
- requires selected event presence;
- exposes only the existing typed musical operation vocabulary;
- carries no authorization, old-value SHA, command identity, revision identity, idempotency, or server authority;
- all authority markers remain false;
- no network/storage/form submission;
- submit/approve/publish remain disabled.

Stage 8-H evaluates local UX only and cannot create server authority.

## Stage 8-I — proof target

The rational read-only timeline foundation must prove:

- the current durable head/history is verified first;
- sealed `revision:read` authorization is checked against exact tenant/job/reviewer/report/base-Canonical/current-parent scope before state/base processing;
- base snapshots equal a fresh deterministic base Canonical materialization;
- revision snapshots bind the exact current revision and resulting state SHA-256;
- revision validation SHA/blocking/unresolved counts are independently recomputed and must exactly match immutable revision evidence;
- timing uses exact rational values only;
- beat positions, event ends, and simultaneity groups are deterministic and bounded;
- current event-derived `eventExtentEnd` is recomputed rather than trusting potentially stale Stage 8-C `observedDuration` metadata;
- pitch, TAB, XML provenance, source artifacts, credentials, edit commands, corrected XML, and playback assets are excluded;
- `cursorNavigation=true` and `canSeek=true` are presentation-only;
- `canLoop=false`, `canPlay=false`, `canMutate=false`, `canApprove=false`, `canPublish=false`, and `authoritativeTruth=false` remain fixed;
- per-measure loop bounds are evidence only with `playbackAuthority=false`;
- no audio/network/runtime framework is introduced.

Stage 8-I is a repository/server projection foundation only. It is not a playback engine.

## Still locked / not proved

- production identity/session provider and production RBAC source;
- live Gate E Teacher Review transport binding;
- public or internal Teacher Review HTTP routes;
- production DB/object-store deployment;
- multi-host distributed consensus/full-store anti-rollback authority;
- corrected MusicXML production persistence/transport;
- browser writable editor activation;
- audio/MIDI/SoundFont playback execution;
- exact teacher approval;
- publication.

## Safe continuation after Stage 8-I

If Stage 8-I passes exact-head CI and merges, the next safe repository-only slice may add an isolated playback scheduler **only** if it consumes the exact Stage 8-I snapshot/timeline identity, cannot mutate revisions, accepts no arbitrary executable or untrusted SoundFont/MIDI authority, and has deterministic pause/stop/seek/loop convergence tests.

Live browser mutation remains blocked until Gate E production authentication/authorization/idempotency/privacy controls are complete and explicitly bound to Stage 8-G.

Approval remains later and must bind one exact immutable revision plus one exact validated corrected-MusicXML artifact hash. Publication remains later still.
