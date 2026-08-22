# Stage 8 Revision Materialization and Durable Store Foundation

Status: implementation foundation; no Teacher Review route or production activation.

## Purpose

This Stage 8 slice closes the next boundary after the Teacher Review contract foundation:

```text
verified Canonical Score evidence
  -> exact authorized ScoreEditCommand
  -> semantic old-value precondition
  -> deterministic teacher musical-state materialization
  -> deterministic validation evidence
  -> immutable TeacherScoreRevision
  -> atomic expected-parent append
  -> restart-time chain/hash verification
```

The upstream Canonical Score artifact is never changed in place. The materializer clones the Canonical projection without its self-hash, applies one closed command to the clone, and hashes the resulting musical state deterministically.

## Old-value precondition

`ScoreEditCommand.oldValueSha256` is evaluated against the exact current semantic target value with purpose separation:

```text
SHA256("scoremosaic/teacher-review/old-value/v1\0" || canonical-json(value))
```

The current value is selected by operation type. A mismatch fails closed before mutation. This prevents a stale event/value from being silently overwritten even when the revision parent itself is current.

## Supported materialization operations

The implementation supports only the operation allowlist already frozen by the Stage 8 command contract:

- `set_pitch`
- `set_effective_duration`
- `set_written_type`
- `set_dots`
- `set_staff_voice`
- `set_time_signature`
- `set_tab`
- `remove_event`

No arbitrary object path, XML fragment, renderer-native mutation, expression, or unrestricted raw MusicXML edit is accepted.

Derived written duration is recomputed only from the explicitly edited written type/dot values. A time-signature edit at measure onset also recomputes the measure's deterministic expected duration. These are derived fields, not hidden musical guesses.

## Validation behavior

Every materialized state produces an immutable deterministic validation report and SHA-256 identity. Current checks cover the closed Canonical projection plus foundational musical invariants including:

- Canonical version/root/part/measure/event structure;
- exact rational timing representation;
- measure observed-versus-expected duration evidence;
- active meter versus expected duration;
- non-grace positive effective duration;
- note/rest pitch invariants;
- written type/dot versus written-duration consistency;
- staff/voice bounds;
- event identifier/order consistency;
- chord onset/index consistency;
- overlapping events inside one staff/voice unless they are members of the same chord group.

A validation problem is recorded as evidence. It is not silently repaired. Draft revision creation may therefore carry blocking issues; approval/publication remain locked.

Tie/tuplet cross-event semantics, corrected MusicXML regeneration, MusicXML safety validation, and Canonical round-trip verification remain later Stage 8 work and must pass before approval eligibility can be introduced.

## Durable append-only store

A private SQLite adapter provides a repository-owned durable foundation using standard-library `sqlite3` only. It is not a production database selection and does not enable `production-durable-store-enabled`.

Persistence properties:

- `BEGIN IMMEDIATE` serializes competing writers;
- head movement requires exact expected parent ID and SHA-256;
- exact command replay converges to the existing immutable revision;
- same idempotency slot with different bytes fails closed;
- base Canonical identity cannot change inside a revision chain;
- `previousAuditEventSha256` must match the exact current head audit hash;
- revision/state/validation hashes are independently checked before append;
- revision records expose only draft/immutable/non-approvable/non-publishable state;
- restart loading verifies every persisted revision, state, validation report, parent link, audit predecessor, and the single reachable head chain;
- missing parents, cycles, orphan revisions, state corruption, validation corruption, and head corruption fail closed.

There is no update/delete method for a persisted revision. Undo remains a future append-only inverse-revision operation, not destructive history mutation.

## Concurrency and restart evidence

The executable Stage 8 tests cover:

- deterministic repeated materialization;
- upstream Canonical immutability;
- old-value mismatch rejection;
- stale parent rejection at materialization;
- visible blocking validation evidence;
- deterministic derived written duration;
- persistent restart recovery;
- exact replay idempotency;
- second revision with exact parent/audit predecessor;
- two concurrent writers from one parent, with exactly one winner;
- persisted-state corruption detection;
- wrong audit predecessor rejection.

## Security non-activation

This slice does not add or activate:

- public or internal HTTP mutation routes;
- external identity/session authentication;
- production RBAC policy storage;
- production database/object storage;
- corrected MusicXML materialization;
- approval;
- publication;
- renderer/playback authority;
- OMR dispatch/orchestration changes.

All existing Stage 8 activation flags remain fail-closed.

## Next gate

The next safe Stage 8 slice is to strengthen revision validation for the remaining contracted musical structures and add deterministic corrected-MusicXML materialization, structural safety validation, Canonical re-normalization, and exact round-trip/revision consistency evidence. Writable UI/API activation still remains blocked after that slice until its own Gate E/TR-8A evidence is satisfied.
