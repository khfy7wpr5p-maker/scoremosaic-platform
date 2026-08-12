# Clarity-OMR Service

## Current status

This service contains a verified, private Clarity-OMR CPU runtime while keeping browser upload, Gateway orchestration, persistent storage, and public routing disabled.

Implemented now:

- pinned upstream source commit `c6bb8a4d2a5b52842a9c41bd0f761f58d02f6f82`
- verified source archive SHA-256
- pinned Hugging Face model revision `ee14c1e41ab371fe27bf8a2707ea588560077e73`
- verified SHA-256 values for `yolo.pt` and `model.safetensors`
- exact CPU dependency lock with `torch==2.13.0+cpu` and `torchvision==0.28.0+cpu`
- `GET /health` reporting the expected runtime while upload/conversion remain disabled
- `GET /ready` returning 200 only after source, model, dependency, and CPU checks succeed
- bounded stable runtime diagnostics: raw stdout/stderr and provider exception text are redacted, and failed readiness suppresses untrusted source/model/dependency fields
- bounded internal PDF-to-MusicXML helper with fixed server-controlled options
- generated, non-copyrighted PDF smoke fixture in GitHub Actions
- MusicXML size, XML, root-element, and unsafe-declaration validation
- non-root UID/GID `65532`, read-only root filesystem, dropped capabilities, and `no-new-privileges`
- private Compose network with no published host port or public proxy route

## Security boundary

The HTTP service exposes health and readiness only. All non-GET methods return 405 and unknown routes return 404. No HTTP request can submit a PDF, select a model, set an output path, alter beam width, enable GPU, or create a job.

The internal helper accepts only server-controlled `.pdf` paths within `/tmp/scoremosaic-clarity`. Symbolic links, workspace escapes, unsupported suffixes, stale output files, and unsafe MusicXML declarations are rejected.

The fixed internal command is equivalent to:

```text
python /opt/clarity/omr.py <server-controlled.pdf>
  --output <server-controlled.musicxml>
  --device cpu
  --beam-width 2
  --pdf-dpi 300
  --work-dir <server-controlled-directory>
```

Runtime execution is forced offline with Hugging Face and Transformers offline flags. Model downloads occur only during the reproducible image build and are checksum-verified. No user-controlled Clarity options are accepted.

Clarity natively receives PDF in this stage. The service does not claim native JPG/JPEG/PNG support. Image inputs may be securely normalized by a later Gateway preprocessing stage after the application upload security gates are complete.

## Endpoints

```text
GET /health -> 200 while the adapter process is running
GET /ready  -> 200 only when the pinned CPU runtime and two models verify
```

Readiness does not authorize conversion through HTTP. The capability payload remains:

```json
{
  "acceptedInputFormats": ["application/pdf"],
  "computeMode": "cpu",
  "nativePdfOnly": true,
  "uploadEnabled": false,
  "conversionEnabled": false
}
```

## Pinned provenance

| Component | Pin |
|---|---|
| Upstream source | `c6bb8a4d2a5b52842a9c41bd0f761f58d02f6f82` |
| Model revision | `ee14c1e41ab371fe27bf8a2707ea588560077e73` |
| Stage A model | `info/yolo.pt` |
| Stage B model | `info/model.safetensors` |
| PyTorch | `2.13.0+cpu` |
| Torchvision | `0.28.0+cpu` |

Exact source/model checksums and license notes are recorded in `THIRD_PARTY_NOTICES.md`. Exact Python dependencies are recorded in `requirements-runtime.txt`.

The upstream source declares GPL-3.0. The pinned model repository does not expose a separate model license in the runtime path. Public service or image distribution requires a separate model provenance and licensing review.

## Configuration

| Variable | Default | Boundary |
|---|---:|---|
| `SCOREMOSAIC_CLARITY_HOST` | `127.0.0.1` | loopback or wildcard bind only |
| `SCOREMOSAIC_CLARITY_PORT` | `8081` | 1024–65535 |
| `SCOREMOSAIC_CLARITY_LOG_LEVEL` | `INFO` | DEBUG, INFO, WARNING, ERROR, CRITICAL |
| `SCOREMOSAIC_CLARITY_COMPUTE_MODE` | `disabled` | `disabled` or `cpu`; GPU rejected |
| `SCOREMOSAIC_CLARITY_PYTHON_COMMAND` | `/usr/local/bin/python` | absolute path |
| `SCOREMOSAIC_CLARITY_SOURCE_ROOT` | `/opt/clarity` | absolute non-root path |
| `SCOREMOSAIC_CLARITY_SOURCE_REVISION` | pinned commit | exact 40-character lowercase revision |
| `SCOREMOSAIC_CLARITY_MODEL_REVISION` | pinned model revision | exact 40-character lowercase revision |
| `SCOREMOSAIC_CLARITY_PROBE_TIMEOUT_SECONDS` | `90` | 1–300 seconds |
| `SCOREMOSAIC_CLARITY_MAX_REQUEST_BYTES` | `20971520` | 1 KiB–100 MiB |
| `SCOREMOSAIC_CLARITY_MAX_PAGES` | `40` | 1–200 |
| `SCOREMOSAIC_CLARITY_MAX_IMAGE_PIXELS` | `80000000` | 1–200 megapixels |
| `SCOREMOSAIC_CLARITY_REQUEST_TIMEOUT_SECONDS` | `1200` | 60–3600 seconds |
| `SCOREMOSAIC_CLARITY_PDF_DPI` | `300` | 150–400 |
| `SCOREMOSAIC_CLARITY_BEAM_WIDTH` | `2` | 1–5 |
| `SCOREMOSAIC_CLARITY_WORKSPACE_ROOT` | `/tmp/scoremosaic-clarity` | absolute non-root path |

The container image sets compute mode to `cpu`. The disabled default remains useful for source-level unit tests and fail-closed operation outside the image.

## Local checks

From the repository root:

```bash
python -m compileall -q services/clarity-service/src
python -m unittest discover -s services/clarity-service/tests -v
```

The full image build and real generated-score transcription are intentionally run by GitHub Actions because they require large pinned model assets and more memory than the lightweight Codespaces verification step.

## Still disabled

- HTTP PDF/JPG/JPEG/PNG upload
- Gateway job creation, queueing, cancellation, or orchestration
- public domain, browser route, or direct engine access
- persistent PDF, intermediate-image, or MusicXML storage
- user authentication and authorization
- Ensemble comparison and candidate ranking
- Canonical Score Model
- teacher review, editor, approval, and note tracking
