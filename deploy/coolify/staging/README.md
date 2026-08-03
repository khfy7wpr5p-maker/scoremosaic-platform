# Coolify Staging

## Current status

This directory defines a private Coolify staging topology with two verified OMR runtimes and two control/foundation services:

- OMR Gateway foundation: health/readiness probes only; upload and orchestration disabled
- HOMR adapter: verified HOMR `0.7.0` CPU runtime and three pinned ONNX models
- Clarity-OMR foundation: health-only; engine/model not installed
- Audiveris adapter: verified Audiveris `5.11.0` runtime

Audiveris and HOMR can perform private container/CI smoke transcriptions and create temporary score artifacts. There is still no HTTP upload route, Gateway job execution, persistent artifact storage, public API, production deployment, Ensemble comparison, or teacher approval flow.

## Staging topology

```text
Coolify staging resource
  |
  `-- internal Docker network: omr-internal
       |-- omr-gateway:8090             (orchestration disabled)
       |-- homr-foundation:8080          (HOMR 0.7.0 CPU runtime)
       |-- clarity-foundation:8081       (engine/model unavailable)
       `-- audiveris-foundation:8082     (Audiveris 5.11.0 runtime)
```

All four services use `expose`, never `ports`. They have no assigned domain and explicitly disable Traefik routing. The `omr-internal` network is marked internal. Browser or public-internet traffic must not be routed directly to the Gateway or an engine service.

## HOMR runtime boundary

The HOMR image installs the pinned PyPI package `homr==0.7.0`, exact CPU dependency versions, and three upstream ONNX model assets. The build verifies the package wheel, all model archives, and all installed model files with fixed SHA-256 values.

The private helper invokes only this server-defined command:

```text
homr --gpu no <server-controlled-image-path>
```

HOMR `0.7.0` performs its own internal title handling. The container is tested without network access. Client-controlled HOMR options are rejected, and only JPG/JPEG or PNG images inside the temporary workspace are eligible. PDF rasterization belongs to a later secured Gateway/preprocessing stage.

Default staging resources:

| HOMR resource | Value |
|---|---:|
| CPU | `2.00` |
| Memory | `4096m` |
| Non-executable workspace | `1073741824` bytes (1 GiB) |
| Request timeout | `900` seconds |
| Process limit | `128` |

The root filesystem remains read-only. Input images, intermediate files, and MusicXML are restricted to `/tmp/scoremosaic-homr`, a non-persistent `noexec,nosuid,nodev` mount owned by UID/GID `65532`. Replacing the container removes this workspace.

## Audiveris runtime boundary

The Audiveris image installs the official Ubuntu 24.04 x86_64 release package for version `5.11.0`. The build verifies the pinned SHA-256 before installation. The adapter invokes only server-defined command arguments and requires input/output paths to stay inside its temporary workspace.

Default staging resources:

| Audiveris resource | Value |
|---|---:|
| CPU | `2.00` |
| Memory | `4096m` |
| Non-executable OMR workspace | `805306368` bytes (768 MiB) |
| Executable JNA-only workspace | `67108864` bytes (64 MiB) |
| Request timeout | `600` seconds |
| Process limit | `128` |

The main Audiveris workspace is `noexec,nosuid,nodev`. JNA native extraction is redirected to a separate smaller `exec,nosuid,nodev` mount that must never contain user source files or OMR output.

## Readiness behavior

Coolify health checks use `/health`, not `/ready`.

Expected staging status after a successful deployment:

```text
omr-gateway /health -> 200
omr-gateway /ready  -> 503 orchestration_disabled

homr /health        -> 200
homr /ready         -> 200 only when package 0.7.0 and all model hashes verify

clarity /health     -> 200
clarity /ready      -> 503 engine/model not installed

audiveris /health  -> 200
audiveris /ready   -> 200 only when the pinned 5.11.0 command executes
```

Engine readiness does not authorize file upload or HTTP conversion. It means only that a private runtime is installed and verified.

## Security defaults

Each service is configured with:

- non-root UID/GID `65532:65532`
- read-only root filesystem
- all Linux capabilities dropped
- `no-new-privileges`
- process-count, CPU, memory, timeout, and temporary-workspace limits
- service-specific non-persistent temporary mounts
- bounded shutdown and restart behavior
- no public proxy route

The Gateway remains unable to create jobs. The main application must finish its PDF/image/XML security stages before real user documents can be routed to this environment.

## Coolify resource setup

Use a Git-connected application with the Docker Compose build pack so the repository Compose file remains the source of truth.

| Setting | Value |
|---|---|
| Repository | private `scoremosaic-platform` repository |
| Git access | GitHub App or deploy key |
| Branch | approved staging branch or `main` after merge |
| Base directory | `/` |
| Docker Compose location | `/deploy/coolify/staging/compose.yaml` |
| Public domains | none |
| Production flag | disabled / staging only |

Copy only the non-secret values from `.env.example` into Coolify environment settings. Never commit tokens, passwords, private keys, callback secrets, storage credentials, user documents, or generated OMR artifacts.

## Pre-deployment gate

1. Use an explicitly approved Git commit.
2. Require successful Foundation, HOMR Runtime, Clarity, Audiveris Runtime, Gateway, and Coolify staging checks.
3. Confirm that no service has a domain or published host port.
4. Confirm HOMR remains pinned to `0.7.0`, CPU mode, and its verified package/model checksums.
5. Confirm Audiveris remains pinned to `5.11.0` and its verified package checksum.
6. Confirm the HOMR and Audiveris main workspaces remain `noexec`.
7. Confirm Coolify contains only non-secret resource variables from `.env.example`.
8. Confirm there is no persistent volume for PDFs, images, MusicXML, `.omr`, model files, or Gateway job data.
9. Confirm Render remains unchanged as fallback until staging acceptance is complete.
10. Complete AGPL notice and source-availability review before any public or user-facing network use.

## Staging verification

1. Confirm all four containers return 200 from `/health`.
2. Confirm HOMR `/ready` returns 200, version `0.7.0`, CPU mode, and three verified models.
3. Confirm Audiveris `/ready` returns 200 and version `5.11.0`.
4. Confirm Clarity `/ready` remains 503 for the expected unavailable reason.
5. Confirm Gateway `/ready` remains 503 with `orchestration_disabled` and separate engine states.
6. Confirm every container runs as UID `65532` with a read-only root filesystem.
7. Confirm HOMR and Audiveris user-data workspaces are `noexec,nosuid,nodev`.
8. Confirm there are no public domains, published ports, or proxy routes.
9. Confirm the Gateway resolves engine service names only through `omr-internal`.
10. Confirm all temporary smoke artifacts disappear after container replacement.

A successful runtime deployment does not authorize real user uploads.

## Rollback procedure

This stage has no database migration or persistent user artifact:

1. Stop automatic deployment while the incident is reviewed.
2. Record the failing commit and sanitized diagnostics without copying user documents into GitHub issues.
3. Restore the previous successful deployment from Coolify history, or deploy an approved Git revert/known-good commit.
4. Re-run all staging verification checks.
5. If the private network, engine readiness, or resource limits do not recover, stop the ScoreMosaic staging resource and continue using the unchanged Render fallback.

Do not force-push `main`, enable a public route as a recovery shortcut, or preserve temporary OMR artifacts outside approved workspaces.

## Explicit non-goals

- Coolify server installation
- production deployment
- DNS, public domain, proxy, or HTTPS configuration
- real Clarity integration
- HTTP file upload or Gateway job creation
- PDF rasterization in HOMR
- persistent source/output storage
- user authentication
- Ensemble Engine or Canonical Score Model
- teacher review, editor, approval, or note tracking
