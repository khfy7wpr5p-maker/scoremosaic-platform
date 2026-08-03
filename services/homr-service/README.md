# HOMR Service

## Current status

This branch contains a health-only service foundation. The HOMR engine, model files, conversion endpoint, PDF ingestion, artifact storage, and job execution are deliberately not installed or enabled.

Implemented now:

- Python 3.12 standard-library service with no runtime dependencies
- `GET /health` returning service health while clearly reporting that HOMR is not installed
- `GET /ready` returning HTTP 503 until real engine integration is complete
- all mutating HTTP methods disabled
- bounded environment configuration
- non-root container user
- read-only container filesystem with a small temporary filesystem
- dropped Linux capabilities and `no-new-privileges`
- private Compose network with no published host port
- unit, image, health, readiness, and Compose checks in GitHub Actions

## Security boundary

The service is private infrastructure. It must not receive browser traffic directly and must not be assigned a public domain. `compose.yaml` uses only `expose`, not `ports`, and attaches the service to an internal Docker network.

The current service does not accept files or MusicXML. No filename, path, callback URL, engine output, or client-provided identifier is trusted.

## Current endpoints

```text
GET /health  -> 200; process is running, engine is not installed
GET /ready   -> 503; conversion is unavailable
```

All other paths return 404. Non-GET methods return 405.

## Configuration

| Variable | Default | Allowed boundary |
|---|---:|---|
| `SCOREMOSAIC_HOMR_HOST` | `127.0.0.1` | loopback or wildcard bind addresses only |
| `SCOREMOSAIC_HOMR_PORT` | `8080` | 1024–65535 |
| `SCOREMOSAIC_HOMR_LOG_LEVEL` | `INFO` | DEBUG, INFO, WARNING, ERROR, CRITICAL |
| `SCOREMOSAIC_HOMR_MAX_REQUEST_BYTES` | `20971520` | 1 KiB–100 MiB |
| `SCOREMOSAIC_HOMR_MAX_PAGES` | `40` | 1–200 |
| `SCOREMOSAIC_HOMR_REQUEST_TIMEOUT_SECONDS` | `120` | 1–900 seconds |
| `SCOREMOSAIC_HOMR_WORKSPACE_ROOT` | `/tmp/scoremosaic-homr` | absolute path only |

The request, page, timeout, and workspace settings are reserved for later job execution. They do not enable upload or conversion in this foundation package.

## Local checks

From the repository root:

```bash
python -m compileall -q services/homr-service/src
python -m unittest discover -s services/homr-service/tests -v
```

Docker is intentionally tested by GitHub Actions and later by Coolify staging rather than inside the current Codespaces container.

## Planned internal contract

Real integration may add these private capabilities only after security gates exist:

```text
POST   /internal/jobs
GET    /internal/jobs/{runId}
GET    /internal/jobs/{runId}/artifacts
POST   /internal/jobs/{runId}/cancel
DELETE /internal/jobs/{runId}
```

## Acceptance gate before real HOMR integration

- pinned upstream HOMR revision and dependency lock
- license and source-revision record
- authenticated service-to-service access
- secure PDF validation and strict size/page limits
- server-generated job and artifact paths
- timeout, cancellation, cleanup, and restart recovery
- immutable candidate artifacts with hashes and engine metadata
- safe MusicXML validation before downstream use
- no automatic teacher approval or publication
