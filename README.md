# ScoreMosaic Platform

ScoreMosaic is an independent, multi-engine optical music recognition (OMR) platform for producing isolated OMR candidates, validating them as untrusted artifacts, comparing musical evidence, and preparing structured findings for teacher review.

## Current status

ScoreMosaic is in **controlled development**. The repository contains private runtime foundations for HOMR, Clarity-OMR, Audiveris, the OMR Gateway, Ensemble comparison contracts, fixed evaluation assets, and an isolated ST-OMR development track.

The public data plane is intentionally **not enabled**:

- Gateway upload is disabled.
- Gateway orchestration/execution is disabled.
- Production persistence/publication is disabled.
- Engine services remain private to the container network.
- Teacher approval and publication are not yet production APIs.

## Secure target flow

```text
External application
        |
        | authenticated/versioned API (not enabled yet)
        v
Safe Intake Gate
PDF/image signature + MIME + bytes + pages + pixels + path safety
        |
        v
Immutable source artifact + SHA-256/provenance
        |
        v
OMR Gateway / durable job orchestration (execution still disabled)
        |
        +----------------+----------------+
        |                |                |
        v                v                v
      HOMR            Clarity         Audiveris
        |                |                |
        +----------------+----------------+
                         |
                         v
              Candidate Safety Gate v1
        MXL/ZIP + XML declarations + size/depth/count budgets
                         |
                         v
                  Canonical Score
                         |
                         v
                Ensemble Comparator
                         |
                         v
              Structured review report
                         |
                         v
              Teacher Review / approval
                         |
                         v
                 Publication barrier
```

A successful engine process does **not** make its output trusted. HOMR, Clarity, and Audiveris candidates must pass `contracts/candidate-safety-policy-v1.json` before they can be treated as safe input to canonicalization or comparison.

## Implemented security foundations

- Private internal engine network; no public engine ports.
- Non-root, read-only containers with dropped capabilities and `no-new-privileges`.
- Pinned engine/model revisions and checksum verification where applicable.
- GitHub Actions references pinned to immutable commit SHAs.
- Gateway health/orchestration contracts with upload and execution disabled.
- Immutable candidate/artifact lifecycle contracts.
- Canonical Score, Ensemble comparator/report, and fixed evaluation foundations.
- Candidate Safety v1 for HOMR, Clarity, and Audiveris engine outputs.

## Activation gates still required

Before any external upload or live orchestration is enabled, the platform still requires at minimum:

1. Runtime Safe Intake Gate enforcement for PDF/image signature, MIME, byte, page, pixel, and path limits.
2. Authenticated service-to-service engine requests.
3. Durable job state, idempotency, retry/cancellation, and restart recovery.
4. Production immutable object storage and provenance retention.
5. External API authentication/authorization, rate limits, and abuse controls.
6. Teacher Review API with RBAC, immutable revisions, and approval-to-publication barrier.
7. Production monitoring, backup/restore, rollback, and supply-chain hardening gates.

## Core principles

1. User input, remote responses, and engine output are untrusted until validated.
2. Original source documents and raw engine outputs remain immutable.
3. No engine may declare its own output to be the final approved score.
4. Unknown or ambiguous musical content is reported, not silently guessed or merged.
5. Teacher approval is separate from candidate generation and comparison.
6. Learner-facing publication requires an explicit approved revision.
7. Security boundaries are enabled before the capability they protect.

## Repository boundaries

ScoreMosaic is not the learner-facing playback, narration, or lesson application. External applications will integrate only through a versioned authenticated API after the remaining activation gates are demonstrated.

## Development workflow

- Source control: GitHub
- Development environment: GitHub Codespaces
- Automated verification: GitHub Actions
- Integration target: Coolify staging
- Production: blocked until production-readiness gates pass

See `docs/`, `contracts/`, and the service-specific tests for the current architecture and security evidence.
