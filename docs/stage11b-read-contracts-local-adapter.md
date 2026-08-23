# Stage 11-B — Typed Read Contracts + Local Adapter

## Status

**Repository-local read contracts only. No network transport or production data source is activated.**

Stage 11-B defines closed read request/response schemas and a deterministic local adapter backed only by the checked-in Stage 10 fixture.

## Read request kinds

```text
review.read
issues.read
sourceEvidence.read
validation.read
```

`editIntent.prepare` remains outside the read adapter and is handled in Stage 11-C.

## Exact binding

Every valid read request binds:

- `requestId`
- `documentId`
- `revision`
- one allowed request kind

Document or revision mismatch is rejected fail-closed. Unknown request kinds produce a rejected response with `kind=unknown`; they are never interpreted as another operation.

## Local adapter

The adapter is explicitly:

```text
productionAdapter=false
authoritative=false
networkCapable=false
persistent=false
```

It reads only `window.ScoreMosaicFixture`, which is already repository-owned, non-production and non-authoritative.

## Validation presentation

`validation.read` may expose `approvalEligible` and `publicationEligible` fixture labels for UI presentation, but also carries `authoritative=false`. These labels do not create approval or publication authority.

## Security preservation

The adapter may not use fetch/XHR/WebSocket/EventSource, browser persistence, cookies, navigation authority, clipboard/download APIs, dynamic HTML injection, dynamic code execution, or production credentials/artifacts.

## Next slice

Stage 11-C may define a typed `editIntent.prepare` request/response and local intent adapter. It must remain distinct from ScoreEditCommand creation and server mutation.
