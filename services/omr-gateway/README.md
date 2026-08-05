# OMR Gateway Foundation

## Current status

This service remains a private, health-only foundation for the shared ScoreMosaic OMR Gateway. It centralizes the configured internal addresses for Audiveris, HOMR, and Clarity, but it does not accept files, create jobs through HTTP, call an OMR conversion endpoint, persist artifacts, or produce MusicXML.

Phase 11 adds a **versioned orchestration-plan contract library** without enabling orchestration. The library can deterministically describe a future job plan, engine-run lifecycle, timeout policy, source/candidate artifact relationships, and security boundaries. It performs no file, network, queue, database, or storage operation.

Implemented now:

- Python 3.12 standard-library HTTP service
- `GET /health` returning process health and disabled capabilities
- `GET /ready` returning HTTP 503 while orchestration remains disabled
- bounded readiness probes for the three private engine `/ready` endpoints
- isolated probe results so one unavailable engine does not hide the others
- declared future PDF, JPEG (`.jpg`/`.jpeg`), and PNG input capability
- immutable in-memory job and engine-run record model aligned with the existing OMR job contract
- versioned `1.0` orchestration-plan JSON Schema
- deterministic orchestration plan, run, candidate, and artifact identifiers
- explicit lifecycle transitions and bounded timeout policy
- immutable source and candidate artifact relationships
- independent candidate namespaces for Audiveris, HOMR, and Clarity
- exact runtime verifier for plan hashes, relationships, policies, and disabled boundaries
- non-root, read-only container foundation
- no public port or direct browser route

## Current endpoints

```text
GET /health -> 200; gateway process is running
GET /ready  -> 503; orchestration and upload are disabled
```

All other paths return 404. Non-GET methods return 405. In particular, `/internal/jobs` and an orchestration endpoint do not exist in this foundation.

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

## Orchestration contract v1 boundary

`build_orchestration_plan()` creates an immutable deterministic plan only. Its serialized shape is governed by:

```text
contracts/omr-orchestration-plan.schema.json
```

The contract defines:

- one immutable source artifact and SHA-256
- one to three canonical engine runs
- symbolic endpoint keys rather than user-supplied URLs
- one isolated candidate namespace per engine
- expected immutable MusicXML and diagnostic artifact slots
- per-engine timeout values from 30 to 7200 seconds
- monotonic timeout accounting beginning at dispatch
- a bounded cancellation grace period
- terminal timeout behavior with no automatic retry
- explicit engine-run state transitions
- deterministic `planId` and `planSha256`
- exact verification that rejects modified identifiers, relationships, hashes, policies, extra fields, ranking, or execution flags

The contract does **not** dispatch the plan. `transportProfile` is only a future adapter label. `endpointKey` is one of `audiveris`, `homr`, or `clarity`; it is not a URL, hostname, path, token, or credential.

All decision and execution boundaries remain fixed:

```json
{
  "executionEnabled": false,
  "uploadEnabled": false,
  "persistenceEnabled": false,
  "networkDispatchEnabled": false,
  "engineRanking": false,
  "winnerSelection": false,
  "automaticMerge": false,
  "automaticCorrection": false,
  "teacherApproval": false,
  "publication": false
}
```

See `docs/gateway-orchestration-contract-v1.md` for the complete architectural boundary.

## Existing job model boundary

`build_job_record()` creates an immutable in-memory planning record only. It validates the existing `job_...` identifier format and creates one unique engine run and candidate namespace per requested engine.

It does not:

- accept or read a user file
- create a queue entry
- start an engine
- write a database record
- create storage paths on disk
- merge or rank candidate results
- approve or publish output

The candidate separation is intentionally explicit. The v1 orchestration plan strengthens it with a unique candidate identifier and run-specific namespace:

```text
candidates/{jobId}/{engine}/{candidateId}
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

The engine addresses are deployment configuration, never orchestration-plan or user input. Readiness probes read at most 64 KiB from each response and use a strict timeout.

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
- concrete engine adapter request/response contracts
- server-generated job, run, candidate, and artifact identifiers
- queue, timeout enforcement, cancellation, cleanup, and restart recovery
- immutable source and candidate artifact hashes
- safe MusicXML validation
- controlled storage with retention rules
- real engine adapters with pinned versions
- no automatic teacher approval or publication

## Explicit non-goals

- public API or domain
- real upload or conversion
- live network dispatch or orchestration execution
- database, queue, or persistent storage
- automatic Ensemble comparison invocation
- engine ranking, preferred candidate, or winner selection
- automatic MusicXML merge or correction
- user editor, teacher approval, or note tracking
- ST-OMR implementation or integration
