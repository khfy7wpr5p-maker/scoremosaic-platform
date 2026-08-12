# Gate C.2-E — Receiver Verification Adapter Foundation

Status: contract foundation only. Live engine receiver routes and dispatch remain disabled.

## Purpose

Gate C.2-E composes the already-merged internal dispatch security primitives into
one receiver-side fail-closed verification boundary:

- C.2-B exact engine target and reserved `POST /internal/transcribe` path;
- C.2-C job/source/run/candidate/artifact dispatch identity;
- C.2-D credential-generation proof and bounded rotation semantics;
- C.2-A authenticated request HMAC, freshness, observed method/path, and replay
  callback ordering.

The output is one immutable `VerifiedDispatchRequest`. It is verification
evidence only. It is **not** permission to execute an OMR engine and does not
register or activate an HTTP route.

## Inputs

The adapter accepts only already-constructed contract evidence:

- one orchestration plan supplied by the future receiver-side trusted state
  boundary;
- one exact C.2-B `EngineDispatchTarget`;
- one C.2-D `CredentialRotationSet`;
- one C.2-D `GenerationBoundRequest` containing the inner C.2-A envelope;
- receiver-observed HTTP method and path;
- exact immutable request body bytes;
- receiver current time;
- the C.2-D generation-scoped replay callback.

C.2-E does not resolve network addresses, read HTTP streams, read production
secrets, or obtain orchestration plans from storage. Those are separate future
runtime boundaries.

## Security-significant verification order

The adapter uses this order:

1. require the C.2-D request object shape;
2. require C.2-B target/envelope consistency and C.2-C semantic dispatch identity
   against the supplied orchestration plan and exact request body;
3. select exactly the labeled C.2-D credential generation;
4. verify the C.2-D generation HMAC;
5. verify the inner C.2-A binding, observed method/path, freshness, payload length,
   payload digest, and HMAC;
6. only after those checks succeed may C.2-A invoke the supplied replay callback;
7. require the selected credential binding, target engine, and C.2-C identity to
   converge on the same receiver identity;
8. return immutable verified evidence.

Step 2 is deliberately side-effect free and occurs before replay reservation.
This prevents a request that is cryptographically signed but carries a wrong
job/source/run/candidate/artifact control payload from consuming a replay
reservation. Passing this semantic precheck does **not** authenticate the request;
C.2-D and C.2-A cryptographic verification remain mandatory before any verified
result is returned.

## Exact request body

The request body remains the closed canonical C.2-C dispatch identity payload.
C.2-E accepts only exact `bytes`; mutable buffers are rejected by the underlying
C.2-C boundary.

The adapter does not retain the raw request body in `VerifiedDispatchRequest`.
It retains only the already-validated payload SHA-256 together with semantic
identity evidence.

## VerifiedDispatchRequest

A successful result carries:

- C.2-E contract version;
- exact C.2-B target evidence;
- exact C.2-C `DispatchIdentityBinding`;
- the exact C.2-D `GenerationCredential` accepted for this request;
- request timestamp;
- nonce;
- authenticated payload SHA-256.

The exact accepted `GenerationCredential` is carried because C.2-D result
verification must use the same credential generation that authenticated the
request, including an already-accepted previous-generation request whose result
arrives after its new-request grace period.

The credential is runtime authentication context. C.2-E does not serialize or
persist its secret and does not define how future durable orchestration stores or
recovers in-flight authentication context.

## Safe diagnostics

`VerifiedDispatchRequest.as_safe_dict()` may expose only bounded non-secret
metadata, including:

- target identity;
- dispatch identity and its SHA-256;
- credential generation ID;
- request timestamp and nonce;
- payload SHA-256;
- the fact that replay reservation succeeded.

It must not expose:

- credential bytes;
- C.2-A request signature;
- C.2-D generation signature;
- provider exception details;
- raw request body.

The object representation also redacts credential material.

## Replay boundary

C.2-E does not create a replay store. It only composes the existing C.2-A/C.2-D
callback boundary.

A replay callback returning anything other than exact `True` fails closed as a
replay. Callback exceptions fail closed as replay-check unavailability without
propagating private backend diagnostic text.

Durable atomic crash/restart-safe replay state remains Gate D work and is still a
prerequisite for future live authenticated dispatch activation.

## Regression evidence

The C.2-E regression suite covers at least:

- valid current-generation request convergence to one immutable typed result;
- one replay callback invocation only after successful verification;
- signed but wrong job/source/run semantic identity rejected before replay;
- generation proof tamper rejected before replay;
- receiver-observed method/path mismatch rejected before replay;
- cross-engine target confusion rejected before replay;
- mutable request body rejected before replay;
- replay detection fails closed;
- replay backend exception fails closed without diagnostic leakage;
- safe result diagnostics contain no secret or authentication proof;
- `/internal/transcribe` remains unregistered in the existing Gateway HTTP app.

Existing C.2-A/B/C/D regression suites remain authoritative for their individual
primitive guarantees; C.2-E tests their composition rather than replacing them.

## Explicit non-activation

Gate C.2-E does **not**:

- register `/internal/transcribe`;
- modify `app.py` or an engine HTTP handler;
- send a network request;
- execute HOMR, Audiveris, or Clarity;
- enable Gateway orchestration mode;
- create Redis, Postgres, SQLite, or another persistent replay implementation;
- provision or rotate production credentials;
- authorize a production dispatch origin;
- implement timeout/cancellation;
- implement retries;
- add upload, durable job/artifact state, Teacher Review, approval, or publication.

After C.2-E, the receiver security primitives have a single composition boundary,
but live receiver wiring remains disabled. Timeout/cancellation, bounded retry,
safe diagnostic/error convergence, Gate D durable replay/state, and separate
activation evidence remain future gates.
