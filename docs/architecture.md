# ScoreMosaic Architecture

Status: **authoritative current architecture through Stage 11-F**  
Current-state contract: `contracts/architecture-current-state-v1.json`

Historical Gate B-E details remain documented in their dedicated gate documents. Current activation truth is defined by this document together with:

- `docs/architecture-stage5-7-current.md`
- `docs/architecture-stage8-current.md`
- `docs/architecture-stage9-11-current.md`

## 1. Purpose

ScoreMosaic is a security-first OMR and teacher-review platform. It receives untrusted score documents, preserves immutable source lineage, obtains bounded OMR evidence, validates engine outputs as untrusted artifacts, derives deterministic Canonical Score representations, compares evidence, and supports immutable teacher review and publication preparation.

ScoreMosaic is not the learner-facing playback, narration, or lesson application.

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

## 7. Stage status map

| Stage | Current status | Authority meaning |
|---|---|---|
| 5 | Controlled staging execution complete | Authenticated bounded private dispatch/execution exists in controlled staging; not production activation. |
| 6 | Candidate ingestion/persistence complete | Engine results can become immutable authenticated candidates; candidates are not truth. |
| 7 | Canonical/Ensemble convergence complete | Deterministic Canonical admission and neutral comparison; >=2 Canonical candidates required. |
| 8 | Teacher Review/publication preparation complete | Exact immutable review/approval/publication-handoff lineage; external publication effect locked. |
| 9 | Production foundation contracts complete | Provider architecture documented; real provisioning deferred. |
| 10 | Repository UI experience complete | Disconnected, fixture-backed, non-authoritative product UI. |
| 11 | Typed UI/application local integration complete | Typed local adapters/state model complete; live API remains locked. |

## 8. Authority invariants

1. External input and engine output remain untrusted until their applicable gates pass.
2. Source documents, raw candidates, revisions, approvals, and publication handoffs are immutable lineage artifacts.
3. AI/OMR evidence cannot directly mutate authoritative score state.
4. Canonical admission and musical validation remain deterministic and fail closed.
5. Unknown or ambiguous content is surfaced as evidence or abstention, not silently guessed.
6. Teacher approval is explicit and bound to an exact immutable revision/artifact.
7. Publication is a separate transition from approval.
8. Browser/local application state is never server authority.
9. Production activation requires a separate security gate and concrete external facts.

## 9. Current boundaries

### Repository evidence proves

- Safe Intake and Candidate Safety contracts;
- controlled-staging private dispatch/execution and candidate persistence;
- Stage 7 deterministic convergence;
- Stage 8 immutable teacher-review/publication-preparation chain;
- Stage 9 production architecture contracts;
- Stage 10 disconnected product experience;
- Stage 11 typed local UI/application integration.

### Repository evidence does not prove

- public production upload/API traffic;
- real production provider provisioning;
- production PostgreSQL/object-storage operation;
- production Authentik/Infisical runtime;
- production credentials/DNS/TLS;
- live public Teacher Review write routes;
- production publication execution;
- production browser playback;
- ST-OMR Gateway/Ensemble integration;
- ST-OMR superiority over the current multi-engine baseline.

## 10. Current development boundary

Safe autonomous repository work may continue only where it does not cross external production effects. Any step that creates paid provider resources, real credentials, DNS/TLS changes, public traffic, production persistence, or actual publication requires a separate explicit operational gate.
