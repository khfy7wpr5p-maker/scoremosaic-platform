# ScoreMosaic Web Preview v1

Status: **public GitHub Pages preview deployment authorized; runtime deployment not yet verified**  
Contract: `contracts/web-preview-v1.json`  
Current architecture state: `contracts/architecture-current-state-v1.json`

Web Preview v1 packages the existing Stage 10 product experience and Stage 11 typed local application scripts into one deterministic static artifact. The user has explicitly authorized publishing this fixture-only artifact through GitHub Pages. That authority is narrow: it does not activate browser API networking, authentication, persistence, real upload, production data, server writes, approval, publication, or production traffic.

This workstream is unnumbered and does not create Stage 12.

## Purpose

The preview exists so the current ScoreMosaic interface can be inspected as a real browser experience without pretending that the product is connected to production.

```text
Stage 10 UI source
        +
Stage 11 local typed application scripts
        ↓
scripts/build_web_preview.py
        ↓
standalone static artifact
        ↓
CI security validation
        ↓
GitHub Pages artifact
        ↓
GitHub Pages deployment
        ↓
PUBLIC FIXTURE-ONLY PREVIEW
```

## Source-of-truth behavior

The build does not create a second product implementation. It copies the checked-in Stage 10 UI assets, places the four Stage 11 local application scripts under `application/`, and rewrites only their relative script paths in the generated artifact.

A visible banner is injected into the generated page:

```text
NON-PRODUCTION PREVIEW · FIXTURE DATA ONLY · NO API · NO PERSISTENCE
```

The generated directory is not committed to the repository. Re-running the builder against the same source tree must produce byte-identical files.

## Security boundary

The preview retains the Stage 10 CSP boundary:

```text
default-src 'none'
style-src 'self'
img-src 'self' data:
connect-src 'none'
script-src 'self'
object-src 'none'
frame-src 'none'
base-uri 'none'
form-action 'none'
```

The generated preview must contain no browser network or persistence capability such as `fetch`, XMLHttpRequest, WebSocket, EventSource, sendBeacon, localStorage, sessionStorage, IndexedDB, or cookie writes. It must not reference external HTTP resources.

The fixture remains non-authoritative. Structured Edit produces only local intent. It cannot create ScoreEditCommand, TeacherScoreRevision, approval, publication, or production persistence.

## CI artifact

`.github/workflows/web-preview-v1-ci.yml` remains the non-deploying verification workflow. It builds and validates the static preview and uploads a downloadable Actions artifact with `contents: read` only.

Uploading that CI artifact is not itself a public deployment.

## GitHub Pages deployment workflow

`.github/workflows/web-preview-pages-deploy.yml` is the only authorized public preview deployment path. It is intentionally constrained:

- deployment source is `main` only;
- pull requests never execute the Pages deployment;
- the build job has only `contents: read`;
- the deploy job has only the GitHub Pages permissions required for deployment: `pages: write` and `id-token: write`;
- all external GitHub Actions are pinned to full immutable commit SHAs;
- no production secret or provider credential is supplied;
- no `configure-pages` auto-enablement token is used;
- the same hardened fixture-only builder and preview security regressions run before upload;
- deployment targets the `github-pages` environment only.

The repository-level GitHub Pages setting cannot be assumed from repository code. A successful deployment run is required before `githubPagesEnabled`, `publicPreviewDeployed`, `publicUrlAssigned`, or preview `publicTrafficActivated` may become true in the architecture state.

## Current pre-deployment truth

```text
publicPreviewDeploymentAuthorized=true
githubPagesDeploymentWorkflowReady=true
githubPagesSiteConfigurationVerified=false
githubPagesEnabled=false
publicPreviewDeployed=false
publicUrlAssigned=false
browserNetworkActivated=false
liveApiActivated=false
productionPersistenceActivated=false
publicTrafficActivated=false
```

A successful Pages deployment may change only the preview-specific deployment/public-traffic facts. Production `publicApiActivated`, production `publicTrafficActivated`, authentication, storage, writes, approval, and publication remain independently locked.
