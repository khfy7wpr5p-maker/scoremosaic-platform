# Stage 8-G — Server-Authorized Write Boundary Foundation

## Status and scope

Stage 8-G is a repository-only server write-boundary foundation. It composes the already-merged Stage 8 authorization, immutable command/revision, deterministic materialization/validation, and durable exact-parent append layers into one bounded in-process write path.

It does **not** register an HTTP route, activate browser mutation, select a production identity/session provider, enable corrected-artifact production storage, approve a revision, or publish a score.

## Security order

One write attempt follows this order:

```text
trusted RevisionScope + fresh durable head
  -> sealed revision:propose grant verification
  -> closed bounded write-request envelope
  -> ScoreEditCommand hash/schema validation
  -> exact tenant/job/reviewer/report/Canonical/parent binding
  -> exact current-state binding
  -> old-value/location precondition + deterministic in-memory edit
  -> visible deterministic validation evidence
  -> atomic provider-neutral idempotency reservation
  -> raw sealed-grant re-verification at revision creation
  -> immutable TeacherScoreRevision
  -> Stage 8-B exact-parent CAS append
  -> bounded non-authoritative write result
```

Authorization intentionally precedes parsing of the caller request body and precedes the idempotency callback. An unauthorized or stale-grant caller cannot use malformed payloads to reach edit materialization or idempotency state.

## Request contract

`contracts/teacher-review-write-request-v1.schema.json` is closed and contains only:

- `schemaVersion`;
- one existing closed `ScoreEditCommand`;
- `requestSha256`, recomputed over the exact canonical request body.

The boundary rejects extra keys, raw XML, JSON Patch shapes, arbitrary object paths, renderer mutation objects, floating-point/non-canonical values, excessive nesting/nodes, and oversized request bodies.

The request envelope itself carries no authority. Every identity is compared to server-trusted scope and the freshly authenticated durable parent.

## Current-state proof

For the first revision, the supplied review state must exactly match a fresh deterministic materialization of the bound base Canonical payload.

For later revisions, the supplied state SHA-256 must equal the `resultingMusicalStateSha256` of the freshly authenticated durable head revision. The state must also retain the exact base Canonical SHA-256.

A browser-constructed or unpersisted edited state therefore cannot masquerade as current server state.

## Idempotency foundation

Stage 8-G defines a provider-neutral atomic reservation seam. The server derives the reservation slot from exact tenant/job/reviewer/report/Canonical/parent scope plus `commandId` and binds it to the exact request and command SHA-256 values.

The provider may return only:

- `reserved` — first exact request for that slot;
- `replay` — exact duplicate request with the same stable server-created timestamp;
- `conflict` — same slot but different request/command evidence.

A conflict fails closed. Provider failure or malformed receipt fails closed before durable append.

The stable `createdAt` returned by an exact reservation/replay makes concurrent exact duplicates construct the same immutable revision. Stage 8-B's exact-current-revision replay semantics then converge the two attempts to one durable revision without overwrite or rewind.

An old command whose parent is no longer current is rejected as stale before idempotency reuse. Stage 8-G does not turn idempotency into authority to replay historical writes over a newer head.

## Validation behavior

`apply_score_edit_command` remains the only edit materializer. Stage 8-G does not duplicate musical rules.

Old-value mismatch, stale musical location, missing target part/measure/event, invalid operation/value, or cross-scope command fails closed. Post-edit musical validator findings remain visible evidence. A revision containing blocking findings may be stored as an immutable draft, but it remains non-approvable and non-publishable.

No hidden correction is performed.

## Error boundary

Externally meaningful Stage 8-G categories are intentionally bounded, including:

- `WRITE_AUTHORIZATION_DENIED`;
- `WRITE_STALE_PARENT`;
- `WRITE_REQUEST_*`;
- `WRITE_COMMAND_INVALID`;
- `WRITE_SCOPE_MISMATCH`;
- `WRITE_CURRENT_STATE_MISMATCH`;
- `WRITE_STALE_TARGET`;
- `WRITE_EDIT_REJECTED`;
- `WRITE_IDEMPOTENCY_*`;
- `WRITE_STORE_INVALID`.

Provider exception text, SQLite details, signing material, authorization signatures, raw XML, source artifact paths, and internal stack data are not returned by the safe result.

## Activation boundary

Repository metadata exposes only:

`server-write-boundary-foundation-enabled=true`

The following remain false:

- `write-api-enabled`;
- `public-api-enabled`;
- `approval-enabled`;
- `publication-enabled`;
- `corrected-musicxml-materialization-enabled`;
- `production-durable-store-enabled`.

Gate E production/live API prerequisites therefore remain authoritative. Stage 8-G cannot be interpreted as permission to expose this in-process function through a network route.

## Merge gate

Stage 8-G may merge only if fresh exact-head evidence proves:

1. Stage 8-A through 8-F regressions remain green;
2. authorization precedes request parsing/idempotency access;
3. cross-tenant/reviewer/report/Canonical and stale-parent requests fail closed;
4. stale old-value/location requests do not reserve or append;
5. current-state mismatch cannot append;
6. provider conflict/failure cannot append;
7. two exact concurrent duplicates converge to one durable revision;
8. blocking validator evidence remains visible and cannot silently authorize approval/publication;
9. request JSON Schema is valid and closed;
10. no HTTP route/browser-write/approval/publication activation is introduced.
