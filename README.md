# ScoreMosaic Platform

ScoreMosaic is an independent, multi-engine optical music recognition (OMR) and teacher-review support platform. It preserves OMR candidates, normalizes musical evidence, detects disagreements, and prepares structured findings for human review.

ScoreMosaic does not treat any OMR output as automatically correct, and it is not the learner-facing playback, narration, MIDI, accessibility, or lesson application.

## Start here

- [`AI_CONTEXT.md`](AI_CONTEXT.md) — single entry point for AI assistants and contributors
- [`docs/current-status.md`](docs/current-status.md) — real implementation state and current gaps
- [`docs/package-status.md`](docs/package-status.md) — package versions and test-evidenced status

## Current maturity

**Test-evidenced architecture and contract foundation — not yet a production OMR service.**

The repository currently includes:

- private, verified runtime foundations for Audiveris, HOMR, and Clarity-OMR;
- a health-only OMR Gateway with deterministic orchestration and candidate/artifact lifecycle contracts;
- an append-only artifact state model with immutable source and per-engine candidate evidence;
- the Canonical Score Model for safe, provenance-preserving MusicXML normalization;
- a neutral Ensemble Comparator and versioned comparison report;
- bounded real-engine fixtures and automated contract checks;
- architecture, security, artifact, deployment, and teacher-review specifications.

The repository does **not** yet provide an externally available upload API or a persistent end-to-end OMR workflow. Live Gateway dispatch, queues, database persistence, artifact storage writes, restart recovery, automatic Gateway-to-Ensemble execution, teacher approval, learner publication, and ST-OMR integration remain disabled or unimplemented.

## Target architecture

```text
Teacher or external application
              |
              | versioned authenticated API (future)
              v
         OMR Gateway
              |
              | secure intake, job lifecycle,
              | dispatch, timeouts, cancellation,
              | immutable artifact references
              v
      Immutable source artifact
              |
       +------+------+------+
       |             |      |
       v             v      v
  Audiveris         HOMR  Clarity
       |             |      |
       +------+------+------+
              |
              v
   Immutable engine candidates
              |
              v
     Canonical Score Model
              |
              v
      Ensemble Comparator
              |
              v
   Versioned comparison report
              |
              v
 Teacher review and revisions (future)
              |
              v
      Approved MusicXML only
              |
              v
 Learner-facing application (outside this repository)
```

The complete enabled runtime path shown above is still under development.

## Component status

| Component | Current responsibility | Status |
|---|---|---|
| `services/omr-gateway` | Health boundary, orchestration plan, and append-only candidate/artifact lifecycle | Version `0.3.0`; contracts implemented and tested; upload, dispatch, storage, persistence, and execution disabled |
| `services/audiveris-service` | Private isolated Audiveris `5.11.0` runtime | Real container smoke path tested; no public upload API |
| `services/homr-service` | Private isolated HOMR `0.7.0` CPU runtime | Real container smoke path tested; no public upload API |
| `services/clarity-service` | Private isolated Clarity-OMR CPU runtime | Real container smoke path tested; no public upload API |
| `services/ensemble-service` | Canonical MusicXML normalization, neutral comparison, and versioned reporting | Deterministic library foundation implemented and tested; no automatic winner or merge |
| `contracts/` | Versioned job, orchestration, artifact, Canonical, comparison, and review schemas | Implemented schemas; implementation coverage differs by contract |
| Teacher review | Human correction, immutable revisions, approval, and publication boundary | Specified in documentation; API and editor not implemented |
| ST-OMR | Future teacher-assisted recommendation or learning capability | Not implemented; no service, model, dataset, or active contract |

## Musical evidence model

The Canonical Score Model preserves evidence needed for reliable comparison, including:

- part, measure, staff, voice, and event position;
- pitch, alteration, octave, note, and rest identity;
- exact written and effective durations;
- chords, ties, dots, tuplets, `backup`, and `forward` timing;
- time signatures and divisions;
- guitar string and fret evidence when available;
- source engine, source artifact, XML path, and source event index.

Raw engine candidates remain distinct. Normalization and comparison must not erase where an event came from.

## Gateway contract foundation

The Gateway currently contains two tested deterministic contracts:

1. **Orchestration Plan Contract v1** — defines source identity, requested engines, isolated runs, candidate namespaces, expected artifacts, timeouts, lifecycle rules, and disabled boundaries.
2. **Candidate and Artifact Lifecycle Contract v1** — defines immutable source evidence, separate raw result/MusicXML/diagnostic artifacts, candidate and artifact state transitions, hash-before-seal rules, and an append-only event hash chain.

These are in-memory libraries. They do not accept uploads, dispatch engines, write files, create database rows, or publish queue events.

## Core principles

1. OMR output is evidence, not automatically approved truth.
2. Original inputs and raw engine outputs remain immutable.
3. Every candidate keeps its engine identity, version, diagnostics, hashes, and provenance.
4. Engine services remain private and do not receive direct external traffic.
5. Untrusted PDF, image, MusicXML, filenames, archives, model assets, and remote responses require strict validation and resource limits.
6. Candidate comparison remains neutral: no silent winner selection, overwrite, merge, or automatic correction.
7. Corrections create new revisions instead of modifying raw artifacts.
8. Teacher approval is required before any result can be published to a learner-facing application.
9. Lifecycle transitions must be explicit, auditable, bounded, and recoverable.
10. Development changes are verified through branches, pull requests, and automated checks before production use.

## Current execution boundary

The following capabilities are intentionally disabled until their security, persistence, recovery, and authorization requirements are implemented:

- external PDF or image upload;
- authenticated job creation;
- live Gateway-to-engine dispatch;
- queues, retries, and cancellation execution;
- persistent job and artifact storage;
- runtime artifact writes and mutation;
- restart recovery;
- automatic Gateway-to-Canonical-to-Ensemble execution;
- engine ranking or preferred-engine selection;
- automatic MusicXML merge or correction;
- teacher approval through an API;
- publication to a learner-facing system;
- ST-OMR training, inference, or integration.

This boundary prevents a contract or smoke-test foundation from being mistaken for a production-ready service.

## Teacher-review boundary

The planned review workflow is:

```text
needs_review
    -> under_review
    -> corrected
    -> approved
    -> published
```

Teacher decisions must create auditable revisions and preserve the original score, every engine candidate, the comparison report, unresolved warnings, and approval metadata. Only an explicitly approved revision may cross the learner-publication boundary.

## ST-OMR future direction

ST-OMR is a reserved future capability, not a current engine or active implementation.

A safe first role would be to consume immutable engine candidates, Ensemble disagreement evidence, and teacher-verified revisions, then produce explainable correction recommendations. It must not silently modify raw candidates, declare an automatically approved score, or publish directly to learners.

Before ST-OMR work begins, the platform should establish:

1. secure authenticated intake;
2. content-addressed artifact storage and persistent jobs;
3. restart-safe Gateway execution;
4. Gateway-to-Canonical-to-Ensemble integration;
5. an auditable teacher-review and revision system;
6. a representative teacher-verified guitar and TAB benchmark dataset;
7. quality metrics and regression gates for pitch, rhythm, structure, and TAB accuracy.

## Near-term implementation order

1. Reconcile remaining architecture and phase-document drift.
2. Define secure file intake and preprocessing.
3. Add isolated content-addressed artifact storage while preserving the append-only lifecycle contract.
4. Add persistent jobs, idempotency, cleanup, and restart recovery.
5. Enable real private engine dispatch with timeouts and cancellation.
6. Validate and seal real engine outputs.
7. Connect candidates to Canonical normalization and Ensemble reporting.
8. Implement teacher-review revisions, approval, and authorization.
9. Build representative guitar, staff-plus-TAB, TAB-only, rhythm, chord, multi-voice, scan, and phone-photo benchmarks.
10. Deliver approved MusicXML to a separate learner-facing application.
11. Evaluate ST-OMR only after sufficient teacher-verified correction data exists.

## Repository boundaries

ScoreMosaic owns OMR processing, candidate evidence, comparison, and review-support boundaries. It does not own learner playback, Turkish narration, lesson delivery, MIDI interaction, or accessibility presentation.

Engine containers, storage paths, model files, and raw internal endpoints must never be exposed directly to external applications.

## Repository layout

```text
AI_CONTEXT.md                  Single AI/contributor entry point
README.md                      Project overview and target architecture
contracts/                     Versioned platform data contracts
docs/current-status.md         Real project state snapshot
docs/package-status.md         Test-evidenced package status
docs/                          Architecture, security, review, and contract specifications
services/omr-gateway/          Gateway and deterministic contract foundation
services/audiveris-service/    Private Audiveris runtime foundation
services/homr-service/         Private HOMR runtime foundation
services/clarity-service/      Private Clarity-OMR runtime foundation
services/ensemble-service/     Canonical normalization and comparison foundation
deploy/                        Deployment foundations
.github/workflows/             Automated verification
```

## Development and deployment

- Source control: GitHub
- Development environment: GitHub Codespaces
- Automated verification: GitHub Actions
- Integration target: Coolify staging
- Production: only after security, persistence, recovery, review, licensing, and acceptance gates pass

See `AI_CONTEXT.md`, `docs/current-status.md`, and `docs/package-status.md` before using older phase or roadmap documents as current-state evidence.