# ScoreMosaic Live UI ↔ API Security Architecture v1

Status: **approved repository security-architecture baseline; runtime activation remains locked**  
Machine-readable contract: `contracts/live-ui-api-security-architecture-v1.json`

This workstream defines how the completed Stage 10/11 browser/application model may later connect to authenticated server data without turning browser state into authority. It is **unnumbered** and does not consume Stage 12.

## 1. Fixed authority model

```text
Browser UI
  -> authenticated session context
  -> versioned same-origin API
  -> server authorization
  -> application/domain boundary
  -> persistence
```

The browser cannot manufacture principal identity, tenant/resource authorization, command identity, TeacherScoreRevision, approval or publication authority.

`editIntent.prepare` remains local intent preparation. It is not a server mutation endpoint and is not a ScoreEditCommand.

## 2. Identity and session

Target identity provider remains Authentik using OIDC/OAuth2 Authorization Code + PKCE. The intended web security shape is a server-side BFF or equivalent confidential boundary:

- provider access/refresh tokens are not exposed to application JavaScript;
- tokens are not placed in localStorage or sessionStorage;
- browser state uses a bounded server-side session referenced by `__Host-scoremosaic_session`;
- the cookie is HttpOnly, Secure, SameSite=Lax, Path=/ and has no Domain attribute;
- session idle/absolute expiration must be bounded by runtime configuration;
- authentication rotates the session; logout invalidates it server-side.

No session field or IdP role claim grants document/revision authority by itself.

## 3. Authorization

Every protected request is authorized server-side.

Required checks include:

```text
authenticated principal
  -> tenant membership
  -> operation authorization
  -> exact document scope
  -> exact revision scope where applicable
```

Authorization is deny-by-default. Browser-supplied role claims, disabled/hidden controls and route visibility are presentation only.

## 4. Versioned API transport

The baseline API namespace is `/api/v1`.

Initial read mapping preserves Stage 11 vocabulary:

```text
review.read
GET /api/v1/documents/{document_id}/revisions/{revision_id}/review

issues.read
GET /api/v1/documents/{document_id}/revisions/{revision_id}/issues

sourceEvidence.read
GET /api/v1/documents/{document_id}/revisions/{revision_id}/source-evidence

validation.read
GET /api/v1/documents/{document_id}/revisions/{revision_id}/validation
```

All schemas are versioned and request bodies are endpoint-bounded. The server emits the canonical correlation ID. A client request ID may aid correlation but can never become command or revision identity.

Mutation endpoints are intentionally **not** activated by this contract. Their exact catalog requires a separate Teacher Review API contract.

## 5. CSRF, origin and CORS

State-changing methods (`POST`, `PUT`, `PATCH`, `DELETE`) require:

- authenticated server session;
- session-bound CSRF token;
- exact allowed-origin verification;
- fail-closed rejection when CSRF/origin evidence is missing or invalid.

Credentialed wildcard CORS is forbidden. Same-origin API is the baseline. Any cross-origin expansion requires a versioned architecture change.

## 6. CSP transition

Current disconnected UI remains:

```text
connect-src 'none'
```

The maximum baseline for a future activated same-origin API is:

```text
connect-src 'self'
```

That change is **not activated** by this repository contract. Unsafe eval and default unsafe inline script execution remain forbidden.

## 7. Teacher Review mutation safety

Any future score mutation must prove:

```text
principal
+ tenant/resource authorization
+ exact current parent revision
+ stable target identity
+ old-value precondition
+ closed operation vocabulary
```

The browser cannot directly create authoritative score state. A stale revision or precondition mismatch fails closed.

Validation PASS does not approve. Approval does not publish.

## 8. Idempotency and retry

Every mutation requires idempotency semantics.

The idempotency key is only an opaque retry token. It is never musical/domain identity.

Server scope binds the token to principal, tenant, operation, resource, exact parent revision and request digest.

- same key + same request digest -> same committed outcome;
- same key + different digest -> reject;
- ambiguous mutation outcome -> reconcile, do not silently re-execute;
- browser automatic mutation retry is forbidden;
- safe reads may use bounded backoff and must respect server retry guidance.

## 9. Error/privacy boundary

External errors expose stable error category/code and correlation ID, not internal implementation detail.

Never expose:

- credentials/tokens;
- raw provider exception text;
- source document content;
- full MusicXML;
- unrestricted local paths;
- sensitive cross-resource existence information.

## 10. Audit

Protected operations require append-only audit evidence with server timestamp, principal, tenant where applicable, operation, resource/revision identity, outcome and correlation ID.

Session, CSRF and raw idempotency tokens must not be logged.

## 11. Rate limit and abuse protection

Rate limits are server-side defense-in-depth and do not grant authorization. Runtime values remain deployment configuration rather than invented repository facts.

Mutation throttling must not trigger silent replay.

## 12. Kill switch / rollback

Runtime architecture must support independent disablement of:

- all live UI↔API transport;
- mutation transport;
- read transport.

CSP can fail back to `connect-src 'none'`. Auth failure fails closed. Rollback cannot rewrite immutable TeacherScoreRevision history.

## 13. Required negative coverage

The contract requires tests for missing/expired/forged sessions, tenant/resource isolation, browser role escalation, CSRF/origin attacks, wildcard credentialed CORS, stale revision writes, old-value mismatch, unknown target identity, idempotency replay misuse, ambiguous write retries, correlation-ID authority escalation, privacy leaks and direct browser calls to OMR/downstream engines.

## 14. Runtime prerequisites

Before any live activation, a separate reviewed runtime gate must have concrete evidence for:

- Teacher Review API contract;
- final production origin/domain and TLS;
- Authentik runtime configuration;
- production secret provisioning;
- database/artifact persistence;
- negative security + E2E tests;
- rollback exercise.

This repository contract grants none of those operational facts.

## 15. Activation locks

All remain false:

```text
liveNetworkActivated
connectSrcSelfActivated
authRuntimeActivated
sessionRuntimeActivated
rbacRuntimeActivated
productionArtifactReadActivated
teacherReviewServerWriteActivated
scoreEditCommandCreationActivated
teacherScoreRevisionCreationActivated
approvalExecutionActivated
publicationExecutionActivated
realUploadActivated
productionInfrastructureActivated
publicTrafficActivated
```
