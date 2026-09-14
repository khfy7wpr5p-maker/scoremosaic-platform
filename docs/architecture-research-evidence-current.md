# ScoreMosaic Research Evidence — Current Architecture

Status: **authoritative research/evaluation addendum; no production authority change**  
Current architecture state contract: `contracts/architecture-current-state-v1.json`  
As of repository main: `dfd8b8607607383fd1e250ce704e97af84a5101b` (2026-08-30)

This addendum records repository work merged after the Stage 5-11 architecture baseline that materially changes research/evaluation capability or safe integration seams without changing Stage 7 production authority, Teacher Review authority, or production activation.

## 1. Authority baseline remains unchanged

The Stage 7 production-candidate engine set is still:

```text
audiveris
homr
clarity
```

At least two Canonical candidates are still required for Stage 7 comparison. ST-OMR is not a Gateway engine and does not contribute to Stage 7 quorum. No research package ranks engines, selects a winner, automatically merges/corrects MusicXML, mutates TeacherScoreRevision, approves, publishes, or grants production authority.

## 2. Polyphonic OMR research evidence chain

The merged research chain is:

```text
SM-POLY-02  polyphonic taxonomy + Teacher-Gold fixture schema
  -> SM-POLY-03  deterministic Teacher-Gold registry/harness
  -> SM-POLY-04  per-engine semantic metrics
  -> SM-POLY-05  visual/BBox evidence sidecar
  -> SM-POLY-06  source-quality evidence profile
  -> SM-POLY-07  polyphony-complexity evidence profile
  -> SM-POLY-08  engine reliability/calibration evidence
  -> SM-POLY-09  ST-OMR shadow evidence
  -> SM-POLY-11  Convergence Evidence Vector v2
```

These packages are research-only. They create versioned, deterministic, provenance-bound evidence and preserve unavailable evidence as unavailable instead of inventing values.

### 2.1 Teacher-Gold readiness

SM-POLY-03 provides the registry/harness and readiness gates, but the repository does not contain a sufficiently populated verified Teacher-Gold corpus. Therefore:

```text
teacherGoldHarnessReady=true
teacherGoldEvaluationComplete=false
minimumResearchBenchmarkReady=false
```

The minimum research threshold remains 500 eligible verified fixtures with required coverage; the target remains 1000. Repository harness readiness is not corpus readiness.

### 2.2 Per-engine semantic evidence

SM-POLY-04 records parse, structure, pitch, duration, onset, voice, staff, tie, tuplet, measure, relation and structural-distance evidence independently per engine. It intentionally has no single aggregate accuracy score and no winner selection.

Teacher-edit metrics are versioned but currently unavailable. The declared future method is:

```text
TEACHER_REVISION_COMMAND_COUNT_V1
```

SM-POLY-13 is the planned owner for extracting this Teacher Review workload evidence.

### 2.3 Visual/source/complexity evidence

SM-POLY-05, SM-POLY-06 and SM-POLY-07 add separate evidence families for:

- page/event localization and optional symbol regions;
- source-page degradation/quality dimensions;
- polyphonic complexity such as voice count, simultaneity, staff, tuplets, ties, grace notes and overlaps.

These evidence families do not modify Stage 6 candidate contracts or Stage 7 convergence.

### 2.4 Reliability evidence

SM-POLY-08 provides deterministic descriptive reliability/calibration evidence, including exact-rational Brier/ECE-style statistics where reported confidence exists. It does not fit or deploy a recalibration model and does not create a production threshold.

### 2.5 ST-OMR shadow evidence

SM-POLY-09 adds provenance-bound ST-OMR shadow observations/reports beside immutable current-engine baseline references. This is evidence plumbing, not a completed real-world shadow benchmark and not ST-OMR promotion.

Current truth remains:

```text
stOmrShadowEvidenceContractReady=true
realWorldShadowBenchmarkComplete=false
stOmrIntegratedIntoGateway=false
```

### 2.6 Convergence Evidence Vector v2

SM-POLY-11 can place the exact Stage 7 result SHA beside immutable artifact sets from SM-POLY-04/05/06/07/08/09.

The v2 context is deliberately opaque across evidence families:

```text
directFixtureBindingClaimed=false
crossArtifactIdentityMatchClaimed=false
aggregateConfidenceScore=null
engineRanking=null
winner=null
```

A future direct cross-artifact join must validate upstream payload identities at the relevant fixture/source/Teacher-Gold granularity and introduce a separately versioned binding method.

## 3. Real Score Intake → Teacher Review Core

Merged E7-I/E7-K work establishes a fail-closed Real Score Intake seam from verified Stage 7/Canonical evidence into the Teacher Review editor runtime:

```text
verified Stage 7 candidate handoff
  -> Canonical Score binding
  -> real-score-intake-v1 / v1.1
  -> bounded Canonical projection
  -> pinned ST Score Editor Core runtime shapes
  -> revision-bound semantic targets
  -> Teacher Review Core bridge
```

Chord-aware semantic targets and full-score Core projection are repository-integrated. This grants no upload, networking, persistence, automatic correction, approval, publication, or production authority.

## 4. ST-Orchestration preview integration

### H7-C

A local-process, non-authoritative ST-Orchestration preview bridge exists for the exact `string-seat-ranking-v0` capability and pinned model identity. It presents evidence in Teacher Review and has no Apply action.

### H7-D

A server-side authenticated staging preview transport is active at repository/staging integration level:

- HMAC-SHA256 request authentication;
- HTTPS-only non-loopback policy with exact allowed-origin pin;
- bounded request/response/timeouts;
- model/source/result validation;
- browser-safe evidence only.

H7-D does not prove production readiness. H7-E remains a separate human gate requiring broader reliability/generalization evidence and production operational authority.

## 5. Score Discovery consumer boundary

SD-4B adds a disconnected Score Discovery consumer contract. Browser-facing state strips remote asset URLs and unsafe locator modes. A server-side handoff can only be formed for bounded `direct-import + public access + HTTPS + PDF/MusicXML/MXL` results and has only:

```text
authority = discovery-handoff-only
```

Every eligible discovery handoff must still pass existing Safe Intake. Live Gateway networking and production import remain disabled.

## 6. What the repository now proves

The repository now proves, at contract/test/integration level:

- versioned polyphonic OMR taxonomy and benchmark harness infrastructure;
- deterministic per-engine semantic evidence;
- visual, source-quality and polyphonic-complexity research sidecars;
- descriptive reliability evidence;
- ST-OMR shadow-evidence contracts;
- Convergence Evidence Vector v2 reference-only evidence integration;
- Real Score Intake v1/v1.1 into the pinned Teacher Review Core runtime;
- local and authenticated-staging ST-Orchestration preview evidence;
- disconnected Score Discovery consumer/handoff policy.

It still does **not** prove broad real-world OMR accuracy, a populated Teacher-Gold benchmark, a completed real-world ST-OMR shadow benchmark, selective-prediction safety, ST-OMR production promotion, H7-E production orchestration, live discovery networking, production Teacher Review API activation, or production readiness.

## 7. Next development sequence

The safest evidence-first order is:

1. **SM-POLY-13 — Teacher Review workload instrumentation.** Extract deterministic edit-count evidence from immutable TeacherScoreRevision/ScoreEditCommand lineage using `TEACHER_REVISION_COMMAND_COUNT_V1`; populate edits/measure and edits/page without changing teacher authority.
2. **Populate and qualify real Teacher-Gold evidence.** Move SM-POLY-03 from harness-only/NOT_READY toward the >=500 minimum with notation-category, scan-quality, licensing and provenance coverage; do not fabricate readiness.
3. **Versioned direct cross-artifact join.** Bind Stage 7, semantic, visual, source-quality, complexity, reliability and shadow evidence only where exact fixture/source identities are validated. Do not retrofit this claim into SM-POLY-11 v2.
4. **Selective prediction / abstention research.** Evaluate whether calibrated evidence can support abstention thresholds. Keep thresholds research-only until held-out Teacher-Gold evidence and no-regression gates are satisfied.
5. **ST-OMR promotion decision gate.** Only after real Teacher-Gold, real-world shadow, category-stratified no-regression, deterministic musical validation and rollback evidence exist should a versioned Stage 7 migration be considered.
6. **H7-E / live infrastructure gates remain separate.** Production orchestration, live Teacher Review API, provider provisioning and publication require explicit operational authorization and must not be coupled to research-evidence completion.

No package number is assigned here to the future cross-artifact join or selective-prediction work. Repository numbering must be introduced by its own explicit contract/PR rather than inferred from missing labels.
