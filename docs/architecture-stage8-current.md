# ScoreMosaic Stage 8 Current Architecture

Status: **Stage 8-A contract foundation merged; Stage 8-B controlled durable revision-store foundation in review**.

Stage 8-A merge base on `main`: `2e63bf9ba064adb7ee86dcf95bf8e0cc5958ee61`.

## Position

```text
Stage 7 read-only evidence
  -> Review Report + Canonical identity
  -> exact reviewer/tenant/resource authorization decision
  -> closed bounded ScoreEditCommand
  -> immutable draft TeacherScoreRevision
  -> validation evidence binding
  -> append-only audit identity
  -> controlled durable revision scope
  -> atomic exact-parent append
  -> HMAC-sealed revision record + head
  -> restart/recovery re-verification
  -> [LOCKED] deterministic musical-state materialization/validation
  -> [LOCKED] corrected MusicXML materialization
  -> [LOCKED] writable review transport/UI
  -> [LOCKED] exact revision/hash approval
  -> [LOCKED] publication
```

Stage 8 never mutates Stage 5-7 source, engine candidate, Canonical or Ensemble evidence in place. Teacher work forms a new immutable lineage.

## Stage 8-A proof

Merged repository evidence proves:

- purpose-separated HMAC-sealed reviewer authorization;
- exact tenant/job/reviewer/report/Canonical/parent scope;
- raw sealed-grant re-verification at the revision boundary;
- closed edit-command schema and bounded operation allowlist;
- no arbitrary XML, JSON Patch, object paths or renderer-native mutation objects;
- deterministic command and draft revision identities;
- immutable `TeacherScoreRevision` records;
- stale-parent preconditions;
- append-only audit predecessor identity;
- approval/publication authority remains false.

## Stage 8-B proof target

The controlled SQLite provider adds repository-level evidence for:

- append-only durable revision records;
- exact resource-scope sealing;
- purpose-separated HMAC record/head integrity;
- one transaction for record insert plus current-head advancement;
- exact-parent optimistic concurrency with one winner for competing revisions;
- exact-current-revision idempotent replay;
- restart recovery after pre-commit crash windows;
- read-path record/head/parent/audit-chain re-verification;
- cross-tenant, stale-parent, tamper, wrong-key and symlink rejection.

This remains a controlled provider, not production storage. `production-durable-store-enabled` remains false.

## Still locked / not proved

- production identity/session provider and RBAC policy source;
- public or internal Teacher Review mutation HTTP route;
- production database/object storage deployment;
- distributed multi-host consensus;
- anti-rollback protection against restoration of an older complete valid database snapshot;
- semantic old-value comparison against a materialized musical state;
- deterministic application of edit operations to Canonical-derived state;
- musical/structural post-edit validation;
- corrected MusicXML generation and Canonical round-trip verification;
- renderer/cursor/playback activation;
- teacher approval and publication.

## Next safe Stage 8 slice

After Stage 8-B passes CI and merges, the next slice is deterministic revision-state materialization and validation. It must implement only fields represented safely in the existing Canonical contract, verify old-value preconditions, preserve exact rational timing, and keep MusicXML export/approval/publication separately locked.
