# ScoreMosaic Roadmap

Current architecture state contract: `contracts/architecture-current-state-v1.json`  
Current research/evaluation addendum: `docs/architecture-research-evidence-current.md`

Every capability is gated. Code presence, model accuracy, a green test, a successful UI demo or a staging transport does not grant broader authority by implication.

## Current secure-development status

| Area | Status | Security / authority meaning |
|---|---|---|
| Safe Intake B.1-B.6 | ✅ Complete foundation | Untrusted PDF/JPEG/PNG input is fail-closed before later processing. |
| Stage 5 controlled staging | ✅ Complete | Authenticated bounded private dispatch/execution; not production/public activation. |
| Stage 6 candidate persistence | ✅ Complete | Audiveris/HOMR/Clarity candidates are authenticated and immutable; candidates are not truth. |
| Stage 7 Canonical/Ensemble | ✅ Complete | Deterministic Canonical admission and neutral comparison; >=2 Canonical candidates required. |
| Stage 8 Teacher Review | ✅ Repository scope complete | Immutable revision/validation/approval/publication-handoff lineage; publication execution locked. |
| Stage 9 production foundation | ✅ Repository scope complete | Provider/security/storage architecture documented; real provisioning deferred. |
| Stage 10 product UI | ✅ Repository scope complete | Disconnected fixture-backed product UI. |
| Stage 11 typed application layer | ✅ Repository scope complete | Typed local reads/edit intents/state; live API locked. |
| Real Score Intake v1/v1.1 | ✅ Repository integration complete | Verified Stage 7/Canonical evidence projects into pinned Score Editor Core; no production persistence/automatic correction. |
| ST-Orchestration H7-C | ✅ Local preview integration | Non-authoritative `string-seat-ranking-v0` evidence only. |
| ST-Orchestration H7-D | ✅ Authenticated staging integration | Server-side authenticated staging evidence; production/H7-E disabled. |
| Score Discovery SD-4B | ✅ Disconnected consumer boundary | Eligible handoff is `discovery-handoff-only`; Safe Intake still required; live Gateway off. |
| SM-POLY-02→13 research chain | ✅ Research evidence infrastructure through Teacher Review workload evidence | No Stage 7 quorum/authority change. |
| SM-POLY-13 Teacher workload | ✅ Repository evidence package | `TEACHER_REVISION_COMMAND_COUNT_V1`; read-only exact revision/command lineage; page evidence may remain unavailable. |
| Teacher-Gold corpus | 🟡 Harness ready, corpus not minimum-ready | >=500 eligible verified fixtures + required coverage still needed. |
| ST-OMR real-world shadow benchmark | 🟡 Contract/evidence plumbing ready, benchmark incomplete | No production promotion. |
| UI Architecture Phase 1 | ✅ Repository pre-Figma baseline | High-fidelity Figma still pending. |
| Web Preview v1 | ✅ Public fixture-only Pages preview verified | No live API, persistence, real data or production authority. |
| Live UI↔API security architecture | ✅ Repository baseline | Runtime/auth/browser network off. |
| Teacher Review API Security Harness v1 | ✅ Repository baseline | HTTP routes/live identity/production persistence off. |
| Downstream Music Application Integration | 🟡 Architecture-only | Guitar TAB live integration off. |
| Production infrastructure | 🔒 Not activated | No provider resources/production DB/object store/credentials/DNS/TLS/public API. |
| Publication execution | 🔒 Not activated | Stage 8 stops at non-executing handoff. |
| Playback | 🔒 Not activated | No production audio/MIDI runtime. |

## Current architecture sequence

```text
Safe Intake
  -> Stage 5 controlled execution
  -> Stage 6 candidate persistence
  -> Stage 7 Canonical + Ensemble
  -> Real Score Intake where applicable
  -> Stage 8 Teacher Review + validation + approval/publication preparation
  -> Stage 9 production architecture contracts
  -> Stage 10 disconnected product UI
  -> Stage 11 typed local application integration
  -> unnumbered UI/API/security/integration workstreams
  -> research evidence chain SM-POLY-02→13
  -> [LIVE / EXTERNAL / PROMOTION GATES]
```

UI Architecture Phase 1 does not consume or reserve Stage 12 numbering. Web Preview, Live UI↔API Security, Teacher Review API/harness, Real Score Intake integration, H7-C/H7-D, Score Discovery and research packages likewise do not imply a Stage 12 assignment.

## Current research/evaluation architecture

The polyphonic OMR evidence chain now includes SM-POLY-13:

```text
SM-POLY-02 taxonomy + benchmark schema
  -> SM-POLY-03 Teacher-Gold registry/harness
  -> SM-POLY-04 per-engine semantic metrics
  -> SM-POLY-05 visual/BBox evidence
  -> SM-POLY-06 source-quality evidence
  -> SM-POLY-07 polyphony-complexity evidence
  -> SM-POLY-08 reliability/calibration evidence
  -> SM-POLY-09 ST-OMR shadow evidence
  -> SM-POLY-11 Convergence Evidence Vector v2
  -> SM-POLY-13 Teacher Review workload evidence
```

SM-POLY-13 implements `TEACHER_REVISION_COMMAND_COUNT_V1` as a read-only research derivation from exact immutable TeacherScoreRevision/ScoreEditCommand lineage. One validated revision-command pair is one edit. Duplicate/replayed/tampered or scope-mismatched evidence fails closed. Measure denominators must be bound to the edited Canonical SHA; page denominators are never guessed.

This remains evidence infrastructure, not production decision authority. Current locks remain:

```text
production engines = audiveris / homr / clarity
stage7 minimum Canonical candidates = 2
stOmrIntegratedIntoGateway = false
teacherGoldEvaluationComplete = false
realWorldShadowBenchmarkComplete = false
directCrossArtifactJoinValidated = false
selectivePredictionAuthorized = false
```

No repository evidence supports an aggregate winner score or automatic MusicXML merge/correction.

## Where development stopped

The verified main baseline before the SM-POLY-13 branch is the architecture-sync merge `b26e6c512edc88f9215bfe1b97199d309adf9f7c` (2026-09-14). The current repository package advances the research layer through **SM-POLY-13 — Teacher Review Workload Evidence** without changing production authority.

SM-POLY-13 now supplies:

- versioned workload evidence contract;
- exact revision and audit hash validation;
- exact command hash validation through the existing Stage 8 validator;
- complete parent/audit lineage checks;
- duplicate/replay and unreferenced-command rejection;
- exact rational edits/measure;
- edits/page only when explicit page denominator evidence exists;
- a separately tested SM-POLY-04 projection adapter;
- dedicated CI and authority regression coverage.

There is no current repository definition for SM-POLY-10 or SM-POLY-12; missing numbers must not be guessed or retroactively assigned.

## Next development — priority order

### 1. POPULATE_AND_QUALIFY_REAL_TEACHER_GOLD_EVIDENCE

**Recommended immediate next repository/evaluation work after SM-POLY-13.**

Goal: move SM-POLY-03 from a correct harness-only/NOT_READY state to a useful real benchmark without weakening provenance or licensing rules.

Minimum gate remains:

```text
>= 500 eligible verified fixtures
+ required notation-category coverage
+ required scan-quality coverage
+ verified provenance/license eligibility
```

Target remains 1000. No synthetic/private/unverified item may be counted as verified merely to cross a threshold.

Priority corpus coverage should include polyphonic piano/keyboard, guitar notation where relevant, multi-voice rhythm, ties, tuplets, dotted rhythms, chords, staff/voice ambiguity, degraded scans and representative clean digital scores.

SM-POLY-13 workload evidence should be attached only where exact Teacher Review lineage and exact Canonical/fixture bindings are provable. Missing teacher/page evidence remains unavailable.

### 2. Versioned direct cross-artifact join

Goal: replace SM-POLY-11’s intentionally opaque artifact-set context with a new versioned evidence binding that proves exact identity relationships where they actually exist.

Required:

- exact fixture/source/page/measure/engine/Teacher-Gold identities as applicable;
- upstream payload validation, not SHA-label inference;
- explicit one-to-one/one-to-many semantics;
- duplicate/conflicting identity rejection;
- include SM-POLY-13 workload only when exact Canonical/fixture lineage is proven;
- no reinterpretation of SM-POLY-11 v2 semantics;
- package number remains **unassigned** until its own contract/PR is created.

### 3. Selective prediction / abstention research

Goal: determine whether reliability, source quality, complexity, semantic and teacher-workload evidence can support safe abstention.

Required before any threshold has operational meaning:

- held-out Teacher-Gold evidence;
- category/scan/complexity stratification;
- coverage-risk curves;
- calibration error and failure-mode analysis;
- explicit false-confidence penalties;
- conservative abstention behavior;
- no production threshold until a separate authorization gate.

The package number is intentionally unassigned.

### 4. Versioned ST-OMR promotion decision gate

Only after the preceding evidence gates and sufficient real-world evidence should ScoreMosaic consider changing the Stage 7 engine contract.

Required evidence:

- exact model/dataset/training provenance;
- minimum-ready Teacher-Gold benchmark;
- real-world shadow evaluation;
- category-stratified no-regression evidence against current engines;
- document-level MusicXML semantic correctness;
- meter/rhythm/pitch/voice/structure validation;
- calibrated abstention;
- adversarial/corrupt-input behavior;
- rollback and previous-model retention.

Promotion must be a versioned migration. Existing Audiveris/HOMR/Clarity authority cannot disappear by implication.

## Parallel but separate gates

### C. Disconnected authenticated-API adapter / security test harness — ✅ complete repository baseline

**Teacher Review API Security Harness v1** is complete at repository baseline and remains disconnected from live HTTP, production identity and production persistence. The next infrastructure step is D and requires external operational authority.

### H7-E — production orchestration

H7-D staging success does not authorize H7-E. H7-E requires a separate human gate, broader reliability/generalization evidence, production deployment provenance, secrets, replay control, monitoring and rollback.

### External production provisioning

Provider activation requires explicit operational authority for Hetzner/Coolify resources, production PostgreSQL/object storage, Authentik, secrets, DNS/TLS, monitoring, backup/restore and spend.

### Production Teacher Review activation

Requires real identity/session/RBAC, durable exact-parent revision persistence, authorized read/write scope, artifact persistence, audit/recovery and anti-rollback evidence. The repository API harness alone is not production activation.

### Publication execution

Requires exact publisher destination, credentials, idempotency/recovery, published-artifact persistence and explicit execution authority. Approval and publication remain separate transitions.

### Live downstream music application integration

Requires versioned request/response contracts, exact approved source revision and corrected MusicXML hash binding, service authentication, timeout/retry/idempotency/failure isolation, stale-source invalidation, provenance and rollback/disable behavior.

MusicXML-to-GuitarTab-Engine must additionally carry tuning/fret/capo/instrument context and playability/alternative/abstention evidence.

### Live Score Discovery networking/import

SD-4B is disconnected. Any live Gateway call/import must preserve server-side sanitization, `discovery-handoff-only` authority, mandatory Safe Intake and rollback/disable behavior.

## Fixed architectural principles

1. AI/OMR/model output is evidence, not authoritative musical truth.
2. Deterministic validation owns structural admission wherever possible.
3. Source/candidate/revision/approval/publication artifacts preserve immutable lineage.
4. Unknown/ambiguous music is surfaced or abstained, never silently guessed.
5. Browser state is not server authority.
6. Teacher approval is explicit and exact-identity bound.
7. Publication is separate from approval.
8. Research evidence is not production authority.
9. ST-OMR training success alone never authorizes removal of current engines.
10. Downstream applications never become upstream score authority.
11. Production activation requires concrete provider/runtime evidence and a dedicated gate.

## Current stop boundaries

Repository-only work may continue while authority locks remain intact. Stop for explicit operational authorization before:

- paid provider resource creation;
- real production credential/bootstrap operations;
- DNS/TLS changes;
- production/public API traffic beyond the verified fixture-only preview;
- production data writes;
- H7-E production inference;
- production publication execution;
- live downstream music-service activation;
- live Score Discovery import/network activation;
- destructive provider operations.
