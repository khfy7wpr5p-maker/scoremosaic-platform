# ScoreMosaic Stage 8 Current Architecture

Status: **Stage 8-A through Stage 8-I merged; Stage 8-D authorization-first hardening merged; Stage 8-J non-executing transport state-machine foundation in review**.

Current main before Stage 8-J: `839a17b306f23509a33df36fc2f5705f16e59cf3`.

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
  -> recomputed validation equality with immutable revision evidence
  -> exact rational beat/event/simultaneity timing
  -> fresh Stage 8-I timeline inside Stage 8-J public plan builder
  -> deterministic presentation-only cursor plan
  -> sealed immutable stopped/navigating/paused transport state
  -> [LOCKED] loop execution
  -> [LOCKED] audio/playback execution
  -> [LOCKED] live Gate E transport/server resolution
  -> [LOCKED] live/public write API and browser mutation
  -> [LOCKED] exact revision/artifact approval
  -> [LOCKED] publication
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

Security hardening merged after Stage 8-I moves sealed authorization ahead of state/base/revision/report processing and catches only expected `Stage8ContractError`; unexpected runtime/programming faults are not masked as authorization failures.

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
- data minimization: no pitch/TAB/XML provenance/source artifact/credential/edit-command/corrected-XML/playback asset;
- presentation-only cursor navigation and seek;
- `canLoop=false`, `canPlay=false`, `canMutate=false`, approval/publication/authoritative truth false;
- no audio/network/runtime framework.

## Stage 8-J — proof target

The non-executing transport state-machine foundation must prove:

- its public plan builder does not accept a caller-supplied timeline;
- it internally builds one fresh Stage 8-I timeline from exact current store/grant/state/base inputs;
- any Stage 8-I capability expansion such as `canPlay=true` fails closed;
- the plan binds exact `timelineSha256`, scope, snapshot, and validation evidence;
- cursor points are deterministic exact `(measureOrdinal, onset)` groups;
- cursor event refs contain only part/measure/event/staff/voice/kind identities;
- pitch/TAB/provenance/assets/credentials/commands remain excluded;
- plan/state public constructors are sealed against forged alternate timing state;
- state binds exact `planSha256`, `timelineSha256`, and snapshot;
- cross-plan state use fails closed;
- start/pause/seek/stop/advance transitions are deterministic;
- repeated already-satisfied transitions converge idempotently;
- natural end converges to stopped;
- loop execution is explicitly forbidden;
- no wall-clock, tempo, audio, MIDI, SoundFont, network, subprocess, or renderer execution authority is introduced;
- plan execution/audio/loop/mutation/approval/publication capabilities remain false;
- every state fixes execution/audio/loop/mutation/approval/publication false.

Stage 8-J is cursor transport evidence only. `transport-state-machine-foundation-enabled=true` does not mean playback is enabled; `audio-playback-enabled=false` is explicit.

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
- exact teacher approval;
- publication.

## Safe continuation after Stage 8-J

If Stage 8-J passes all exact-head gates and merges, the next safe work should remain non-authoritative. Two possible repository-only directions are:

1. an exact revision + corrected-artifact **approval eligibility contract** that still does not activate approval, or
2. a separately isolated audio-executor contract that remains disabled and proves it cannot mutate revisions or accept arbitrary executable/untrusted assets.

Given Gate E is still incomplete, live browser mutation/public API activation remains blocked. Approval, when eventually enabled, must bind one exact immutable revision plus one exact validated corrected-MusicXML artifact hash. Publication remains later still.
