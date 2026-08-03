# HOMR Service

## Current status

This service contains a verified, private HOMR CPU runtime. It does not expose file upload or conversion over HTTP.

Implemented now:

- pinned `homr==0.7.0` package with verified wheel SHA-256
- exact Python runtime dependency versions
- three pinned CPU ONNX model assets with archive and installed-file SHA-256 verification
- `GET /health` reporting runtime metadata while upload and conversion remain disabled
- `GET /ready` returning 200 only when the exact package, executable, and all model hashes are verified
- bounded internal CPU transcription helper with fixed command-line options
- JPG/JPEG and PNG input support for private runtime tests
- generated, non-copyrighted score fixture producing temporary MusicXML in CI
- non-root UID/GID 65532, read-only root filesystem, dropped capabilities, and `no-new-privileges`
- private Compose network with no published host port or public proxy route

## Security boundary

The service is private infrastructure. It must not receive browser traffic directly and must not be assigned a public domain.

The HTTP server accepts only `GET /health` and `GET /ready`. All mutating methods are disabled. Runtime readiness does not authorize processing a user document.

The internal helper accepts no client-controlled HOMR flags and forces CPU mode:

```text
homr --gpu no <server-controlled-image-path>
```

HOMR `0.7.0` performs its own internal title handling. The container is tested without network access, and no title, OCR, model, or command option is accepted from a client.

Input and output paths must remain inside the private temporary workspace. Symbolic links, unsupported suffixes, path escapes, and pre-existing output artifacts are rejected.

## Current endpoints

```text
GET /health  -> 200; process and configured runtime metadata
GET /ready   -> 200 only after package, command, and model verification
```

All other paths return 404. Non-GET methods return 405.

## Input scope

HOMR currently processes raster score images:

```text
image/jpeg
image/png
```

PDF rasterization is not part of this service. A later secured Gateway/preprocessing stage may convert validated PDF pages into bounded images before private HOMR execution.

## Configuration

| Variable | Default | Allowed boundary |
|---|---:|---|
| `SCOREMOSAIC_HOMR_HOST` | `127.0.0.1` | loopback or wildcard bind addresses only |
| `SCOREMOSAIC_HOMR_PORT` | `8080` | 1024–65535 |
| `SCOREMOSAIC_HOMR_LOG_LEVEL` | `INFO` | DEBUG, INFO, WARNING, ERROR, CRITICAL |
| `SCOREMOSAIC_HOMR_RUNTIME_MODE` | `disabled` | `disabled` or `homr` |
| `SCOREMOSAIC_HOMR_COMMAND` | `/usr/local/bin/homr` | absolute path only |
| `SCOREMOSAIC_HOMR_VERSION` | `0.7.0` | semantic version |
| `SCOREMOSAIC_HOMR_PROBE_TIMEOUT_SECONDS` | `30` | 1–180 seconds |
| `SCOREMOSAIC_HOMR_MAX_REQUEST_BYTES` | `20971520` | 1 KiB–100 MiB |
| `SCOREMOSAIC_HOMR_MAX_PAGES` | `40` | reserved, 1–200 |
| `SCOREMOSAIC_HOMR_MAX_IMAGE_PIXELS` | `80000000` | 1–200 million pixels |
| `SCOREMOSAIC_HOMR_REQUEST_TIMEOUT_SECONDS` | `900` | 30–1800 seconds |
| `SCOREMOSAIC_HOMR_WORKSPACE_ROOT` | `/tmp/scoremosaic-homr` | absolute non-root path only |

The request and page limits remain reserved for the later authenticated job layer. They do not enable upload in this runtime integration.

## Local checks

From the repository root:

```bash
python -m compileall -q services/homr-service/src
python -m unittest discover -s services/homr-service/tests -v
```

The real model build and generated-score transcription are tested by GitHub Actions because the current Codespaces development container does not provide the project Docker runtime.

## Explicitly not implemented

- HTTP image or PDF upload
- Gateway job creation or dispatch
- PDF rasterization
- persistent source or MusicXML storage
- public routing or browser access
- authentication or authorization
- Ensemble comparison and candidate ranking
- teacher approval, editor behavior, or publication
