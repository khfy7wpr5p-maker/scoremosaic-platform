# Coolify Staging

## Current status

This directory defines a private Coolify staging topology with three verified OMR runtimes and one control service:

- OMR Gateway foundation: health/readiness probes only; upload and orchestration disabled
- HOMR adapter: verified HOMR `0.7.0` CPU runtime and three pinned ONNX models
- Clarity adapter: pinned Clarity source snapshot, CPU dependencies, and two model files
- Audiveris adapter: verified Audiveris `5.11.0` runtime

The three engines can perform private container/CI smoke transcriptions and create temporary score artifacts. There is still no HTTP upload route, Gateway job execution, persistent artifact storage, public API, production deployment, Ensemble comparison, or teacher approval flow.

## Staging topology

```text
Coolify staging resource
  |
  `-- internal Docker network: omr-internal
       |-- omr-gateway:8090             (orchestration disabled)
       |-- homr-foundation:8080          (HOMR 0.7.0 CPU runtime)
       |-- clarity-foundation:8081       (pinned Clarity CPU runtime)
       `-- audiveris-foundation:8082     (Audiveris 5.11.0 runtime)
```

All services use `expose`, never `ports`. They have no assigned domain and explicitly disable Traefik routing. The `omr-internal` network is marked internal. Browser or public-internet traffic must not be routed directly to the Gateway or an engine service.

## Clarity runtime boundary

The Clarity image uses source commit `c6bb8a4d2a5b52842a9c41bd0f761f58d02f6f82` and model revision `ee14c1e41ab371fe27bf8a2707ea588560077e73`. The source archive, `yolo.pt`, and `model.safetensors` are verified with fixed SHA-256 values during image build. Runtime dependencies are pinned, including CPU-only `torch==2.13.0+cpu` and `torchvision==0.28.0+cpu`.

The private helper invokes only server-defined PDF conversion arguments:

```text
python /opt/clarity/omr.py <server-controlled.pdf>
  --output <server-controlled.musicxml>
  --device cpu
  --beam-width 2
  --pdf-dpi 300
  --work-dir <server-controlled-directory>
```

Clarity natively receives PDF in this stage. JPG/JPEG/PNG are not advertised as native Clarity inputs. Future Gateway preprocessing may normalize image inputs after the application security gates are complete.

Default staging resources:

| Clarity resource | Value |
|---|---:|
| CPU | `2.00` |
| Memory | `6144m` |
| Non-executable workspace | `2147483648` bytes (2 GiB) |
| Request timeout | `1200` seconds |
| Process limit | `256` |

The root filesystem remains read-only. PDF input, page images, intermediate files, and MusicXML are restricted to `/tmp/scoremosaic-clarity`, a non-persistent `noexec,nosuid,nodev` mount owned by UID/GID `65532`. The runtime is tested without network access so model downloads cannot occur during inference.

The upstream source declares GPL-3.0. The model repository does not expose a separate model license in the pinned runtime path; public service or image distribution therefore requires a separate model provenance and licensing review.

## HOMR runtime boundary

The HOMR image installs `homr==0.7.0`, exact CPU dependency versions, and three upstream ONNX model assets. Package and model hashes are verified. It accepts only server-controlled JPG/JPEG or PNG paths in its temporary workspace and runs with GPU disabled.

Default HOMR resources are `2.00` CPUs, `4096m` memory, a 1 GiB non-executable workspace, a `900` second timeout, and a `128` process limit.

## Audiveris runtime boundary

The Audiveris image installs the pinned `5.11.0` release. The main OMR workspace is `noexec,nosuid,nodev`; JNA native extraction is redirected to a separate smaller `exec,nosuid,nodev` mount. User files and generated score artifacts must never enter the JNA mount.

Default Audiveris resources are `2.00` CPUs, `4096m` memory, a 768 MiB main workspace, a 64 MiB JNA workspace, a `600` second timeout, and a `128` process limit.

## Readiness behavior

Coolify health checks use `/health`, not `/ready`.

```text
omr-gateway /health -> 200
omr-gateway /ready  -> 503 orchestration_disabled

homr /health        -> 200
homr /ready         -> 200 only when package and three model hashes verify

clarity /health     -> 200
clarity /ready      -> 200 only when source, CPU runtime, and two models verify

audiveris /health  -> 200
audiveris /ready   -> 200 only when the pinned 5.11.0 command executes
```

Engine readiness does not authorize file upload or HTTP conversion. It means only that a private runtime is installed and verified.

## Security defaults

Each service uses non-root UID/GID `65532:65532`, a read-only root filesystem, dropped Linux capabilities, `no-new-privileges`, bounded CPU/memory/process/time limits, non-persistent temporary workspaces, and no public proxy route.

The Gateway remains unable to create jobs. The main application must finish its PDF/image/XML security stages before real user documents can be routed here.

## Coolify resource setup

Use a Git-connected application with the Docker Compose build pack. Configure:

| Setting | Value |
|---|---|
| Repository | private `scoremosaic-platform` repository |
| Branch | approved staging branch or `main` after merge |
| Base directory | `/` |
| Docker Compose location | `/deploy/coolify/staging/compose.yaml` |
| Public domains | none |
| Production flag | disabled / staging only |

Copy only the non-secret values from `.env.example`. Never commit tokens, passwords, private keys, storage credentials, user documents, or generated OMR artifacts.

## Pre-deployment gate

1. Use an explicitly approved Git commit with all Foundation, HOMR, Clarity, Audiveris, Gateway, and Coolify checks successful.
2. Confirm no service has a domain, published host port, or enabled Traefik route.
3. Confirm all source/package/model revisions and SHA-256 values remain pinned.
4. Confirm Clarity remains CPU-only and its workspace remains `noexec,nosuid,nodev`.
5. Confirm there is no persistent volume for source documents, intermediate files, MusicXML, `.omr`, or Gateway job data.
6. Confirm Render remains unchanged as fallback until staging acceptance is complete.
7. Complete GPL/AGPL and Clarity model-license reviews before public or user-facing use.

## Staging verification

1. Confirm all four containers return 200 from `/health`.
2. Confirm HOMR `/ready` reports version `0.7.0`, CPU mode, and three verified models.
3. Confirm Clarity `/ready` reports the pinned source/model revisions, CPU-only PyTorch, and two verified models.
4. Confirm Audiveris `/ready` reports version `5.11.0`.
5. Confirm Gateway `/ready` remains 503 with `orchestration_disabled` and separate engine states.
6. Confirm every container runs as UID `65532` with a read-only root filesystem.
7. Confirm no public domains, published ports, proxy routes, or persistent score workspaces exist.
8. Confirm temporary artifacts disappear after container replacement.

A successful runtime deployment does not authorize real user uploads.

## Rollback procedure

This stage has no database migration or persistent user artifact. Stop automatic deployment, record sanitized diagnostics, restore the previous successful Coolify deployment or an approved Git revert, and repeat all staging checks. Keep Render unchanged as fallback.

Do not force-push `main`, enable a public route as a recovery shortcut, or preserve temporary OMR artifacts outside approved workspaces.

## Explicit non-goals

- Coolify server installation or production deployment
- DNS, public domain, proxy, or HTTPS configuration
- HTTP file upload or Gateway job creation
- image-to-PDF normalization for Clarity
- persistent source/output storage
- user authentication
- Ensemble Engine or Canonical Score Model
- teacher review, editor, approval, or note tracking
