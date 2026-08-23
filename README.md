# ScoreMosaic Platform

ScoreMosaic is a security-first optical music recognition and teacher-review platform. It treats external documents and OMR outputs as untrusted evidence, preserves immutable lineage, derives deterministic Canonical Score representations, supports bounded teacher correction, and separates human approval from publication.

Current architecture state contract: `contracts/architecture-current-state-v1.json`

## Current status

ScoreMosaic is in controlled development through **Stage 11-F**.

```text
Stage 5   ✅ controlled-staging private dispatch/execution
Stage 6   ✅ authenticated candidate ingestion/persistence
Stage 7   ✅ Canonical + Ensemble convergence
Stage 8   ✅ repository Teacher Review / approval / publication preparation
Stage 9   ✅ repository production-foundation contracts
Stage 10  ✅ disconnected product UI experience
Stage 11  ✅ typed local UI/application integration
```

Approved unnumbered workstreams now sit after Stage 11 without consuming Stage 12 numbering:

```text
UI Architecture Phase 1                 ✅ repository baseline; Figma next
Web Preview v1                          ✅ public fixture-only GitHub Pages preview
Downstream Music Application Integration 🟡 architecture-only seam
```

These completions do **not** mean production activation.

The following remain locked:

- public production upload/API traffic;
- production Hetzner resources and private network;
- production PostgreSQL and object storage;
- production Authentik/Infisical runtime;
- production credentials, DNS/TLS and production public visibility;
- live Teacher Review write API;
- production approval persistence;
- actual publication execution;
- production playback;
- ST-OMR Gateway/Stage 7 integration;
- live MusicXML-to-GuitarTab-Engine integration.

The public Web Preview is a separate, CSP-locked fixture deployment. It does not activate upload, browser API networking, persistence, real user data or any production authority.

Repository tests establish deterministic behavior and security boundaries, not broad OMR accuracy. The fixed current-engine dataset is one deliberately small score case and the ST-OMR evaluation uses three synthetic fixtures; teacher-gold and real-world shadow evidence are still required. The project is therefore not production-ready.

## Current secure flow

```text
untrusted PDF/image
  -> Safe Intake B.1-B.6
  -> immutable source + job binding
  -> controlled-staging authenticated execution
  -> authenticated immutable engine candidates
  -> Candidate Safety
  -> deterministic Canonical Score
  -> neutral Ensemble comparison/evidence
  -> immutable Teacher Review revisions
  -> deterministic validation + corrected MusicXML
  -> explicit human approval
  -> publisher-bound non-executing handoff
  -> [EXTERNAL PUBLICATION EFFECT LOCKED]
```

AI/OMR output never directly mutates authoritative musical state.

## Current OMR engines

The authoritative Stage 7 v1 candidate-engine set remains:

- Audiveris
- HOMR
- Clarity

At least two Canonical candidates are required for Stage 7 comparison.

ST-OMR is an isolated architecture/development track and is not currently in the Gateway or Stage 7 quorum. A future ST-OMR-primary or ST-OMR-only migration must be versioned and evidence-gated; model training success alone does not authorize removing the current engines.

## Teacher Review and UI

Stage 8-A through 8-O provide repository foundations for exact reviewer authorization, typed ScoreEditCommand, immutable TeacherScoreRevision, deterministic validation, corrected MusicXML, explicit human approval and non-executing publication handoff.

Stage 10/11 add a disconnected product/UI layer:

```text
Stage 10 UI
  -> Stage 11 typed local application contract
  -> fail-closed state/correlation
  -> typed local read/edit-intent adapters
  -> checked-in non-production fixture
```

The browser is non-authoritative. A local edit intent is not a ScoreEditCommand.

`UI Architecture Phase 1` now defines the complete pre-Figma product architecture:

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

It is an approved unnumbered workstream, not Stage 12.

## Downstream music applications

ScoreMosaic reserves a safe downstream seam for future music applications after validated Teacher Review artifacts.

```text
validated / approved MusicXML
  -> typed downstream application contract
  -> dedicated adapter
  -> downstream music service
```

The first reserved target is `MusicXML-to-GuitarTab-Engine`. It is a derivative guitar arrangement/fingering service, not an OMR or score-authority service. Raw OMR candidates are not valid production inputs; the browser cannot call the engine directly; live integration is not activated.

## Production foundation

Stage 9 documents the planned production topology, including Hetzner Germany + Coolify, PostgreSQL 18, object-storage immutability/copy semantics, Authentik OIDC/RBAC and Infisical capability requirements.

No real provider resource or production credential is activated by those contracts.

## Core principles

1. External input and engine output are untrusted until validated.
2. Source documents, raw candidates and teacher revisions remain immutable.
3. AI/OMR evidence does not grant musical authority.
4. Deterministic composition/validation is preferred for musical structure.
5. Ambiguity is surfaced or abstained, not silently guessed.
6. Teacher approval is explicit and exact-identity bound.
7. Publication is a separate side effect from approval.
8. Browser/local application state is not server authority.
9. UI modernization preserves Design System → UI → Contract → Adapter → Server layering.
10. Downstream music applications do not mutate upstream ScoreMosaic musical authority.
11. Production activation requires a separate security gate and concrete operational facts.

## Architecture documents

Current architecture:

- `docs/architecture.md`
- `docs/architecture-stage5-7-current.md`
- `docs/architecture-stage8-current.md`
- `docs/architecture-stage9-11-current.md`
- `docs/ui-architecture-phase1.md`
- `docs/downstream-music-application-integration-boundary.md`
- `docs/licensing-governance.md`
- `docs/st-omr-architecture-contract-v1.md`
- `docs/teacher-review-score-editor-architecture-contract.md`
- `docs/roadmap.md`

Historical gate/stage documents remain evidence for the boundary they originally established and should not be read as newer activation-state overrides.

## Development workflow

- Source control: GitHub
- Automated verification: GitHub Actions
- Integration target: controlled/private staging
- Production: blocked until external provisioning and production-readiness gates pass

## Licensing

ScoreMosaic is **source-available, not OSI open source**. First-party software
is available for permitted noncommercial purposes under the
[PolyForm Noncommercial License 1.0.0](LICENSE). Commercial use requires a
separate signed written agreement; see [COMMERCIAL-LICENSE.md](COMMERCIAL-LICENSE.md).

First-party documentation and identified repository-owned synthetic test/model
assets use CC BY-NC 4.0. Third-party engines, packages, model assets and other
materials retain their own terms and are not relicensed by ScoreMosaic. Some
current OMR components are AGPL/GPL or have unresolved model licensing, so
commercial production/redistribution remains blocked until the exact deployment
passes the dependency-license gate.

See [LICENSE-SCOPE.md](LICENSE-SCOPE.md), [NOTICE](NOTICE),
[TRADEMARKS.md](TRADEMARKS.md), and [CONTRIBUTING.md](CONTRIBUTING.md) for the
complete repository policy.
