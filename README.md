# ScoreMosaic Platform

ScoreMosaic is an independent, multi-engine optical music recognition (OMR) and teacher-review support platform.

It is designed to run isolated OMR engines, preserve every candidate result, normalize safe musical evidence into a shared model, detect disagreements, and prepare structured findings for human review.

ScoreMosaic does not treat an OMR result as automatically correct. It is not the learner-facing playback, narration, MIDI, accessibility, or lesson application.

## Start here

- [`AI_CONTEXT.md`](AI_CONTEXT.md) — single starting point for AI-assisted work and repository rules.
- [`docs/current-status.md`](docs/current-status.md) — actual platform state, enabled boundaries, missing capabilities, and next safe milestone.
- [`docs/package-status.md`](docs/package-status.md) — package versions and test/CI-backed evidence.

These status files distinguish executable behavior from plans and should be updated whenever capabilities or package evidence change.

## Current maturity

**Architecture and executable foundation — not yet a production or persistent end-to-end OMR service.**

The repository currently includes:

- private runtime integrations for Audiveris, HOMR, and Clarity-OMR;
- OMR Gateway `0.3.0` with deterministic orchestration-plan and append-only candidate/artifact lifecycle contracts;
- the Canonical Score Model for safe, provenance-preserving MusicXML normalization;
- a neutral Ensemble Comparator;
- a versioned comparison report;
- fixed real-engine fixtures and automated verification;
- security, artifact, deployment, and teacher-review specifications.

The repository does not yet provide an externally available upload API or a persistent complete job workflow. Live Gateway dispatch, queues, database persistence, artifact storage writes, automatic Gateway-to-Ensemble execution, teacher approval, learner publication, and ST-OMR integration remain disabled or unimplemented.

## Target architecture

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

The complete enabled runtime path shown above is still under development.

## Component status

| Component | Current responsibility | Status |
|---|---|---|
| `services/omr-gateway` | Health boundary, orchestration-plan v1, and candidate/artifact lifecycle v1 | Contract libraries implemented and CI-verified; upload, dispatch, execution, persistence, and storage writes disabled |
| `services/audiveris-service` | Private Audiveris 5.11.0 runtime | Runtime-integrated and CI-verified; no public upload API |
| `services/homr-service` | Private HOMR 0.7.0 CPU runtime | Runtime-integrated and CI-verified; no public upload API |
| `services/clarity-service` | Private pinned Clarity-OMR CPU runtime | Runtime-integrated and CI-verified; no public upload API |
| `services/ensemble-service` | Canonical MusicXML normalization, neutral comparison, real-engine fixtures, and versioned reporting | Library implemented and CI-verified; no automatic winner, merge, correction, or public API |
| `contracts/` | Versioned job, artifact, canonical-score, orchestration, comparison, and review schemas | Checked by related CI workflows; schemas do not enable runtime execution |
| Teacher review | Human correction, immutable revisions, approval, and publication boundary | Specified; API and editor not implemented |
| ST-OMR | Future teacher-assisted recommendation or learning capability | Not implemented; no service, model, dataset, contract, or CI workflow |

## Core principles

1. OMR output is evidence, not automatically approved truth.
2. Original inputs and raw engine outputs remain immutable.
3. Every candidate retains its engine identity, version, diagnostics, hashes, and provenance.
4. Engine services remain private and do not receive direct external traffic.
5. Untrusted PDF, image, MusicXML, filename, archive, model, and engine-response data requires strict validation and resource limits.
6. Candidate comparison remains neutral: no silent winner selection, overwrite, merge, or automatic correction.
7. Corrections create new revisions rather than modifying raw artifacts.
8. Teacher approval is required before publication to a learner-facing application.
9. Lifecycle transitions must be explicit, auditable, cancellable, and recoverable before external use.
10. Development changes are verified through feature branches, pull requests, and automated checks.

## Current execution boundary

The following remain intentionally disabled or absent:

- external PDF or image upload;
- live Gateway-to-engine dispatch;
- durable queues, retries, and restart recovery;
- persistent job and artifact storage;
- automatic Gateway-to-Ensemble execution;
- engine ranking or preferred-engine selection;
- automatic MusicXML merge or correction;
- teacher approval through an API;
- publication to a learner-facing system;
- ST-OMR training, inference, or integration.

A contract, schema, health endpoint, or successful bounded smoke test must not be described as a production-ready end-to-end service.

## Musical evidence model

The Canonical Score Model preserves evidence needed for comparison, including:

- part, measure, staff, voice, and event position;
- pitch, alteration, octave, note, and rest identity;
- exact written and effective durations;
- chords, ties, dots, tuplets, backup, and forward timing;
- time signatures and divisions;
- guitar string and fret when available;
- source engine, source artifact, and source location provenance.

Raw engine candidates remain distinct. Normalization and comparison must not erase their origin.

## ST-OMR future boundary

ST-OMR is a reserved future capability, not a current engine or active package.

A safe first role would be to consume immutable candidates, Ensemble disagreement evidence, and teacher-verified revisions, then produce explainable correction recommendations. It must not silently alter raw results, approve a score, or publish directly to learners.

Before ST-OMR work begins, the platform should establish secure persistent Gateway execution, candidate storage and recovery, Gateway-to-Ensemble integration, teacher revisions and approval, representative guitar/TAB data, and measurable quality gates.

## Repository boundaries

ScoreMosaic owns OMR processing, candidate evidence, comparison, and review-support boundaries.

It does not own learner playback, Turkish narration, lesson delivery, MIDI interaction, or accessibility presentation. Those capabilities belong in a separate learner-facing application that consumes only approved outputs through a future versioned authenticated API.

Engine containers, storage paths, model files, and raw internal endpoints must not be exposed directly to external applications.

## Repository layout

```text
AI_CONTEXT.md                 AI entry point and repository working rules
contracts/                    Versioned platform data contracts
docs/                         Status, architecture, security, review, and model specifications
services/omr-gateway/         Private Gateway contract foundation
services/audiveris-service/   Private Audiveris runtime
services/homr-service/        Private HOMR runtime
services/clarity-service/     Private Clarity-OMR runtime
services/ensemble-service/    Canonical normalization and comparison library
deploy/                       Deployment configuration foundations
.github/workflows/            Automated verification
```

## Development and deployment

- Source control: GitHub
- Development environment: GitHub Codespaces
- Automated verification: GitHub Actions
- Integration target: Coolify staging
- Production: only after security, persistence, recovery, review, deployment, and acceptance gates pass

See [`docs/current-status.md`](docs/current-status.md) for the real platform state and [`docs/package-status.md`](docs/package-status.md) for package-level test evidence.