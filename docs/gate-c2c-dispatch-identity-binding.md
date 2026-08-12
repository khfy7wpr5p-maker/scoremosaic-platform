# Gate C.2-C — Dispatch Job / Source / Run / Result Identity Binding Foundation

## Status

Contract foundation only. This slice does not enable orchestration, engine execution, persistence, storage, or network dispatch.

Gate C.2-C closes the semantic identity gap between the existing deterministic Gateway orchestration plan and the already-merged Gate C.2-A authenticated request envelope / Gate C.2-B exact dispatch target foundation.

The purpose is to ensure that a valid authenticated request cannot be treated as authorization for a different job, source artifact, engine run, candidate, or reserved result-artifact slot, and that returned-result identity metadata cannot be substituted together with modified result bytes without the engine-scoped credential.

## Dispatch identity source of truth

A dispatch identity is derived only from an orchestration plan that passes the existing exact deterministic `verify_orchestration_plan()` verifier.

The supplied mapping is detached into one complete in-memory snapshot first. That exact detached snapshot is then both verified and used to derive the identity. The implementation does not verify one mutable mapping state and later derive identity from a second read of the caller-owned mapping.

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

1. detach one complete orchestration-plan snapshot;
2. verify that exact snapshot with the existing deterministic verifier;
3. derive one expected C.2-C identity from the same verified snapshot;
4. validate the existing C.2-B target and envelope metadata relationship;
5. require the exact received control payload bytes to equal the canonical C.2-C identity payload;
6. require the C.2-A envelope payload length and SHA-256 to match those exact bytes;
7. at an actual receiver, separately run the existing C.2-A cryptographic signature, timestamp, and replay verification before accepting the request.

C.2-C does not replace C.2-A cryptographic verification. `require_authenticated_dispatch_identity()` is a semantic identity check and deliberately does not reserve replay nonces.

## Authenticated result identity

The foundation defines an authenticated result-identity claim for exact returned bytes.

A result identity repeats the trusted dispatch lineage and additionally binds:

- the C.2-C dispatch identity SHA-256;
- exact result payload byte length;
- exact result payload SHA-256;
- C.1 engine-scoped credential-binding metadata;
- an HMAC-SHA256 authentication proof over the complete result lineage and result digest.

The HMAC proof is derived from the same bounded engine-scoped `EngineCredential` contract already used by C.2-A. A result is rejected unless its plan, job, source, run, engine, candidate, namespace, expected artifact IDs, dispatch identity digest, byte length, payload digest, credential binding, and authentication proof all match the trusted dispatch identity.

The signature is redacted from object representation and safe diagnostics expose only whether a signature is present.

This result authentication is contract-level integrity evidence only. It does not provide transport encryption, credential-rotation grace semantics, durable replay state, response freshness, or engine execution. Those remain later Gate C responsibilities. It also does not declare returned engine content safe, correct, canonical, or approved. Candidate Safety and later artifact lifecycle / durable-state gates remain authoritative for their own boundaries.

## Fail-closed regression evidence

The focused regression suite covers:

- deterministic identity generation for Audiveris, HOMR, and Clarity;
- one-snapshot verification/derivation against a stateful mapping;
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
- authenticated result from another dispatch/run;
- result artifact identity tamper;
- exact returned-result byte tamper;
- attacker-recomputed result length/digest without a valid MAC;
- result-signature tamper;
- cross-engine result credential confusion.

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
