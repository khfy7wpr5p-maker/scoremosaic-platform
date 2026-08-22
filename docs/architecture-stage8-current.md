# ScoreMosaic Stage 8 Current Architecture

Status: **Stage 8-A through Stage 8-F merged; Stage 8-G server-authorized write-boundary foundation in review**.

Current Stage 8-F main: `7e1f7dd6522ae563d767e820450b6f0082ef7106`.

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
  -> [LOCKED] live/public write API and browser mutation
  -> [LOCKED] cursor/playback authority
  -> [LOCKED] exact revision/artifact approval
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

## Stage 8-E — merged

The read-only browser gate proves:

- a separate replaceable prototype preserves the UI-0B no-script/disconnected baseline;
- only the bounded `scoremosaic-teacher-review-projection-v1` shape is consumed;
- unknown projection fields or capability expansion fail closed;
- `connect-src 'none'` keeps all network access disabled;
- browser storage, cookies, navigation, forms and dynamic code execution remain absent;
- projection content reaches the DOM only through safe textual sinks;
- issue order/initial focus are deterministic;
- Arrow Up/Down, Home and End provide keyboard issue navigation;
- absent events remain explicit evidence rather than hidden repair;
- edit, approval, publication and playback controls remain disabled.

No public/internal Teacher Review route or browser mutation authority is added by Stage 8-E.

## Stage 8-F — merged

The corrected MusicXML derivative gate proves:

- one exact immutable revision and one exact resulting review state are revalidated before export;
- the stored validation report hash and issue counts are recomputed from that exact state;
- MusicXML materialization is deterministic and bounded;
- generated XML passes an independent streaming structural-safety gate before semantic reuse;
- Canonical re-normalization uses existing parser semantics with explicit `teacher-review` provenance rather than impersonating an OMR engine;
- the ordinary OMR normalizer remains closed to the Teacher Review source identity;
- the regenerated Canonical representation matches the exact review state under the documented editable-musical semantic projection;
- event IDs/XML provenance and derived `observedDuration`/`writtenDuration` are not confused with editable musical truth;
- the corrected artifact binds exact revision/state/XML/safety/round-trip hashes;
- artifact status remains immutable draft with approval/publication false.

`corrected-musicxml-materialization-enabled=false` remains locked because production corrected-artifact storage/transport has not been authorized.

## Stage 8-G — proof target

The server-authorized write-boundary foundation must prove:

- a fresh durable head is established from trusted server scope before request-body parsing;
- the sealed `revision:propose` grant is verified against exact tenant/job/reviewer/report/Canonical/current-parent scope before any request parsing or idempotency callback;
- the transport envelope is closed, bounded and SHA-256 bound to one existing closed `ScoreEditCommand`;
- raw XML, arbitrary paths/patches and renderer-native mutation objects remain impossible;
- the command's authorization-decision/job/reviewer/report/Canonical/parent identities exactly match trusted server scope;
- the first write uses a freshly materialized base Canonical state; later writes require a state SHA-256 matching the exact durable head revision;
- old-value/location/value-domain checks remain delegated to the deterministic Stage 8-C materializer;
- validator failures remain visible evidence and are never silently repaired;
- a provider-neutral atomic idempotency reservation binds exact scope/parent/command/request hashes;
- provider conflict/failure cannot append a revision;
- concurrent exact duplicates use one stable server timestamp and converge through Stage 8-B to one immutable revision;
- stale historical parents cannot regain write authority through idempotency;
- safe write results remain draft/non-approvable/non-publishable and expose no live-route capability.

Stage 8-G is an in-process repository foundation only. `server-write-boundary-foundation-enabled=true` does not activate `write-api-enabled` or `public-api-enabled`.

## Still locked / not proved

- production identity/session provider and production RBAC source;
- public or internal Teacher Review HTTP routes;
- production DB/object-store deployment;
- multi-host distributed consensus and full-store anti-rollback authority;
- corrected MusicXML production persistence/transport;
- browser writable editor activation;
- renderer/cursor/playback authority;
- exact teacher approval;
- publication.

## Safe continuation after Stage 8-G

After Stage 8-G passes exact-head CI and merges, browser-facing mutation must remain locked until the live Gate E authentication/authorization/idempotency/privacy boundary is complete and explicitly bound to this server write contract. Repository-only editor request composition and accessibility work may proceed without network authority, but no browser may generate server authority locally.

Approval remains a separate later gate and must bind one exact immutable revision **and** one exact validated corrected-MusicXML artifact hash. Publication remains later still.
