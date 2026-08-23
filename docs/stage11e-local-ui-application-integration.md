# Stage 11-E — Local UI ↔ Application Integration

## Status

**Disconnected fixture-backed integration only. No live API, authentication, server write, production persistence, playback, publication, or infrastructure is activated.**

Stage 11-E connects the Stage 10 product experience to the Stage 11 typed local application boundary.

## Local chain

```text
Stage 10 UI
  ↓
ScoreMosaicLocalApplication
  ↓
Application State reducer
  ↓
Typed Local Read / Edit-Intent Adapters
  ↓
Checked-in Stage 10 Fixture
```

No link in this chain is authoritative or network-capable.

## Read flow

The UI no longer treats the fixture object as its presentation data source. It requests:

```text
review.read
issues.read
sourceEvidence.read
validation.read
```

through `ScoreMosaicLocalApplication`. Every response is correlated by the Stage 11 state reducer before data can reach the UI.

If any required local state fails to become `ready`, the UI fails closed to an unavailable presentation. There is no production or network fallback.

## Edit-intent flow

Structured Edit keeps the same bounded operation subset but now sends the proposed local correction through `ScoreMosaicLocalApplication.prepareEditIntent()`.

A preview is rendered only after:

- exact local document/revision/issue/target checks;
- bounded operation validation;
- all-false request authority validation;
- reducer response correlation;
- returned local-intent authority checks.

The result remains a local intent, not a ScoreEditCommand.

## Browser security

The Stage 10 CSP remains fail closed:

```text
connect-src 'none'
form-action 'none'
object-src 'none'
frame-src 'none'
base-uri 'none'
```

All Stage 11 scripts are repository-local. No external script, stylesheet, asset, endpoint, cookie, browser persistence, credential, production artifact, service worker, navigation authority, download/clipboard, dynamic HTML, or dynamic-code behavior is introduced.

## Authority preservation

```text
productionApplication=false
authoritative=false
networkCapable=false
persistent=false
```

The UI, local application, reducer, adapters, fixture, renderer output and local intent remain non-authoritative.

Server authorization, old-value preconditions, ScoreEditCommand creation, TeacherScoreRevision creation, approval and publication remain outside this stage.

## Next slice

Stage 11-F may aggregate Stage 11-A through 11-E into repository-only exit eligibility. It must keep live API integration, auth/session/RBAC, server writes, production frontend/runtime, publication, playback and Stage 9 provisioning ineligible.
