# ScoreMosaic Stage 8 Current Architecture

Status: **Stage 8-A, Stage 8-B, Stage 8-C and Stage 8-D merged; Stage 8-E read-only browser workspace in review**.

Current Stage 8-D main: `1b5f85f71134cc824c63192a7b83e251e087f488`.

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
  -> [LOCKED] corrected MusicXML derivative
  -> [LOCKED] browser mutation transport/UI
  -> [LOCKED] cursor/playback authority
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

## Stage 8-C — merged

The deterministic review-state layer proves:

- exact upstream Canonical SHA-256 scope before materialization;
- bounded closed Canonical structures at the consumed boundary;
- only the frozen Stage 8 operation allowlist is applied;
- exact part/measure/event/staff/voice/onset target binding;
- operation-specific `oldValueSha256` stale-field protection;
- deterministic immutable state and validation-report hashes;
- visible overflow/underfill/voice-overlap/chord-alignment evidence without silent repair;
- two sequential materialized revisions converge with the Stage 8-B exact-parent durable store.

The review state remains narrower than corrected MusicXML and never grants approval/publication authority.

## Stage 8-D — merged

The read-only workspace boundary proves:

- exact `revision:read` HMAC authorization for tenant/job/reviewer/report/Canonical/snapshot;
- base snapshots must equal a fresh deterministic Canonical materialization;
- revision snapshots must pass Stage 8-B revision validation and bind their exact resulting state SHA-256;
- independent re-validation of the consumed Stage 7 comparison report, nested comparison hash, candidate identities, difference IDs and neutrality boundaries;
- deterministic bounded pagination with explicit total count and `hasMore`;
- stable issue focus metadata against the exact snapshot;
- no raw MusicXML, XML path, artifact reference, source artifact hash, credential, signature or action list in the projection;
- capabilities frozen to read-only/non-authoritative/non-approvable/non-publishable.

Stage 8-D is a server-side projection contract only. It exposes no HTTP route and no browser mutation authority.

## Stage 8-E — proof target

The read-only browser gate binds the Stage 8-D projection to the repository-owned application shell without widening server authority:

- a separate replaceable prototype preserves the original UI-0B no-script/disconnected baseline;
- only one embedded `scoremosaic-teacher-review-projection-v1` payload is consumed;
- unknown projection fields or capability expansion fail closed;
- `connect-src 'none'` keeps all network access disabled;
- browser storage, cookies, navigation, forms and dynamic code execution remain absent;
- projection content reaches the DOM only through safe textual sinks;
- issue order is preserved and the first item is selected deterministically;
- Arrow Up/Down, Home and End provide keyboard issue navigation;
- focus and candidate observations are presentation-only;
- absent events remain explicit evidence rather than being silently repaired;
- edit, approval, publication and playback controls remain disabled.

No public/internal Teacher Review route is added by Stage 8-E. The browser cannot create ScoreEditCommand or TeacherScoreRevision objects.

## Still locked / not proved

- production identity/session provider and RBAC source;
- public or internal Teacher Review HTTP routes;
- production DB/object-store deployment;
- multi-host distributed consensus and full-store anti-rollback authority;
- corrected MusicXML generation;
- MusicXML safety validation and Canonical round-trip for teacher derivatives;
- browser writable editor activation;
- renderer/cursor/playback authority;
- exact teacher approval;
- publication.

## Safe continuation after Stage 8-E

After Stage 8-E passes exact-head CI and merges, isolate corrected MusicXML as a deterministic derivative of one exact TeacherScoreRevision. Safety validation must precede Canonical re-normalization, and the re-normalized Canonical state must match the exact teacher revision before any browser write transport, approval or publication authority is considered. Browser mutation remains locked while this derivative gate is incomplete.
