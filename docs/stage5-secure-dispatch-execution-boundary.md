# Stage 5 Secure Dispatch and Engine Execution Boundary

Status: **Stage 5-B3b implementation contract**  
Scope: controlled staging only  
Production activation: **not authorized**

This document records the trust-boundary and recovery semantics for the Stage 5 Gateway → engine path. It supplements older roadmap text that predates merged PRs #102–#114. Repository code, merged contracts and fresh CI evidence remain authoritative when older roadmap prose conflicts.

## Current Stage 5 chain

1. immutable source intake and durable job identity;
2. canonical orchestration plan;
3. Dispatch Input Capsule v1;
4. atomic `queued(1) -> dispatching(2)` arbitration;
5. authenticated trusted-plan provisioning;
6. authenticated dispatch receiver acceptance;
7. authenticated immutable source delivery;
8. authenticated one-shot engine execution trigger;
9. bounded engine execution metadata handoff.

Stage 5 ends at step 9. **Result bytes are not returned to the Gateway and are not persisted as candidates by this stage.** Result ingestion is a Stage 6 authority boundary.

## Trust boundaries

Every network-delivered plan, identity and source is untrusted until its owning receiver verifies it. Private networking is routing, not authentication.

The Gateway may reach an engine execution route only when all of the following converge:

- exact allowlisted staging engine origin;
- verified immutable Dispatch Input Capsule;
- exact authenticated control-dispatch result;
- exact authenticated source-delivery result;
- the HMAC-sealed Gateway source-delivery claim is present and valid;
- durable revision 2 is still exactly `dispatching`;
- restart policy is reconciliation-only;
- exact plan/run/candidate/source identity converges;
- a purpose-separated execution credential generation resolves;
- the request is canonical, bounded and HMAC authenticated.

No caller-controlled URL, hostname, filesystem path, redirect target, proxy route or retry policy is accepted.

## Side-effect ordering

Stage 5-B3b uses this order:

1. validate endpoint and capsule without side effects;
2. converge dispatch and source-delivery evidence;
3. re-open and authenticate the durable source-delivery claim;
4. re-open and authenticate durable `dispatching(2)` state;
5. derive exact planned timeout and candidate identity;
6. resolve the purpose-separated execution credential;
7. deterministically serialize and sign the execution request;
8. atomically create the Gateway execution-trigger claim;
9. perform exactly one direct HTTP `POST /internal/execute`;
10. accept only strict bounded metadata-only execution evidence.

Wrong plan/source/job/run/engine/target/durable evidence therefore fails before the execution-trigger claim and before network I/O.

The execution-trigger claim is intentionally written **before** network I/O. After that point a connection failure, timeout, malformed response, redirect, receiver failure, lost response or process crash is ambiguous. The request is never automatically repeated.

## Authentication domain separation

Execution uses a credential namespace distinct from provisioning, dispatch and source delivery:

`scoremosaic-authenticated-execution-trigger-v1:staging:scoremosaic-omr-gateway:<engine>:<audience>`

The authenticated message covers contract version/environment, caller identity, exact engine/audience, credential key/generation, exact method/path, timestamp, nonce, payload byte length, payload SHA-256 and exact canonical request bytes.

Secret values, raw credentials and signatures are not stored in durable state or safe result views. Safe request diagnostics expose only a nonce digest and signature presence; never the raw nonce or signature.

## Network safety

- origin must equal the staging allowlist;
- method is fixed to `POST`;
- path is fixed to `/internal/execute`;
- redirects are rejected;
- no caller URL is accepted;
- no proxy abstraction is used;
- connection timeout is fixed and bounded;
- response timeout is deterministically tied to verified orchestration `timeoutSeconds` plus fixed transport grace;
- response bytes are capped at 16 KiB;
- unexpected/duplicate response fields fail closed;
- `resultReturnAllowed=true` or `resultPersistenceAllowed=true` fails closed.

The orchestration execution timeout remains 30–7200 seconds. It is not silently shortened to the control-plane 30-second timeout because that would manufacture routine ambiguous executions.

## Durable state and restart semantics

Revision 2 is a hard rollback/recovery boundary. `queued(1) -> dispatching(2)` competes with terminal cancellation for the same revision slot. Once `dispatching(2)` exists, automatic network resend or engine re-execution is forbidden.

The Gateway additionally stores create-once HMAC-sealed claims for source delivery and execution trigger. An existing exact execution-trigger claim means **reconciliation required**, not safe retry. Missing, replaced, corrupt or MAC-invalid durable prerequisites fail closed.

Older code that cannot understand `dispatching(2)` plus these one-shot claims must not resume or mutate the same durable state.

## Metadata-only Stage 5 response

A successful Stage 5 execution response may contain only bounded safe metadata: exact identity bindings, execution claim hash, output count, output byte sizes, output SHA-256 values and explicit one-shot/restart policy flags.

It must not contain output bytes or authorize result persistence. Any privilege escalation or schema confusion is rejected while the already-created execution claim remains a reconciliation fence.

## Required Stage 5-B3b tests

- 10-repeat deterministic request bytes/signature;
- wrong source identity before credential/network;
- non-allowlisted SSRF destination before credential/network;
- missing durable `dispatching(2)` state;
- missing/tampered source-delivery claim;
- transport ambiguity and restart/retry prohibition;
- redirect rejection;
- response privilege-escalation rejection;
- bounded metadata-only response validation;
- concurrency with exactly one network winner.

Existing Stage 5 suites continue to own malformed framing, duplicate metadata, credential rotation, replay, source receiver, dispatch/cancellation race, engine execution sandbox/output bounds and receiver fail-closed behavior.

## Stage boundary

Authorized by Stage 5-B3b:

`verified capsule + durable dispatching + authenticated source evidence`
` -> one authenticated one-shot engine execution request`
` -> bounded metadata-only execution evidence`

Locked until Stage 6:

- engine output byte retrieval;
- engine-result schema parsing;
- result artifact persistence;
- candidate persistence;
- partial-success convergence across engines.

Still locked:

- production activation;
- arbitrary external engine destinations;
- automatic retry of ambiguous execution;
- engine/AI output becoming authoritative score state;
- teacher publication or UI-driven authoritative mutation.
