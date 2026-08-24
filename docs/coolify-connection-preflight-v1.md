# ScoreMosaic Coolify Connection Preflight v1

Current architecture state contract: `contracts/architecture-current-state-v1.json`

Status: **repository preflight ready; Coolify is not connected**.

This is an unnumbered repository-only operational preparation workstream. It does not create or consume Stage 12 numbering and does not change the Stage 5–11 architecture map.

## Purpose

Prepare one exact, fail-closed handoff for a future **private Coolify staging** connection without creating provider resources, storing credentials, activating networking, assigning a domain, enabling public routing, accepting real user documents or enabling production persistence.

The machine-readable contract is `contracts/coolify-connection-preflight-v1.json`. The deterministic validator is `scripts/validate_coolify_connection_preflight.py`.

## Exact connection target

```text
Provider:          Coolify
Environment:       staging
Repository:        khfy7wpr5p-maker/scoremosaic-platform
Branch:            main
Base directory:    /
Compose:           /deploy/coolify/staging/compose.yaml
Environment file:  /deploy/coolify/staging/.env.example
Public domains:    none
Production flag:   false
Build pack:        Docker Compose
```

The staging Compose contains only:

```text
homr-foundation:8080
clarity-foundation:8081
audiveris-foundation:8082
omr-gateway:8090
```

All services remain on the internal `omr-internal` network. They use `expose`, not published host ports. Traefik routing remains disabled. The Gateway remains in `SCOREMOSAIC_GATEWAY_ORCHESTRATION_MODE=disabled`.

## Repository preflight sequence

```text
versioned preflight contract
  -> non-secret .env.example validation
  -> docker compose config render
  -> exact service-set validation
  -> no published ports / no persistent volumes
  -> internal-only network validation
  -> non-root/read-only/cap-drop/no-new-privileges validation
  -> pinned OMR runtime/revision validation
  -> Gateway orchestration-disabled validation
  -> architecture activation-lock validation
  -> deterministic preflight handoff JSON
  -> GitHub Actions artifact
  -> [STOP: EXTERNAL COOLIFY CONNECTION]
```

A successful GitHub Actions preflight artifact is **not a deployment** and is **not evidence that Coolify is connected**.

## Fail-closed security invariants

The preflight fails if any of the following becomes true:

- a service publishes a host port;
- a service uses a persistent or bind-mounted score volume;
- Traefik routing is enabled;
- the staging network is no longer internal;
- a service loses its read-only root filesystem, non-root UID/GID, capability drop or no-new-privileges boundary;
- Gateway orchestration is enabled;
- pinned HOMR, Clarity or Audiveris identities drift;
- production/provider activation flags become true;
- a secret-like key appears in the committed staging environment template.

Source documents, intermediate pages, MusicXML and `.omr` artifacts remain temporary staging data only. No real user upload is authorized by this workstream.

## External facts deliberately not stored in the repository

The repository does not invent or commit the following values:

- Coolify base URL;
- Coolify project/environment identity;
- Coolify destination server identity;
- Git source/repository access credential or equivalent Coolify secret.

These values are resolved only at the future external connection step. Real credentials, API tokens, private keys and passwords must not be pasted into source files, issue/PR text, CI artifacts or committed `.env` files.

## Licensing and promotion boundary

Private staging readiness does not resolve third-party production licensing. In particular, unresolved HOMR/Clarity model licensing and third-party redistribution questions remain independent locks. This preflight cannot authorize public or user-facing OMR service, real user documents, production redistribution or commercial third-party use.

## Coolify connection acceptance criteria

When external provider execution is explicitly performed later, the first connection must remain **private staging only**:

1. Git-connected application points to the approved `main` commit.
2. Base directory is `/` and Compose path is `/deploy/coolify/staging/compose.yaml`.
3. No public domain is assigned.
4. No host port is published.
5. Traefik routes remain disabled.
6. Gateway `/ready` remains unavailable with `orchestration_disabled`; `/health` may be healthy.
7. Engine services may become healthy/readiness-capable only within the private staging network.
8. No persistent user-score storage is attached.
9. No production identity, production database, production object store or public API is activated.
10. No real user upload is accepted.

Provider connection evidence must be recorded separately from repository preflight evidence. Connection does not imply production readiness.

## Current stop boundary

Repository preflight work may complete autonomously. Stop before provider-side mutation unless the exact Coolify destination and operational authority are available. Do not create paid infrastructure, store real credentials, alter DNS/TLS, assign a public route, enable production persistence or route real user documents as part of this repository workstream.
