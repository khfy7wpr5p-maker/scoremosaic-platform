# Audiveris Service

## Current status

This branch contains a health-only Audiveris adapter foundation. Audiveris, a Java runtime, file upload, PDF/image decoding, OMR processing, `.omr` project generation, MusicXML export, artifact storage, and job execution are deliberately not installed or enabled.

Implemented now:

- Python 3.12 standard-library service with no runtime dependencies
- `GET /health` reporting process health while clearly declaring that Audiveris and Java execution are disabled
- `GET /ready` returning HTTP 503 until real engine integration is complete
- declared future gateway input capability for PDF, JPEG (`.jpg`/`.jpeg`), and PNG
- upload and conversion flags fixed to `false`
- runtime mode fixed to `disabled`
- bounded environment configuration, including future request, page, image-pixel, and timeout limits
- non-root container user
- read-only container filesystem with a small temporary filesystem
- dropped Linux capabilities and `no-new-privileges`
- private Compose network with no published host port
- unit, image, health, readiness, non-root, format-capability, and Compose checks in GitHub Actions

## Security boundary

The service is private infrastructure. It must not receive browser traffic directly and must not be assigned a public domain. `compose.yaml` uses only `expose`, not `ports`, and attaches the service to the internal OMR network.

The current service does not accept files or MusicXML. The declared formats are a future gateway contract only. During real integration, the gateway must validate and normalize PDF, JPEG, and PNG before invoking Audiveris. Native compatibility and conversion behavior must be tested against the pinned Audiveris revision rather than assumed.

No filename, path, callback URL, engine output, Java option, `.omr` project, MusicXML file, or client-provided identifier is trusted.

## Current endpoints

```text
GET /health  -> 200; process is running, engine and Java execution are disabled
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
  "runtimeMode": "disabled",
  "uploadEnabled": false,
  "conversionEnabled": false
}
```

`.jpg` and `.jpeg` are represented by the same MIME type: `image/jpeg`.

## Configuration

| Variable | Default | Allowed boundary |
|---|---:|---|
| `SCOREMOSAIC_AUDIVERIS_HOST` | `127.0.0.1` | loopback or wildcard bind addresses only |
| `SCOREMOSAIC_AUDIVERIS_PORT` | `8082` | 1024–65535 |
| `SCOREMOSAIC_AUDIVERIS_LOG_LEVEL` | `INFO` | DEBUG, INFO, WARNING, ERROR, CRITICAL |
| `SCOREMOSAIC_AUDIVERIS_RUNTIME_MODE` | `disabled` | must remain `disabled` in this foundation |
| `SCOREMOSAIC_AUDIVERIS_MAX_REQUEST_BYTES` | `20971520` | 1 KiB–100 MiB |
| `SCOREMOSAIC_AUDIVERIS_MAX_PAGES` | `40` | 1–200 |
| `SCOREMOSAIC_AUDIVERIS_MAX_IMAGE_PIXELS` | `80000000` | 1–200 megapixels |
| `SCOREMOSAIC_AUDIVERIS_REQUEST_TIMEOUT_SECONDS` | `300` | 1–1800 seconds |
| `SCOREMOSAIC_AUDIVERIS_WORKSPACE_ROOT` | `/tmp/scoremosaic-audiveris` | absolute path only |

These request, page, pixel, timeout, and workspace settings are reserved for later gateway-controlled job execution. They do not enable upload, Java execution, or OMR conversion.

## Local checks

From the repository root:

```bash
python -m compileall -q services/audiveris-service/src
python -m unittest discover -s services/audiveris-service/tests -v
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

## Acceptance gate before real Audiveris integration

- pinned Audiveris source or release revision and verified distribution checksum
- pinned compatible Java runtime and dependency inventory
- license and source provenance records
- authenticated service-to-service access
- secure PDF/JPEG/PNG validation using magic bytes and decoded-content limits
- EXIF orientation handling and metadata stripping for camera images
- server-generated job, workspace, `.omr`, and artifact paths
- strict Java process arguments with no client-controlled command-line options
- CPU, memory, process, timeout, cancellation, cleanup, and restart recovery controls
- immutable candidate artifacts with hashes and engine/runtime metadata
- safe `.omr` and MusicXML handling before downstream use
- no automatic teacher approval or publication
