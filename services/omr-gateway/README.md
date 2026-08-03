# OMR Gateway Foundation

## Current status

This service is a private, health-only foundation for the shared ScoreMosaic OMR Gateway. It centralizes the configured internal addresses for Audiveris, HOMR, and Clarity, but it does not accept files, create jobs through HTTP, call an OMR conversion endpoint, persist artifacts, or produce MusicXML.

Implemented now:

- Python 3.12 standard-library HTTP service
- `GET /health` returning process health and disabled capabilities
- `GET /ready` returning HTTP 503 while orchestration remains disabled
- bounded readiness probes for the three private engine `/ready` endpoints
- isolated probe results so one unavailable engine does not hide the others
- declared future PDF, JPEG (`.jpg`/`.jpeg`), and PNG input capability
- immutable in-memory job and engine-run record model aligned with the existing OMR job contract
- independent candidate namespaces for Audiveris, HOMR, and Clarity
- non-root, read-only container foundation
- no public port or direct browser route

## Current endpoints

```text
GET /health -> 200; gateway process is running
GET /ready  -> 503; orchestration and upload are disabled
```

All other paths return 404. Non-GET methods return 405. In particular, `/internal/jobs` does not exist in this foundation.

The health payload declares:

```json
{
  "gateway": "running",
  "capabilities": {
    "acceptedInputFormats": [
      "application/pdf",
      "image/jpeg",
      "image/png"
    ],
    "uploadEnabled": false,
    "orchestrationEnabled": false,
    "orchestrationMode": "disabled",
    "candidateIsolation": true
  },
  "engines": {
    "audiveris": "not_ready",
    "homr": "not_ready",
    "clarity": "not_ready"
  }
}
```

The liveness endpoint does not contact sibling services. The readiness endpoint performs bounded private probes and still returns 503 because orchestration is fixed to disabled.

## Job model boundary

`build_job_record()` creates an immutable in-memory planning record only. It validates the existing `job_...` identifier format and creates one unique engine run and candidate namespace per requested engine.

It does not:

- accept or read a user file
- create a queue entry
- start an engine
- write a database record
- create storage paths on disk
- merge or rank candidate results
- approve or publish output

The candidate separation is intentionally explicit:

```text
candidates/{jobId}/audiveris
candidates/{jobId}/homr
candidates/{jobId}/clarity
```

No engine is allowed to overwrite another engine's candidate.

## Configuration

| Variable | Default | Boundary |
|---|---:|---|
| `SCOREMOSAIC_GATEWAY_HOST` | `127.0.0.1` | loopback or wildcard bind address only |
| `SCOREMOSAIC_GATEWAY_PORT` | `8090` | 1024-65535 |
| `SCOREMOSAIC_GATEWAY_LOG_LEVEL` | `INFO` | DEBUG, INFO, WARNING, ERROR, CRITICAL |
| `SCOREMOSAIC_GATEWAY_ORCHESTRATION_MODE` | `disabled` | must remain disabled |
| `SCOREMOSAIC_GATEWAY_PROBE_TIMEOUT_SECONDS` | `1` | 1-10 seconds per engine |
| `SCOREMOSAIC_GATEWAY_MAX_REQUEST_BYTES` | `20971520` | reserved future limit; 1 KiB-100 MiB |
| `SCOREMOSAIC_GATEWAY_MAX_PAGES` | `40` | reserved future limit; 1-200 |
| `SCOREMOSAIC_GATEWAY_MAX_IMAGE_PIXELS` | `80000000` | reserved future limit; 1-200 megapixels |
| `SCOREMOSAIC_GATEWAY_WORKSPACE_ROOT` | `/tmp/scoremosaic-gateway` | absolute path only |
| `SCOREMOSAIC_GATEWAY_AUDIVERIS_BASE_URL` | `http://audiveris-foundation:8082` | administrator-controlled HTTP(S) base URL without credentials/path/query |
| `SCOREMOSAIC_GATEWAY_HOMR_BASE_URL` | `http://homr-foundation:8080` | same boundary |
| `SCOREMOSAIC_GATEWAY_CLARITY_BASE_URL` | `http://clarity-foundation:8081` | same boundary |

The engine addresses are deployment configuration, never user input. Readiness probes read at most 64 KiB from each response and use a strict timeout.

## Local checks

From the repository root:

```bash
python -m compileall -q services/omr-gateway/src
python -m unittest discover -s services/omr-gateway/tests -v
```

Docker validation is performed in GitHub Actions and later in Coolify staging.

## Required gates before real orchestration

- secure PDF/JPEG/PNG validation by magic bytes and decoded-content limits
- authenticated service-to-service requests
- server-generated job, run, and artifact identifiers
- queue, timeout, cancellation, cleanup, and restart recovery
- immutable source and candidate artifact hashes
- safe MusicXML validation
- controlled storage with retention rules
- real engine adapters with pinned versions
- no automatic teacher approval or publication

## Explicit non-goals

- public API or domain
- real upload or conversion
- database, queue, or persistent storage
- Ensemble comparison
- Canonical Score Model
- user editor, teacher approval, or note tracking
