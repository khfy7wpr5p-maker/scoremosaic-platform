# Clarity-OMR Service

## Status

Specification placeholder only. No Clarity-OMR source code, model weights, image, or runtime is installed in Phase 0.

## Planned responsibility

The service will wrap one pinned Clarity-OMR code revision and one verified model revision behind a private internal API. It returns an immutable candidate result and diagnostics.

## Required behavior before integration

- Private network only
- Non-root isolated container
- Explicit CPU/GPU mode and resource limits
- Pinned source and model revisions
- Model checksum verification before startup
- No mutable model download during a user request
- License, source, and model provenance records
- Health and readiness checks
- Safe timeout, cancellation, and partial-output handling
- Candidate artifact hash and version metadata
- No approval or publication authority

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

## Acceptance gate

Real Clarity-OMR integration starts only after the same security core required for HOMR exists, plus model checksum, controlled download, and CPU/GPU behavior tests.
