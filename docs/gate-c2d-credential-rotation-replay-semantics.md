# Gate C.2-D — Credential Generation, Rotation, and Replay Reservation Semantics

Status: contract foundation only. Live engine dispatch remains disabled.

## Purpose

Gate C.2-D adds explicit credential-generation identity, bounded current/previous
rotation semantics, and persistence-neutral replay reservation semantics on top of
the completed C.1, C.2-A, C.2-B, and C.2-C foundations.

This slice is intentionally additive. It does not rewrite the completed C.2-A
request envelope or C.2-C result identity contracts. Instead, C.2-D adds a
second generation proof that cryptographically binds the exact non-secret
credential generation ID to the complete already-authenticated request envelope
or result identity.

No route is registered, no request is sent, no durable replay store is created,
and no production credential is provisioned or rotated by this slice.

## Credential generation identity

The existing Gate C.1 `credential_key` remains the logical binding for one:

- auth contract version;
- environment;
- Gateway caller identity;
- engine;
- engine audience identity.

C.2-D adds a separate non-secret `credentialGenerationId`. A generation ID:

- is 1 to 64 ASCII lowercase characters;
- starts with `[a-z0-9]`;
- thereafter permits only `[a-z0-9._-]`;
- is not derived from secret material;
- is validated before provider lookup;
- is safe to use in bounded diagnostics.

Credential resolution is scoped by both the logical C.1 credential key and the
exact generation ID. The receiver must select the requested generation directly.
Trying every available secret until one verifies is prohibited.

## Rotation set

One active rotation set contains:

- exactly one current generation;
- optionally one previous generation;
- one rotation activation timestamp;
- when a previous generation exists, one exclusive grace deadline.

Current and previous generations must use the exact same validated C.1 binding
and must have different generation IDs.

The previous-generation grace interval is bounded to at most 300 seconds.
A previous generation is accepted only while:

`rotation_started_at <= now < previous_valid_until`

At the grace deadline it fails closed as expired. Unknown generations fail
closed. Before the rotation activation timestamp the set is not active.

New request proofs always use only the current generation.

## Generation-bound request proof

C.2-D uses `scoremosaic-s2s-request-generation-v1` with HMAC-SHA256.

The generation proof covers:

- proof version and algorithm;
- exact `credentialGenerationId`;
- the complete C.2-A authenticated request envelope, including its inner HMAC
  signature and all method/path/timestamp/nonce/payload identity fields.

The HMAC key is the exact secret for the selected generation.

Receiver order is:

1. validate C.2-D generation-proof structure;
2. select exactly the labeled current or unexpired previous generation;
3. verify the C.2-D generation HMAC;
4. invoke the existing C.2-A receiver verifier with that exact generation
   credential;
5. only after both cryptographic layers succeed may C.2-A reach the replay
   callback.

A generation-proof failure therefore cannot reserve replay state.

For an in-flight request signed by the previous generation during the bounded
grace period, the receiver returns the exact selected `GenerationCredential` as
contract evidence. That credential becomes the immutable authentication context
for the accepted dispatch and its result proof.

The rotation grace deadline controls whether a **new request** using the previous
generation may be accepted. It is not re-applied later to a dispatch that was
already authenticated and accepted before the deadline.

## Replay reservation semantics

C.2-D defines only replay reservation identity and expiry. It does not implement
the durable store.

The reservation key is a SHA-256 digest over canonical non-secret fields:

- C.2-D contract version;
- validated C.1 binding version;
- caller identity;
- engine;
- audience identity;
- environment;
- logical credential key;
- credential generation ID;
- nonce.

The request timestamp is deliberately **not** part of the reservation key. The
same nonce under the same credential generation therefore maps to the same
reservation identity even if a caller changes only the timestamp.

Timestamp is used only to calculate reservation expiry:

`expires_at = request_timestamp + max_request_age_seconds`

The reservation TTL input is bounded to 1–600 seconds. A live atomic replay
store must reserve this key exactly once until expiry.

A nonce may be reused under a different credential generation because the
credential generation is part of the reservation identity. This prevents a
retired generation's replay state from colliding with a separately authenticated
new generation while keeping replay protection strict within each generation.

## Generation-bound result proof

C.2-D uses `scoremosaic-dispatch-result-generation-v1` with HMAC-SHA256.

The proof covers:

- proof version and algorithm;
- exact `credentialGenerationId`;
- the complete authenticated C.2-C `DispatchResultIdentity`, including its inner
  result HMAC, dispatch lineage, expected artifact IDs, result byte length, and
  result SHA-256.

Result verification requires the exact `GenerationCredential` returned when the
request was authenticated. The caller does **not** re-select a credential from
the current rotation set and does not re-apply the previous-generation grace
deadline to an already accepted in-flight dispatch.

Verification therefore proceeds as:

1. validate the generation-bound result structure;
2. validate the supplied exact accepted `GenerationCredential`;
3. verify the result generation HMAC with that exact credential;
4. require the proof generation ID to equal the accepted credential generation;
5. run the existing C.2-C result verifier with the same exact credential.

This prevents a legitimate request accepted just before the previous-generation
grace deadline from being rejected merely because its bounded OMR execution
finishes after the rotation grace period. Timeout/cancellation policy remains a
separate Gate C control and is not weakened by this rule.

The exact accepted generation credential must be carried as dispatch authentication
context by the future live orchestration layer. This contract does not define or
persist that runtime state; durable state remains Gate D work.

## Fail-closed evidence

Regression evidence for this slice covers at least:

- malformed generation IDs rejected before provider lookup;
- exact logical-key + generation provider lookup;
- provider exception mapping without diagnostic leakage;
- current/previous generation collision rejection;
- missing or excessive grace-window rejection;
- current-only signing selection;
- exact generation receiver selection without secret fallback;
- previous generation acceptance before and rejection at its deadline for new
  request verification;
- generation-label tamper rejection for request proofs;
- generation-proof failure before replay reservation;
- generation ID delivered to replay reservation callback after both auth layers;
- replay key independence from timestamp and scoping by generation;
- an accepted previous-generation request result remaining verifiable after the
  request grace deadline using its exact accepted credential;
- generation-label tamper rejection for result proofs;
- secret and HMAC proof redaction from safe representations.

## Persistent replay boundary

Gate C.2-D deliberately does **not** add Redis, Postgres, SQLite, an in-memory
production substitute, or any other replay persistence implementation.

The existing C.2-A contract remains authoritative that durable replay state is a
Gate D responsibility. Gate D must provide an atomic crash/restart-safe
check-and-reserve implementation using the C.2-D reservation semantics before
live authenticated dispatch can be activated.

## Activation effect

None.

After C.2-D:

- `/internal/transcribe` remains unregistered;
- network dispatch remains disabled;
- orchestration mode remains disabled;
- no persistent replay database exists;
- no production secret is provisioned or rotated;
- no durable job/artifact state is added;
- no retry behavior is enabled;
- upload, Teacher Review, approval, and publication remain disabled.

Passing C.2-D proves only generation/rotation/replay semantics. Live receiver
wiring, timeout/cancellation enforcement, bounded retries, safe diagnostic
convergence, Gate D durable replay state, and separate activation approval remain
required.
