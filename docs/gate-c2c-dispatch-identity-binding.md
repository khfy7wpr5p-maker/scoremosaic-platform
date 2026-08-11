# Gate C.2-C — Dispatch Job / Source / Run / Result Identity Binding Foundation

## Status

Contract foundation only. This slice does not enable orchestration, engine execution, persistence, storage, or network dispatch.

Gate C.2-C closes the semantic identity gap between the existing deterministic Gateway orchestration plan and the already-merged Gate C.2-A authenticated request envelope / Gate C.2-B exact dispatch target foundation.

The purpose is to ensure that a valid authenticated request cannot be treated as authorization for a different job, source artifact, engine run, candidate, or reserved result-artifact slot.

## Dispatch identity source of truth

A dispatch identity is derived only from an orchestration plan that passes the existing exact deterministic `verify_orchestration_plan()` verifier.

For exactly one planned engine run, the identity binds:

- orchestration `planId`;
- orchestration `planSha256`;
- `jobId`;
- immutable source artifact ID;
- server-controlled source artifact reference;
- source SHA-256;
- source byte size;
- source media type;
- engine `runId`;
- exact engine identity;
- `candidateId`;
- candidate namespace;
- expected MusicXML artifact ID;
- expected diagnostic artifact ID.

The identity is immutable in memory and serialized to one closed canonical JSON control payload. The canonical payload has a bounded maximum size and a deterministic SHA-256 identity digest.

## Relationship to C.2-A and C.2-B

The C.2-C canonical identity payload is the exact payload that must be covered by the existing C.2-A payload length/SHA-256/signature metadata when this contract is used for a future private dispatch.

The validation order is:

1. verify the existing orchestration plan exactly;
2. derive one expected C.2-C identity for the planned engine;
3. validate the existing C.2-B target and envelope metadata relationship;
4. require the exact received control payload bytes to equal the canonical C.2-C identity payload;
5. require the C.2-A envelope payload length and SHA-256 to match those exact bytes;
6. at an actual receiver, separately run the existing C.2-A cryptographic signature, timestamp, and replay verification before accepting the request.

C.2-C does not replace C.2-A cryptographic verification. `require_authenticated_dispatch_identity()` is a semantic identity check and deliberately does not read credentials or reserve replay nonces.

## Result identity

The foundation also defines a pure result-identity claim for exact returned bytes.

A result identity repeats the trusted dispatch lineage and additionally binds:

- the C.2-C dispatch identity SHA-256;
- exact result payload byte length;
- exact result payload SHA-256.

A result is rejected unless its plan, job, source, run, engine, candidate, namespace, expected artifact IDs, dispatch identity digest, byte length, and payload digest match the trusted dispatch identity.

This is identity/integrity evidence only. It does not declare returned engine content safe, correct, canonical, or approved. Candidate Safety and later artifact lifecycle / durable-state gates remain authoritative for their own boundaries.

## Fail-closed regression evidence

The focused regression suite covers:

- deterministic identity generation for Audiveris, HOMR, and Clarity;
- signed control payload matching the exact planned run;
- signed payload from another job;
- source SHA-256 swap;
- cross-engine run identity;
- run ID swap;
- candidate ID/namespace swap;
- MusicXML artifact ID swap;
- diagnostic artifact ID swap;
- malformed run identifiers;
- duplicate artifact identities;
- tampered orchestration plans;
- authenticated-envelope payload digest mismatch;
- result from another dispatch/run;
- result artifact identity tamper;
- exact returned-result byte tamper.

## Explicit non-activation

This slice does not:

- register `/internal/transcribe` in any engine;
- send a network request;
- enable `SCOREMOSAIC_GATEWAY_ORCHESTRATION_MODE`;
- create jobs, queues, workers, retry loops, or cancellation handlers;
- add persistence, database, object storage, or workspace writes;
- add persistent replay storage or credential-rotation grace semantics;
- provision production credentials or production engine origins;
- modify Candidate Safety behavior;
- modify Canonical Score, Ensemble, Teacher Review, approval, or publication behavior;
- claim that result bytes are safe MusicXML.

## Remaining Gate C work

After C.2-C, Gate C still requires separately reviewed work for:

- persistent replay and credential-rotation semantics;
- live receiver wiring;
- timeout and cancellation enforcement;
- bounded retry policy and implementation;
- safe diagnostic/error convergence;
- final controlled activation evidence.

Gate D durable job/artifact state remains a later gate and is not implemented by this contract foundation.
