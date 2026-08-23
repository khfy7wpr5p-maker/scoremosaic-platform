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
| UI Architecture Phase 1 | ✅ Approved repository baseline in progress | Unnumbered product-design workstream; no live activation; Figma follows green baseline. |
| Downstream Music Application Integration | 🟡 Architecture-only seam | Validated/approved MusicXML may later feed bounded derivative services; GuitarTab live integration off. |
| ST-OMR architecture/development track | 🟡 Isolated | Not in Gateway/Stage 7 quorum; no production authority. |
| Production infrastructure | 🔒 Not activated | No paid/provider resources, production DB/object store, credentials, DNS/TLS or public traffic activated by repo stages. |
| Live Teacher Review API | 🔒 Not activated | Stage 8 server foundations exist, but public/live UI↔server transport and production persistence remain gated. |
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
  -> High-fidelity Figma / prototype
  -> [LIVE/EXTERNAL GATES]
```

UI Architecture Phase 1 does not consume or reserve Stage 12 numbering.

## Immediate approved workstream — UI Architecture Phase 1

Goal: finish the complete product/UI architecture before high-fidelity Figma.

Required sequence:

```text
1. Product navigation
2. Dashboard / Documents
3. New Document + Upload/OMR processing presentation
4. Teacher Review Workspace v1
5. Score Viewer interaction architecture
6. Structured Edit architecture
7. Validation / Revision architecture
8. Approval / Publication UX
9. Design System architecture
10. High-fidelity Figma
11. Clickable prototype
12. Design Freeze v1
```

Repository architecture work covers items 1-9 first. Figma begins only after the Phase 1 architecture contract and compatibility tests are green.

Fixed UI boundaries:

- browser is not authority;
- renderer is not musical truth;
- local edit intent is not ScoreEditCommand;
- validation pass is not approval;
- save/edit is not approval;
- approval is not publication;
- real upload/auth/server write/playback/publication remain locked;
- future visual modernization starts in Figma/Design System/UI before changing lower authority layers.

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
- UI Phase 1 and downstream integration drift guards;
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

### C. Live UI↔API security design

Goal: connect the completed Stage 10/11 UI contract model and approved Phase 1 product architecture to real server data without giving the browser authority.

Required before activation:

- authenticated principal/session semantics;
- tenant/resource RBAC;
- exact versioned endpoints;
- origin/CSRF/production CSP policy;
- exact-current revision + old-value checks;
- idempotency/failure/retry semantics;
- privacy-safe errors/logs;
- append-only audit evidence;
- rollback/kill switch;
- production credential handling.

Activation effect: none until a separate reviewed runtime gate.

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
- public traffic;
- production data writes;
- production publication execution;
- live downstream music-service activation;
- destructive provider operations.
