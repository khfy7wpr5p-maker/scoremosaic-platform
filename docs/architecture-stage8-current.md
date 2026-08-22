# ScoreMosaic Stage 8 Current Architecture

Status: **Stage 8-A through Stage 8-G merged; Stage 8-H disconnected structured edit-intent composer in review**.

Current Stage 8-G main: `027ea2c3a0d823c880a346cdb486c9149b346dc0`.

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
  -> disconnected local typed BrowserEditIntent
  -> [LOCKED] live Gate E transport/server resolution
  -> [LOCKED] live/public write API and browser mutation
  -> [LOCKED] cursor/playback authority
  -> [LOCKED] exact revision/artifact approval
  -> [LOCKED] publication
```

Teacher Review never mutates source artifacts, engine candidates, Stage 7 Canonical artifacts or Ensemble evidence in place. Teacher work forms a separate immutable lineage.

## Stage 8-A — merged

Repository evidence proves purpose-separated HMAC reviewer authorization, exact tenant/job/reviewer/report/Canonical/parent scope, raw sealed-grant re-verification, a closed edit-command schema and operation allowlist, deterministic immutable draft revisions, stale-parent protection, append-only audit identity, and no approval/publication authority.

## Stage 8-B — merged

The controlled durable-provider layer proves append-only exact-resource revision records, purpose-separated HMAC integrity, `BEGIN IMMEDIATE` exact-parent optimistic concurrency, exact replay convergence, synchronous transactional record/head commits, crash rollback/restart re-verification, symlink/inode substitution defenses, and fail-closed cross-tenant/stale-parent/wrong-key/tamper behavior.

`production-durable-store-enabled=false` remains locked. Full-store rollback detection still requires a separately durable anti-rollback authority.

## Stage 8-C — merged

The deterministic review-state layer proves exact upstream Canonical scope, bounded closed structures, the frozen Stage 8 operation allowlist, exact musical target binding, operation-specific old-value SHA-256 protection, deterministic state/validation hashes, visible validator evidence without silent repair, and sequential integration with the Stage 8-B exact-parent store.

## Stage 8-D — merged

The read-only projection layer proves exact `revision:read` authorization, exact base/revision snapshot binding, independent Stage 7 report re-validation, bounded deterministic pagination/focus, source/credential data minimization, and capabilities frozen to read-only/non-authoritative/non-approvable/non-publishable. No HTTP route is exposed.

## Stage 8-E — merged

The read-only browser layer proves a repository-owned local adapter with `connect-src 'none'`, no browser storage/navigation/forms/dynamic HTML sink, deterministic keyboard issue navigation, explicit absent-event evidence, and disabled edit/approval/publication/playback controls. It preserves the original UI-0B disconnected baseline.

## Stage 8-F — merged

The corrected MusicXML derivative layer proves exact revision/state revalidation, deterministic bounded MusicXML generation, independent structural safety validation, explicit `teacher-review` Canonical provenance, semantic round-trip equality for editable musical fields, and immutable draft artifact evidence. Production corrected-artifact persistence/transport remains locked.

## Stage 8-G — merged

The server-authorized write-boundary foundation proves:

- a fresh durable head is established before caller request parsing;
- sealed `revision:propose` authorization is verified against exact trusted tenant/job/reviewer/report/Canonical/current-parent scope before request parsing or idempotency access;
- the request envelope is closed, bounded and SHA-256 bound to one existing closed `ScoreEditCommand`;
- raw XML, arbitrary paths/patches and renderer-native mutation objects remain impossible;
- first-write and later-write current state are independently bound to fresh base Canonical or the exact durable head revision;
- Stage 8-C remains the only edit/location/old-value musical validator;
- provider-neutral atomic idempotency binds exact scope/parent/command/request evidence;
- provider conflict/failure cannot append;
- concurrent exact duplicates deterministically converge to one immutable revision;
- stale historical parents cannot regain authority through idempotency;
- safe results remain draft/non-authoritative/non-approvable/non-publishable;
- `write-api-enabled=false` and `public-api-enabled=false` remain locked.

Stage 8-G is an in-process repository foundation only and is not a live endpoint.

## Stage 8-H — proof target

The disconnected structured edit-intent composer must prove:

- it consumes only an exact Stage 8-D read-only projection whose `canEdit`, `canApprove`, `canPublish`, and `authoritativeTruth` values remain false;
- a selected event must be present in the exact snapshot before any local intent can be prepared;
- it exposes only the existing typed Stage 8 operation vocabulary;
- operation values are bounded and no raw XML, arbitrary path, patch, executable expression or renderer-native mutation object exists;
- the BrowserEditIntent binds exact projection/snapshot/difference/focus evidence but is explicitly not a `ScoreEditCommand`;
- the intent omits authorization, Stage 8 issue authority, old-value SHA-256, exact current staff/voice/onset proof, command ID/SHA, idempotency, revision and corrected-artifact identity;
- every authority marker is fixed to false;
- local JSON preview uses text-only sinks;
- CSP keeps network and form submission disabled;
- cookies, browser storage, navigation, dynamic code evaluation and HTML injection remain absent;
- keyboard issue navigation and labelled form controls remain accessible;
- submit/approve/publish remain disabled.

Stage 8-H has no activation effect. It evaluates structured correction UX only.

## Still locked / not proved

- production identity/session provider and production RBAC source;
- live Gate E Teacher Review transport binding;
- public or internal Teacher Review HTTP routes;
- production DB/object-store deployment;
- multi-host distributed consensus and full-store anti-rollback authority;
- corrected MusicXML production persistence/transport;
- browser writable editor activation;
- renderer/cursor/playback authority;
- exact teacher approval;
- publication.

## Safe continuation after Stage 8-H

After Stage 8-H passes exact-head CI and merges, live browser mutation must remain locked until Gate E is production-ready and explicitly binds authenticated/authorized principal identity, abuse/idempotency controls and privacy-safe transport to Stage 8-G.

The next repository-only safe area may evaluate read-only rational cursor/timeline mapping against one exact revision snapshot, provided it remains presentation-only, has no playback/audio authority, and cannot alter musical state. Any cursor/playback slice must be independently gated.

Approval remains a later separate gate and must bind one exact immutable revision and one exact validated corrected-MusicXML artifact hash. Publication remains later still.
