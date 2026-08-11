# Gate C.2-B — Engine Dispatch Target Allowlist Contract Foundation

## Status

Contract foundation only. This slice does not enable orchestration or engine execution.

Gate C.2-B binds the existing C.1 service identity and C.2-A authenticated request envelope to one exact private engine dispatch target before signing can proceed.

## Exact current allowlist

The contract accepts the current private test/staging foundations only:

| Engine | Audience identity | Exact origin | Method | Exact path |
|---|---|---|---|---|
| Audiveris | `scoremosaic-audiveris-foundation` | `http://audiveris-foundation:8082` | `POST` | `/internal/transcribe` |
| HOMR | `scoremosaic-homr-foundation` | `http://homr-foundation:8080` | `POST` | `/internal/transcribe` |
| Clarity | `scoremosaic-clarity-foundation` | `http://clarity-foundation:8081` | `POST` | `/internal/transcribe` |

`production` is deliberately not present in the dispatch-origin allowlist. Production dispatch therefore fails closed until a separate reviewed production target update and activation gate are approved.

The `/internal/transcribe` path is a reserved contract target only. This slice does not register that route in any engine service.

## Fail-closed ordering

A future private dispatch adapter must preserve this order:

1. validate the exact `EngineEndpoint` structure;
2. validate C.1 binding-to-engine identity;
3. require an environment-specific allowlisted origin;
4. require the fixed dispatch method/path;
5. only then use C.2-A request signing;
6. at the receiver, require the received method/path to match the signed envelope before replay reservation.

The helper `sign_authenticated_dispatch_request()` performs target allowlist validation before C.2-A signing reads credential bytes. Callers cannot supply an arbitrary dispatch method or route to that helper.

## Rejection evidence

Regression coverage includes:

- unknown engine;
- cross-engine identity binding;
- cross-engine origin confusion;
- unknown hostname;
- wrong port or scheme;
- credentials/path/query/fragment or malformed port in an origin;
- production target absence;
- valid signed envelope aimed at a non-allowlisted path;
- method mismatch;
- cross-engine envelope mismatch;
- allowlist failure before credential secret access;
- non-secret diagnostics.

## Explicit non-activation

This slice does not:

- change `SCOREMOSAIC_GATEWAY_ORCHESTRATION_MODE=disabled`;
- send any network request;
- create `/internal/transcribe` handlers;
- enable upload, conversion, jobs, storage, persistence, or publication;
- provision production credentials;
- add persistent replay state;
- define credential-rotation grace semantics;
- authorize a production origin;
- activate HOMR, Clarity, or Audiveris dispatch.

Later Gate C slices still need live receiver wiring, durable replay handling, job/source/result identity binding, timeout/cancellation enforcement, bounded retry, and safe diagnostic/error convergence before private orchestration can be considered for a separate activation decision.
