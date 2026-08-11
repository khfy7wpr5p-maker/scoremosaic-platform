# Gate C.1 — Service-to-Service Authentication Contract Foundation

Status: contract foundation only. Live engine dispatch remains disabled.

## Purpose

Gate C.1 establishes the first fail-closed authentication contract for private Gateway-to-engine communication without activating orchestration, upload, storage, publication, or production secret provisioning.

This slice exists to prevent a later network-dispatch implementation from treating an internal network location as authentication.

## Fixed identities

The caller identity is:

- `scoremosaic-omr-gateway`

The approved engine audiences are:

| Engine key | Audience identity |
|---|---|
| `audiveris` | `scoremosaic-audiveris-foundation` |
| `homr` | `scoremosaic-homr-foundation` |
| `clarity` | `scoremosaic-clarity-foundation` |

Unknown engine keys fail closed.

## Environment separation

The contract recognizes only these explicit environment names:

- `test`
- `staging`
- `production`

Environment names are not normalized. A value such as `STAGING`, `dev`, or whitespace-padded `staging` is rejected. The environment participates in the credential lookup key so staging and production cannot silently reuse the same logical credential binding.

Recognition of the `production` contract name does not provision a production credential and does not authorize production deployment.

## Credential source contract

Gate C.1 does not choose or provision a production secret backend. Instead, credential retrieval is an injected resolver that receives one non-secret logical key containing:

- authentication contract version;
- environment;
- Gateway caller identity;
- engine key;
- engine audience identity.

A resolver must return opaque bytes for exactly that logical key. Missing credentials, provider failures, non-byte values, or values outside the bounded `32..512` byte range fail closed.

The authentication contract never reads a credential from an endpoint URL. Existing Gateway configuration already rejects URL usernames/passwords, query strings, fragments, and non-root paths.

## Secret-handling boundary

Raw credential bytes are deliberately absent from:

- endpoint URLs;
- safe diagnostic metadata;
- exception messages/categories;
- object `repr` output;
- repository configuration;
- this contract document and its tests.

Provider exception text is not propagated because an external secret backend can include secret material in its own diagnostic message.

The credential object exposes raw bytes only through an explicitly transport-oriented method for a later authenticated transport adapter. Gate C.1 itself never calls that method for network dispatch.

## Identity binding

Before a later transport adapter can use a credential, the binding must match:

- current contract version;
- Gateway caller identity;
- exact engine key;
- exact expected audience identity;
- explicit approved environment.

Cross-engine binding, caller tampering, audience tampering, and contract-version mismatch are rejected with stable bounded categories.

## Activation effect

None.

After Gate C.1:

- `SCOREMOSAIC_GATEWAY_ORCHESTRATION_MODE` remains `disabled`;
- the Gateway still has no live engine dispatch path;
- existing readiness probes remain foundation probes and are not promoted into an authenticated production transport;
- no public upload endpoint is added;
- no persistent job/artifact storage is added;
- no production secret value is stored in Git or provisioned by this slice.

A later Gate C slice must select and implement the actual authenticated request/receiver mechanism, including receiver-side verification and any replay/rotation requirements, before orchestration can be considered for activation.

## Negative evidence required by this slice

The tests must demonstrate at least:

- unknown engine rejection;
- unknown/non-canonical environment rejection;
- separate environment credential bindings;
- distinct per-engine credential bindings;
- cross-engine identity rejection;
- caller/audience/version tamper rejection;
- missing credential rejection;
- invalid credential type/length rejection;
- provider diagnostic redaction;
- secret redaction from diagnostic metadata and `repr`.

Passing Gate C.1 tests is necessary foundation evidence only; it is not sufficient to declare Gate C complete.
