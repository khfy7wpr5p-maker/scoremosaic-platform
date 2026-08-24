# Teacher Review API Harness v1

Current architecture state: `contracts/architecture-current-state-v1.json`  
Machine-readable contract: `contracts/teacher-review-api-harness-v1.json`  
Parent API contract: `contracts/teacher-review-api-v1.json`

Status: **repository-only disconnected authenticated-API adapter/security harness; no HTTP route or provider runtime**.

This workstream closes the safe repository implementation gap between the Teacher Review API v1 contract and the already-merged Stage 8-G server write boundary. It deliberately stops before Coolify/provider connection, Authentik/session runtime, production persistence, public API routing, real browser networking, approval or publication.

It is an unnumbered workstream and does not consume Stage 12.

## 1. Purpose

`scoremosaic_teacher_review.api_harness.handle_revision_proposal` accepts an in-process request envelope representing what a future same-origin server/BFF route would receive. The harness uses deterministic server-side collaborators for session identity, CSRF, resource authorization, musical-operation authorization, document context, idempotency and audit.

It does **not** open a socket, register a framework route, start an HTTP listener or connect to an external identity provider.

The boundary exercised by tests is:

```text
non-authoritative API intent
  -> session test double
  -> CSRF + exact Origin
  -> document-scope authorization
  -> bounded closed intent parser
  -> operation authorization
  -> server-scoped idempotency inspection
  -> fresh document/revision context
  -> exact projection/snapshot verification
  -> server-resolved target + staff/voice/onset
  -> server-resolved oldValueSha256
  -> sealed revision:propose grant
  -> server command identity
  -> ScoreEditCommand
  -> internal teacher-review-write-request-v1
  -> Stage 8-G
  -> immutable TeacherScoreRevision
  -> safe audit evidence
  -> bounded public result
```

The browser intent never becomes authority.

## 2. Exact security order

Authentication, CSRF and exact-origin checks run before any request-body parsing. Coarse document authorization also runs before parsing, preventing malformed-body details from becoming a resource-existence or authorization oracle.

Only after these gates does the harness parse the closed `scoremosaic-teacher-review-api-edit-intent-v1` shape and authorize the requested musical operation.

The server then resolves the exact current durable head and compares:

- projection SHA-256;
- snapshot kind;
- current revision ID/SHA when present;
- current musical-state SHA-256;
- stable part/measure/event identity.

A mismatch fails closed before Stage 8-G.

## 3. Server-only command construction

The harness constructs all authority-sensitive `ScoreEditCommand` fields on the server side:

- reviewer identity from the authenticated principal;
- tenant/job/report/Canonical scope from the server document context;
- parent revision identity from the durable head;
- staff, voice and onset from the current server musical state;
- `oldValueSha256` from the current target value;
- authorization decision/grant from a server signing key;
- command identity from a server factory.

The public intent cannot provide or override these fields.

The first API operation surface remains exactly:

```text
set_pitch
set_effective_duration
set_dots
remove_event
```

No wider Stage 8 operation becomes public by implication.

## 4. Two idempotency layers

The harness has a small non-production outer reconciliation ledger in addition to the existing Stage 8-G provider-neutral reservation seam.

The outer ledger hashes the raw `Idempotency-Key`; the raw key is never included in audit or result data. It binds the key to principal, tenant, document, operation, requested parent and exact request digest.

Behavior:

- exact committed request -> returns the same revision as `replayed` without invoking Stage 8-G again;
- same key with a different request binding -> `409 conflict`;
- unresolved/pending mutation -> `503` with `reconciliationRequired=true` and no automatic mutation retry.

This is intentionally conservative. Idempotency is not authority to replay an old historical mutation over a newer head.

## 5. Ambiguous mutation quarantine

A provider/process exception after the Stage 8 invocation begins cannot prove whether the durable append happened. Likewise, an audit-sink failure after a successful append cannot safely be treated as a clean failure.

In either case the outer slot stays `pending`. The response exposes no document/revision/current-head identity and reports reconciliation required. Repeating the exact request does not invoke Stage 8-G again.

A later live implementation must reconcile through an independently authorized read before deciding whether any new mutation is permitted.

## 6. Safe public error mapping

Rejected, stale, conflict and unavailable responses keep these values null:

```text
requestId
documentId
parent
revision
```

Public error results never contain:

- session or CSRF tokens;
- raw Idempotency-Key;
- authorization grants/signatures;
- provider exception text;
- stack traces;
- raw MusicXML;
- filesystem paths.

Success remains an immutable `draft` revision with both `approvalEligible=false` and `publicationEligible=false`.

## 7. Test-double boundary

Repository tests may use deterministic in-memory collaborators for:

- authenticated principal;
- resource and operation authorization;
- document context;
- outer idempotency/reconciliation;
- Stage 8 idempotency reservation;
- audit collection.

These collaborators are not production provider choices and contain no real credentials or user data.

## 8. Activation locks

All live/runtime locks remain false:

```text
httpRoutesRegistered
httpListenerActivated
browserNetworkActivated
liveTeacherReviewReadApiActivated
liveTeacherReviewWriteApiActivated
authRuntimeActivated
sessionRuntimeActivated
rbacRuntimeActivated
productionPersistenceActivated
productionIdentityActivated
productionSecretsActivated
correctedMusicXmlProductionPersistenceActivated
approvalExecutionActivated
publicationExecutionActivated
publicApiActivated
productionPublicTrafficActivated
```

The existing public GitHub Pages fixture preview is a separate explicitly authorized non-production surface and does not change these production locks.

## 9. Coolify boundary

After this harness passes its exact-head CI/review/merge gates, the remaining transition to Coolify is external provisioning/runtime work. Repository readiness does not authorize:

- creating or changing a Coolify provider account/server;
- entering real credentials or signing keys;
- connecting Authentik, PostgreSQL or object storage;
- assigning DNS/domains/TLS;
- enabling a public API route;
- enabling real PDF/JPG/PNG upload;
- sending real user documents to OMR engines.

Those remain explicit operational gates.
