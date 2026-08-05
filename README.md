# ScoreMosaic Platform

ScoreMosaic is an independent, multi-engine optical music recognition (OMR) and teacher-review support platform. It is designed to run isolated OMR engines, preserve every candidate result, normalize musical evidence into a shared model, detect disagreements, and prepare structured findings for human review.

ScoreMosaic does not treat any OMR output as automatically correct, and it is not the learner-facing playback, narration, or lesson application.

## Current maturity

**Architecture and executable foundation — not yet a production OMR service.**

The repository currently includes:

- private runtime foundations for Audiveris, HOMR, and Clarity-OMR;
- a private OMR Gateway foundation with a deterministic, versioned orchestration-plan contract;
- the Canonical Score Model for safe, provenance-preserving MusicXML normalization;
- a neutral Ensemble Comparator and versioned comparison report;
- fixed real-engine fixtures and automated contract checks;
- architecture, security, artifact, and teacher-review specifications.

The repository does **not** yet provide an externally available upload API or a persistent end-to-end OMR workflow. Live Gateway dispatch, queues, database persistence, artifact storage, Ensemble execution through the Gateway, teacher approval, learner publication, and ST-OMR integration remain disabled or unimplemented.

## Target architecture

```text
Teacher or external application
              |
              | versioned authenticated API (future)
              v
         OMR Gateway
              |
              | secure intake, job lifecycle,
              | engine dispatch, timeouts,
              | cancellation and artifact references
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

The current implementation establishes the engine, contract, canonicalization, and comparison foundations. The complete enabled runtime path shown above is still under development.

## Component status

| Component | Current responsibility | Status |
|---|---|---|
| `services/omr-gateway` | Health boundary and deterministic orchestration-plan contract for Audiveris, HOMR, and Clarity | Foundation implemented; upload, network dispatch, queues, persistence, and execution disabled |
| `services/audiveris-service` | Private isolated Audiveris runtime foundation | Implemented as an internal runtime boundary; no public upload API |
| `services/homr-service` | Private isolated HOMR runtime foundation | Implemented as an internal runtime boundary; no public upload API |
| `services/clarity-service` | Private isolated Clarity-OMR runtime foundation | Implemented as an internal runtime boundary; no public upload API |
| `services/ensemble-service` | Canonical MusicXML normalization, neutral comparison, and versioned reporting | Foundation implemented as a deterministic comparison component; no automatic winner or merge |
| `contracts/` | Versioned schemas for jobs, canonical scores, orchestration plans, comparison reports, and review records | Implemented and validated in CI |
| Teacher review | Human correction, immutable revisions, approval, and publication boundary | Specified in documentation; API and editor not yet implemented |
| ST-OMR | Future teacher-assisted recommendation or learning capability | Not implemented; no service, model, dataset, or active contract exists |

## Musical evidence model

The Canonical Score Model is intended to preserve the evidence needed for reliable music comparison, including:

- part, measure, staff, voice, and event position;
- pitch, alteration, octave, note, and rest identity;
- exact written and effective durations;
- chords, ties, dots, tuplets, backup, and forward timing;
- time signatures and divisions;
- guitar string and fret evidence when available;
- source engine, source artifact, and source location provenance.

Raw engine candidates remain distinct. Normalization and comparison must not erase where an event came from.

## Core principles

1. OMR output is evidence, not automatically approved truth.
2. Original inputs and raw engine outputs remain immutable.
3. Every candidate keeps its engine identity, version, diagnostics, hashes, and provenance.
4. Engine services remain private and do not receive direct external traffic.
5. Untrusted PDF, image, MusicXML, filenames, archives, and model artifacts require strict validation and resource limits.
6. Candidate comparison must remain neutral: no silent winner selection, overwrite, merge, or automatic correction.
7. Corrections create new revisions instead of modifying raw artifacts.
8. Teacher approval is required before any result can be published to a learner-facing application.
9. Public lifecycle transitions must be explicit, auditable, cancellable, and recoverable.
10. Development changes are verified through branches, pull requests, and automated checks before production use.

## Current execution boundary

The following capabilities are intentionally disabled until their security, persistence, and recovery requirements are implemented:

- external PDF or image upload;
- live Gateway-to-engine dispatch;
- job queues and retry execution;
- persistent job and artifact storage;
- automatic Gateway-to-Ensemble execution;
- engine ranking or preferred-engine selection;
- automatic MusicXML merge or correction;
- teacher approval through an API;
- publication to a learner-facing system;
- ST-OMR training, inference, or integration.

This boundary prevents a contract or test foundation from being mistaken for a production-ready service.

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

A safe first role for ST-OMR would be to consume immutable engine candidates, Ensemble disagreement evidence, and teacher-verified revisions, then produce explainable correction recommendations. It must not silently modify raw candidates, declare an automatically approved score, or publish directly to learners.

Before ST-OMR work begins, the platform should first establish:

1. a secure and persistent Gateway execution pipeline;
2. Gateway-to-Canonical-to-Ensemble integration;
3. an auditable teacher-review and revision system;
4. a representative teacher-verified guitar and TAB benchmark dataset;
5. quality metrics and regression gates for pitch, rhythm, structure, and TAB accuracy.

Any future ST-OMR design must be introduced through a separate versioned contract and reviewed security boundary.

## Near-term implementation order

1. Secure file intake and validation.
2. Persistent jobs, artifact storage, hashes, cleanup, and restart recovery.
3. Real Gateway dispatch to private engine adapters with timeouts and cancellation.
4. Automatic candidate validation and Canonical Score Model normalization.
5. Ensemble comparison and versioned report generation within the job lifecycle.
6. Teacher-review API, immutable revisions, approval, and authorization.
7. Representative guitar, staff-plus-TAB, TAB-only, rhythm, chord, multi-voice, scan, and phone-photo benchmarks.
8. Delivery of approved MusicXML to a separate learner-facing application.
9. Controlled evaluation of ST-OMR recommendations after sufficient verified data exists.

## Repository boundaries

ScoreMosaic owns OMR processing, candidate evidence, comparison, and review-support boundaries. It does not own learner playback, Turkish narration, lesson delivery, MIDI interaction, or accessibility presentation. Those capabilities belong in a separate learner-facing application that consumes only approved platform outputs through a versioned authenticated API.

Engine containers, storage paths, model files, and raw internal endpoints must never be exposed directly to external applications.

## Repository layout

```text
contracts/                    Versioned platform data contracts
docs/                         Architecture, security, review, and model specifications
services/omr-gateway/         Private Gateway and orchestration contract foundation
services/audiveris-service/   Private Audiveris runtime foundation
services/homr-service/        Private HOMR runtime foundation
services/clarity-service/     Private Clarity-OMR runtime foundation
services/ensemble-service/    Canonical normalization and comparison foundation
deploy/                       Deployment foundations
.github/workflows/            Automated verification
```

## Development and deployment

- Source control: GitHub
- Development environment: GitHub Codespaces
- Automated verification: GitHub Actions
- Integration target: Coolify staging
- Production: only after security, persistence, recovery, review, and acceptance gates pass

See `docs/` and `contracts/` for the detailed specifications. Service-specific runtime and security boundaries are documented in each service directory.
