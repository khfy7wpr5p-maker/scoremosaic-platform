# ScoreMosaic Roadmap

Current architecture state contract: `contracts/architecture-current-state-v1.json`

Every capability is gated. Code presence, model accuracy, a successful UI demo, a completed Figma prototype or a green local test never grants broader production authority by implication.

## Current secure-development status

| Area | Status | Security meaning |
|---|---|---|
| Safe Intake B.1-B.6 | ✅ Complete foundation | Untrusted PDF/JPEG/PNG intake is fail-closed before later processing. |
| Controlled staging dispatch/execution — Stage 5 | ✅ Complete | Authenticated bounded private staging dispatch/execution exists; production/public activation does not. |
| Candidate ingestion/persistence — Stage 6 | ✅ Complete | Audiveris/HOMR/Clarity candidates are authenticated, bounded and immutable; candidates are not truth. |
| Canonical/Ensemble convergence — Stage 7 | ✅ Complete | Deterministic Canonical admission + neutral comparison; >=2 Canonical candidates required. |
| Teacher Review/publication preparation — Stage 8 | ✅ Complete repository scope | Immutable revision/validation/approval/publication-handoff lineage exists; external publication execution locked. |
| Production foundation — Stage 9 | ✅ Complete repository scope | Hetzner/Coolify/PostgreSQL/Object Storage/Auth/RBAC/Secrets architecture documented; real provisioning deferred. |
| Product UI experience — Stage 10 | ✅ Complete repository scope | Disconnected fixture-backed product UI; no production backend authority. |
| Typed UI/application integration — Stage 11 | ✅ Complete repository scope | Closed typed reads/edit-intent/state model/local integration; live API locked. |
| UI Architecture Phase 1 | ✅ Repository pre-Figma baseline complete | Unnumbered product-design workstream; Figma application/high-fidelity still pending. |
| Web Preview v1 | ✅ Repository build ready | Deterministic fixture-only static preview artifact can be built/downloaded from CI; public deployment remains locked. |
| Live UI↔API Security Architecture | ✅ Complete repository baseline | OIDC/session, server authorization, CSRF/origin/CSP, idempotency, audit and rollback contracts complete; runtime off. |
| Teacher Review API Contract v1 | ✅ Complete repository baseline | Exact read + bounded revision-proposal API contracts bridge browser intent to Stage 8 authority; no routes registered. |
| Downstream Music Application Integration | 🟡 Architecture-only seam | Validated/approved MusicXML may later feed bounded derivative services; GuitarTab live integration off. |
| ST-OMR architecture/development track | 🟡 Isolated | Not in Gateway/Stage 7 quorum; no production authority. |
| Production infrastructure | 🔒 Not activated | No paid/provider resources, production DB/object store, credentials, DNS/TLS or public traffic activated by repo stages. |
| Public Web Preview | 🔒 Not activated | No GitHub Pages/Netlify/Coolify Preview URL or public traffic is created by the repository preview build. |
| Live Teacher Review API | 🔒 Not activated | Security/API contracts exist, but HTTP routes, live auth, browser network and production persistence remain gated. |
| Publication execution | 🔒 Not activated | Stage 8-O stops at non-executing publisher-bound handoff. |
| Playback | 🔒 Not activated | Review timeline/presentation state exists; no real audio/MIDI/SoundFont runtime. |

## Current architecture sequence

```text
Safe Intake
  -> Stage 5 controlled execution
  -> Stage 6 candidate persistence
  -> Stage 7 Canonical + Ensemble evidence
  -> Stage 8 immutable Teacher Review + approval/publication preparation
  -> Stage 9 production architecture contracts
  -> Stage 10 disconnected product UI
  -> Stage 11 typed local UI/application integration
  -> UI Architecture Phase 1  [unnumbered]
  -> Web Preview v1 build  [unnumbered, repository only]
  -> Live UI↔API Security Architecture  [unnumbered, repository only]
  -> Teacher Review API Contract v1  [unnumbered, repository only]
  -> High-fidelity Figma / prototype
  -> [LIVE/EXTERNAL GATES]
```

UI Architecture Phase 1 does not consume or reserve Stage 12 numbering. Web Preview v1, Live UI↔API Security and Teacher Review API are likewise unnumbered and do not imply a Stage 12 assignment.

## Approved repository workstream — UI Architecture Phase 1

Goal: finish the complete product/UI architecture before high-fidelity Figma.

Repository-side architecture is complete through brand rules, Design System foundations, core components, music-domain components and product interaction patterns. Figma application and high-fidelity work remain separate.

Fixed UI boundaries:

- browser is not authority;
- renderer is not musical truth;
- local edit intent is not ScoreEditCommand;
- validation pass is not approval;
- save/edit is not approval;
- approval is not publication;
- real upload/auth/server write/playback/publication remain locked;
- future visual modernization starts in Figma/Design System/UI before changing lower authority layers.

## Completed repository preview build — Web Preview v1

Goal: make the current Stage 10/11 disconnected product UI inspectable as one deterministic browser-ready static artifact without activating public hosting or backend behavior.

Safe build path:

```text
Stage 10 UI + fixture
  + Stage 11 local typed application scripts
  -> deterministic preview builder
  -> visible NON-PRODUCTION / FIXTURE DATA marker
  -> CSP-locked standalone static files
  -> CI security regressions
  -> downloadable Actions artifact
  -> [PUBLIC PREVIEW DEPLOYMENT LOCKED]
```

The preview retains `connect-src 'none'`, contains no browser persistence/network API, and cannot upload, authenticate, create ScoreEditCommand/TeacherScoreRevision, approve, publish, or persist production state.

GitHub Pages, Netlify, Coolify Preview, public URL assignment and public traffic require a separate operational gate.

## Completed repository security baseline — Live UI↔API Security

Goal: define how the completed Stage 10/11 UI contract model may later connect to real server data without giving the browser authority.

Repository baseline now defines:

- Authentik OIDC/OAuth2 Authorization Code + PKCE target model;
- state/nonce/redirect/issuer/audience/signature/token validation requirements;
- server-managed session boundary with provider tokens excluded from application JavaScript;
- tenant/resource authorization on every protected request;
- exact versioned `/api/v1` read mappings;
- CSRF/origin/CORS requirements;
- current `connect-src 'none'` and future maximum same-origin `connect-src 'self'` transition rule;
- exact-current revision and server-resolved old-value mutation guards;
- idempotency/reconciliation rules;
- privacy-safe errors/audit evidence;
- rate-limit and rollback/kill-switch requirements.

Activation effect: none. HTTP/runtime/auth/browser-network/production flags remain false.

## Completed repository API baseline — Teacher Review API Contract v1

Goal: define the public API seam without exposing Stage 8-G internal authority envelopes to the browser.

Safe request path:

```text
browser non-authoritative intent
  -> session / CSRF / exact-origin gate
  -> server resource authorization
  -> fresh durable-head + snapshot check
  -> server stable-target and old-value resolution
  -> server authorization grant + command identity
  -> internal Stage 8-G write envelope
  -> immutable draft TeacherScoreRevision
  -> bounded public result
```

The public v1 mutation surface reserves only:

```text
POST /api/v1/documents/{document_id}/revision-proposals
```

The first browser operation surface remains the four Stage 11 operations:

```text
set_pitch
set_effective_duration
set_dots
remove_event
```

Stage 8's broader internal closed vocabulary is not implicitly exposed.

No approval/publication endpoints are defined here. No HTTP route is registered and no live network/server write/production persistence is activated.

## Approved architecture-only extension — downstream music applications

Goal: preserve a safe seam for future sibling music applications without coupling them into OMR or Teacher Review authority.

Safe sequence:

```text
approved / validated Teacher Review artifact
  -> exact corrected MusicXML hash + revision identity
  -> typed downstream application contract
  -> dedicated adapter
  -> downstream application
```

First reserved target: `MusicXML-to-GuitarTab-Engine`.

Its future role is guitar arrangement/fingering derivation. It must not consume raw OMR candidates for production output, mutate Canonical Score, create TeacherScoreRevision, approve, publish or be called directly by the browser.

## Next safe workstreams

### A. Architecture consistency and governance

Goal: keep machine-readable architecture state, current docs and CI synchronized.

Required:

- architecture-current-state contract;
- cross-document consistency tests;
- stale/current document classification;
- UI/preview/security/API/downstream integration drift guards;
- no current document may overclaim production activation.

Activation effect: none.

### B. ST-OMR specialist training and evaluation

Goal: improve ScoreMosaic-native OMR without weakening current Stage 7 safety.

Safe sequence:

```text
specialist training
  -> fixed validation
  -> untouched final evaluation
  -> end-to-end semantic evaluation
  -> ST-OMR shadow integration contract
  -> shadow runtime evidence
  -> optional primary promotion
  -> optional sole-OMR migration
```

Required before any ST-OMR production promotion:

- exact model/dataset provenance;
- teacher-gold evaluation;
- notation-category and scan-quality stratification;
- document-level MusicXML semantic correctness;
- meter/rhythm/pitch/voice/structure exactness;
- calibrated abstention/uncertainty;
- deterministic Duration/Meter/Pitch/Voice validation;
- adversarial/corrupt input tests;
- rollback and previous-model retention;
- no-regression evidence against current baseline.

Current Audiveris/HOMR/Clarity production-candidate contracts remain unchanged until a versioned migration passes these gates.

### C. Disconnected authenticated-API adapter / security test harness

Goal: implement the security/API contracts against deterministic non-production collaborators without enabling browser networking or production identity/persistence.

Required before any live runtime activation:

- contract-faithful request/response adapter;
- server-side principal/resource-scope test doubles only;
- CSRF/origin/idempotency/stale-parent negative tests;
- server construction of ScoreEditCommand from non-authoritative intent;
- exact Stage 8-G boundary composition;
- reconciliation behavior for ambiguous mutations;
- safe error/audit mapping;
- no HTTP listener/public route;
- no provider credentials or production persistence.

Activation effect: none.

### D. External production provisioning

Goal: instantiate the Stage 9 design with real provider evidence.

Human/external inputs required before this work can cross the boundary:

- Hetzner project/account and spend authority;
- final compute sizing after ST-OMR inference benchmark;
- production domain decision before public traffic;
- real PostgreSQL/Object Storage resources;
- Authentik deployment;
- Infisical capability/license decision;
- real machine identities/secrets;
- monitoring/rollback/backup/restore evidence.

No repository contract may invent these facts.

### E. Production Teacher Review activation

Goal: wire Stage 8 server-side revision/approval foundations to an authenticated production UI/API.

Requires C + D plus:

- real production session/RBAC evidence;
- production durable exact-parent revision persistence;
- authorized read/write resource scope;
- corrected MusicXML production artifact persistence;
- human approval persistence;
- operational audit trail;
- failure/recovery and anti-rollback evidence.

### F. Publication execution

Goal: execute Stage 8-O publisher-bound handoff against one exact authorized destination.

Requires:

- exact publisher identity/destination;
- explicit publication execution authority;
- provider credentials;
- production persistence semantics;
- published-artifact/audit record;
- replay/idempotency/recovery evidence.

Publication remains a separate side effect from approval.

### G. Live downstream music-application integration

Goal: connect one exact approved/validated ScoreMosaic artifact to a separately authorized downstream service.

Requires:

- versioned typed request/response contract;
- exact source revision + corrected MusicXML hash binding;
- service authentication/authorization;
- timeout/retry/idempotency/failure isolation;
- deterministic or version-bound result provenance;
- stale-source invalidation;
- audit evidence;
- rollback/disable boundary.

For MusicXML-to-GuitarTab-Engine, tuning/fret/capo/instrument context and guitar playability/alternative/abstention evidence must also be explicit.

## Fixed architectural principles

1. AI and OMR output are evidence, not authoritative musical truth.
2. Deterministic validation/composition owns final structural decisions wherever possible.
3. Source/candidate/revision/approval/publication artifacts remain immutable lineage.
4. Unknown/ambiguous music is surfaced or abstained, never silently guessed.
5. Browser state is not server authority.
6. Teacher approval is explicit and exact-identity bound.
7. Publication is separate from approval.
8. Production activation requires concrete provider/runtime evidence and a dedicated gate.
9. ST-OMR training success alone never authorizes removal of the current OMR engines.
10. UI modernization must preserve typed-contract/adapter/server authority layering.
11. Downstream music applications never become upstream ScoreMosaic musical authority.

## Current stop boundaries

Repository-only work may continue while all live/production activation locks remain false. Stop for explicit operational authority before:

- paid resource creation;
- real credential generation/bootstrap;
- DNS/TLS changes;
- public preview/site traffic;
- production data writes;
- production publication execution;
- live downstream music-service activation;
- destructive provider operations.
