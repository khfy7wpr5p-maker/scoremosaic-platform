# ScoreMosaic Architecture

Status: **authoritative current architecture through Stage 11-F plus approved unnumbered workstreams**  
Current-state contract: `contracts/architecture-current-state-v1.json`

Historical Gate B-E details remain documented in their dedicated gate documents. Current activation truth is defined by this document together with:

- `docs/architecture-stage5-7-current.md`
- `docs/architecture-stage8-current.md`
- `docs/architecture-stage9-11-current.md`
- `docs/ui-architecture-phase1.md`
- `docs/web-preview-v1.md`
- `docs/live-ui-api-security-architecture-v1.md`
- `docs/teacher-review-api-contract-v1.md`
- `docs/teacher-review-api-harness-v1.md`
- `docs/downstream-music-application-integration-boundary.md`
- `docs/licensing-governance.md`

## 1. Purpose

ScoreMosaic is a security-first OMR and teacher-review platform. It receives untrusted score documents, preserves immutable source lineage, obtains bounded OMR evidence, validates engine outputs as untrusted artifacts, derives deterministic Canonical Score representations, compares evidence, and supports immutable teacher review and publication preparation.

ScoreMosaic may later provide exact validated musical artifacts to downstream music applications, but those applications do not become Canonical, Teacher Review, approval or publication authority.

## 2. Current trust chain

```text
untrusted PDF/image
  -> Safe Intake B.1-B.6
  -> immutable source + job binding
  -> deterministic orchestration plan
  -> durable controlled-staging lifecycle
  -> authenticated fixed-destination private dispatch
  -> bounded one-shot engine execution
  -> authenticated engine result identity
  -> bounded engine-specific result adapter
  -> immutable HMAC-sealed candidate persistence
  -> Candidate Safety
  -> deterministic Canonical Score admission
  -> neutral Ensemble comparison/report
  -> bounded decomposed review evidence
  -> Teacher Review authorization + typed ScoreEditCommand
  -> immutable TeacherScoreRevision
  -> deterministic validation
  -> corrected MusicXML derivative + semantic round-trip
  -> explicit human approval handoff/record
  -> publisher-bound non-executing publication handoff
  -> [EXTERNAL PRODUCTION EFFECT LOCKED]
```

Engine/AI output is evidence. It never directly mutates authoritative musical state and never grants approval or publication authority.

## 3. Current OMR architecture

The current Stage 5-7 production-candidate contract still names three engines:

```text
Audiveris
HOMR
Clarity
```

Stage 6 authenticates and persists bounded candidates. Stage 7 requires at least two Canonical candidates before comparison. Candidate order is deterministic and the comparator remains neutral/read-only.

ST-OMR is currently an isolated architecture/development track and is **not** in the Gateway engine enum or Stage 7 quorum. A future ST-OMR-primary or ST-OMR-only migration is permitted only through a versioned migration contract with shadow benchmarking, teacher-gold evaluation, category-stratified no-regression evidence, calibrated abstention, deterministic musical validation, and explicit rollback. Existing engines must not be removed merely because a model trained successfully; after a proved migration they may remain offline benchmark/reference engines.

## 4. Teacher Review architecture

Stage 8-A through 8-O are complete at repository/preparation level. The repository contains:

- reviewer/resource authorization foundations;
- closed typed ScoreEditCommand contracts;
- immutable TeacherScoreRevision lineage;
- deterministic review state and validation;
- read-only projection;
- corrected MusicXML derivation and semantic round-trip evidence;
- server-authorized non-network write-boundary foundation;
- disconnected BrowserEditIntent;
- approval-candidate evidence;
- explicit human-approval handoff and immutable approval-record foundations;
- publication eligibility and publisher-bound non-executing handoff.

The external publication effect remains locked. Production write persistence, live approval/publication routes, published-artifact persistence, and actual publication execution are not activated.

## 5. UI and application boundary

Stage 10 and Stage 11 are complete at repository/local-integration level.

The current disconnected browser path is:

```text
Stage 10 product UI
  -> typed Stage 11 UI/application contract
  -> local application state/correlation reducer
  -> typed local read/edit-intent adapters
  -> checked-in non-production fixture
```

The browser remains non-authoritative. `connect-src 'none'` remains the current CSP boundary. No browser persistence, production artifact reads, production credentials, live API, server write, playback, approval, publication, or infrastructure activation is granted by Stage 10/11.

A local edit intent is not a ScoreEditCommand. Any future live mutation must independently prove authenticated principal/session semantics, tenant/resource authorization, exact API transport, origin/CSRF/CSP policy, failure/retry/idempotency behavior, audit evidence, exact-current revision validation, old-value preconditions, and rollback/disable behavior.

### 5.1 UI Architecture Phase 1 — approved unnumbered workstream

UI Architecture Phase 1 is **not Stage 12** and does not alter the existing stage map. It defines the product-design structure that sits on top of Stage 10/11 before Figma and before any live API activation.

```text
Product navigation
  -> Dashboard / Documents
  -> New Document / OMR processing presentation
  -> Teacher Review Workspace
  -> Score Viewer interactions
  -> Structured Edit UX
  -> Validation / Revision UX
  -> Approval / Publication UX
  -> Design System
  -> High-fidelity Figma
```

The repository baseline is defined by `contracts/ui-architecture-phase1-v1.json` and `docs/ui-architecture-phase1.md`.

Modernization remains intentionally layered:

```text
Figma / UX
  -> Design System
  -> UI Components
  -> Typed Application Contract
  -> Adapter
  -> Authenticated API
  -> Server / Domain Authority
```

Visual changes should remain above the contract boundary when possible. Data-shape changes belong in typed contracts; transport changes in adapters; authority/business-rule changes in server/domain contracts.

### 5.1.1 Web Preview v1 — verified unnumbered public fixture preview

The repository preview baseline is defined by `contracts/web-preview-v1.json` and `docs/web-preview-v1.md`.

It packages the existing Stage 10 UI plus Stage 11 local typed application scripts into a deterministic standalone static artifact without creating a second UI implementation:

```text
Stage 10 UI + fixture
        +
Stage 11 local adapters/state
        ↓
deterministic preview builder
        ↓
CSP-locked static artifact
        ↓
CI security validation
        ↓
Actions artifact
        ↓
GitHub Pages deployment
        ↓
[PUBLIC FIXTURE-ONLY PREVIEW]
```

The artifact is visibly marked non-production and fixture-only. It retains `connect-src 'none'`, contains no browser network/persistence capability, and cannot upload, authenticate, create ScoreEditCommand/TeacherScoreRevision, approve, publish, or persist production state.

The downloadable CI artifact is not itself a deployment. The separate GitHub Pages workflow has successfully deployed the fixture-only preview at [khfy7wpr5p-maker.github.io/scoremosaic-platform](https://khfy7wpr5p-maker.github.io/scoremosaic-platform/); deployment evidence is pinned in `contracts/web-preview-v1.json`. Netlify, Coolify Preview, browser API traffic, production public traffic, and every production authority remain inactive.

### 5.2 Live UI ↔ API Security Architecture — approved unnumbered workstream

The repository security baseline is defined by `contracts/live-ui-api-security-architecture-v1.json` and `docs/live-ui-api-security-architecture-v1.md`.

It defines a future same-origin authenticated transport without activating it:

```text
Browser
  -> server-managed session
  -> /api/v1
  -> CSRF + exact-origin checks
  -> server tenant/resource authorization
  -> application/domain boundary
```

The target identity provider remains Authentik through OIDC/OAuth2 Authorization Code + PKCE terminated at a server-side BFF or equivalent confidential boundary. Provider access/refresh tokens are not exposed to application JavaScript or browser persistence.

Initial live-read path templates are versioned for `review.read`, `issues.read`, `sourceEvidence.read`, and `validation.read`.

Current `connect-src 'none'` remains active. `connect-src 'self'` is only the maximum future same-origin baseline and cannot activate before a separate runtime gate. Auth/session/RBAC runtime, production artifact reads, server writes, command/revision creation, approval, publication, upload, production infrastructure and public API traffic remain false.

### 5.3 Teacher Review API Contract v1 — approved unnumbered workstream

The repository API baseline is defined by `contracts/teacher-review-api-v1.json` and `docs/teacher-review-api-contract-v1.md`.

The contract reserves exact versioned read endpoints and one bounded future revision-proposal endpoint while preserving the browser/server authority split:

```text
Browser non-authoritative edit intent
  -> authenticated / CSRF / origin gate
  -> server document/resource authorization
  -> exact-current snapshot + stable target resolution
  -> server-derived old-value/location precondition
  -> server-created ScoreEditCommand identity
  -> internal Stage 8-G write envelope
  -> immutable draft TeacherScoreRevision
  -> bounded public revision result
```

The browser may not submit the existing Stage 8-G `teacher-review-write-request-v1` envelope directly and may not provide reviewer/tenant authority, authorization grants/signatures, command identity, old-value preconditions or authoritative staff/voice/onset location.

The initial browser operation surface remains the four Stage 11 families: `set_pitch`, `set_effective_duration`, `set_dots`, and `remove_event`. The broader Stage 8 internal command vocabulary is not implicitly exposed over the API.

No HTTP route is registered by this contract. Live read/write API, browser networking, ScoreEditCommand/TeacherScoreRevision creation, production persistence, approval, publication and public API traffic remain false.

### 5.4 Teacher Review API Security Harness v1 — approved unnumbered repository workstream

The disconnected implementation baseline is defined by `contracts/teacher-review-api-harness-v1.json` and `docs/teacher-review-api-harness-v1.md`.

It exercises the future mutation path against deterministic non-production collaborators without opening a network route:

```text
non-authoritative API intent
  -> session test double
  -> CSRF + exact Origin
  -> document/resource authorization
  -> bounded closed parser
  -> musical-operation authorization
  -> server idempotency/reconciliation ledger
  -> fresh durable head + exact projection/snapshot check
  -> server-resolved staff/voice/onset + oldValueSha256
  -> server-issued revision:propose grant
  -> server-created ScoreEditCommand
  -> internal Stage 8-G write request
  -> Stage 8-G
  -> immutable draft TeacherScoreRevision
  -> safe audit evidence
  -> bounded public result
```

This harness proves server construction of authority-sensitive fields, exact Stage 8-G composition, stale-target/snapshot rejection, exact idempotent replay, conflicting-key rejection and ambiguous mutation quarantine. An exception after mutation begins or an audit failure after append remains pending and requires authorized reconciliation; it is never automatically retried as a fresh mutation.

No HTTP listener, route, browser network, Authentik runtime, provider credential, production persistence, production secret, approval execution, publication execution or production public API is activated.

### 5.5 Downstream music-application integration boundary

Validated ScoreMosaic musical artifacts may later feed sibling applications only through a dedicated downstream boundary.

```text
Canonical / Teacher Review
  -> deterministic validation
  -> corrected MusicXML
  -> exact approved revision/artifact identity
  -> typed downstream application contract
  -> dedicated adapter
  -> music application
```

Raw OMR candidates are not valid production sources for downstream derivation. A downstream service cannot mutate Canonical Score or TeacherScoreRevision and cannot approve or publish.

The first reserved integration is MusicXML-to-GuitarTab-Engine:

```text
approved MusicXML
  -> GuitarTab application contract
  -> GuitarTab adapter
  -> MusicXML-to-GuitarTab-Engine
  -> non-authoritative TAB/fingering candidates
```

This seam is architecture-only today. No live GuitarTab transport or credential is activated.

## 6. Production foundation

Stage 9-A through 9-I are complete as repository production-foundation design. The repository documents a Hetzner Germany + Coolify baseline, PostgreSQL 18 requirements, object-storage immutability/copy semantics, Authentik OIDC/RBAC mapping, Infisical capability requirements, service identity/secret scopes, and crash-safe publication persistence protocol.

These are architecture contracts only. The following remain false:

```text
providerResourcesCreated=false
productionCredentialsProvisioned=false
productionNetworkActivated=false
productionDatabaseActivated=false
productionObjectStorageActivated=false
productionIdentityActivated=false
productionSecretsActivated=false
publicApiActivated=false
publicTrafficActivated=false
publicationExecutionActivated=false
```

Real provisioning remains behind the Stage 9 external-production boundary.

### 6.1 Current maturity and evidence boundary

Repository behavior is strongly regression-tested, but that is not evidence of broad OMR accuracy or production readiness. The fixed current-engine dataset contains one deliberately small score case, and the ST-OMR fixed evaluation contains three repository-owned synthetic fixtures. Teacher-gold evaluation, real-world shadow benchmarking, category-stratified no-regression evidence, production provisioning and live operational validation remain incomplete. Therefore `realOmrAccuracyMeasured=false`, `generalAccuracyClaim=false`, and `productionReady=false` remain explicit in the current-state contract.

### 6.2 Licensing and asset-governance boundary

Repository visibility and runtime authority are separate from licensing. The
canonical policy is defined by `LICENSE`, `LICENSE-SCOPE.md`, `NOTICE`,
`COMMERCIAL-LICENSE.md`, `TRADEMARKS.md`,
`CONTRIBUTOR-LICENSE-AGREEMENT.md`, and `docs/licensing-governance.md`.

First-party code is noncommercial source-available; commercial use requires a
signed agreement. Third-party OMR engines, packages and model assets remain
under their own terms. An agreement for ScoreMosaic-owned code cannot override
AGPL/GPL or third-party model/data obligations.

The current dependency inventory is fail-closed. Audiveris, HOMR,
Clarity-OMR, PyMuPDF and Ultralytics require deployment-specific copyleft or
commercial-license resolution. The HOMR and Clarity model-asset licenses, plus
the complete operating-system/bundled-artifact SBOM, are not yet approved for
production redistribution. These are licensing activation locks in addition to
the existing security, accuracy and infrastructure locks.

## 7. Stage status map

| Stage | Current status | Authority meaning |
|---|---|---|
| 5 | Controlled staging execution complete | Authenticated bounded private staging dispatch/execution exists; not production activation. |
| 6 | Candidate ingestion/persistence complete | Engine results can become immutable authenticated candidates; candidates are not truth. |
| 7 | Canonical/Ensemble convergence complete | Deterministic Canonical admission and neutral comparison; >=2 Canonical candidates required. |
| 8 | Teacher Review/publication preparation complete | Exact immutable review/approval/publication-handoff lineage; external publication effect locked. |
| 9 | Production foundation contracts complete | Provider architecture documented; real provisioning deferred. |
| 10 | Repository UI experience complete | Disconnected, fixture-backed, non-authoritative product UI. |
| 11 | Typed UI/application local integration complete | Typed local adapters/state model complete; live API remains locked. |

Approved unnumbered workstreams:

| Workstream | Status | Meaning |
|---|---|---|
| UI Architecture Phase 1 | Approved repository baseline; Figma application pending | Product navigation, screen architecture, interaction model and Design System defined without live activation. |
| Web Preview v1 | Public fixture-only Pages preview deployed and verified | Deterministic CSP-locked preview is public; browser API, persistence, real data and production traffic remain off. |
| Live UI ↔ API Security Architecture | Approved repository baseline; runtime locked | Identity/session, authorization, API transport, CSRF/origin/CSP, idempotency, audit and rollback rules defined without network activation. |
| Teacher Review API Contract v1 | Approved repository API baseline; routes locked | Exact read/revision-proposal contracts bridge non-authoritative browser intent to Stage 8 server authority without registering HTTP routes. |
| Teacher Review API Security Harness v1 | Approved repository execution harness; runtime locked | Deterministic in-process auth/CSRF/resource/snapshot/idempotency/Stage 8-G composition is tested without HTTP, provider credentials or production persistence. |
| Downstream Music Application Integration | Architecture-only | Safe post-validation seam reserved; MusicXML-to-GuitarTab-Engine live integration remains off. |

## 8. Authority invariants

1. External input and engine output remain untrusted until their applicable gates pass.
2. Source documents, raw candidates, revisions, approvals and publication handoffs are immutable lineage artifacts.
3. AI/OMR evidence cannot directly mutate authoritative score state.
4. Canonical admission and musical validation remain deterministic and fail closed.
5. Unknown or ambiguous content is surfaced as evidence or abstention, not silently guessed.
6. Teacher approval is explicit and bound to an exact immutable revision/artifact.
7. Publication is a separate transition from approval.
8. Browser/local application state is never server authority.
9. Downstream music applications are derivative services, never upstream score authority.
10. Production activation requires a separate security gate and concrete external facts.

## 9. Current boundaries

### Repository evidence proves

- Safe Intake and Candidate Safety contracts;
- controlled-staging private dispatch/execution and candidate persistence;
- Stage 7 deterministic convergence;
- Stage 8 immutable teacher-review/publication-preparation chain;
- Stage 9 production architecture contracts;
- Stage 10 disconnected product experience;
- Stage 11 typed local UI/application integration;
- approved UI Architecture Phase 1 product-design baseline;
- deterministic non-production Web Preview artifact build, CI boundary and verified fixture-only GitHub Pages deployment;
- approved Live UI ↔ API repository security architecture baseline;
- approved Teacher Review API repository contract baseline;
- disconnected Teacher Review API Security Harness with exact Stage 8-G mutation composition and reconciliation tests;
- architecture-only downstream music-application seam.

### Repository evidence does not prove

- a production deployment or any public runtime beyond the verified fixture-only GitHub Pages preview;
- public production upload/API traffic;
- real production provider provisioning;
- production PostgreSQL/object-storage operation;
- production Authentik/Infisical runtime;
- production credentials/DNS/TLS;
- live public Teacher Review read/write routes;
- production publication execution;
- production browser playback;
- ST-OMR Gateway/Ensemble integration;
- ST-OMR superiority over the current multi-engine baseline;
- high-fidelity Figma completion;
- live MusicXML-to-GuitarTab-Engine integration.

## 10. Current development boundary

Safe autonomous repository work may continue only where it does not cross external production effects. Any step that creates paid provider resources, real credentials, DNS/TLS changes, new public traffic beyond the authorized fixture-only Pages preview, production persistence, actual publication, or live downstream provider effects requires a separate explicit operational gate.