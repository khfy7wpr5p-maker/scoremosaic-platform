# Controlled Staging Job Lifecycle

Status: initial provider-backed lifecycle and read-only planned-state recovery implemented.

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

After a provider restart, the recovery boundary reads the authenticated record
under the same source/job lock, freshly rederives the exact plan, lifecycle,
D.1/D.2/D.3/D.4 evidence, and requires exact record content before evaluating
Gate D.5. Every current run is restored only as `planned`, revision `0`, with
disposition `pre_dispatch_candidate` and all execution, retry, network-dispatch,
and state-mutation authority false.

## Provider behavior

The staging provider writes one authenticated create-once record at the
server-derived job path. Exact replay, including after a provider restart with the
same integrity key, returns the original record without overwrite. A different,
malformed, oversized, incorrectly authenticated, or symlink-redirected record
fails closed.

Source writes, source reads, and lifecycle publication share one job-scoped
filesystem lock. Lifecycle publication additionally holds the verified source
descriptor open and rechecks the canonical source inode, size, and SHA-256 before
the create-once record is linked and immediately after linking. If the source
changes in that check-to-link window, the provider removes and syncs the exact
newly linked lifecycle inode before failing closed. A source replacement after an
earlier verification therefore cannot leave published job evidence behind.

Before persistence, the boundary:

1. verifies the E.4C binding against the exact E.4B finalization;
2. reads and rechecks the immutable source hash and size;
3. freshly derives the plan, artifact lifecycle, and D.3 manifest;
4. compares their identifiers and hashes with the accepted E.4C evidence;
5. derives D.1, D.2, and D.4 evidence for the fixed engine set.

## Explicit non-activation

This slice does not create or authorize a queue, worker, state transition beyond
`planned`, transition write, retry, automatic recovery execution, network
request, engine receiver call,
orchestration runtime, OMR engine execution, public route, Candidate Safety
processing, Teacher Review write, approval, or publication.

It is not a new gate or stage and does not change the architecture order. Further
Controlled staging runtime work must add provider-backed transition writes in a
separately bounded and reviewed change before Private OMR orchestration is
considered.
