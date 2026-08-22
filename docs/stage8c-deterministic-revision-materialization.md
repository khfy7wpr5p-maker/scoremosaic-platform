# ScoreMosaic Stage 8-C — Deterministic Revision-State Materialization

Status: **contract/hermetic review-state foundation; no writable/public UI and no corrected MusicXML activation**.

## Purpose

Stage 8-C turns one exact Stage 7 Canonical Score snapshot into an immutable Teacher Review musical state, applies only the Stage 8-A bounded edit allowlist, verifies the old-value precondition, and emits deterministic post-edit validation evidence.

This state is deliberately narrower than MusicXML. It is not a replacement for the Canonical Score, an engraving model, or an approved score artifact.

## Authority chain

```text
verified Canonical Score SHA-256
  -> exact RevisionScope.baseCanonicalSha256
  -> bounded review-state projection
  -> exact stable event location
  -> old-value SHA-256 precondition
  -> one allowlisted typed operation
  -> new immutable review musical state
  -> deterministic validation report
  -> immutable TeacherScoreRevision hashes
  -> Stage 8-B exact-parent durable append
```

No model confidence, Ensemble recommendation, renderer state, or playback result receives correction authority.

## Allowed operations

Stage 8-C implements only the already frozen Stage 8-A operation allowlist:

- `set_pitch`;
- `set_effective_duration`;
- `set_written_type`;
- `set_dots`;
- `set_staff_voice`;
- `set_time_signature` at measure start only;
- `set_tab`;
- `remove_event`.

No insertion, arbitrary object path, XML patch, beam, clef, slur, key-signature or renderer-native mutation is added.

`set_pitch` and `set_tab` require a pitched note. Non-grace duration may not become zero. A time-signature edit is rejected when the source measure already contains mid-measure time-signature changes; this slice does not guess how to rewrite them.

## Old-value precondition

Before mutation the service independently locates the exact `partId / measureId / eventId / staff / voice / onset` target and deterministically hashes the operation-specific current field. That hash must equal `ScoreEditCommand.oldValueSha256`.

This detects a stale musical field even when the revision parent itself has not changed. A mismatch fails closed and produces no state mutation.

For `remove_event`, the old-value precondition covers the complete normalized event record.

## Validation evidence

The initial deterministic validator reports, without silently repairing:

- measure overflow — blocking;
- measure underfill — warning for non-implicit measures;
- overlapping non-chord events in the same staff/voice — blocking;
- chord-group onset/staff/voice misalignment — blocking.

The report always carries:

- `authoritativeCorrection=false`;
- `approvalEligible=false`;
- `publicationEligible=false`.

A blocking finding therefore remains review evidence. The mutated draft state is retained for inspection; no hidden auto-correction is performed.

## Bounded input

The materializer verifies the exact Canonical SHA-256 against the trusted Stage 8 revision scope, rejects unknown fields in the consumed part/measure/event structures, bounds depth/node/part/measure/event counts, and normalizes exact rational values before hashing.

Upstream Canonical fields not needed for this review-state slice — for example XML timing movement detail — remain upstream evidence and are not claimed to be regenerated here.

## Determinism

Review-state and validation-report hashes use canonical sorted compact JSON. The same Canonical snapshot and typed command must produce byte-equivalent logical output and identical hashes across repeated runs.

## Explicitly still locked

Stage 8-C does not activate or prove:

- corrected MusicXML generation;
- MusicXML safety validation of a corrected derivative;
- Canonical round-trip equivalence of an exported derivative;
- writable HTTP/API transport;
- browser editor mutation authority;
- cursor or playback;
- approval;
- publication;
- production durable storage.

Those are separate gates and must not be inferred from a passing review-state validator.

## Merge evidence gate

Required before merge:

- Stage 8-A authorization/revision tests remain green;
- Stage 8-B durable/concurrency/restart tests remain green;
- all eight existing operation types are exercised;
- old-value and location stale cases fail closed;
- cross-Canonical scope/hash mismatch fails closed;
- invalid note/rest operation combinations fail closed;
- measure/chord/voice validator evidence is deterministic;
- two sequential materialized revisions persist and reopen through Stage 8-B;
- activation flags for write/public/approval/publication/corrected-MusicXML/production store remain false.
