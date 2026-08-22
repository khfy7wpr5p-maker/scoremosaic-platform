# ScoreMosaic Stage 8 Current Architecture

Status: **Stage 8-A and Stage 8-B merged; Stage 8-C deterministic review-state materialization in review**.

Current Stage 8-B main: `d15c9f3e738e00284715d5565ecc89b7777b4754`.

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
  -> [LOCKED] corrected MusicXML derivative
  -> [LOCKED] read/write browser integration
  -> [LOCKED] cursor/playback
  -> [LOCKED] exact revision/hash approval
  -> [LOCKED] publication
```

Teacher Review never mutates source artifacts, engine candidates, Stage 7 Canonical artifacts or Ensemble evidence in place. Teacher work forms a separate immutable lineage.

## Stage 8-A — merged

Repository evidence proves:

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

## Stage 8-B — merged

Controlled durable-provider evidence proves:

- fixed private SQLite persistence boundary;
- append-only revision records and exact resource scope;
- purpose-separated HMAC scope/record/head integrity;
- `BEGIN IMMEDIATE` exact-parent optimistic concurrency;
- exactly one winner for competing different revisions based on one parent;
- exact-current-revision idempotent replay without historical rewind;
- record + head commit in one `synchronous=FULL` transaction;
- crash rollback before commit;
- restart re-verification of HMAC, revision/audit hash, sequence, parent/audit chain and head convergence;
- repeated root/database symlink and inode substitution checks;
- cross-tenant, stale-parent, wrong-key and tamper failures are fail-closed.

This is still a controlled repository provider. `production-durable-store-enabled=false`. Restoring an older complete otherwise-valid database snapshot is not claimed detectable without a separately durable anti-rollback authority.

## Stage 8-C — proof target

The review-state layer is intentionally narrower than corrected MusicXML. It verifies the exact upstream Canonical hash and independently validates only the musical structures it consumes.

It applies only the existing Stage 8-A allowlist:

- pitch;
- effective duration;
- written type;
- dots;
- staff/voice;
- measure-start time signature;
- TAB string/fret;
- event removal.

Before mutation, the current operation-specific value is deterministically hashed and must match `oldValueSha256`. Exact part/measure/event/staff/voice/onset must also match. The output is a new immutable review musical state plus deterministic validation evidence; failures are surfaced and never silently repaired.

Initial validation covers measure overflow/underfill, same-voice overlap and chord alignment. The validation report explicitly remains non-authoritative and ineligible for approval/publication.

## Still locked / not proved

- production identity/session provider and RBAC source;
- public or internal Teacher Review mutation HTTP routes;
- production DB/object-store deployment;
- multi-host distributed consensus and full-store anti-rollback authority;
- corrected MusicXML generation;
- MusicXML safety validation and Canonical round-trip for teacher derivatives;
- browser writable editor activation;
- renderer/cursor/playback authority;
- exact teacher approval;
- publication.

## Safe continuation after Stage 8-C

After Stage 8-C passes exact-head CI and merges, proceed to a read-only Teacher Review projection/focus contract before any browser mutation surface. Corrected MusicXML remains a later isolated derivative gate, and approval/publication remain separate from saving a draft revision.
