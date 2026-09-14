# ScoreMosaic Architecture

Status: **authoritative current architecture through Stage 11-F plus merged unnumbered integration/research workstreams through SM-POLY-11**  
Current-state contract: `contracts/architecture-current-state-v1.json`

Current architecture truth is defined by this document together with:

- `docs/architecture-stage5-7-current.md`
- `docs/architecture-stage8-current.md`
- `docs/architecture-stage9-11-current.md`
- `docs/architecture-research-evidence-current.md`
- `docs/ui-architecture-phase1.md`
- `docs/web-preview-v1.md`
- `docs/live-ui-api-security-architecture-v1.md`
- `docs/teacher-review-api-contract-v1.md`
- `docs/teacher-review-api-harness-v1.md`
- `docs/downstream-music-application-integration-boundary.md`
- `docs/licensing-governance.md`

Historical gate/stage documents remain evidence for their original boundaries but do not override these current-state sources.

## 1. Purpose

ScoreMosaic is a security-first optical music recognition, evidence comparison and teacher-review platform. It treats external documents and OMR/model output as untrusted evidence, preserves immutable lineage, derives deterministic Canonical Score representations, supports bounded Teacher Review, and keeps approval/publication separate from inference.

Validated ScoreMosaic artifacts may later feed downstream music applications, but downstream services never become Canonical, Teacher Review, approval or publication authority.

## 2. Current trust chain

```text
untrusted PDF/image
  -> Safe Intake B.1-B.6
  -> immutable source + job binding
  -> deterministic orchestration plan
  -> controlled private staging dispatch/execution
  -> authenticated engine result identity
  -> bounded engine-specific result adapter
  -> immutable HMAC-sealed candidate persistence
  -> Candidate Safety
  -> deterministic Canonical Score admission
  -> neutral Stage 7 Ensemble comparison/report
  -> decomposed review evidence
  -> Real Score Intake binding where applicable
  -> Teacher Review / pinned Score Editor Core projection
  -> typed ScoreEditCommand authority boundary
  -> immutable TeacherScoreRevision
  -> deterministic validation
  -> corrected MusicXML derivative + semantic round-trip
  -> explicit human approval handoff/record
  -> publisher-bound non-executing publication handoff
  -> [EXTERNAL PRODUCTION EFFECT LOCKED]
```

Engine/AI output remains evidence. It cannot directly mutate authoritative musical state or grant approval/publication authority.

## 3. Stage 5-7 OMR architecture

The production-candidate engine set remains exactly:

```text
Audiveris
HOMR
Clarity
```

Stage 6 authenticates and persists bounded immutable candidates. Stage 7 requires at least two Canonical candidates before neutral comparison. Candidate order is deterministic and the comparator is read-only.

ST-OMR is **not** in the Gateway engine set or Stage 7 quorum. Any future ST-OMR-primary or ST-OMR-only migration requires a separately versioned migration with real Teacher-Gold evidence, real-world shadow benchmarking, category-stratified no-regression evidence, calibrated abstention/selective-prediction evidence, deterministic musical validation and rollback. Training success alone cannot authorize promotion.

### 3.1 Research evidence beside Stage 7

The following merged packages create a research/evaluation evidence layer without changing production convergence authority:

```text
SM-POLY-02  taxonomy + benchmark schema
  -> SM-POLY-03  Teacher-Gold registry/harness
  -> SM-POLY-04  per-engine semantic metrics
  -> SM-POLY-05  visual/BBox sidecar
  -> SM-POLY-06  source-quality profile
  -> SM-POLY-07  polyphony-complexity profile
  -> SM-POLY-08  reliability/calibration evidence
  -> SM-POLY-09  ST-OMR shadow evidence
  -> SM-POLY-11  Convergence Evidence Vector v2
```

SM-POLY-11 binds immutable evidence artifact sets beside an exact Stage 7 result SHA. It intentionally does not assert cross-artifact fixture identity, compute a single confidence score, rank engines, choose a winner, merge/correct MusicXML or alter Stage 7 quorum.

The Teacher-Gold harness is implemented, but the verified corpus is not sufficiently populated for the minimum research benchmark. Real-world ST-OMR shadow benchmarking is also incomplete. Therefore broad OMR accuracy, ST-OMR superiority and production-readiness claims remain prohibited.

The next explicitly planned research package is **SM-POLY-13**, responsible for Teacher Review workload instrumentation using `TEACHER_REVISION_COMMAND_COUNT_V1`. Package numbers for a future direct cross-artifact join or selective-prediction work are intentionally unassigned.

See `docs/architecture-research-evidence-current.md`.

## 4. Teacher Review architecture

Stage 8-A through 8-O are complete at repository/preparation level. The repository contains:

- reviewer/resource authorization foundations;
- closed typed ScoreEditCommand contracts;
- immutable TeacherScoreRevision lineage;
- deterministic review state and validation;
- corrected MusicXML derivation and semantic round-trip evidence;
- server-authorized non-network mutation foundation;
- approval-candidate evidence;
- explicit human approval handoff/record foundations;
- publication eligibility and publisher-bound non-executing handoff.

The external publication effect remains locked. Production write persistence, live approval/publication routes, published-artifact persistence and actual publication execution are not activated.

### 4.1 Real Score Intake → Score Editor Core

Real Score Intake v1/v1.1 is repository-integrated from verified Stage 7/Canonical evidence into the pinned ST Score Editor Core runtime shapes:

```text
verified Stage 7 handoff
  -> Canonical Score binding
  -> Real Score Intake v1/v1.1
  -> bounded full-score projection
  -> pinned Score Editor Core
  -> revision-bound semantic targets
  -> Teacher Review bridge
```

Chord-aware semantic targets and full-score projection are implemented. This grants no live upload, networking, production persistence, automatic correction, approval or publication authority.

### 4.2 ST-Orchestration evidence preview

H7-C provides a local non-authoritative preview for the exact `string-seat-ranking-v0` capability. H7-D advances this to an authenticated server-side staging transport with HMAC-SHA256, bounded I/O/timeouts and exact non-loopback origin pinning.

The browser receives no staging endpoint or authentication secret and has no Apply action. H7-D is evidence presentation only; Canonical Score and TeacherScoreRevision mutation remain forbidden. **H7-E is a separate human/operational gate** and requires broader reliability/generalization evidence.

## 5. UI and application boundary

Stages 10 and 11 are complete at repository/local-integration level. The current browser path remains non-authoritative:

```text
Stage 10 product UI
  -> typed Stage 11 application contract
  -> local state/correlation reducer
  -> typed local read/edit-intent adapters
  -> fixture / validated browser-safe evidence
```

`connect-src 'none'` remains the general fixture-preview browser network boundary. No browser persistence, production artifact read, server write, playback, approval or publication authority is granted by Stage 10/11.

A browser edit intent is not a ScoreEditCommand. Authority-sensitive fields are server-derived in the disconnected API security harness.

### 5.1 UI Architecture Phase 1

UI Architecture Phase 1 is an approved unnumbered workstream and **not Stage 12**. Repository design-system foundations, core components, music-domain components and product patterns exist. Low-fidelity Figma work started; high-fidelity completion remains pending. UI modernization must stay layered above typed contracts and server authority.

### 5.2 Web Preview v1

The repository has a **verified fixture-only GitHub Pages deployment** built deterministically from the Stage 10/11 UI/application layers. It is non-production, CSP-locked, contains no real user data, and does not activate live upload/API/persistence/authentication/server writes.

### 5.3 Live UI ↔ API security baseline

`docs/live-ui-api-security-architecture-v1.md` defines a future same-origin authenticated model using server-managed sessions, Authentik/OIDC, exact-origin and CSRF checks, server resource authorization, idempotency/reconciliation, audit and rollback. Runtime activation remains false.

### 5.4 Teacher Review API and security harness

`docs/teacher-review-api-contract-v1.md` defines bounded read/revision-proposal contracts without registering HTTP routes. `docs/teacher-review-api-harness-v1.md` proves the mutation composition in-process against deterministic collaborators:

```text
non-authoritative intent
  -> session/CSRF/origin/resource checks
  -> fresh durable head + snapshot
  -> server-resolved target/location/old value
  -> server authorization grant + ScoreEditCommand
  -> Stage 8-G mutation boundary
  -> immutable draft TeacherScoreRevision
  -> safe audit result
```

No live HTTP route, Authentik runtime, browser network, provider credential or production persistence is activated.

## 6. Score Discovery boundary

SD-4B adds a disconnected Score Discovery consumer. Browser-safe results strip remote asset URLs and unsafe locators. Only `direct-import + public access + HTTPS + PDF/MusicXML/MXL` can form a server-side intake handoff, and that handoff has only:

```text
authority = discovery-handoff-only
```

It must re-enter Safe Intake. Live Score Discovery Gateway networking and production import remain disabled.

## 7. Downstream music-application integration

The architecture-only downstream seam remains:

```text
approved / validated Teacher Review artifact
  -> corrected MusicXML + exact revision identity
  -> typed downstream contract
  -> dedicated adapter
  -> downstream music application
```

Raw OMR candidates are not valid production sources for downstream derivation. The first reserved service remains MusicXML-to-GuitarTab-Engine. No live Guitar TAB transport or credential is activated. See `docs/downstream-music-application-integration-boundary.md`.

## 8. Production foundation

Stage 9 production-foundation contracts document Hetzner Germany + Coolify, PostgreSQL 18, object-storage immutability/copy semantics, Authentik OIDC/RBAC, Infisical capability requirements, service identity/secret scopes and publication persistence protocol.

Real provider activation remains false:

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

Coolify private-staging preflight is repository-ready but provider connection is not performed.

## 9. Licensing and asset governance

The policy is defined by `LICENSE`, `LICENSE-SCOPE.md`, `NOTICE`, `COMMERCIAL-LICENSE.md`, `TRADEMARKS.md`, `CONTRIBUTOR-LICENSE-AGREEMENT.md`, and `docs/licensing-governance.md`.

First-party code is noncommercial source-available; third-party engines/packages/model assets keep their own licenses. Unresolved copyleft/model-asset/SBOM obligations remain independent production locks. These are **licensing activation locks** in addition to the accuracy, security and infrastructure gates.

## 10. Current status map

| Area | Status | Authority meaning |
|---|---|---|
| Stage 5 | Controlled staging complete | Bounded private execution; not production. |
| Stage 6 | Candidate persistence complete | Authenticated immutable candidates; not truth. |
| Stage 7 | Canonical/Ensemble convergence complete | >=2 Canonical candidates; neutral comparison. |
| Stage 8 | Teacher Review/publication preparation complete | External publication effect locked. |
| Stage 9 | Production foundation contracts complete | Real provisioning deferred. |
| Stage 10 | Repository UI complete | Disconnected/non-authoritative. |
| Stage 11 | Typed local application integration complete | Live API locked. |
| Real Score Intake v1/v1.1 | Repository-integrated | Verified Canonical → pinned Core; no production authority. |
| H7-C/H7-D ST-Orchestration | Local + authenticated staging evidence ready | Non-authoritative preview; H7-E locked. |
| Score Discovery SD-4B | Disconnected consumer boundary ready | Safe Intake still mandatory; live Gateway off. |
| SM-POLY-02→11 evidence chain | Research integration complete through v2 vector | No Stage 7 authority change. |
| UI Architecture Phase 1 | Repository baseline; high-fidelity pending | No live activation. |
| Web Preview v1 | Public fixture-only preview verified | No production API/data authority. |
| Teacher Review API/harness | Repository baseline complete | Routes/runtime/persistence locked. |
| Downstream music applications | Architecture-only | Live integration locked. |

## 11. Authority invariants

1. External input and engine/model output remain untrusted until applicable gates pass.
2. Source documents, candidates, revisions, approvals and publication handoffs preserve immutable lineage.
3. AI/OMR evidence cannot directly mutate authoritative score state.
4. Canonical admission and musical validation remain deterministic and fail closed.
5. Unknown or ambiguous music is surfaced or abstained, never silently guessed.
6. Teacher approval is explicit and bound to an exact immutable revision/artifact.
7. Publication is separate from approval.
8. Browser/local application state is never server authority.
9. Research evidence does not become production decision authority by implication.
10. Downstream music applications are derivative services, never upstream score authority.
11. Production activation requires a separate gate with concrete external/runtime facts.

## 12. Current evidence gaps and next development

Repository regression/integration evidence is strong, but broad musical accuracy evidence remains incomplete. Current gaps include:

- sufficiently populated verified Teacher-Gold corpus;
- Teacher Review workload/edit-cost evidence;
- real-world ST-OMR shadow benchmark coverage;
- directly validated cross-artifact identity joins;
- held-out selective-prediction/abstention evidence;
- category-stratified no-regression evidence sufficient for ST-OMR promotion;
- production provider/security/backup/restore/observability evidence.

The next evidence-first development sequence is:

```text
SM-POLY-13 Teacher Review workload instrumentation
  -> populate/qualify real Teacher-Gold corpus (>=500 minimum gate)
  -> versioned direct cross-artifact join
  -> selective prediction / abstention research
  -> versioned ST-OMR promotion decision gate
```

H7-E production orchestration, live Teacher Review API activation, provider provisioning, publication execution and downstream live-service activation remain separate human/operational gates.

## 13. Development boundary

Repository-only work may continue while authority and production locks remain intact. Explicit operational authorization is required before paid provider creation, real credential bootstrap, DNS/TLS changes, new production/public API traffic, production persistence, live downstream service effects, H7-E production inference or publication execution.
