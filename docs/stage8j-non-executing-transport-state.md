# Stage 8-J — Non-Executing Review Transport State Machine

Status: repository/server foundation only. It does not emit audio, run a playback clock, load MIDI/SoundFont assets, mutate revisions, expose a route, approve, or publish.

## Purpose

Stage 8-J creates deterministic presentation-cursor transport state from the exact Stage 8-I rational timeline. It prepares pause/stop/seek/advance semantics before any audio executor exists, so later playback cannot introduce a second musical timing truth.

## Authority chain

The public plan builder does **not** accept a caller-supplied timeline object. It accepts the same trusted current-snapshot inputs as Stage 8-I and internally calls `build_review_timeline_projection`:

1. current durable revision head/history is verified by Stage 8-I;
2. sealed `revision:read` authorization is checked against the exact current snapshot;
3. state/base Canonical and revision validation evidence are checked by Stage 8-I;
4. Stage 8-I produces one exact rational timeline and `timelineSha256`;
5. Stage 8-J validates Stage 8-I capability locks and bounded shape;
6. Stage 8-J derives deterministic cursor points and `planSha256`;
7. transport states bind exact `planSha256`, `timelineSha256`, and snapshot identity.

A manually supplied or forged external timeline is not part of the public Stage 8-J API.

## Cursor plan

Cursor points are grouped by exact `(measureOrdinal, onset)` and sorted deterministically. Each point contains only:

- cursor point identity;
- measure ordinal;
- exact rational onset;
- minimal event references: part/measure/event identity, staff, voice, and kind.

The plan deliberately excludes pitch, TAB, XML provenance, source artifacts, corrected MusicXML, credentials, edit commands, MIDI data, audio assets, and wall-clock scheduling.

## State machine

Allowed presentation states:

- `stopped`;
- `navigating`;
- `paused`.

Allowed deterministic operations:

- initialize;
- start cursor navigation;
- pause cursor navigation;
- stop/reset to the first cursor point;
- seek to one existing cursor-point index;
- advance to the next cursor point.

Repeated start while already navigating, repeated pause while paused, repeated seek to the current point, and repeated stopped/reset state converge idempotently.

Natural advancement at the last cursor point converges to `stopped`. No wall-clock or tempo source is consumed.

## Construction integrity

`ReviewTransportPlan` and `ReviewTransportState` use repository-private construction seals. Callers cannot create alternate valid-looking plan/state instances through the public constructors.

Every state is bound to the exact plan/timeline/snapshot identity. Using a state with a different plan fails closed as `TRANSPORT_STALE_PLAN`.

## Execution locks

Plan capabilities are fixed:

- `presentationOnly=true`;
- `cursorAdvanceAllowed=true`;
- `seekAllowed=true`;
- `loopExecutionAllowed=false`;
- `audioExecutionAllowed=false`;
- `mutationAllowed=false`;
- `approvalAllowed=false`;
- `publicationAllowed=false`.

Every transport state additionally fixes:

- `executionAllowed=false`;
- `audioEmissionAllowed=false`;
- `loopExecutionAllowed=false`;
- `mutationAllowed=false`;
- `approvalAllowed=false`;
- `publicationAllowed=false`.

Loop execution has an explicit fail-closed API and always raises `TRANSPORT_LOOP_EXECUTION_FORBIDDEN` in Stage 8-J.

## Resource bounds

Stage 8-J retains the Stage 8-I event budget of 500,000 events, allows at most 500,000 cursor points, and at most 512 minimal event references at one cross-part cursor point.

## No runtime executor

The module imports no audio, MIDI, SoundFont, socket/network, subprocess, wall-clock, or browser/server framework. `audio-playback-enabled=false` remains a feature lock.

## Merge gate

Merge requires exact-head:

- Foundation CI;
- Stage 8-A through Stage 8-I regressions;
- Stage 8-J plan determinism and data-minimization tests;
- construction-seal tests;
- pause/stop/seek/advance convergence tests;
- stale-plan and capability-expansion negative tests;
- explicit loop-execution rejection;
- activation-lock tests;
- closed JSON contracts;
- clean diff;
- zero unresolved review threads;
- no incompatible `main` drift.

A later audio executor, if ever introduced, must be a separate gate. It must consume this exact plan/timeline identity and must not gain revision mutation, arbitrary executable, or untrusted asset authority.
