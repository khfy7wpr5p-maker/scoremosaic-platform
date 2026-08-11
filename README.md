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

Safe Intake Gate B is now implemented as a closed foundation: B.1 signature classification, B.2 declared MIME binding, B.3 observed byte-budget enforcement, B.4 strict PDF structure/page-budget inspection, B.5 decoded JPEG/PNG image/pixel enforcement, B.6 original filename safety, the integrated fail-closed Safe Intake decision, and hostile-input convergence coverage are present on `main`. Gate B completion does **not** activate external upload; there is still no upload endpoint, and later authentication, durable-job, storage, external-API, and production-readiness gates remain required before public traffic is allowed.

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
- Safe Intake Gate B foundation: B.1-B.6, one integrated fail-closed intake decision over exact immutable bytes, and hostile-input convergence coverage.
- Immutable candidate/artifact lifecycle contracts.
- Canonical Score, Ensemble comparator/report, and fixed evaluation foundations.
- Candidate Safety v1 for HOMR, Clarity, and Audiveris engine outputs.

The B.4 PDF inspector parses only structural/page evidence. It does not render pages, extract text/images/attachments, execute embedded content, or enable upload. Encrypted PDFs are rejected in the current Safe Intake v1 slice. Immutable PDF `bytes` are passed to the helper without an additional parent-side payload copy; the Linux helper applies a 256 MiB address-space limit and the private Coolify staging Gateway is budgeted at 512 MiB.

The B.5 image inspector accepts only immutable JPEG/PNG bytes, rejects malformed/truncated or animated inputs, derives dimensions from decoded evidence rather than caller metadata, and enforces a 12,000 px per-dimension and 40,000,000 total-pixel ceiling inside a private helper subprocess with a 256 MiB address-space limit and a 3-second timeout. B.5 does not enable upload or orchestration.

B.6 treats the original filename as metadata only. It rejects unsafe path forms, control/format/surrogate Unicode categories, Windows device aliases, invalid filename shapes, and extensions that disagree with fresh signature-derived format evidence. It never converts the filename into a filesystem or storage path.

`decide_safe_intake()` composes the B.1-B.6 primitives over the same exact immutable `bytes` payload and returns only bounded server-derived evidence after all required checks pass. Existing primitive error categories propagate unchanged. The decision does not persist bytes, derive a storage path, accept an HTTP upload, or dispatch work to an engine.

## Activation gates still required

Gate B is complete as a Safe Intake foundation, but it does not authorize external upload or live orchestration. Before those capabilities are enabled, the platform still requires at minimum:

1. Authenticated service-to-service engine requests.
2. Durable job state, idempotency, retry/cancellation, and restart recovery.
3. Production immutable object storage and provenance retention.
4. External API authentication/authorization, rate limits, abuse controls, and an explicitly reviewed upload boundary wired through the Safe Intake decision.
5. Teacher Review API with RBAC, immutable revisions, and approval-to-publication barrier.
6. Production monitoring, backup/restore, rollback, and supply-chain hardening gates.

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
