# Gate C.2-F — Dispatch Timeout & Cancellation Decision Foundation

Status: contract foundation only. No live timer, cancellation signal, engine execution, route, network dispatch, retry, or persistent state is enabled.

## Purpose

Gate C.2-F converts the timeout and cancellation policy already fixed by the immutable Gateway orchestration plan into one deterministic, fail-closed result-acceptance decision boundary.

It composes only already-accepted evidence:

- one exact verified orchestration plan;
- one C.2-E `VerifiedDispatchRequest` bound to that plan and engine run;
- one receiver-owned dispatch-start monotonic timestamp;
- later receiver-owned monotonic observations;
- an optional receiver-owned cancellation-request monotonic timestamp;
- an optional prior C.2-F decision supplied by a future trusted state boundary.

The output is policy evidence only. It does not start a clock, schedule work, terminate a process, contact an OMR engine, persist lifecycle state, or authorize execution.

## Existing orchestration policy remains authoritative

C.2-F does not redefine the orchestration contract. It derives its policy from the exact verified v1 plan:

- each engine timeout is 30–7200 seconds;
- timeout accounting uses a monotonic clock;
- timeout accounting starts at dispatch;
- cancellation grace is 0–300 seconds;
- timeout is terminal;
- `retryAfterTimeout` is `false`;
- every run has `attemptLimit = 1`.

A plan that does not satisfy the existing deterministic orchestration verifier is rejected before C.2-F context creation.

## Exact dispatch binding

`build_dispatch_deadline_context()` accepts only a C.2-E `VerifiedDispatchRequest` and reconstructs the expected C.2-C dispatch identity from one detached verified orchestration-plan snapshot.

The exact plan, plan SHA-256, job, run, engine, source/candidate/artifact identity, and C.2-E target engine must converge. A modified job, run, engine, plan, or other dispatch identity fails closed as `dispatch_identity_mismatch`.

Timeout duration and cancellation grace are read from the verified plan. C.2-F does not accept caller-supplied replacement timeout or retry values.

## Monotonic time representation

C.2-F uses integer monotonic nanoseconds only.

The accepted range is:

```text
0 .. 2^63 - 1
```

Booleans, negative values, non-integers, values above the bound, observations before dispatch start, future cancellation timestamps, and deadline arithmetic overflow fail closed.

Integer nanoseconds make the timeout boundary exact without wall-clock, timezone, floating-point, or rounding semantics.

C.2-F does not read a clock itself. A future runtime boundary must supply monotonic observations from one consistent clock source.

## Timeout boundary

For one run:

```text
timeoutDeadline = dispatchStarted + timeoutSeconds
```

Result acceptance is exact:

```text
observed < timeoutDeadline  -> active     -> result may be considered
observed >= timeoutDeadline -> timed_out  -> result must be rejected
```

The exact timeout deadline is therefore terminal. There is no one-tick or grace-period acceptance window at the boundary.

## Cancellation boundary

A valid cancellation request before the timeout deadline is terminal immediately at its cancellation timestamp:

```text
cancelRequested < timeoutDeadline -> cancelled
```

If cancellation is first recorded exactly at the timeout deadline or later, timeout wins:

```text
cancelRequested >= timeoutDeadline -> timed_out once deadline is reached
```

This precedence avoids a cancellation event at or after expiry rewriting an already-expired run as a different terminal outcome.

## Cancellation grace is cleanup-only

The orchestration plan's `cancellationGraceSeconds` is represented as a cleanup deadline after a terminal timeout or cancellation decision:

```text
cleanupDeadline = terminalTime + cancellationGraceSeconds
```

The cleanup deadline is future runtime evidence only. It may later bound cooperative shutdown before a process-kill policy exists.

It does **not**:

- extend result acceptance;
- reopen a cancelled run;
- reopen a timed-out run;
- authorize a late engine result;
- create a retry window.

A result received at any point after a terminal cancellation or timeout remains unacceptable even while cleanup grace is still in progress or after cleanup grace has ended.

## Terminal monotonicity

`DispatchDeadlineDecision` has only three states:

```text
active
cancelled
timed_out
```

`cancelled` and `timed_out` are terminal. There is no `running`, `completed`, retry, or success transition in this C.2-F decision contract.

When a future trusted state boundary supplies a valid prior terminal C.2-F decision, later observations preserve that exact terminal status. The decision cannot reopen as `active`.

A prior decision with different plan/job/run/engine/dispatch identity, malformed terminal fields, or regressing observation time fails closed.

C.2-F does not persist prior decisions. Durable lifecycle/event state remains later work.

## Result acceptance guard

`require_dispatch_result_acceptance()` accepts only an exact context/decision identity pair whose decision is still `active`.

It rejects:

- `cancelled`;
- `timed_out`;
- mismatched plan/job/run/engine identity;
- malformed or forged decision shape;
- an active decision observed at or beyond the timeout deadline.

This is a policy guard only. Future result processing must still perform the existing C.2-C/C.2-D authenticated result verification and later artifact/candidate safety gates.

## Safe diagnostics

C.2-F context and decision objects may expose only non-secret policy evidence such as:

- contract version;
- plan ID and plan SHA-256;
- dispatch identity SHA-256;
- job/run/engine identity;
- timeout and grace values;
- monotonic start/deadline/observation values;
- terminal status;
- result-acceptance boolean;
- fixed attempt/retry policy.

They contain no credential, C.2-A request signature, C.2-D generation signature, raw request body, result bytes, provider diagnostic, hostname, or production secret.

## Regression evidence

The C.2-F regression suite covers at least:

- exact C.2-E verified-run binding;
- immutable context construction;
- `attemptLimit = 1` and `retryAfterTimeout = false`;
- active result acceptance one nanosecond before timeout;
- terminal timeout exactly at the deadline;
- late result rejection during and after cleanup grace;
- pre-timeout cancellation becoming immediately terminal;
- cancellation grace never reopening result acceptance;
- timeout precedence at an exact cancellation/deadline tie;
- terminal decisions never reopening;
- job/run/engine identity mismatch rejection;
- bool, negative, out-of-range, future, regressing, and overflow time evidence rejection;
- exact context/decision identity required by the result-acceptance guard.

The initial tests-only commit intentionally fails because `scoremosaic_gateway.dispatch_deadline` does not yet exist. This RED evidence demonstrates the gap before the additive implementation.

## Explicit non-activation

Gate C.2-F does **not**:

- register or activate `/internal/transcribe`;
- add or modify an HTTP handler;
- read a runtime clock directly;
- create a timer, thread, scheduler, queue, worker, signal, subprocess, process-kill action, or cleanup action;
- send a network request;
- execute HOMR, Audiveris, or Clarity;
- enable orchestration;
- implement bounded retry;
- persist run state, terminal decisions, or cancellation events;
- create Redis, Postgres, SQLite, or another durable store;
- provision or rotate production credentials;
- authorize production dispatch targets;
- add upload, Teacher Review, approval, publication, or learner playback behavior.

After C.2-F, timeout/cancellation semantics have one deterministic decision boundary, but actual timeout enforcement and cancellation delivery remain disabled until later controlled runtime and durable-state gates are explicitly approved.
