# ScoreMosaic Current Status

**Status date:** 2026-08-05  
**Verified repository baseline:** `main` at `fcff4f237ab4034297ffcd58c20b54f09d377fea`  
**Baseline change:** Gateway candidate and artifact lifecycle v1

This document states what ScoreMosaic actually contains now. It separates executable foundations from target architecture, planned capabilities, and production claims.

## Executive status

ScoreMosaic has a strong, test-backed architectural and executable foundation, but it is not yet an externally usable or persistent end-to-end OMR platform.

The repository currently proves four main foundations:

1. pinned and isolated Audiveris, HOMR, and Clarity runtime integrations;
2. deterministic Gateway orchestration and candidate/artifact lifecycle contracts;
3. safe, provenance-preserving MusicXML canonicalization;
4. neutral multi-engine comparison and versioned review-report generation.

The repository does not yet prove a complete job path from external file upload to teacher-approved MusicXML.

## Maturity classification

| Area | Current maturity |
|---|---|
| Engine containers | Runtime-integrated and CI-verified foundations |
| OMR Gateway | Health boundary plus deterministic contract libraries |
| Upload and secure intake | Not implemented |
| Live engine dispatch | Disabled by design |
| Job queue and retries | Not implemented |
| Database persistence | Disabled or not implemented |
| Artifact storage writes | Disabled by design |
| Canonical Score Model | Implemented and CI-verified |
| Ensemble Comparator | Implemented as a neutral library and CI-verified |
| Real-engine fixture comparison | Implemented for a bounded synthetic score and CI-verified |
| Versioned comparison report | Implemented and CI-verified |
| Teacher-review API/editor | Specified, not implemented |
| Approved-result publication | Not implemented |
| Learner-facing application | Outside this repository |
| ST-OMR | Reserved future capability; not implemented |
| Production deployment | Not verified |

## Implemented and verified foundations

### Private engine runtimes

The repository contains private service foundations for:

- Audiveris;
- HOMR 0.7.0 in CPU mode;
- Clarity-OMR with pinned source and model revisions in CPU mode.

Their workflows build or validate the runtime boundaries and exercise bounded transcription or smoke-test paths. These integrations do not expose a public upload or conversion API.

### OMR Gateway contracts

`services/omr-gateway` is currently version `0.3.0`.

Implemented contract-library behavior includes:

- deterministic orchestration plans for Audiveris, HOMR, and Clarity;
- stable job, run, candidate, artifact, and namespace identifiers;
- engine-run lifecycle definitions;
- timeout and cancellation policy representation;
- immutable source-artifact policy;
- isolated candidate namespaces;
- append-only candidate and artifact lifecycle events;
- required hashes before artifact sealing;
- prevention of overwrite and cross-engine writes in the contract model.

The latest baseline successfully passed both the Gateway Orchestration Contract v1 workflow and the Candidate and Artifact Lifecycle v1 workflow.

### Canonical Score Model

`services/ensemble-service` can parse bounded safe `score-partwise` MusicXML and normalize it into deterministic canonical structures while preserving provenance.

The model preserves evidence including:

- part, measure, staff, voice, and event position;
- pitch, alteration, octave, note, and rest identity;
- exact rational written and effective durations;
- chords, ties, dots, tuplets, backup, and forward timing;
- time signatures and divisions;
- guitar string and fret when present;
- source engine, source artifact, and source XML location.

DTD and external-entity input is rejected or sanitized at the controlled boundaries defined by the package tests and engine fixture workflow.

### Ensemble comparison and reporting

The Ensemble package contains:

- deterministic canonicalization;
- a neutral comparator for two to eight candidates;
- structured difference evidence;
- versioned comparison-report generation;
- fixed real-engine fixtures produced by Audiveris, HOMR, and Clarity.

The current comparator is evidence-preserving and intentionally does not select a winner, merge MusicXML, correct events, approve a score, or publish results.

## Current target architecture

```text
Teacher or external application
              |
              | future versioned authenticated API
              v
         OMR Gateway
              |
      secure intake and job lifecycle
              |
       +------+------+------+
       |             |      |
       v             v      v
  Audiveris         HOMR  Clarity
       |             |      |
       +------+------+------+
              |
     immutable engine candidates
              |
              v
     Canonical Score Model
              |
              v
      Ensemble Comparator
              |
              v
   versioned comparison report
              |
              v
 teacher review and immutable revisions
              |
              v
      approved MusicXML only
              |
              v
 learner-facing application outside this repository
```

Only the engine, contract, canonicalization, comparison, and reporting foundations are currently executable. The complete connected runtime path is still under development.

## Explicitly disabled runtime capabilities

The current Gateway configuration keeps the following disabled:

- external PDF or image upload;
- orchestration execution;
- live network dispatch to engine services;
- persistent job storage;
- artifact storage writes;
- runtime mutation through HTTP;
- automatic Gateway-to-Ensemble execution.

The Gateway health boundary is not evidence of an enabled OMR job API. Contract objects can be built and verified in memory, but the application does not expose job creation or artifact mutation endpoints.

## Not implemented

The following capabilities are not currently implemented as complete platform behavior:

- authenticated external API;
- file quarantine and secure upload intake;
- durable job queue;
- retry execution and restart recovery;
- database-backed lifecycle state;
- immutable object storage integration;
- real Gateway dispatch to all enabled engine adapters;
- automatic candidate collection and validation inside a job;
- automatic Gateway-to-Canonical-to-Ensemble pipeline;
- teacher-review API;
- teacher editor;
- revision authorization and approval execution;
- publication of approved MusicXML;
- integration with the learner-facing SesliTab application;
- production monitoring, backup, retention, and disaster recovery.

## ST-OMR status

ST-OMR has not started as an implementation package.

There is currently:

- no `services/st-omr-service` directory;
- no model;
- no training dataset;
- no teacher-correction dataset pipeline;
- no inference API;
- no versioned ST-OMR contract;
- no ST-OMR CI workflow;
- no enabled integration point.

The safest future first role is an explainable recommendation component that consumes immutable engine candidates, Ensemble disagreement evidence, and teacher-verified revisions. It must not silently modify raw artifacts or approve scores.

Before ST-OMR work begins, ScoreMosaic should first establish:

1. secure and persistent Gateway execution;
2. candidate storage and restart recovery;
3. Gateway-to-Canonical-to-Ensemble integration;
4. auditable teacher revisions and approval;
5. representative teacher-verified guitar and TAB data;
6. quality metrics and regression gates.

## Known limitations of current evidence

- Real-engine fixture validation proves bounded deterministic processing, not general OMR accuracy.
- The shared real-engine fixture is a simple generated score and is not a representative guitar/TAB benchmark.
- Comparator alignment is currently conservative and ordinal; missing or extra events may create cascading differences.
- No benchmark currently proves robust handling of staff-plus-TAB, TAB-only scores, beams, chords, multiple voices, low-quality scans, or phone photographs.
- Successful CI does not prove production security, scaling, persistence, or recovery.
- Licensing and model-distribution requirements require review before public deployment.

## Next safe implementation milestone

The next major milestone should be a secure, persistent, internal end-to-end Gateway pipeline—not ST-OMR and not automatic winner selection.

Recommended order:

1. secure file intake and validation;
2. durable jobs and immutable artifact storage;
3. real private engine dispatch with timeout and cancellation;
4. candidate validation and canonicalization;
5. Ensemble comparison and report generation inside the job lifecycle;
6. teacher-review API and immutable revisions;
7. guitar and TAB benchmark expansion;
8. approved-output integration with the separate learner application;
9. controlled ST-OMR evaluation only after verified teacher data exists.

## Evidence references

- [`docs/package-status.md`](package-status.md)
- [`services/omr-gateway/pyproject.toml`](../services/omr-gateway/pyproject.toml)
- [`services/ensemble-service/pyproject.toml`](../services/ensemble-service/pyproject.toml)
- [`docs/gateway-orchestration-contract-v1.md`](gateway-orchestration-contract-v1.md)
- [`docs/candidate-artifact-lifecycle-v1.md`](candidate-artifact-lifecycle-v1.md)
- [`docs/canonical-score-model.md`](canonical-score-model.md)
- [`docs/ensemble-comparator-v1-foundation.md`](ensemble-comparator-v1-foundation.md)
- [`docs/ensemble-comparison-report-v1.md`](ensemble-comparison-report-v1.md)
- [`docs/ensemble-real-canonical-fixtures.md`](ensemble-real-canonical-fixtures.md)
- [`docs/security-boundaries.md`](security-boundaries.md)
- [`docs/teacher-review-workflow.md`](teacher-review-workflow.md)

## Update rule

Update this file only after executable behavior or verified project boundaries change. Plans and unmerged proposals must be described as planned, never as current capability.