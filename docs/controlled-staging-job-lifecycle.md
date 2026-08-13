# Controlled Staging Job Lifecycle

Status: initial provider-backed slice implemented; merge remains separately gated.

## Purpose

This is the first bounded step inside **Controlled staging runtime**. It starts
only after the Minimum Staging Vertical Slice has persisted and reverified the
exact immutable source. It then materializes and persists the existing Gate D
initial evidence for every planned engine run:

- D.1 immutable `planned`, revision `0` job-run state;
- D.2 an empty idempotency ledger bound to the exact dispatch identity;
- D.4 one initial provenance record bound to the exact D.3 source manifest.

The orchestration plan is used only as deterministic contract evidence. It is not
executed.

## Provider behavior

The staging provider writes one authenticated create-once record at the
server-derived job path. Exact replay, including after a provider restart with the
same integrity key, returns the original record without overwrite. A different,
malformed, oversized, incorrectly authenticated, or symlink-redirected record
fails closed.

Source writes, source reads, and lifecycle publication share one job-scoped
filesystem lock. Lifecycle publication additionally holds the verified source
descriptor open and rechecks the canonical source inode, size, and SHA-256 before
the create-once record is linked and again before the lock is released. A source
replacement after an earlier verification therefore cannot publish job evidence.

Before persistence, the boundary:

1. verifies the E.4C binding against the exact E.4B finalization;
2. reads and rechecks the immutable source hash and size;
3. freshly derives the plan, artifact lifecycle, and D.3 manifest;
4. compares their identifiers and hashes with the accepted E.4C evidence;
5. derives D.1, D.2, and D.4 evidence for the fixed engine set.

## Explicit non-activation

This slice does not create or authorize a queue, worker, state transition beyond
`planned`, retry, recovery execution, network request, engine receiver call,
orchestration runtime, OMR engine execution, public route, Candidate Safety
processing, Teacher Review write, approval, or publication.

It is not a new gate or stage and does not change the architecture order. Further
Controlled staging runtime work must be separately bounded and reviewed before
Private OMR orchestration is considered.
