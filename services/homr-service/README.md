# HOMR Service

## Status

Specification placeholder only. No HOMR source code, model, image, or runtime is installed in Phase 0.

## Planned responsibility

The service will wrap one pinned HOMR revision behind a private internal API and return an immutable OMR candidate plus diagnostics.

## Required behavior before integration

- Private network only; no public browser-facing endpoint
- Non-root isolated container
- Explicit CPU, memory, time, input-size, page-count, and output-size limits
- Pinned upstream revision and dependency lock
- License and source-revision record
- Health and readiness checks
- Safe cancellation and timeout behavior
- Server-generated job and artifact paths
- Candidate artifact hash and engine-version metadata
- No teacher approval or automatic publication decision

## Planned internal contract

The final endpoint shape will be established in Phase 1. Expected capabilities:

```text
GET    /health
GET    /ready
POST   /internal/jobs
GET    /internal/jobs/{runId}
GET    /internal/jobs/{runId}/artifacts
POST   /internal/jobs/{runId}/cancel
DELETE /internal/jobs/{runId}
```

The service must never trust a filename, local path, callback URL, or MusicXML returned by the engine.

## Acceptance gate

Real HOMR integration starts only after PDF validation, service authentication, artifact storage, timeout, cancellation, and MusicXML security tests exist.
