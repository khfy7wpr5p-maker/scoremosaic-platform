# Clarity-OMR Service

## Current status

This branch contains a health-only Clarity-OMR service foundation. Clarity source code, model weights, inference runtime, file upload, PDF/image decoding, MusicXML generation, artifact storage, and job execution are deliberately not installed or enabled.

Implemented now:

- Python 3.12 standard-library service with no runtime dependencies
- `GET /health` returning service health while clearly reporting that Clarity and its model are not installed
- `GET /ready` returning HTTP 503 until real engine integration is complete
- declared future input capability for PDF, JPEG (`.jpg`/`.jpeg`), and PNG
- upload and conversion flags fixed to `false`
- compute mode fixed to `disabled`
- bounded environment configuration, including future request, page, and image-pixel limits
- non-root container user
- read-only container filesystem with a small temporary filesystem
- dropped Linux capabilities and `no-new-privileges`
- private Compose network with no published host port
- unit, image, health, readiness, non-root, and Compose checks in GitHub Actions

## Security boundary

The service is private infrastructure. It must not receive browser traffic directly and must not be assigned a public domain. `compose.yaml` uses only `expose`, not `ports`, and attaches the service to the internal OMR network.

The current service does not accept files or MusicXML. The declared formats are a future gateway/service contract only; they do not prove that an upstream Clarity revision natively accepts every format. During real integration, the gateway must validate and normalize PDF, JPEG, and PNG before inference.

No filename, path, callback URL, engine output, model file, or client-provided identifier is trusted.

## Current endpoints

```text
GET /health  -> 200; process is running, engine and model are not installed
GET /ready   -> 503; upload and conversion are unavailable
```

All other paths return 404. Non-GET methods return 405.

The health payload declares:

```json
{
  "acceptedInputFormats": [
    "application/pdf",
    "image/jpeg",
    "image/png"
  ],
  "computeMode": "disabled",
  "uploadEnabled": false,
  "conversionEnabled": false
}
```

`.jpg` and `.jpeg` are represented by the same MIME type: `image/jpeg`.

## Configuration

| Variable | Default | Allowed boundary |
|---|---:|---|
| `SCOREMOSAIC_CLARITY_HOST` | `127.0.0.1` | loopback or wildcard bind addresses only |
| `SCOREMOSAIC_CLARITY_PORT` | `8081` | 1024–65535 |
| `SCOREMOSAIC_CLARITY_LOG_LEVEL` | `INFO` | DEBUG, INFO, WARNING, ERROR, CRITICAL |
| `SCOREMOSAIC_CLARITY_COMPUTE_MODE` | `disabled` | must remain `disabled` in this foundation |
| `SCOREMOSAIC_CLARITY_MAX_REQUEST_BYTES` | `20971520` | 1 KiB–100 MiB |
| `SCOREMOSAIC_CLARITY_MAX_PAGES` | `40` | 1–200 |
| `SCOREMOSAIC_CLARITY_MAX_IMAGE_PIXELS` | `80000000` | 1–200 megapixels |
| `SCOREMOSAIC_CLARITY_REQUEST_TIMEOUT_SECONDS` | `180` | 1–900 seconds |
| `SCOREMOSAIC_CLARITY_WORKSPACE_ROOT` | `/tmp/scoremosaic-clarity` | absolute path only |

The request, page, pixel, timeout, and workspace settings are reserved for later gateway-controlled job execution. They do not enable upload or inference.

## Local checks

From the repository root:

```bash
python -m compileall -q services/clarity-service/src
python -m unittest discover -s services/clarity-service/tests -v
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

## Acceptance gate before real Clarity integration

- pinned Clarity source revision and dependency lock
- pinned model revision and verified checksum
- license, source, and model provenance records
- authenticated service-to-service access
- secure PDF/JPEG/PNG validation using magic bytes and decoded-content limits
- EXIF orientation handling and metadata stripping for camera images
- server-generated job and artifact paths
- explicit CPU/GPU resource mode decided only during real integration
- timeout, cancellation, cleanup, and restart recovery
- immutable candidate artifacts with hashes and engine/model metadata
- safe MusicXML validation before downstream use
- no automatic teacher approval or publication
