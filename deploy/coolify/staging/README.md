# Coolify Staging

## Current status

This directory defines a private Coolify staging topology with one real OMR runtime and three control services:

- OMR Gateway foundation: health and readiness probes only; upload and orchestration disabled
- HOMR foundation: health-only; engine not installed
- Clarity-OMR foundation: health-only; engine/model not installed
- Audiveris adapter: verified Audiveris `5.11.0` runtime installed and internally executable

Audiveris can perform a private container/CI smoke transcription and create temporary `.mxl` and `.omr` artifacts. There is still no HTTP upload route, Gateway job execution, persistent artifact storage, public API, production deployment, Ensemble comparison, or teacher approval flow.

## Staging topology

```text
Coolify staging resource
  |
  `-- internal Docker network: omr-internal
       |-- omr-gateway:8090             (orchestration disabled)
       |-- homr-foundation:8080          (engine unavailable)
       |-- clarity-foundation:8081       (engine/model unavailable)
       `-- audiveris-foundation:8082     (Audiveris 5.11.0 runtime)
```

All four services use `expose`, never `ports`. They have no assigned domain and explicitly disable Traefik routing. The `omr-internal` network is marked internal. Browser or public-internet traffic must not be routed directly to the Gateway or an engine service.

## Audiveris runtime boundary

The Audiveris image installs the official Ubuntu 24.04 x86_64 release package for version `5.11.0`. The build verifies the pinned SHA-256 before installation. The adapter invokes only server-defined command arguments and requires input/output paths to stay inside its temporary workspace.

Default staging resources:

| Resource | Value |
|---|---:|
| CPU | `2.00` |
| Memory | `4096m` |
| Temporary workspace | `805306368` bytes (768 MiB) |
| Request timeout | `600` seconds |
| Process limit | `128` |

The root filesystem remains read-only. Only `/tmp/scoremosaic-audiveris` is writable through `tmpfs`; it is intentionally non-persistent. Restarting or replacing the container removes temporary OMR artifacts.

## Readiness behavior

Coolify health checks use `/health`, not `/ready`.

Expected staging status after a successful deployment:

```text
omr-gateway /health -> 200
omr-gateway /ready  -> 503 orchestration_disabled

homr /health        -> 200
homr /ready         -> 503 engine not installed

clarity /health     -> 200
clarity /ready      -> 503 engine/model not installed

audiveris /health  -> 200
audiveris /ready   -> 200 only when the pinned 5.11.0 command executes
```

Audiveris readiness does not authorize file upload or conversion through HTTP. It means only that the private runtime is installed and executable.

## Security defaults

Each service is configured with:

- non-root UID/GID `65532:65532`
- read-only root filesystem
- all Linux capabilities dropped
- `no-new-privileges`
- process-count, CPU, memory, timeout, and temporary-workspace limits
- a service-specific `tmpfs` workspace
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

Before the first deployment of this runtime:

1. Use an explicitly approved Git commit.
2. Require successful Foundation, HOMR, Clarity, Audiveris Runtime, Gateway, and Coolify staging checks.
3. Confirm that no service has a domain or published host port.
4. Confirm Audiveris remains pinned to `5.11.0` and its verified package checksum.
5. Confirm Coolify contains only non-secret resource variables from `.env.example`.
6. Confirm there is no persistent volume for PDFs, images, MusicXML, `.omr`, model files, or Gateway job data.
7. Confirm Render remains unchanged as fallback until staging acceptance is complete.
8. Complete the Audiveris AGPL notice and source-availability review before any public or user-facing network use.

## Staging verification

After deployment:

1. Confirm all four containers return 200 from `/health`.
2. Confirm Audiveris `/ready` returns 200 and reports version `5.11.0`.
3. Confirm HOMR and Clarity `/ready` remain 503 for their expected unavailable reasons.
4. Confirm Gateway `/ready` remains 503 with `orchestration_disabled` and separate engine states.
5. Confirm every container runs as UID `65532`.
6. Confirm root filesystems are read-only and only service-specific temporary directories are writable.
7. Confirm there are no public domains, published ports, or proxy routes.
8. Confirm the Gateway can resolve engine service names only through `omr-internal`.
9. Confirm an Audiveris smoke artifact disappears after container replacement.

A successful runtime deployment does not authorize real user uploads.

## Rollback procedure

This stage has no database migration or persistent user artifact:

1. Stop automatic deployment while the incident is reviewed.
2. Record the failing commit and sanitized container diagnostics without copying user documents into GitHub issues.
3. Restore the previous successful deployment from Coolify history, or deploy an approved Git revert/known-good commit.
4. Re-run all staging verification checks.
5. If the private network, Audiveris readiness, or resource limits do not recover, stop the ScoreMosaic staging resource and continue using the unchanged Render fallback.

Do not force-push `main`, enable a public route as a recovery shortcut, or preserve temporary OMR artifacts outside the approved workspace.

## Explicit non-goals

- Coolify server installation
- production deployment
- DNS, public domain, proxy, or HTTPS configuration
- real HOMR or Clarity integration
- HTTP file upload or Gateway job creation
- persistent source/output storage
- user authentication
- Ensemble Engine or Canonical Score Model
- teacher review, editor, approval, or note tracking
