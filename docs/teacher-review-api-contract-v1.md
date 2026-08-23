# ScoreMosaic Teacher Review API Contract v1

Status: **approved repository API-contract baseline; no HTTP route or runtime activation**  
Machine-readable contract: `contracts/teacher-review-api-v1.json`  
Edit-intent request schema: `contracts/teacher-review-api-edit-intent-v1.schema.json`  
Revision-result schema: `contracts/teacher-review-api-revision-result-v1.schema.json`  
Current architecture state: `contracts/architecture-current-state-v1.json`

This workstream defines the exact public Teacher Review API boundary that may later sit between the Stage 11 typed UI/application layer and the already-merged Stage 8 server-side Teacher Review foundations. It is unnumbered and does not consume Stage 12.

No route is registered and no production persistence, authentication runtime, server write, approval, publication or public traffic is activated by this package.

## 1. Critical public/internal separation

The browser must never submit the Stage 8-G internal write envelope directly.

```text
Browser UI
  -> non-authoritative API edit intent
  -> session / CSRF / exact-origin gate
  -> server resource authorization
  -> fresh exact-current snapshot resolution
  -> server-side target + old-value resolution
  -> server-side authorization grant
  -> server-generated ScoreEditCommand identity
  -> internal teacher-review-write-request-v1
  -> Stage 8-G authorized write boundary
  -> immutable TeacherScoreRevision
  -> safe public API result
```

The existing `teacher-review-write-request-v1.schema.json` remains an internal server boundary. Its nested `ScoreEditCommand` includes trusted identities and old-value/location preconditions that the browser is not allowed to manufacture.

## 2. Read endpoints

The four reads already reserved by Live UI ↔ API Security v1 remain exact:

```text
GET /api/v1/documents/{document_id}/revisions/{revision_id}/review
GET /api/v1/documents/{document_id}/revisions/{revision_id}/issues
GET /api/v1/documents/{document_id}/revisions/{revision_id}/source-evidence
GET /api/v1/documents/{document_id}/revisions/{revision_id}/validation
```

This contract additionally reserves:

```text
GET /api/v1/documents/{document_id}/revisions
GET /api/v1/documents/{document_id}/revisions/{revision_id}
```

All protected reads require server-side principal, tenant and resource authorization. Route visibility in the browser never counts as authorization.

## 3. Revision-proposal endpoint

The only mutation route reserved by v1 is:

```text
POST /api/v1/documents/{document_id}/revision-proposals
```

Request schema:

```text
scoremosaic-teacher-review-api-edit-intent-v1
```

Response schema:

```text
scoremosaic-teacher-review-api-revision-result-v1
```

The route remains disabled until a separate runtime gate.

## 4. Browser request surface

The request may contain only:

- schema version;
- non-authoritative client request ID;
- exact projection SHA-256;
- exact base/revision snapshot identity and musical-state SHA-256;
- bounded evidence context;
- stable part/measure/event target IDs;
- one bounded operation;
- optional reason.

The browser may **not** provide:

- reviewer or tenant authority;
- authorization decision/grant/signature;
- command ID/SHA;
- old-value SHA-256;
- authoritative staff/voice/onset location;
- approval or publication decisions.

Those values are resolved server-side from authenticated scope and the fresh durable head.

## 5. Initial operation surface

The first live-browser API surface intentionally matches the current Stage 11 UI contract:

```text
set_pitch
set_effective_duration
set_dots
remove_event
```

Stage 8 internally already supports a broader closed command vocabulary, including `set_written_type`, `set_staff_voice`, `set_time_signature` and `set_tab`. Their existence does not make them public API operations.

Expanding the browser/API operation set requires a versioned contract change and new UI/security evidence. No operation outside the Stage 8 closed vocabulary can be introduced by this API.

## 6. Exact snapshot rules

A request binds to one exact projection and musical snapshot.

For a base snapshot:

```text
kind = base
revisionId = null
revisionSha256 = null
stateSha256 = exact base state SHA-256
```

For a revision snapshot:

```text
kind = revision
revisionId = exact current revision ID
revisionSha256 = exact current revision SHA-256
stateSha256 = exact current musical-state SHA-256
```

The server re-reads the durable head. Any projection, revision or state mismatch fails as stale before Stage 8-G is reached.

## 7. Server resolution order

The required order is security-sensitive:

```text
1. authenticate session
2. validate CSRF + exact Origin
3. authorize operation + document scope
4. parse bounded API intent
5. resolve fresh durable head
6. verify projection/snapshot binding
7. resolve stable target against current state
8. resolve current staff/voice/onset + oldValueSha256
9. issue/resolve revision:propose grant
10. generate server command identity
11. construct + validate ScoreEditCommand
12. construct internal teacher-review-write-request-v1
13. invoke Stage 8-G
14. map only safe result fields
15. append security audit evidence
```

Authorization precedes use of request content as authority. The public request itself never grants permission.

## 8. Idempotency

`Idempotency-Key` is required for revision proposals.

It is an opaque retry token, not a command/revision identity. Server scope binds it to principal, tenant, document, operation, exact parent revision and request digest.

- exact key + exact digest may replay the same committed revision;
- same key + different digest fails as conflict;
- an old historical parent cannot be replayed over a newer head;
- the browser must not silently auto-retry ambiguous writes;
- ambiguous outcomes require read/reconciliation first.

Stage 8-G remains the final provider-neutral reservation/append boundary.

## 9. Safe public result

A successful/replayed public response may expose only bounded revision evidence:

- revision ID/SHA;
- resulting musical-state SHA;
- validation-report SHA;
- blocking/unresolved issue counts;
- immutable draft state.

The result explicitly remains:

```text
status = draft
approvalEligible = false
publicationEligible = false
```

Internal authorization grants/signatures, provider exception detail, raw MusicXML and filesystem paths are never public response fields.

## 10. Error / HTTP semantics

Reserved semantics:

| Condition | HTTP |
|---|---:|
| Read success | 200 |
| New revision created | 201 |
| Exact idempotent replay | 200 |
| Malformed request | 400 |
| Unauthenticated | 401 |
| Unauthorized | 403 |
| Unknown/not-visible resource | 404 |
| Stale/idempotency conflict | 409 |
| Semantically rejected edit | 422 |
| Rate limited | 429 |
| Temporarily unavailable | 503 |

Error payloads use stable public codes and correlation IDs. Cross-tenant existence must not be disclosed through differentiated error detail.

## 11. Approval/publication remain outside v1

This contract defines no approval or publication endpoint.

A revision proposal cannot:

- approve the resulting revision;
- publish it;
- make it publication eligible;
- persist corrected MusicXML to production.

Approval requires its own exact-human-authority contract. Publication remains a separate later side effect.

## 12. Negative security coverage

Required cases include browser-supplied reviewer/auth/command/old-value fields, unsupported operations, raw XML/JSON Patch, stale projection/revision/state hashes, missing/unknown targets, tenant/resource crossing, missing idempotency, conflicting replay, historical-parent replay, missing CSRF, wrong Origin, unauthorized-body oracle attempts, internal-error leakage and attempts to smuggle approval/publication decisions through a revision proposal.

## 13. Activation locks

All remain false:

```text
httpRoutesRegistered
liveTeacherReviewReadApiActivated
liveTeacherReviewWriteApiActivated
browserNetworkActivated
authRuntimeActivated
sessionRuntimeActivated
rbacRuntimeActivated
productionPersistenceActivated
scoreEditCommandCreationActivated
teacherScoreRevisionCreationActivated
correctedMusicXmlProductionPersistenceActivated
approvalExecutionActivated
publicationExecutionActivated
publicTrafficActivated
```
