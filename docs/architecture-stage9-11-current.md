# ScoreMosaic Stage 9-11 Current Architecture

Status: **authoritative current-activation addendum for Stage 9-11**  
Current architecture state contract: `contracts/architecture-current-state-v1.json`

## Stage 9 — production foundation contracts

Stage 9-A through 9-I are complete at repository architecture/contract level.

The repository documents:

- Hetzner Germany + Coolify baseline;
- trust zones and maximum planned connectivity;
- purpose-separated service identities and secret scopes;
- PostgreSQL 18 durability/backup/restore/migration requirements;
- object-storage immutability and independent-copy semantics;
- Authentik OIDC and deny-by-default RBAC mapping;
- Infisical capability/license eligibility requirements;
- crash-safe publication persistence protocol.

Stage 9 does **not** prove or activate any provider resource. Real provisioning, billing, credentials, DNS/TLS, public traffic, production database/object storage, Authentik, Infisical and publication execution remain external-gated.

## Stage 10 — repository UI/application experience

Stage 10-A through 10-F are complete at repository/disconnected-UI level.

Evidence includes:

- UI/application authority contract;
- integrated ScoreMosaic product shell;
- deterministic checked-in review fixture;
- local issue filtering/focus/source-evidence/validation presentation;
- bounded disconnected edit-intent UX;
- accessibility/responsive hardening.

The browser is not production authority. No live API, auth/session/RBAC runtime, upload, server write, playback, publication or infrastructure activation is implied.

## Stage 11 — typed UI/application contracts

Stage 11-A through 11-F are complete at repository/local-integration level.

```text
Stage 10 UI
  -> Stage 11 closed request vocabulary
  -> ScoreMosaicLocalApplication
  -> fail-closed application state/correlation reducer
  -> typed local read/edit-intent adapters
  -> checked-in non-production fixture
```

### Closed read vocabulary

```text
review.read
issues.read
sourceEvidence.read
validation.read
```

### Closed local mutation-intent vocabulary

```text
editIntent.prepare
```

A local intent is not a ScoreEditCommand. It carries no server authorization, old-value precondition, command identity, revision authority, approval authority or publication authority.

### Fail-closed state model

The UI application state is bounded to:

```text
idle
loading
ready
empty
rejected
unavailable
```

Request/response correlation must match exact schema, request ID, kind, document and revision. Stale/mismatched/unknown responses are rejected rather than rendered as trusted data.

## Approved post-Stage-11 UI workstream

`UI Architecture Phase 1` is an approved **unnumbered** product-design workstream. It is not Stage 12 and does not alter the stage sequence.

It defines:

```text
Product navigation
  -> Dashboard / Documents
  -> New Document / OMR processing presentation
  -> Teacher Review Workspace v1
  -> Score Viewer interactions
  -> Structured Edit UX
  -> Validation / Revision UX
  -> Approval / Publication UX
  -> Design System
  -> High-fidelity Figma
```

The workstream contract is `contracts/ui-architecture-phase1-v1.json`. High-fidelity Figma starts only after the repository baseline and consistency tests are green.

This workstream remains presentation/architecture only: real upload, live API, production auth, server write, approval execution, publication execution, playback and infrastructure stay locked.

## Downstream music-application extension seam

A separate architecture-only seam exists for later validated MusicXML consumers, including MusicXML-to-GuitarTab-Engine.

```text
validated / approved Teacher Review artifact
  -> exact corrected MusicXML identity
  -> typed downstream application contract
  -> dedicated adapter
  -> downstream music service
```

Raw OMR candidates are not valid production inputs to this seam. A downstream service cannot mutate Canonical Score or TeacherScoreRevision and cannot approve or publish. Live GuitarTab integration is not activated.

## Browser/network boundary

The current disconnected UI keeps `connect-src 'none'` and repository-local scripts only.

The following remain disabled:

```text
liveApiIntegrationEligible=false
productionFrontendEligible=false
realUploadEligible=false
authRuntimeEligible=false
sessionRuntimeEligible=false
rbacRuntimeEligible=false
productionArtifactReadEligible=false
teacherReviewServerWriteEligible=false
scoreEditCommandCreationEligible=false
teacherScoreRevisionCreationEligible=false
approvalExecutionEligible=false
publicationExecutionEligible=false
playbackEligible=false
productionInfrastructureEligible=false
```

## Relationship to Stage 8

Stage 8 already defines the server-side repository foundations for typed ScoreEditCommand, immutable TeacherScoreRevision, validation, explicit human approval and non-executing publication handoff.

Stage 10/11 and UI Architecture Phase 1 do not bypass or replace that chain. They provide disconnected/local product and design layers that may later connect to it only after a separate live-integration security gate proves authentication, authorization, transport, CSRF/origin/CSP, exact-current revision checks, old-value preconditions, failure/retry/idempotency, audit and rollback.

## Relationship to Stage 9

Stage 10/11 and UI Architecture Phase 1 do not provision infrastructure. Real Hetzner, PostgreSQL, object storage, Authentik, Infisical, credentials, DNS/TLS and public traffic remain deferred behind Stage 9-I.

## Current stop boundary

Repository-only architecture, UI design contracts and tests may continue where they preserve all activation locks. The next **live** transition requires concrete operational facts and a narrow security gate.

No repository document may treat local UI/Figma readiness as permission to:

- create real provider resources;
- accept production/public traffic;
- read production artifacts;
- create server-side teacher revisions from browser state;
- approve or publish;
- activate playback;
- expose production credentials;
- call GuitarTab/downstream engines directly from the browser.
