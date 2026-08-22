# ScoreMosaic Stage 8 Current Architecture

Status: **Stage 8-A through Stage 8-J merged; Stage 8-D authorization-first hardening merged; Stage 8-K approval-eligibility contract foundation in review**.

Current main before Stage 8-K: `f5c4a568a0b498210bfa52abaa7c1585e207e78f`.

## Current trust chain

```text
Stage 7 immutable read-only evidence
  -> Review Report + exact Canonical SHA-256
  -> HMAC-sealed reviewer/tenant/resource authorization
  -> closed bounded ScoreEditCommand
  -> exact parent + stable musical location
  -> old-value SHA-256 precondition
  -> deterministic Canonical-derived review musical state
  -> deterministic post-edit validation evidence
  -> immutable draft TeacherScoreRevision
  -> controlled durable exact-parent append
  -> authorization-first read-only review projection
  -> disconnected read-only browser review
  -> exact revision/state corrected-MusicXML derivative
  -> generated-XML safety + Canonical semantic round-trip
  -> server-authorized non-network write boundary
  -> disconnected local BrowserEditIntent
  -> exact-current revision:read Stage 8-I timeline
  -> exact rational beat/event/simultaneity timing
  -> Stage 8-J non-executing presentation transport state
  -> exact current durable head re-verification
  -> exact supplied-vs-rebuilt corrected artifact equality
  -> validation-count equality
  -> deterministic Stage 8-K approval-candidate evidence
  -> [LOCKED] approval grant
  -> [LOCKED] publication
  -> [LOCKED] loop/audio/playback execution
  -> [LOCKED] live Gate E transport/server resolution
  -> [LOCKED] live/public write API and browser mutation
```

Teacher Review never mutates source artifacts, engine candidates, Stage 7 Canonical artifacts, or Ensemble evidence in place. Teacher work forms a separate immutable lineage.

## Stage 8-A through Stage 8-C — merged

- purpose-separated HMAC reviewer authorization and exact resource/parent scope;
- closed typed edit commands with no arbitrary XML/patch/path execution;
- immutable draft revisions and append-only audit lineage;
- controlled durable exact-parent storage with HMAC integrity and crash/restart verification;
- deterministic Canonical-derived review state;
- exact target and old-value preconditions;
- visible musical validation without silent repair.

## Stage 8-D — merged and hardened

The read-only server projection binds exact `revision:read` authorization, snapshot identity, Stage 7 report evidence, deterministic pagination/focus, and minimized non-authoritative output.

Security hardening moves sealed authorization ahead of state/base/revision/report processing and catches only expected `Stage8ContractError`; unexpected runtime/programming faults are not masked as authorization failures.

No HTTP route is activated.

## Stage 8-E — merged

Disconnected read-only browser workspace with CSP `connect-src 'none'`, no storage/forms/navigation/dynamic HTML injection, deterministic keyboard issue navigation, and disabled mutation/approval/publication/playback controls.

## Stage 8-F — merged

Exact revision/state corrected-MusicXML derivative with bounded deterministic generation, independent structural-safety validation, explicit Teacher Review provenance, semantic Canonical round-trip equality, and immutable draft corrected-artifact evidence.

Production corrected-artifact persistence/transport remains locked.

## Stage 8-G — merged

Server-authorized in-process write foundation:

- fresh durable head before caller request parsing;
- sealed `revision:propose` authorization against exact current scope/parent;
- closed hashed request envelope;
- exact current-state and Stage 8-C old-value/location validation;
- provider-neutral idempotency;
- exact-parent CAS append and duplicate convergence;
- no raw XML/arbitrary patches;
- no live route activation.

`write-api-enabled=false` and `public-api-enabled=false` remain locked.

## Stage 8-H — merged

Disconnected typed BrowserEditIntent composer. It can prepare local structured musical intent for a present event but carries no authorization, old-value hash, command/revision identity, idempotency, or server authority. Network submission, approval, and publication remain disabled.

## Stage 8-I — merged

The rational read-only timeline proves:

- current durable head/history and exact `revision:read` authorization before state/base processing;
- fresh base Canonical or exact current revision/state binding;
- independent recomputation of validation SHA/blocking/unresolved counts and exact equality with immutable revision evidence;
- exact rational event onset/duration/end/beat positions and deterministic simultaneity groups;
- recomputed current `eventExtentEnd` instead of stale Stage 8-C `observedDuration` metadata;
- data minimization and presentation-only cursor/seek evidence;
- no audio/network/runtime framework.

## Stage 8-J — merged

The non-executing transport state-machine foundation proves:

- public plan construction rebuilds one fresh Stage 8-I timeline rather than accepting caller-supplied timing evidence;
- Stage 8-I capability expansion fails closed;
- plans bind exact timeline/scope/snapshot/validation identity;
- cursor points are deterministic exact `(measureOrdinal, onset)` groups with minimized event references;
- plan/state constructors are sealed;
- cross-plan state use fails closed;
- start/pause/seek/stop/advance transitions are deterministic and repeated satisfied transitions converge;
- natural end converges to stopped;
- loop execution is explicitly forbidden;
- no wall-clock, tempo, audio, MIDI, SoundFont, network, subprocess, or renderer execution authority exists;
- execution/audio/loop/mutation/approval/publication capabilities remain false.

`transport-state-machine-foundation-enabled=true` does not mean playback is enabled; `audio-playback-enabled=false` remains explicit.

## Stage 8-K — proof target

The approval-eligibility foundation must prove:

- the supplied revision is the exact authenticated current durable head for one exact `RevisionScope`;
- the full caller-supplied immutable revision equals the independently loaded persisted record;
- the supplied musical state remains exactly bound to the current revision;
- the supplied Stage 8-F corrected artifact is independently rebuilt from the same scope/revision/state pair;
- both MusicXML bytes and the complete artifact record match that rebuild exactly;
- Stage 8-F structural-safety and semantic-round-trip evidence remains true;
- revision/artifact scope, state, validation, and identity hashes match exactly;
- blocking/unresolved counts are re-bound to the persisted revision;
- `candidateEligible=true` only when both counts are zero;
- non-zero counts produce bounded ineligibility reasons rather than silent repair or guessed approval;
- evidence construction is sealed and deterministic;
- evidence always fixes approval/publication/mutation/write/authoritative-truth authority to false;
- the Stage 8-F artifact itself remains immutable draft with its original approval/publication flags false;
- no route, production provider, approval signature, approval persistence, or publication behavior is introduced.

Stage 8-K is an approval **candidate evidence** layer only. `approval-eligibility-foundation-enabled=true` does not activate approval; `approval-enabled=false` remains authoritative.

## Still locked / not proved

- production identity/session provider and production RBAC source;
- live Gate E Teacher Review transport binding;
- public/internal Teacher Review HTTP routes;
- production DB/object-store deployment;
- multi-host distributed consensus/full-store anti-rollback authority;
- corrected MusicXML production persistence/transport;
- browser writable editor activation;
- real-time clock/audio/MIDI/SoundFont playback execution;
- loop execution;
- exact teacher approval authorization/signature/persistence;
- publication.

## Safe continuation after Stage 8-K

If Stage 8-K passes all exact-head gates and merges, actual approval must remain a separate stage. The next safe repository-only approval slice may define purpose-separated approval authorization plus immutable approval-record semantics only if it consumes exact current Stage 8-K evidence, prevents replay/stale-revision approval, keeps publication separate, and still exposes no live route or production provider.

A separate disabled audio-executor contract may also be explored later, but it must not share authority with approval or mutation and must not accept arbitrary executable or untrusted assets.
