# Stage 11-A — UI ↔ Application Boundary

## Status

**Contract design only. No live API, authentication, persistence, server mutation, playback, publication, or production infrastructure is activated.**

Stage 11-A turns the Stage 10 repository-only UI into a typed application-boundary design. The UI may ask for bounded read models and may prepare a bounded edit intent, but the browser remains non-authoritative.

## Allowed request vocabulary

```text
review.read
issues.read
sourceEvidence.read
validation.read
editIntent.prepare
```

Unknown request kinds fail closed.

## Response envelope

Every application response is designed around the same bounded envelope:

```text
schemaVersion
requestId
kind
state
  success | empty | rejected | unavailable
data
error
```

A `success` response requires `error=null`. Non-success states cannot imply authorization, approval, publication, or musical authority.

## Identity binding

Repository-local contracts carry exact `documentId`, `revision`, and `requestId` bindings. Production tenant/principal semantics remain deferred until the later live-auth security gate.

## Authority boundary

The following implications are forbidden:

```text
browser request == authorization
local adapter == production server
UI validation == authoritative validation
edit intent == ScoreEditCommand
successful render == approval
published label == public publication
```

Any future mutation requires server-side authorization, exact-current revision validation, old-value preconditions where applicable, and the existing Teacher Review command/revision chain.

## Preserved locks

The Stage 10-F and Stage 9-I locks remain unchanged:

- no network or production API;
- no auth/session/RBAC runtime;
- no upload;
- no browser persistence;
- no production artifact reads or credentials;
- no Teacher Review server write;
- no ScoreEditCommand or TeacherScoreRevision creation;
- no approval/publication execution;
- no playback;
- no production infrastructure activation.

## Next slice

Stage 11-B may define typed read/query contracts and deterministic local read adapters. It must not activate network transport.
