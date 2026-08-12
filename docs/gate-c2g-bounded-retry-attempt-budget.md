# Gate C.2-G — Bounded Retry / Attempt-Budget Enforcement Foundation

## Purpose

Gate C.2-G converts the already-approved orchestration v1 attempt policy into a deterministic, fail-closed decision boundary.

It does **not** introduce a new retry capability. The existing orchestration v1 contract is authoritative:

- each engine run has `attemptLimit = 1`;
- `retryAfterTimeout = false`;
- `completed`, `failed`, `cancelled`, and `timed_out` are terminal.

Therefore the bounded retry policy for v1 is intentionally:

```text
1 total execution attempt
=
0 retry attempts
```

A future proposal to permit attempt 2 or higher would change the orchestration contract and must be reviewed as a separate architecture/security change. C.2-G does not make that change.

## Contract files

```text
services/omr-gateway/src/scoremosaic_gateway/dispatch_retry.py
services/omr-gateway/tests/test_dispatch_retry.py
```

This foundation is additive. It does not modify the existing C.2-E receiver verification, C.2-F deadline/cancellation logic, orchestration contract, application routes, engine clients, or deployment configuration.

## Trust chain

C.2-G consumes already-validated security context rather than creating new authority:

```text
immutable orchestration plan
        +
C.2-E VerifiedDispatchRequest
        +
C.2-F DispatchDeadlineContext
        ↓
DispatchAttemptBudget
        ↓
terminal attempt evidence
        ↓
DispatchRetryDecision
```

The output decision can deny retry. It cannot start work, enqueue work, schedule work, select another credential, create a new run, or authorize network dispatch.

## Exact identity binding

A `DispatchAttemptBudget` is bound to the same exact:

- `planId`
- `planSha256`
- dispatch identity SHA-256
- `jobId`
- `runId`
- engine

already established by C.2-C, C.2-E, and C.2-F.

Budget construction fails closed when:

- the orchestration plan is not the exact verified deterministic v1 shape;
- the C.2-E verified request does not match the exact plan/run;
- the C.2-F deadline context belongs to another plan/job/run/engine;
- the orchestration plan attempts to widen `attemptLimit`;
- the timeout policy attempts to enable retry after timeout.

No caller-supplied URL, credential, next-run identifier, candidate identifier, or artifact identifier is accepted by this contract.

## Attempt-number rule

The only valid v1 attempt number is:

```text
1
```

The pure validator rejects:

- booleans;
- zero;
- negative values;
- attempt number 2 or higher.

Attempt number 2 or higher fails with an exhausted-budget decision category. C.2-G never derives a new run identity from that request.

The validator does not start the first attempt. It only proves whether an attempt number is within the immutable v1 budget.

## Terminal-state policy

The closed terminal vocabulary is:

```text
completed
failed
cancelled
timed_out
```

Every one of these states is non-retryable in orchestration v1.

The deterministic result is always:

```text
retryAllowed = false
nextAttemptNumber = null
attemptsRemaining = 0
reasonCategory = retry_prohibited_by_v1_attempt_budget
```

Nonterminal or invented values such as `planned`, `queued`, `dispatching`, `running`, `active`, or `retrying` cannot enter the terminal retry-decision path.

## Relationship to C.2-F

C.2-F already makes timeout and cancellation terminal for result acceptance.

C.2-G provides a narrow adapter that accepts only C.2-F decisions whose status is:

- `cancelled`, or
- `timed_out`,

and whose exact plan/job/run/engine identity matches the C.2-G budget.

An active C.2-F decision is not terminal attempt evidence.

This preserves the invariant:

```text
C.2-F terminal decision
→ no result acceptance
→ no C.2-G retry
→ no reopened execution
```

Cancellation grace remains cleanup-only. It does not create an additional retry window.

## Completed and failed evidence

The orchestration contract already defines `completed` and `failed` as terminal states. C.2-G can normalize those closed terminal labels into non-retryable evidence bound to the exact budget identity.

This foundation does not create or persist lifecycle state. A future live system must obtain `completed` or `failed` from its authoritative durable lifecycle/state mechanism before using that evidence operationally.

Because C.2-G can only deny retry, fabricated terminal evidence cannot grant an additional execution attempt. Durable lifecycle authority remains outside this package.

## Safe diagnostics

C.2-G exposes bounded safe dictionaries containing only non-secret identity/policy evidence such as:

- plan/job/run/engine identifiers;
- attempt number and limit;
- terminal status;
- retry boolean;
- remaining-attempt count;
- stable reason category.

It does not expose or retain:

- credential secrets;
- HMAC signatures;
- request nonces;
- authorization headers;
- raw payload bytes;
- provider errors;
- engine response bodies.

Safe decision evidence also contains no `nextRunId`, candidate ID, or artifact ID because C.2-G is not permitted to create another execution identity.

## Explicit non-activation

C.2-G does **not**:

- register or activate `POST /internal/transcribe`;
- send a network request;
- execute HOMR, Audiveris, or Clarity;
- enable orchestration mode;
- create a queue or scheduler;
- create a retry worker;
- implement exponential backoff;
- sleep or create timers;
- create attempt 2;
- generate a new run/candidate/artifact identity;
- persist retry counters or lifecycle state;
- create Redis, Postgres, SQLite, or another state store;
- provision production credentials or engine targets;
- enable upload, Teacher Review, approval, or publication.

## Gate D boundary

Durable job state, idempotency, restart recovery, persisted cancellation/retry evidence, and crash-window handling remain Gate D responsibilities.

C.2-G deliberately contains no durable counter. A future state store must preserve the exact v1 budget and must not reinterpret restart/recovery as permission to create attempt 2.

If a future architecture wants recoverable multi-attempt retries, that work must first define a separately approved versioned attempt/identity/idempotency model rather than silently widening this v1 contract.

## Regression requirements

C.2-G acceptance evidence includes tests proving that:

- the budget is bound to the exact verified plan/job/run/engine;
- the budget is immutable and fixes `attemptLimit = 1`;
- `retriesRemaining = 0`;
- attempt number 1 is the only allowed attempt number;
- bool, zero, negative, and attempt 2+ values fail closed;
- `completed`, `failed`, `cancelled`, and `timed_out` are all non-retryable;
- nonterminal/unknown states are rejected;
- wrong job/run/engine terminal evidence is rejected;
- C.2-F timeout cannot reopen execution through retry;
- C.2-F cancellation cannot reopen execution through retry;
- active C.2-F evidence cannot enter the terminal path;
- widening orchestration `attemptLimit` is rejected;
- safe decision evidence creates no next run/candidate/artifact identity;
- no credential, signature, nonce, or other authentication proof enters safe retry evidence.

## Exit condition

C.2-G is a contract foundation only. Its completion does not activate dispatch.

Gate C still requires safe diagnostic/error convergence and final controlled activation evidence. Live orchestration remains disabled until all required Gate C controls, Gate D durable-state requirements, and the separate activation gate are satisfied.
