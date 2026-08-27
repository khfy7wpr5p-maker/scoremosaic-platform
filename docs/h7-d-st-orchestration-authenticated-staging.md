# H7-D — ST-Orchestration Authenticated Staging Preview

Status: **HUMAN APPROVED / SERVER-SIDE STAGING TRANSPORT ACTIVE / PRODUCTION DISABLED**  
Date: 2026-08-28

## Purpose

H7-D advances the H7-C local-only bridge to an authenticated **server-side staging transport** while preserving the same non-authoritative Teacher Review boundary.

```text
ScoreMosaic validated symbolic preview
        ↓
ScoreMosaic server-side H7-D adapter
        ↓
HMAC-SHA256 authenticated staging request
        ↓
exact ST-Orchestration main 80b1e925…
        ↓
H7-D transport boundary
        ↓
unchanged H7-C model runtime
        ↓
deterministic feasibility veto
        ↓
exact O5-C string-seat model
        ↓
validated H7-D result
        ↓
browser-safe evidence object
        ↓
Teacher Review Orchestration Preview
```

The browser has no staging endpoint, authentication key, direct engine call, or network transport capability.

## Exact target

- ST-Orchestration main: `80b1e925804616d36c2b46c8074e6a608aa7bff4`
- H7-D contract blob: `4f519d5ec978b305db4b670ea64c333460aa4a79`
- H7-D staging runtime blob: `27204251ccd37b96a004e3eba1602959b94caaf6`
- H7-D CLI blob: `083936a44136d5edc8b5c07931af0606bfc2bf29`
- inherited H7-C contract blob: `1392bb3cb929620dc8645af4b2a808e99c338e91`
- inherited H7-C local runtime blob: `e51c5ed970afcafa2318a2da6177595120a04203`
- model: `o5c-ossq-anonymous-context-v0`
- model fingerprint: `15cd94722a0ba2724ceea6f450f16a87ef455fa8bc21d4b619f0bda6d880ca14`
- threshold: `0.55`
- capability: `string-seat-ranking-v0`

## Authentication

The server-side ScoreMosaic adapter signs each request with HMAC-SHA256 over:

```text
POST
/v1/staging/orchestration/preview
<unix_timestamp>
<16-byte-random-nonce-as-lowercase-hex>
<request-body-sha256>
```

The real shared key is runtime configuration only and must contain at least 32 bytes. It is never embedded into generated browser evidence, source files, contracts, or deployment URLs.

The ST side enforces a 300-second clock window and process-local nonce replay rejection. A future multi-instance staging deployment must use an equivalent shared replay-control layer.

## Endpoint policy

Production-like staging calls require HTTPS. Plain HTTP is accepted by the ScoreMosaic adapter only when the caller explicitly enables the loopback test harness and the host is loopback. Redirects are rejected rather than followed. URL credentials, endpoint paths, query strings, and fragments are rejected. Requests and responses are size-bounded and timed out.

The repository does not provision an external staging hostname, DNS record, TLS certificate, persistent secret, or production credential. CI uses real loopback HTTP plus a visibly synthetic test-only key to verify the protocol end to end.

## Teacher Review boundary

The server-side adapter converts an authenticated and independently validated H7-D response into a browser-safe evidence object. The object intentionally contains no endpoint or secret and advertises:

```text
productionArtifact = false
authoritative = false
networkCapable = false
sourceMutationAllowed = false
teacherRevisionMutationAllowed = false
approvalCapable = false
publicationCapable = false
automaticLearningCapable = false
```

The browser presentation adapter accepts H7-C and H7-D only as separate exact schemas pinned to their exact ST commits. H7-D is labeled `Authenticated staging preview · non-authoritative` in Teacher Review. There is no Apply action.

## Fail-closed cases

H7-D rejects malformed endpoints, weak secrets, identity or source-hash drift, wrong model/capability/threshold, invalid status, deterministic-vetoed proposals, threshold/status contradictions, malformed alternatives, result-hash drift, redirects, unexpected content type/encoding, oversized responses, timeouts, and authentication failures.

## Authority still closed

H7-D does not authorize production credentials, production inference, Canonical Score mutation, TeacherScoreRevision mutation, Apply/auto-accept, approval/publication, ST-OMR integration, H4 rerun, post-H4 retuning, automatic learning, or broader/full-score orchestration claims.

**H7-E remains a separate human gate and also requires broader reliability/generalization evidence.** H7-D transport success is not production-readiness evidence.
