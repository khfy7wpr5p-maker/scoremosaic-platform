# Stage 8-K — Approval Eligibility Contract Foundation

Status: repository/server-only proof target. This stage does **not** approve a score and does not enable publication.

## Purpose

Stage 8-K answers one bounded question: can the exact current immutable Teacher Review revision and its independently rebuilt corrected MusicXML derivative be treated as an **approval candidate**?

Eligibility is evidence only. It is not approval authority.

## Required trust chain

```text
controlled durable RevisionScope
  -> authenticated/reverified current durable head/history
  -> exact current TeacherScoreRevision
  -> exact resulting ReviewMusicalState
  -> deterministic Stage 8-F corrected MusicXML rebuild
  -> exact supplied-vs-rebuilt document equality
  -> exact supplied-vs-rebuilt artifact-record equality
  -> structural-safety + semantic-round-trip evidence
  -> validation issue-count equality
  -> deterministic ApprovalEligibilityEvidence
  -> [LOCKED] approval grant
  -> [LOCKED] publication
```

## Fail-closed identity requirements

The builder accepts only:

- the exact current durable revision head for the supplied `RevisionScope`;
- a persisted revision whose complete record equals the caller-supplied immutable revision;
- the exact musical state bound by that revision;
- an exact Stage 8-F artifact whose MusicXML bytes and artifact record equal a fresh deterministic rebuild from the same revision/state pair.

Historical/stale revisions, missing heads, persistence mismatches, state mismatches, artifact document substitutions, artifact record substitutions, or scope/hash mismatches fail closed and produce no eligibility evidence.

## Eligibility policy

A fully verified current candidate is `candidateEligible=true` only when both stored validation counts are zero:

- `blockingIssueCount == 0`
- `unresolvedIssueCount == 0`

Otherwise the evidence remains valid but reports `candidateEligible=false` with the closed reasons `BLOCKING_ISSUES_PRESENT` and/or `UNRESOLVED_ISSUES_PRESENT`.

This policy never silently repairs musical state and never converts unresolved evidence into authority.

## Locked authority

Every Stage 8-K evidence object fixes these fields to false:

- `approvalGranted`
- `publicationGranted`
- `mutationGranted`
- `writeGranted`
- `authoritativeTruth`

The Stage 8-F corrected artifact itself remains `status=draft`, `immutable=true`, `approvalEligible=false`, and `publicationEligible=false`. Stage 8-K does not mutate that artifact or its revision lineage.

`approval-eligibility-foundation-enabled=true` therefore means only that the repository can derive bounded eligibility evidence. `approval-enabled=false` and `publication-enabled=false` remain authoritative activation locks.

## Exclusions

Stage 8-K does not introduce:

- approval authorization or an approval signature;
- approval persistence or approval state transitions;
- publication eligibility or publication transport;
- public/internal HTTP routes;
- browser mutation;
- production identity/session/RBAC providers;
- production durable/object storage;
- audio/MIDI/SoundFont execution;
- network, subprocess, clock, or renderer authority.

## Verification requirements

Before merge, exact-head CI must prove:

- deterministic repeated eligibility evidence;
- exact current-head and full persisted-revision binding;
- stale historical revision rejection;
- independent corrected-artifact rebuild equality;
- document and record substitution rejection;
- zero-issue candidate eligibility;
- blocking/unresolved issue ineligibility;
- sealed evidence construction;
- closed JSON Schema and false authority markers;
- existing Stage 8-A through Stage 8-J regressions;
- no live route/runtime dependency activation;
- clean diff and zero unresolved review threads.

## Safe continuation

After Stage 8-K merges, actual approval must remain a separate gate. A later approval stage would require purpose-separated authorization, exact current Stage 8-K evidence identity, immutable approval record semantics, replay/idempotency protection, audit lineage, and explicit continued separation from publication.
