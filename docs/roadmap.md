# ScoreMosaic Roadmap

Every phase is gated. A later phase must not begin merely because the previous code exists; its acceptance checks must pass first.

## Phase 0 — Foundation

Scope:

- Repository boundaries and architecture
- Security boundaries
- Job and review-report contracts
- Teacher-review workflow
- Empty service specifications
- Safe environment and repository rules

Exit criteria:

- Documents and JSON contracts reviewed
- No real secrets committed
- No engine, model, or production deployment added
- Foundation pull request approved

## Phase 1 — Contract and security core

Scope:

- Versioned API contract
- Strict PDF validation
- Secure XML/MusicXML validation with DTD and external entity processing disabled
- Job state machine
- Artifact naming, hashing, retention, and cleanup rules
- Authentication, authorization, idempotency, rate limits, and safe logging
- Contract tests and threat-model tests

Exit criteria:

- Malformed and hostile PDF/XML fixtures fail safely
- Path traversal and oversized input tests pass
- Secrets are server-side only
- No engine integration required

## Phase 2 — HOMR service

Scope:

- Isolated service adapter
- Pinned runtime and upstream revision
- Health and readiness endpoints
- Time, memory, and file limits
- Immutable candidate output
- Guitar-score benchmark set

Exit criteria:

- Reproducible container build
- Health, timeout, cancellation, and failure tests pass
- Version and license records are present
- No public engine endpoint

## Phase 3 — Clarity-OMR service

Scope and gates mirror Phase 2, with additional model controls:

- Pinned model revision
- Model checksum verification
- Controlled model download or prebuilt image process
- CPU/GPU behavior documented separately

## Phase 4 — Ensemble comparator v1

Scope:

- Safe normalization into a common event model
- Measure alignment
- Structural MusicXML checks
- Pitch, rhythm, rest, chord, voice, staff, and TAB disagreement detection
- Confidence evidence and provenance
- Review-report generation

Non-goal:

- No raw MusicXML merging or automatic correction in v1

Exit criteria:

- Deterministic comparison on fixed fixtures
- Every issue points to source engine evidence
- Unknown or ambiguous cases remain unresolved rather than guessed

## Phase 5 — Teacher review API and editor contract

Scope:

- Review queue
- Issue decisions
- Immutable revisions
- Undo and revision history
- Corrected MusicXML validation
- Approval and rejection records
- Accessibility requirements for the future editor

Exit criteria:

- Original engine artifacts cannot be overwritten
- Every correction records old value, new value, user, reason, and time
- Publishing is blocked without teacher approval

## Phase 6 — Audiveris adapter

Scope:

- Add Audiveris as a third candidate engine
- Compare Coolify Audiveris with the independent Render reference environment
- Preserve `.omr` project output when available

Exit criteria:

- Multiple guitar PDFs pass end-to-end staging tests
- Restart, storage, cancellation, cleanup, and recovery tests pass

## Phase 7 — Coolify production readiness

Scope:

- Staging soak tests
- Backups and restore test
- Monitoring and alerts
- Capacity and concurrency limits
- Production secrets
- Rollback procedure

Exit criteria:

- Production deployment is reproducible
- Restore and rollback are demonstrated
- Render is not removed until Coolify has remained stable through an agreed observation period

## Change-control rule

Each phase uses a dedicated feature branch and pull request. Direct feature work on `main` is prohibited by project policy, even before branch protection is configured.
