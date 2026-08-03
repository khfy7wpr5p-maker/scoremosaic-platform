# Coolify Staging Foundation

## Current status

This directory defines a private Coolify staging foundation for four health-only services:

- OMR Gateway foundation
- HOMR foundation
- Clarity-OMR foundation
- Audiveris foundation

It does not deploy a real OMR engine, accept files, run orchestration, create MusicXML, expose a public API, or configure production. The root `compose.yaml` remains the development and CI reference; this Compose file is specific to Coolify staging.

## Staging topology

```text
Coolify staging resource
  |
  `-- internal Docker network: omr-internal
       |-- omr-gateway:8090
       |-- homr-foundation:8080
       |-- clarity-foundation:8081
       `-- audiveris-foundation:8082
```

All four services use `expose`, never `ports`. They have no assigned domain and explicitly disable Traefik routing. The `omr-internal` network is marked internal. Browser or public internet traffic must not be routed directly to the gateway or an engine service.

The gateway centralizes administrator-controlled private engine addresses and can probe each engine's `/ready` endpoint. Upload and orchestration remain fixed to disabled. One engine being unavailable does not hide the state of the others.

## Security and resource defaults

Each service is configured with:

- non-root UID/GID `65532:65532`
- read-only root filesystem
- all Linux capabilities dropped
- `no-new-privileges`
- process-count, CPU, memory, and temporary-workspace limits
- a separate service-specific `tmpfs` workspace
- restart policy and bounded shutdown grace period
- health check against `/health`

Engine `/ready` endpoints remain HTTP 503 because no real engine is installed. Gateway `/ready` remains HTTP 503 because orchestration is disabled. Coolify health checks must use `/health`, not `/ready`, during this foundation stage.

## Input capability boundary

The foundations declare future PDF, JPEG (`.jpg`/`.jpeg`), and PNG capability. Upload, decoding, normalization, OMR execution, `.omr` generation, MusicXML generation, artifact storage, and Ensemble comparison remain disabled.

## Coolify resource setup

Use a Git-connected application with the Docker Compose build pack so the repository Compose file remains the source of truth.

Recommended staging settings:

| Setting | Value |
|---|---|
| Repository | private `scoremosaic-platform` repository |
| Git access | GitHub App or deploy key |
| Branch | approved staging branch or `main` after merge |
| Base directory | `/` |
| Docker Compose location | `/deploy/coolify/staging/compose.yaml` |
| Public domains | none |
| Production flag | disabled / staging environment only |

Copy only the non-secret values from `.env.example` into the Coolify environment settings. Do not upload a populated `.env` file and do not commit tokens, passwords, private keys, model credentials, callback secrets, or storage credentials.

The `omr-gateway` name and port `8090` are now used by the health-only gateway container. They do not authorize a domain, public route, upload endpoint, or orchestration.

## Pre-deployment gate

Before the first real staging deployment, verify all of the following:

1. The selected Git commit is explicitly approved.
2. GitHub Actions for foundation, HOMR, Clarity, Audiveris, Gateway, and Coolify staging are successful.
3. No service has a domain or published host port.
4. Coolify contains only non-secret resource variables from `.env.example`.
5. Any future secret is entered through Coolify secret/environment storage, never Git.
6. No persistent volume contains user PDFs, images, MusicXML, `.omr` files, model weights, or gateway job data.
7. Render remains unchanged as the existing fallback until staging acceptance is complete.

## Staging verification

After deployment:

1. Confirm all four containers report healthy through `/health`.
2. Confirm each engine `/ready` returns 503 with its expected engine-not-installed reason.
3. Confirm gateway `/ready` returns 503 with `orchestration_disabled` and separate engine states.
4. Confirm every container runs as UID `65532`.
5. Confirm root filesystems are read-only and only service-specific temporary directories are writable.
6. Confirm there are no public domains, published ports, or proxy routes.
7. Confirm the gateway can reach engine service names only through `omr-internal`.
8. Confirm restarting containers does not create persistent user, OMR, or gateway job data.

A successful health-only deployment does not authorize file uploads or real OMR processing.

## Rollback procedure

This foundation has no database migration or persistent user artifact, so rollback must be code/configuration-only:

1. Stop automatic deployment while the incident is reviewed.
2. Record the failing deployment commit and container logs without copying user documents into GitHub issues.
3. Use Coolify deployment history to restore the previous successful deployment when that control is available.
4. Otherwise, select the previous known-good Git commit or create an approved Git revert commit, then redeploy.
5. Re-run the staging verification checklist.
6. If private-network or health checks do not recover, stop the ScoreMosaic staging resource and continue using the unchanged Render fallback.

Do not force-push `main`, delete failing evidence, or enable a public route as a recovery shortcut.

## Explicit non-goals

- Coolify server installation
- production deployment
- DNS, domain, proxy, or HTTPS configuration
- real Audiveris, HOMR, or Clarity integration
- Java, ML model, or GPU activation
- file upload or storage
- real Gateway job creation or orchestration
- user authentication
- Ensemble Engine
- Canonical Score Model
- teacher review, editor, approval, or note tracking
