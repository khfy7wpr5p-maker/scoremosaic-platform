# Stage 8-I — Rational Read-Only Review Timeline

Status: repository foundation only. No audio, playback engine, live route, browser mutation, approval, or publication authority is enabled.

## Purpose

Stage 8-I derives deterministic cursor/timeline evidence from one exact current Teacher Review snapshot. It exists so later renderer and playback work can consume the same validated musical timeline without inventing timing independently.

The timeline is evidence and navigation structure, not musical authority. Teacher revisions remain authoritative only through the existing Stage 8 revision contracts and deterministic validators.

## Security order

The server-side builder follows this order:

1. validate trusted `RevisionScope` and controlled durable store type;
2. read and fully verify the current durable revision head/history;
3. verify the sealed `revision:read` grant against exact tenant/job/reviewer/report/base-Canonical/current-parent scope;
4. only after authorization, validate the supplied state against either a fresh base Canonical materialization or the exact current revision state SHA-256;
5. recompute deterministic musical validation from the exact state;
6. for revision snapshots, require recomputed validation SHA/counts to exactly match the immutable revision evidence;
7. derive bounded rational cursor/timeline evidence from the current state;
8. emit an immutable deterministic timeline hash.

Authorization therefore precedes caller-controlled state/base processing. A stale read grant cannot inspect a newer revision through this boundary.

## Exact timing model

All musical timing remains rational:

- event onset;
- effective duration;
- event end;
- beat unit;
- beat index and offset within beat;
- expected measure end;
- event-derived measure extent;
- simultaneity membership.

No floating-point musical timing is introduced.

Additive meters such as `3+2/8` are represented without flattening the source meter string. Beat position is derived from the declared beat type and exact onset.

## Derived-duration safety

Stage 8-C intentionally preserves some Canonical-derived metadata across edits. In particular, `observedDuration` may remain stale after an allowlisted event-duration edit.

Stage 8-I therefore does **not** expose `observedDuration` as timeline truth. The timeline recomputes `eventExtentEnd` from the current event onsets and effective durations. Loop-bound evidence uses this recomputed extent plus the current expected measure duration.

This prevents stale derived metadata from becoming cursor/playback evidence.

## Validation binding

For a base snapshot, validation is freshly computed from the freshly matched base state.

For a revision snapshot, Stage 8-I independently recomputes:

- `validationReportSha256`;
- `blockingIssueCount`;
- `unresolvedIssueCount`.

Those values must exactly match the immutable revision record. A validly stored revision whose validation evidence does not describe its exact resulting state fails closed with `TIMELINE_REVISION_VALIDATION_MISMATCH`.

## Data minimization

The timeline intentionally excludes:

- pitch values;
- TAB/string/fret values;
- XML/source provenance;
- source artifact references and hashes;
- credentials/signatures;
- edit commands;
- corrected MusicXML;
- authorization grants;
- playback assets.

It contains only identities and exact timing needed for cursor/navigation evidence.

## Simultaneity

Events sharing one exact onset in one measure receive one deterministic `simultaneityId` and an XML-order-sorted list of simultaneous event IDs. The group is bounded to 256 events and grants no chord-repair or playback authority.

## Capabilities

The contract is fixed to:

- `readOnly=true`;
- `cursorNavigation=true`;
- `canSeek=true`;
- `canLoop=false`;
- `canPlay=false`;
- `canMutate=false`;
- `canApprove=false`;
- `canPublish=false`;
- `authoritativeTruth=false`.

`canSeek=true` means a consumer may move a presentation cursor within this already validated timeline. It does not authorize audio, revision writes, or server mutation.

Measure `loopBounds` are evidence only. `playbackAuthority=false` is fixed inside every measure and global `canLoop=false` remains locked.

## Failure policy

Failures are explicit and fail closed. Important categories include:

- `TIMELINE_AUTHORIZATION_DENIED`;
- `TIMELINE_STALE_SNAPSHOT`;
- `TIMELINE_STORE_INVALID`;
- `TIMELINE_STATE_MISMATCH`;
- `TIMELINE_REVISION_VALIDATION_MISMATCH`;
- bounded part/measure/event/simultaneity limit failures;
- invalid rational/time-signature/event structure failures.

There is no hidden repair or coercion.

## Not activated by Stage 8-I

Stage 8-I does not add or enable:

- HTTP/public Teacher Review routes;
- browser write submission;
- production identity/session provider;
- production durable provider;
- audio engine;
- MIDI/SoundFont loading;
- playback scheduling;
- loop execution;
- corrected-MusicXML production transport;
- teacher approval;
- publication.

The existing live-authority feature flags remain false.

## Merge gate

Stage 8-I is mergeable only if exact-head evidence proves:

- Foundation CI passes;
- Stage 8-A through Stage 8-H regressions pass;
- Stage 8-I rational timing, stale-snapshot, state-binding, validation-binding, data-minimization, activation-lock, and deterministic-output tests pass;
- the timeline schema is valid and foundation-compatible;
- no unresolved PR review thread remains;
- the branch is not behind `main`;
- no incompatible `main` drift exists.

A later playback slice must be independently gated and consume this exact revision/timeline identity rather than deriving a second musical truth.
