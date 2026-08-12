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

A monotonic clock is required to be **nondecreasing**, not strictly increasing on every read. Consecutive valid observations may therefore carry the same nanosecond value. C.2-F treats only a strictly smaller later timestamp as time regression; equality alone is not regression evidence.

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

A cancellation request may validly have the **same monotonic timestamp** as the most recent non-terminal active observation. Equal-tick evidence is accepted because monotonic clocks need not advance between consecutive reads. Only a cancellation timestamp strictly earlier than the prior observation is rejected as `cancellation_time_regression`.

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

A prior decision with different plan/job/run/engine/dispatch identity, malformed terminal fields, or strictly regressing observation time fails closed. A cancellation timestamp strictly earlier than an already-observed active decision also fails closed rather than retroactively rewriting history; equality is permitted as valid nondecreasing monotonic evidence.

C.2-F does not persist prior decisions. Durable lifecycle/event state remains later work.

## Result acceptance guard

`require_dispatch_result_acceptance()` never treats a previously issued `active` decision as sufficient evidence by itself. The caller must provide a **fresh result-arrival monotonic observation** from the same receiver-owned monotonic clock source. The guard re-evaluates the supplied prior decision at that arrival time before result processing may continue.

An optional fresh cancellation-request monotonic timestamp may also be supplied at result arrival. If that evidence makes the run cancelled, or if the fresh arrival observation reaches or passes the timeout deadline, the guard fails closed as `dispatch_result_not_acceptable`.

Therefore a stale pre-timeout `active` decision cannot authorize a result that actually arrives at or after timeout. If the refreshed decision remains active, the guard returns that refreshed active decision for downstream policy evidence.

The guard rejects:

- `cancelled`;
- `timed_out`;
- a stale `active` decision whose fresh result-arrival observation is now timed out or cancelled;
- mismatched plan/job/run/engine identity;
- malformed or forged decision shape;
- strictly regressing or otherwise invalid fresh monotonic evidence.

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
- stale pre-timeout active evidence cannot authorize a result arriving at the timeout boundary;
- fresh cancellation evidence at result arrival is applied before result acceptance;
- equal-tick cancellation after an active observation is valid nondecreasing monotonic evidence;
- late result rejection during and after cleanup grace;
- pre-timeout cancellation becoming immediately terminal;
- cancellation grace never reopening result acceptance;
- timeout precedence at an exact cancellation/deadline tie;
- terminal decisions never reopening;
- job/run/engine identity mismatch rejection;
- bool, negative, out-of-range, future, strictly regressing, and overflow time evidence rejection;
- exact context/decision identity required by the result-acceptance guard.

The initial tests-only commit intentionally fails because `scoremosaic_gateway.dispatch_deadline` does not yet exist. This RED evidence demonstrates the original gap before the additive implementation. A later focused RED regression demonstrates that the original result guard lacked fresh result-arrival monotonic evidence before that flaw was remediated. A further focused RED regression demonstrates that rejecting equal-tick cancellation as regression was incorrect before the comparison was narrowed to strictly earlier timestamps.

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
