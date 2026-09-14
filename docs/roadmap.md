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
| SM-POLY-02→11 research chain | ✅ Research evidence infrastructure through Convergence Vector v2 | No Stage 7 quorum/authority change. |
| Teacher-Gold corpus | 🟡 Harness ready, corpus not minimum-ready | >=500 eligible verified fixtures + required coverage still needed. |
| ST-OMR real-world shadow benchmark | 🟡 Contract/evidence plumbing ready, benchmark incomplete | No production promotion. |
| UI Architecture Phase 1 | ✅ Repository pre-Figma baseline | High-fidelity Figma still pending. |
| Web Preview v1 | ✅ Public fixture-only Pages preview verified | No live API, persistence, real data or production authority. |
| Live UI↔API security architecture | ✅ Repository baseline | Runtime/auth/browser network off. |
| Teacher Review API + harness | ✅ Repository baseline | HTTP routes/live identity/production persistence off. |
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
  -> research evidence chain SM-POLY-02→11
  -> [LIVE / EXTERNAL / PROMOTION GATES]
```

UI Architecture Phase 1 does not consume or reserve Stage 12 numbering. Web Preview, Live UI↔API Security, Teacher Review API/harness, Real Score Intake integration, H7-C/H7-D, Score Discovery and research packages likewise do not imply a Stage 12 assignment.

## Current research/evaluation architecture

The polyphonic OMR evidence chain currently stops at SM-POLY-11:

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
```

This is evidence infrastructure, not production decision authority. Current locks remain:

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

The last merged main change is **SM-POLY-11 — Convergence Evidence Vector v2** (`dfd8b8607607383fd1e250ce704e97af84a5101b`, 2026-08-30).

That work completed the reference-only integration of Stage 7 result identity with immutable artifact sets from semantic metrics, visual evidence, source quality, complexity, reliability and ST-OMR shadow evidence. It explicitly stopped before:

- a validated direct cross-artifact fixture/source join;
- selective-prediction or abstention thresholds;
- any ST-OMR production promotion;
- Teacher Review workload/edit-cost instrumentation.

SM-POLY-04 and SM-POLY-11 both reserve the next named research owner as **SM-POLY-13**, method `TEACHER_REVISION_COMMAND_COUNT_V1`.

There is no current repository definition for SM-POLY-10 or SM-POLY-12; missing numbers must not be guessed or retroactively assigned.

## Next development — priority order

### 1. SM-POLY-13 — Teacher Review workload instrumentation

**Recommended immediate next repository work.**

Goal: turn immutable Teacher Review history into deterministic evaluation evidence without changing Teacher Review authority.

Required scope:

- consume only validated immutable TeacherScoreRevision / ScoreEditCommand lineage;
- define exact counting semantics for `TEACHER_REVISION_COMMAND_COUNT_V1`;
- derive teacher edits per measure and per page where denominator evidence is valid;
- preserve unavailable evidence as unavailable;
- bind exact source/revision/fixture provenance;
- reject duplicate/replayed/malformed command evidence;
- populate the already-versioned SM-POLY-04 teacher-edit fields through a separately tested adapter;
- no model training side effect;
- no winner selection, automatic correction, approval or publication authority.

Acceptance evidence should include deterministic fixtures, tamper tests, duplicate/replay tests, denominator edge cases, revision-lineage mismatch tests and dedicated CI.

### 2. Populate and qualify real Teacher-Gold evidence

Goal: move SM-POLY-03 from a correct empty/not-ready harness to a useful research benchmark.

Minimum gate remains:

```text
>= 500 eligible verified fixtures
+ required notation-category coverage
+ required scan-quality coverage
+ verified provenance/license eligibility
```

Target remains 1000. No synthetic/private/unverified item may be counted as verified merely to cross a threshold.

Priority corpus coverage should include polyphonic piano/keyboard, guitar notation where relevant, multi-voice rhythm, ties, tuplets, dotted rhythms, chords, staff/voice ambiguity, degraded scans and representative clean digital scores.

### 3. Versioned direct cross-artifact join

Goal: replace SM-POLY-11’s intentionally opaque artifact-set context with a new versioned evidence binding that proves exact identity relationships where they actually exist.

Required:

- exact fixture/source/page/measure/engine/Teacher-Gold identities as applicable;
- upstream payload validation, not SHA-label inference;
- explicit one-to-one/one-to-many semantics;
- duplicate/conflicting identity rejection;
- no reinterpretation of SM-POLY-11 v2 semantics;
- package number remains **unassigned** until its own contract/PR is created.

### 4. Selective prediction / abstention research

Goal: determine whether reliability, source quality, complexity and semantic evidence can support safe abstention.

Required before any threshold has operational meaning:

- held-out Teacher-Gold evidence;
- category/scan/complexity stratification;
- coverage-risk curves;
- calibration error and failure-mode analysis;
- explicit false-confidence penalties;
- conservative abstention behavior;
- no production threshold until a separate authorization gate.

The package number is intentionally unassigned.

### 5. Versioned ST-OMR promotion decision gate

Only after Steps 1-4 and sufficient real-world evidence should ScoreMosaic consider changing the Stage 7 engine contract.

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
