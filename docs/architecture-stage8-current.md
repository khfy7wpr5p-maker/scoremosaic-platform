# ScoreMosaic Stage 8 Current Architecture

Status: **Stage 8 contract foundation**.

Base Stage 7 main before this work: `ce3164f615e05e04181ddfbdcc6bcbdd345f709a`.

## Position

```text
Stage 7 read-only evidence
  -> Review Report + Canonical identity
  -> exact reviewer authorization decision
  -> closed ScoreEditCommand
  -> stale-parent precondition
  -> immutable draft TeacherScoreRevision identity
  -> validation evidence binding
  -> append-only audit-chain identity
  -> [LOCKED] durable revision persistence
  -> [LOCKED] corrected MusicXML materialization
  -> [LOCKED] approval
  -> [LOCKED] publication
```

Stage 8 does not mutate Stage 5-7 engine, candidate, Canonical, or Ensemble artifacts. It creates a new teacher-owned evidence lineage only after exact authorization/resource binding.

## Current proof level

Proved at repository contract/hermetic level:

- closed authorization evidence contract;
- purpose-separated HMAC integrity for authorization grants;
- exact job/reviewer/report/Canonical/parent bindings;
- closed bounded operation allowlist;
- stable event location requirements;
- closed old-value hash precondition field and command binding;
- deterministic command and revision identities;
- semantic old-value comparison and musical-state mutation remain deferred to the next validation/materialization slice;
- stale-parent fail-closed behavior;
- immutable draft revision record;
- append-only audit predecessor binding;
- approval/publication lock state.

Not proved or activated:

- external identity provider or session authentication;
- production RBAC policy store;
- cross-process durable atomic revision-head compare-and-swap;
- production DB/object storage;
- public or internal mutation transport;
- MusicXML regeneration and round-trip validation;
- teacher approval/publication.

## Next safe Stage 8 slice

The next implementation slice should add deterministic revision materialization/validation against the Canonical model plus a durable append-only revision store with atomic expected-parent semantics. No writable UI or public route should precede those gates.
