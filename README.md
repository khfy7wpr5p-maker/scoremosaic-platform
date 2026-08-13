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

Safe Intake Gate B is implemented as a closed foundation: B.1 signature classification, B.2 declared MIME binding, B.3 observed byte-budget enforcement, B.4 strict PDF structure/page-budget inspection, B.5 decoded JPEG/PNG image/pixel enforcement, B.6 original filename safety, the integrated fail-closed Safe Intake decision, and hostile-input convergence coverage are present on `main`. Gate B completion does **not** activate external upload; there is still no upload endpoint, and later external-API, safe-upload-session, production storage/runtime, rate/abuse, and production-readiness controls remain required before public traffic is allowed.

Gate C.1 and C.2-A through C.2-G contract foundations plus C-DIAG-1 engine runtime diagnostic redaction and C-DIAG-2 dispatch diagnostic convergence are present on `main`. These foundations bind service and dispatch identities, authenticated request/result evidence, exact targets, credential generations, replay reservations, timeout/cancellation decisions, and the v1 one-attempt/zero-retry policy. C-DIAG-1 prevents raw HOMR, Clarity, and Audiveris runtime stdout/stderr and provider exception text from crossing the current probe, readiness, transcription-result, or raised-error surfaces. C-DIAG-2 maps receiver-verification, dispatch-deadline, retry-budget, and unexpected dispatch failures into a closed immutable outward diagnostic vocabulary, rejects non-exact diagnostic strings, and does not inspect exception text. Live receiver routes, durable replay persistence, network dispatch, and orchestration activation remain disabled.

Gate D.1-D.6 are complete as a **durable state/recovery contract and convergence foundation**. They cover fail-closed job state, idempotency/replay semantics, immutable source/candidate storage authority, SHA-256 provenance records, restart-recovery decisions, and partial-output/crash-window convergence. This does **not** mean production persistence is active: no database/S3/MinIO/filesystem provider, durable read/write adapter, queue/worker runtime, automatic process restart, storage-write runtime, or live orchestration authority is enabled.

Gate E is now **in progress**. E.1 provides provider-neutral external-principal authentication evidence. E.2 provides deny-by-default external authorization-decision evidence bound to an exact principal, environment, and canonical operation. E.3A provides provider-neutral authenticated-operation rate-slot reservation evidence, E.3B provides provider-neutral external request-idempotency admission evidence, and E.3C composes those foundations into one exact-request admission binding that evaluates E.3A freshly before E.3B and fails closed on callback authority mutation. These remain admission-contract foundations only: they do not execute an operation or activate upload, job creation, persistence, network dispatch, or orchestration. Provider/runtime authentication wiring, resource/tenant scope where an authoritative ownership model exists, production/runtime rate and idempotency adapters that preserve E.3C semantics, edge/anonymous abuse controls, safe upload sessions, privacy-safe live API errors/logs, and versioned public route wiring remain outstanding.

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
- Gate C.1/C.2-A-C.2-G internal-dispatch contract foundations plus C-DIAG-1 bounded engine runtime diagnostic redaction and C-DIAG-2 bounded dispatch diagnostic mapping; live dispatch remains disabled.
- Gate D.1-D.6 durable job/artifact state, idempotency, storage-authority, provenance, restart-recovery, and crash-window/partial-output contract/convergence foundations; operational persistence and live orchestration remain disabled.
- Gate E.1 provider-neutral external-principal authentication foundation.
- Gate E.2 deny-by-default external authorization-decision foundation; allowed decisions still carry no operation-execution authority.
- Gate E.3A provider-neutral authenticated-operation rate-slot reservation foundation; no production rate-state backend or HTTP 429 wiring is activated.
- Gate E.3B provider-neutral external request-idempotency admission foundation; no durable idempotency backend or live request wiring is activated.
- Gate E.3C fail-closed external admission composition foundation; it evaluates rate admission freshly, binds the exact idempotent request, and detects authority mutation across provider callbacks without granting runtime capability.
- Immutable candidate/artifact lifecycle contracts.
- Canonical Score, Ensemble comparator/report, and fixed evaluation foundations.
- Candidate Safety v1 for HOMR, Clarity, and Audiveris engine outputs.

The B.4 PDF inspector parses only structural/page evidence. It does not render pages, extract text/images/attachments, execute embedded content, or enable upload. Encrypted PDFs are rejected in the current Safe Intake v1 slice. Immutable PDF `bytes` are passed to the helper without an additional parent-side payload copy; the Linux helper applies a 256 MiB address-space limit and the private Coolify staging Gateway is budgeted at 512 MiB.

The B.5 image inspector accepts only immutable JPEG/PNG bytes, rejects malformed/truncated or animated inputs, derives dimensions from decoded evidence rather than caller metadata, and enforces a 12,000 px per-dimension and 40,000,000 total-pixel ceiling inside a private helper subprocess with a 256 MiB address-space limit and a 3-second timeout. B.5 does not enable upload or orchestration.

B.6 treats the original filename as metadata only. It rejects unsafe path forms, control/format/surrogate Unicode categories, Windows device aliases, invalid filename shapes, and extensions that disagree with fresh signature-derived format evidence. It never converts the filename into a filesystem or storage path.

`decide_safe_intake()` composes the B.1-B.6 primitives over the same exact immutable `bytes` payload and returns only bounded server-derived evidence after all required checks pass. Existing primitive error categories propagate unchanged. The decision does not persist bytes, derive a storage path, accept an HTTP upload, or dispatch work to an engine.

## Activation gates still required

Gate B, the Gate C security contracts, Gate D contract/convergence foundation, and Gate E.1-E.3C external API security foundations do not by themselves authorize external upload or live orchestration. Before those capabilities are enabled, the platform still requires at minimum:

1. Separately approved live receiver/dispatch wiring on top of the completed C.1/C.2-A-C.2-G and C-DIAG-1/C-DIAG-2 foundations, with operational credential/replay protections and no security-boundary weakening.
2. A separately reviewed operational persistence layer/provider for durable replay/job/artifact/provenance state, plus queue/worker/process-recovery behavior if activated; Gate D.1-D.6 currently provide only the contract/convergence authority model.
3. Production immutable object storage and retention/restore behavior bound to the existing immutable artifact/provenance contracts.
4. Remaining Gate E controls: provider/runtime authentication wiring, resource/user/tenant scope where applicable, production/runtime rate-limit and idempotency adapters that preserve E.3C exact-request/fresh-rate semantics, edge/anonymous abuse protection, privacy-safe external errors/logs, and an explicitly reviewed upload-session boundary wired through Safe Intake.
5. Teacher Review API with TR-8A RBAC/audit authorization, immutable revisions, and approval-to-publication barrier.
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

ScoreMosaic is not the learner-facing playback, narration, or lesson application. External applications will integrate only through a versioned authenticated and authorized API after the remaining activation gates are demonstrated.

## Development workflow

- Source control: GitHub
- Development environment: GitHub Codespaces
- Automated verification: GitHub Actions
- Integration target: Coolify staging
- Production: blocked until production-readiness gates pass

See `docs/`, `contracts/`, and the service-specific tests for the current architecture and security evidence.
