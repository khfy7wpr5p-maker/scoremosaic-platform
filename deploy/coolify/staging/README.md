# Coolify Staging Foundation

## Current status

This directory defines a private Coolify staging foundation for the three health-only OMR adapter services:

- HOMR foundation
- Clarity-OMR foundation
- Audiveris foundation

It does not deploy a real OMR engine, enable file upload, create MusicXML, expose a public API, or configure production. The root `compose.yaml` remains the development and CI reference; this Compose file is specific to Coolify staging.

## Staging topology

```text
Coolify staging resource
  |
  `-- internal Docker network: omr-internal
       |-- homr-foundation:8080
       |-- clarity-foundation:8081
       |-- audiveris-foundation:8082
       `-- omr-gateway:8090 (reserved name and port; no container yet)
```

The three services use `expose`, never `ports`. They have no assigned domain and explicitly disable Traefik routing. The `omr-internal` network is marked internal. Browser or public internet traffic must not be routed directly to an engine service.

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

`/ready` intentionally remains HTTP 503 because no real engine is installed. Coolify health checks must use `/health`, not `/ready`, during this foundation stage.

## Input capability boundary

The service foundations declare future PDF, JPEG (`.jpg`/`.jpeg`), and PNG capability. Upload, decoding, normalization, OMR execution, `.omr` generation, and MusicXML generation remain disabled.

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

The reserved gateway name `omr-gateway` and port `8090` are documentation and contract placeholders only. No gateway service is created in this stage.

## Pre-deployment gate

Before the first real staging deployment, verify all of the following:

1. The selected Git commit is an explicitly approved commit.
2. GitHub Actions for foundation, HOMR, Clarity, Audiveris, and Coolify staging are successful.
3. No service has a domain or published host port.
4. Coolify contains only non-secret resource variables from `.env.example`.
5. Any future secret is entered through Coolify secret/environment storage, never Git.
6. No persistent volume contains user PDFs, images, MusicXML, `.omr` files, or model weights.
7. Render remains unchanged as the existing fallback until staging acceptance is complete.

## Staging verification

After deployment:

1. Confirm all three containers report healthy through `/health`.
2. Confirm `/ready` returns 503 with the expected engine-not-installed reason.
3. Confirm each container runs as UID `65532`.
4. Confirm the root filesystem is read-only and only the service-specific temporary directory is writable.
5. Confirm there are no public domains, published ports, or proxy routes.
6. Confirm a service can be reached only by another container attached to `omr-internal`.
7. Confirm restarting a container does not create persistent user or OMR data.

A successful health-only deployment does not authorize file uploads or real OMR processing.

## Rollback procedure

This foundation has no database migration or persistent user artifact, so rollback must be code/configuration-only:

1. Stop automatic deployment while the incident is reviewed.
2. Record the failing deployment commit and container logs without copying user documents into GitHub issues.
3. Use Coolify deployment history to restore the previous successful deployment when that control is available.
4. Otherwise, select the previous known-good Git commit or create an approved Git revert commit, then redeploy.
5. Re-run the staging verification checklist.
6. If the private-network or health checks do not recover, stop the ScoreMosaic staging resource and continue using the unchanged Render fallback.

Do not force-push `main`, delete the failing evidence, or enable a public route as a recovery shortcut.

## Explicit non-goals

- Coolify server installation
- production deployment
- DNS, domain, proxy, or HTTPS configuration
- real Audiveris, HOMR, or Clarity integration
- Java, ML model, or GPU activation
- OMR Gateway implementation
- file upload or storage
- user authentication
- Ensemble Engine
- teacher review, editor, approval, or note tracking
