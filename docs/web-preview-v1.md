# ScoreMosaic Web Preview v1

Status: **repository build ready; not published**  
Contract: `contracts/web-preview-v1.json`  
Current architecture state: `contracts/architecture-current-state-v1.json`

Web Preview v1 packages the existing Stage 10 product experience and Stage 11 typed local application scripts into one deterministic static artifact that can be opened in a browser or later supplied to an explicitly authorized preview host.

This workstream is unnumbered. It does not create Stage 12 and does not activate GitHub Pages, Netlify, Coolify, a public URL, browser networking, authentication, persistence, approval, publication, or production traffic.

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
private/downloadable Actions artifact
        ↓
[PUBLIC PREVIEW DEPLOYMENT LOCKED]
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

The generated preview must contain no browser network or persistence capability such as `fetch`, XMLHttpRequest, WebSocket, EventSource, sendBeacon, localStorage, sessionStorage, IndexedDB, or cookie writes.

The fixture remains non-authoritative. Structured Edit produces only local intent. It cannot create ScoreEditCommand, TeacherScoreRevision, approval, publication, or production persistence.

## CI artifact

`.github/workflows/web-preview-v1-ci.yml` builds and validates the static preview and uploads it as the Actions artifact:

```text
scoremosaic-web-preview-v1
```

The workflow has only `contents: read` permission. It intentionally contains no `deploy-pages`, `configure-pages`, Pages write permission, OIDC write permission, deployment environment, provider credential, or production secret.

Uploading a CI artifact is not a public deployment and does not assign a public URL.

## Public preview gate

A future GitHub Pages/Netlify/Coolify Preview deployment is a separate operational transition because it creates externally reachable traffic. Before that transition, the exact host, visibility, CSP/header behavior, preview labeling, branch/ref policy, rollback/disable procedure, and absence of real credentials/data must be reviewed explicitly.

Current activation truth:

```text
githubPagesEnabled=false
publicPreviewDeployed=false
publicUrlAssigned=false
browserNetworkActivated=false
liveApiActivated=false
productionPersistenceActivated=false
publicTrafficActivated=false
```
