# Gate C.2-A — Authenticated Request Envelope and Receiver Verification Contract Foundation

Status: contract foundation only. Live engine dispatch remains disabled.

## Purpose

Gate C.2-A defines the first deterministic authenticated request envelope for private Gateway-to-engine communication and a fail-closed receiver verification order. It does not register an engine execution route, send a network request, enable orchestration, provision production secrets, or persist replay state.

The goal is to make later private transport prove caller identity, engine audience, environment, request integrity, freshness, and one-time nonce acceptance instead of trusting network location.

## Relationship to Gate C.1

Gate C.1 remains authoritative for:

- Gateway caller identity;
- approved engine identities/audiences;
- explicit `test`, `staging`, and `production` environments;
- environment- and engine-scoped credential lookup keys;
- bounded opaque credential material;
- fail-closed credential resolution and secret redaction.

Gate C.2-A consumes an already resolved `EngineCredential`. It does not change the Gate C.1 credential-source contract and does not introduce a repository-stored secret.

## Authentication mechanism

The request proof uses:

- request contract version `scoremosaic-s2s-request-v1`;
- algorithm `HMAC-SHA256`;
- the exact opaque Gate C.1 credential bytes as the HMAC key;
- deterministic canonical JSON with sorted keys and compact separators;
- lowercase hexadecimal SHA-256 digests and signatures.

The signed canonical fields are:

- request contract version;
- algorithm;
- Gate C.1 binding version;
- Gateway caller identity;
- engine key;
- engine audience identity;
- environment;
- non-secret Gate C.1 credential lookup key;
- exact HTTP method;
- exact canonical path;
- Unix timestamp in seconds;
- 128-bit nonce encoded as exactly 32 lowercase hexadecimal characters;
- payload byte length;
- payload SHA-256.

The raw credential and raw payload are never placed inside the envelope.

## Method and path boundary

This foundation authorizes only the `POST` method for a future authenticated internal dispatch surface. Existing `/health` and `/ready` status routes are not changed by this slice.

Authenticated paths must be ASCII absolute paths and are rejected if they contain query strings, fragments, backslashes, percent encoding, control characters, or dot-segments. The exact engine route allowlist is a later Gate C slice; C.2-A does not create or activate any route.

Receiver verification must be given the HTTP method and canonical path actually observed by the receiving handler. Those observed values are validated independently and must exactly match the signed envelope method and path before payload/signature success can reach replay reservation. A valid signed envelope therefore cannot be redirected to a different method or canonical route and still authenticate.

## Payload boundary

The contract accepts only exact immutable `bytes` and applies a 20 MiB upper bound before hashing. The envelope binds both payload byte length and SHA-256 digest. Receiver verification rejects size mismatch or digest mismatch before signature success can reach replay-state handling.

This does not replace Gate B Safe Intake. A later live orchestration path must still originate from an accepted Safe Intake decision and bind the exact accepted source/job identity in the later Gate C identity-binding slice.

## Freshness and replay boundary

The request timestamp is accepted only when:

- it is no more than 120 seconds old; and
- it is no more than 30 seconds in the future relative to receiver time.

A receiver must also provide an atomic replay checker for the tuple represented by the authenticated Gate C.1 binding, nonce, and timestamp. The callback must return `True` only when the nonce is accepted and reserved exactly once.

Verification order is deliberately:

1. credential binding validation;
2. envelope structure/version/algorithm validation;
3. envelope-to-credential identity binding;
4. receiver-observed method/path validation and exact match to the signed target;
5. timestamp window;
6. payload byte length and SHA-256;
7. HMAC signature using constant-time comparison;
8. replay check-and-reserve.

The replay store is touched only after cryptographic verification and observed-target verification succeed so unauthenticated or redirected traffic cannot consume replay-state entries. Missing, failed, or non-accepting replay checks fail closed with stable bounded categories.

Gate C.2-A does not implement durable replay persistence. Durable state remains Gate D work; the live receiver integration must select an appropriate atomic replay-store implementation before authenticated dispatch can be activated.

## Rotation boundary

Gate C.2-A signs the existing non-secret Gate C.1 credential lookup key so the receiver can prove that caller and receiver are using the same logical engine/environment binding. It does not yet define overlapping current/previous key acceptance, credential generation identifiers, or a rotation grace window.

Credential rotation semantics are therefore still required before Gate C can be declared complete and before live orchestration activation is considered.

## Fail-closed receiver evidence

Negative regression evidence for this slice must demonstrate at least:

- modified payload rejection;
- modified signed path rejection;
- receiver-observed method mismatch rejection;
- receiver-observed path mismatch rejection;
- invalid receiver-observed target rejection before replay reservation;
- unsupported signing method rejection;
- ambiguous/encoded path rejection;
- request contract version mismatch rejection;
- algorithm mismatch rejection;
- caller, engine, and audience tamper rejection;
- cross-environment rejection;
- credential lookup-key tamper rejection;
- expired and excessive-future timestamp rejection;
- malformed nonce rejection;
- replay rejection;
- replay-store failure mapping without diagnostic leakage;
- invalid signature rejection before replay reservation;
- signature redaction from safe diagnostics and `repr`;
- deterministic signing for identical canonical inputs.

## Activation effect

None.

After Gate C.2-A:

- `SCOREMOSAIC_GATEWAY_ORCHESTRATION_MODE` remains `disabled`;
- no authenticated HTTP request is actually sent;
- HOMR, Clarity, and Audiveris still expose no conversion/upload/job endpoint;
- no receiver service is wired to the reference verifier yet;
- no public upload endpoint is added;
- no persistent job/artifact/replay storage is added;
- no production credential is provisioned;
- no publication behavior is added.

Passing C.2-A proves only the authenticated-request contract foundation. A later Gate C slice must wire receiver verification into explicitly allowlisted internal engine endpoints and retain the no-activation rule until the remaining Gate C controls and a separate activation approval are complete.
