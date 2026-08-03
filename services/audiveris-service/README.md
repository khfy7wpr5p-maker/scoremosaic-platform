# Audiveris Service

## Current status

This service now contains a real, private Audiveris runtime while keeping every user-facing conversion route disabled.

Implemented:

- official Audiveris `5.11.0` Ubuntu 24.04 package
- release asset pinned by filename, version, and SHA-256
- bundled Java runtime supplied by the official Audiveris installer
- `GET /health` for process and installed-runtime metadata
- `GET /ready` that runs the bounded `audiveris -version` command and requires the exact pinned version
- fixed internal batch command for PDF, JPG/JPEG, and PNG smoke conversion
- server-controlled command arguments and workspace paths
- path containment and symbolic-link rejection
- bounded probe and transcription timeouts
- non-root UID/GID `65532:65532`
- read-only root filesystem with a dedicated temporary workspace
- dropped Linux capabilities and `no-new-privileges`
- private Compose and Coolify network placement with no published host port
- generated score fixture used only for CI conversion verification

Still disabled:

- HTTP file upload
- job creation and queueing
- Gateway orchestration
- persistent source or output storage
- public domain or browser access
- Ensemble comparison
- teacher approval, editor, and note tracking

## Pinned upstream package

| Field | Value |
|---|---|
| Audiveris version | `5.11.0` |
| Release asset | `Audiveris-5.11.0-ubuntu24.04-x86_64.deb` |
| SHA-256 | `f20113aaa33b3149ec8d6a09b2a7963360e65fafd92d69389987a85bbc3ec7a3` |
| Architecture | `amd64` / `x86_64` |
| License | AGPL-3.0 |

See `THIRD_PARTY_NOTICES.md`. The Docker build fails if the downloaded package checksum does not match.

## Endpoints

```text
GET /health -> 200 when the Python adapter process is running
GET /ready  -> 200 only when the pinned Audiveris command executes successfully
```

All non-GET methods return 405. Unknown paths return 404. Upload and conversion capability flags remain `false` because no HTTP conversion API exists.

## Internal command boundary

The private helper builds only this form of command:

```text
audiveris -batch -transcribe -export -save -swap -output <server-output> -- <server-input>
```

Callers cannot add Audiveris switches. Input and output paths must remain inside `SCOREMOSAIC_AUDIVERIS_WORKSPACE_ROOT`. Symbolic-link inputs and unsupported suffixes are rejected.

## Configuration

| Variable | Default | Boundary |
|---|---:|---|
| `SCOREMOSAIC_AUDIVERIS_HOST` | `127.0.0.1` | loopback or wildcard bind only |
| `SCOREMOSAIC_AUDIVERIS_PORT` | `8082` | 1024–65535 |
| `SCOREMOSAIC_AUDIVERIS_RUNTIME_MODE` | `disabled` | `disabled` or `audiveris` |
| `SCOREMOSAIC_AUDIVERIS_COMMAND` | `/usr/bin/audiveris` | absolute path |
| `SCOREMOSAIC_AUDIVERIS_VERSION` | `5.11.0` | validated version token |
| `SCOREMOSAIC_AUDIVERIS_PROBE_TIMEOUT_SECONDS` | `20` | 1–120 |
| `SCOREMOSAIC_AUDIVERIS_REQUEST_TIMEOUT_SECONDS` | `600` | 30–1800 |
| `SCOREMOSAIC_AUDIVERIS_WORKSPACE_ROOT` | `/tmp/scoremosaic-audiveris` | absolute non-root path |
| `SCOREMOSAIC_AUDIVERIS_MAX_REQUEST_BYTES` | `20971520` | reserved for later Gateway validation |
| `SCOREMOSAIC_AUDIVERIS_MAX_PAGES` | `40` | reserved for later Gateway validation |
| `SCOREMOSAIC_AUDIVERIS_MAX_IMAGE_PIXELS` | `80000000` | reserved for later Gateway validation |

The container sets runtime mode to `audiveris`; local unit tests default to `disabled` and use injected fake command results.

## Verification

From the repository root:

```bash
python -m compileall -q services/audiveris-service/src
python -m unittest discover -s services/audiveris-service/tests -v
```

GitHub Actions additionally:

1. builds the verified Audiveris image,
2. checks non-root and read-only operation,
3. verifies `/health` and `/ready`,
4. renders the generated SVG score to PNG,
5. performs a real batch transcription,
6. requires a generated `.mxl` artifact,
7. validates private Compose boundaries.

## Security and licensing gates before upload is enabled

- finish existing PDF and XML security stages in the main application
- authenticate Gateway-to-engine traffic
- validate magic bytes, decoded dimensions, page count, and file size
- normalize EXIF orientation and remove camera metadata
- isolate one server-generated workspace per run
- enforce CPU, memory, timeout, cancellation, and cleanup controls
- retain immutable input/output hashes and runtime metadata
- review generated MusicXML before downstream parsing
- complete AGPL source-availability and notice procedures before public network use
- never mark an OMR result as teacher-approved automatically
