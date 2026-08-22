# ScoreMosaic Stage 8 Current Architecture

Status: **Stage 8 contract + deterministic revision materialization/durable-store foundation**.

Base Stage 7 main before Stage 8: `ce3164f615e05e04181ddfbdcc6bcbdd345f709a`.
Stage 8 contract foundation entered `main` as PR #119 at `2e63bf9ba064adb7ee86dcf95bf8e0cc5958ee61`.

## Position

```text
Stage 7 read-only evidence
  -> Review Report + Canonical identity
  -> exact reviewer authorization decision
  -> closed ScoreEditCommand
  -> stale-parent + semantic old-value preconditions
  -> deterministic teacher musical-state materialization
  -> deterministic validation evidence
  -> immutable draft TeacherScoreRevision identity
  -> append-only audit-chain identity
  -> durable local revision persistence + atomic expected-parent append
  -> restart/hash/chain verification
  -> [LOCKED] corrected MusicXML materialization + round-trip verification
  -> [LOCKED] writable Teacher Review transport/UI activation
  -> [LOCKED] approval
  -> [LOCKED] publication
```

Stage 8 does not mutate Stage 5-7 engine, candidate, Canonical, or Ensemble artifacts. It creates a new teacher-owned evidence lineage only after exact authorization/resource binding. The materialized teacher score is a cloned Canonical projection, never an overwrite of the upstream Canonical artifact.

## Current proof level

Proved at repository contract/hermetic level by PR #119:

- closed authorization evidence contract;
- purpose-separated HMAC integrity for authorization grants;
- exact job/reviewer/report/Canonical/parent bindings;
- closed bounded operation allowlist;
- stable event location requirements;
- deterministic command and revision identities;
- stale-parent fail-closed behavior;
- immutable draft revision record;
- append-only audit predecessor binding;
- approval/publication lock state.

Added by the revision materialization/store slice when its CI gate passes:

- purpose-separated semantic old-value comparison against the current target value;
- deterministic clone-only mutation of supported Canonical musical fields;
- deterministic musical-state SHA-256 identity;
- deterministic validation report/hash with visible blocking issues rather than hidden repair;
- exact parent recheck at materialization;
- local durable SQLite append-only revision evidence;
- atomic expected-parent compare/append under competing writers;
- exact replay convergence and idempotency conflict rejection;
- base-Canonical and audit-predecessor chain continuity;
- restart-time verification of revision/state/validation hashes and the complete reachable parent/audit chain;
- corruption, missing-parent, cycle, orphan, stale-parent, and race fail-closed behavior.

Still not proved or activated:

- external identity provider or session authentication;
- production RBAC policy store;
- public or internal mutation transport;
- production database/object-storage provider;
- complete tie/tuplet and MusicXML derivative validation;
- corrected MusicXML regeneration and Canonical round-trip verification;
- writable editor activation;
- teacher approval/publication.

`write-api-enabled`, `public-api-enabled`, `approval-enabled`, `publication-enabled`, `corrected-musicxml-materialization-enabled`, and `production-durable-store-enabled` remain `false`.

## Next safe Stage 8 slice

Strengthen the revision validator for the remaining contracted musical structures, then implement deterministic corrected-MusicXML derivation from one exact immutable revision, Candidate/MusicXML structural safety checks, Canonical re-normalization, and exact round-trip/revision consistency evidence. No writable UI/API, approval, or publication surface may precede those gates and their required authorization evidence.
