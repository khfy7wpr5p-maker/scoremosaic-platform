# ScoreMosaic Platform

ScoreMosaic is an independent, multi-engine optical music recognition (OMR) platform for producing isolated OMR candidates, validating them as untrusted artifacts, comparing musical evidence, and preparing structured findings for teacher review.

## Current status

ScoreMosaic is in **controlled development**. The repository contains private runtime foundations for HOMR, Clarity-OMR, Audiveris, the OMR Gateway, Ensemble comparison contracts, fixed evaluation assets, and an isolated ST-OMR development track.

The public data plane is intentionally **not enabled**:

- Public Gateway document upload is disabled.
- Gateway orchestration/execution is disabled.
- Production persistence/publication is disabled.
- Engine services remain private to the container network.
- Teacher approval and publication are not yet production APIs.

Safe Intake Gate B is implemented as a closed foundation: B.1 signature classification, B.2 declared MIME binding, B.3 observed byte-budget enforcement, B.4 strict PDF structure/page-budget inspection, B.5 decoded JPEG/PNG image/pixel enforcement, B.6 original filename safety, the integrated fail-closed Safe Intake decision, and hostile-input convergence coverage are present on `main`. Gate B completion did **not** activate external upload. The minimum staging vertical slice now invokes E.4B only after exact staging E.3C/E.4A evidence and allows one private create-once source write only after Gate B and E.4C verification; there is still no public HTTP upload endpoint.

Gate C.1 and C.2-A through C.2-G contract foundations plus C-DIAG-1 engine runtime diagnostic redaction and C-DIAG-2 dispatch diagnostic convergence are present on `main`. These foundations bind service and dispatch identities, authenticated request/result evidence, exact targets, credential generations, replay reservations, timeout/cancellation decisions, and the v1 one-attempt/zero-retry policy. C-DIAG-1 prevents raw HOMR, Clarity, and Audiveris runtime stdout/stderr and provider exception text from crossing the current probe, readiness, transcription-result, or raised-error surfaces. C-DIAG-2 maps receiver-verification, dispatch-deadline, retry-budget, and unexpected dispatch failures into a closed immutable outward diagnostic vocabulary, rejects non-exact diagnostic strings, and does not inspect exception text. Live receiver routes, durable dispatch replay persistence, network dispatch, and orchestration activation remain disabled.

Gate D.1-D.6 are complete as a **durable state/recovery contract and convergence foundation**. They cover fail-closed job state, idempotency/replay semantics, immutable source/candidate storage authority, SHA-256 provenance records, restart-recovery decisions, and partial-output/crash-window convergence. Gate D completion did not activate production persistence. The minimum staging slice now reuses Gate D.3 source authority for one bounded private filesystem source write, but no production database/S3/MinIO provider, broader durable job/candidate adapter, queue/worker runtime, automatic process restart, or live orchestration authority is enabled.

Gate E is **in progress**. E.1 provides provider-neutral external-principal authentication evidence. E.2 provides deny-by-default external authorization-decision evidence bound to an exact principal, environment, and canonical operation. E.3A provides provider-neutral authenticated-operation rate-slot reservation evidence, E.3B provides provider-neutral external request-idempotency admission evidence, and E.3C composes those foundations into one exact-request admission binding that evaluates E.3A freshly before E.3B and fails closed on callback authority mutation. E.4 is complete as a bounded **upload-to-source contract/convergence foundation**: E.4A reserves exact canonical Safe Upload Session evidence; E.4B requires the exact session-bound immutable document bytes to pass Gate B and binds server-computed SHA-256 plus exact Safe Intake evidence; E.4C derives deterministic server-owned source/job identity by reusing existing orchestration, artifact-lifecycle, and Gate D.3 immutable storage-authority contracts; the final E.4 closure re-verifies E.4C against exact E.4B evidence and proves replay/tamper/cross-finalization convergence.

The **minimum staging vertical slice** is now implemented as the first real provider-backed use of that trust chain. Starting from exact staging E.3C evidence, it persists E.4A reservation and E.4B finalization state, executes Gate B and E.4C, freshly verifies the source/job binding, and writes the exact accepted source bytes create-once under the server-derived immutable key. Exact replay reuses the same session/finalization/job/source identity; different-document reuse, malformed state, symlink state-path escape, payload mismatch, and immutable-source collision fail closed. This remains private staging behavior: public upload, production providers, engine dispatch, and orchestration are still disabled.

The bounded **Controlled staging runtime** now extends that path into provider-backed initial job lifecycle/provenance and read-only planned-state restart recovery. After re-verifying the exact E.4B/E.4C lineage and immutable source bytes, it persists one authenticated create-once job record containing D.1 `planned` revision `0`, D.2 empty idempotency, and D.4 initial provenance evidence for each fixed engine run. A restarted provider can authenticate that exact record, freshly rederive its contracts, and evaluate D.5 `pre_dispatch_candidate` decisions without changing stored state. Queue, worker, state transitions, automatic recovery execution, network dispatch, orchestration, and engine calls remain disabled.

This implementation is **not** a new E.4D/E.4E gate. Future work should extend the real staging path—next toward durable staging job lifecycle and later controlled dispatch—rather than return to open-ended contract micro-gates unless a concrete P1/P2 requires one.

## Secure target flow

```text
External application
        |
        | authenticated/versioned API (not enabled yet)
        v
Safe Upload Session reservation (E.4A)
        |
        | exact immutable document bytes
        v
Safe Intake Session Finalization (E.4B)
PDF/image signature + MIME + bytes + pages + pixels + path safety
        |
        | bounded accepted hash/evidence only
        v
Immutable source artifact + SHA-256/provenance / job binding (E.4C)
        |
        | E.4 convergence verifier
        v
Private staging immutable source persistence
(minimum staging vertical slice)
        |
        | broader job runtime still disabled
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

## Implemented security foundations and bounded staging behavior

- Private internal engine network; no public engine ports.
- Non-root, read-only containers with dropped capabilities and `no-new-privileges`.
- Pinned engine/model revisions and checksum verification where applicable.
- GitHub Actions references pinned to immutable commit SHAs.
- Gateway health/orchestration contracts with public upload and execution disabled.
- Safe Intake Gate B foundation: B.1-B.6, one integrated fail-closed intake decision over exact immutable bytes, and hostile-input convergence coverage.
- Gate C.1/C.2-A-C.2-G internal-dispatch contract foundations plus C-DIAG-1 bounded engine runtime diagnostic redaction and C-DIAG-2 bounded dispatch diagnostic mapping; live dispatch remains disabled.
- Gate D.1-D.6 durable job/artifact state, idempotency, storage-authority, provenance, restart-recovery, and crash-window/partial-output contract/convergence foundations.
- Gate E.1 provider-neutral external-principal authentication foundation.
- Gate E.2 deny-by-default external authorization-decision foundation; allowed decisions still carry no operation-execution authority.
- Gate E.3A provider-neutral authenticated-operation rate-slot reservation foundation; no production rate-state backend or HTTP 429 wiring is activated.
- Gate E.3B provider-neutral external request-idempotency admission foundation; no production durable idempotency backend or live request wiring is activated.
- Gate E.3C fail-closed external admission composition foundation; it evaluates rate admission freshly, binds the exact idempotent request, and detects authority mutation across provider callbacks without granting execution capability.
- Gate E.4A Safe Upload Session reservation foundation; only canonical `platform.safe_upload_session` admission can reserve/replay bounded session evidence.
- Gate E.4B Safe Intake Session Finalization foundation; exact immutable document bytes must pass Gate B under one exact active E.4A session before bounded atomic finalization evidence can exist.
- Gate E.4C Immutable Source / Job Binding foundation; exact E.4B evidence derives deterministic server-owned job/source/storage identity by reusing existing Gate D.3 authority.
- Gate E.4 closure convergence; exact replay converges to one source/job identity and later consumers can reverify E.4C evidence against exact E.4B evidence while valid-shape post-construction substitutions fail closed.
- Minimum staging vertical slice: stateful private staging E.4A/E.4B records and one create-once immutable source filesystem write after exact Gate B/E.4C verification, with replay/conflict/corruption/symlink/collision regressions; no public route or engine execution.
- Controlled staging job lifecycle and planned-state recovery: authenticated create-once initial D.1/D.2/D.4 evidence plus read-only D.5 `pre_dispatch_candidate` decisions for each fixed engine run after immutable source reverification; no queue, worker, transition, dispatch, orchestration, or engine execution authority.
- Immutable candidate/artifact lifecycle contracts.
- Canonical Score, Ensemble comparator/report, and fixed evaluation foundations.
- Candidate Safety v1 for HOMR, Clarity, and Audiveris engine outputs.

The B.4 PDF inspector parses only structural/page evidence. It does not render pages, extract text/images/attachments, execute embedded content, or enable upload. Encrypted PDFs are rejected in the current Safe Intake v1 slice. Immutable PDF `bytes` are passed to the helper without an additional parent-side payload copy; the Linux helper applies a 256 MiB address-space limit and the private Coolify staging Gateway is budgeted at 512 MiB.

The B.5 image inspector accepts only immutable JPEG/PNG bytes, rejects malformed/truncated or animated inputs, derives dimensions from decoded evidence rather than caller metadata, and enforces a 12,000 px per-dimension and 40,000,000 total-pixel ceiling inside a private helper subprocess with a 256 MiB address-space limit and a 3-second timeout. B.5 does not enable public upload or orchestration.

B.6 treats the original filename as metadata only. It rejects unsafe path forms, control/format/surrogate Unicode categories, Windows device aliases, invalid filename shapes, and extensions that disagree with fresh signature-derived format evidence. It never converts the filename into a filesystem or storage path.

`decide_safe_intake()` composes the B.1-B.6 primitives over the same exact immutable `bytes` payload and returns only bounded server-derived evidence after all required checks pass. Existing primitive error categories propagate unchanged. The decision itself does not persist bytes, derive a storage path, accept an HTTP upload, or dispatch work to an engine; the minimum staging writer acts only after subsequent E.4C verification.

## Activation gates still required

The minimum private staging source-ingest slice does not authorize external document upload or live orchestration. Before those capabilities are enabled, the platform still requires at minimum:

1. Extend the controlled staging runtime from authenticated read-only `planned` recovery into a separately reviewed provider-backed transition write while preserving Gate D.1-D.6 crash/replay rules and keeping engine dispatch disabled.
2. Production E.4A and E.4B stateful providers that preserve original session/finalization replay records and exact conflict semantics without TTL/budget widening or document substitution.
3. Separately approved live receiver/dispatch wiring on top of the completed C.1/C.2-A-C.2-G and C-DIAG-1/C-DIAG-2 foundations, with operational credential/replay protections and no security-boundary weakening.
4. A separately reviewed operational persistence layer/provider for durable replay/job/artifact/provenance state, plus queue/worker/process-recovery behavior if activated.
5. Production immutable object storage and retention/restore behavior bound to the existing immutable artifact/provenance contracts.
6. Remaining Gate E controls: provider/runtime authentication wiring, resource/user/tenant scope where applicable, production/runtime rate-limit and idempotency adapters that preserve E.3C exact-request/fresh-rate semantics, edge/anonymous abuse protection, privacy-safe external errors/logs, and explicit versioned route wiring.
7. Teacher Review API with TR-8A RBAC/audit authorization, immutable revisions, and approval-to-publication barrier.
8. Production monitoring, backup/restore, rollback, and supply-chain hardening gates.

## Core principles

1. User input, remote responses, and engine output are untrusted until validated.
2. Original source documents and raw engine outputs remain immutable.
3. No engine may declare its own output to be the final approved score.
4. Unknown or ambiguous musical content is reported, not silently guessed or merged.
5. Teacher approval is separate from candidate generation and comparison.
6. Learner-facing publication requires an explicit approved revision.
7. Security boundaries are enabled before the capability they protect.

## Repository boundaries

ScoreMosaic is not the learner-facing playback, narration, or lesson application. External applications will integrate only through a versioned authenticated and authorized API after the remaining activation gates are demonstrated. The minimum staging slice is private/internal and exposes no public endpoint.

## Development workflow

- Source control: GitHub
- Development environment: GitHub Codespaces
- Automated verification: GitHub Actions
- Integration target: Coolify staging
- Production: blocked until production-readiness gates pass

See `docs/`, `contracts/`, and the service-specific tests for the current architecture and security evidence.
