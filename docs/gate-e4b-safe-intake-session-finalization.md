# Gate E.4B — Safe Intake Session Finalization

## Status

Gate E.4B is the current bounded Gate E implementation slice in PR #86. It is **not on `main` until that PR is explicitly approved and merged**. Gate E.4A is already on `main`. Gate E.4C and E.4 closure remain outstanding.

## Purpose

E.4B connects one exact, still-active E.4A Safe Upload Session to the completed Gate B Safe Intake decision without creating storage, job, public-route, or orchestration authority.

The trust transition is:

```text
E.4A Safe Upload Session
        |
        | exact session type + canonical operation + active lifetime
        v
exact immutable document bytes
        |
        v
Gate B decide_safe_intake()
        |
        | signature/MIME + bytes + filename + PDF/image structural budgets
        v
bounded Safe Intake evidence
        |
        + server-computed document SHA-256
        v
atomic E.4B finalization reserve / replay / conflict seam
        |
        v
SafeUploadFinalizationDecision
        |
        | no storage/job/execution authority
        v
E.4C — Immutable Source / Job Binding (next)
```

## Normative requirements

1. Only an exact `SafeUploadSessionDecision` from E.4A is accepted.
2. The session operation remains exactly `platform.safe_upload_session`.
3. The session must still be active at finalization time; expiry is fail-closed.
4. The E.4A Safe Intake media-type allowlist must remain the exact canonical tuple. Equality-spoofing or mutable/extensible substitutes are not authority.
5. The document payload must be exact immutable `bytes`.
6. Gate B `decide_safe_intake()` runs before the E.4B provider callback, using the E.4A server-owned byte/page budgets.
7. The document SHA-256 is computed server-side from the exact bytes that passed Gate B.
8. The finalization provider receives only bounded identity/hash/Safe Intake evidence. It receives no raw document bytes and no original filename.
9. One stateful provider operation must atomically reserve, replay, or reject a conflict for the exact session finalization.
10. Exact replay returns the original finalization identity/evidence. The provider must not rewrite the original finalization timestamp or substitute different document evidence.
11. Reusing one session for different document bytes must fail closed as a finalization conflict.
12. Session/request mutation across callback seams must fail closed.
13. Direct construction of trusted finalization decisions is sealed.
14. Accepted E.4B evidence grants no upload-route, storage-write, source/job creation, operation-execution, network-dispatch, or orchestration authority.

## Provider obligation

The contract is provider-neutral. A future production finalization provider must supply the stateful atomic guarantee that a session has exactly one immutable finalized document identity. The contract validates receipt type, shape, exact binding, time bounds, and Safe Intake evidence, but it does not itself persist state.

The provider must therefore preserve the original finalization record on replay and return `conflict` when the same session is presented with a different document identity. This obligation is part of E.4B runtime activation and does **not** create another abstract E.4 sub-gate.

## Current implementation boundary

`services/omr-gateway/src/scoremosaic_gateway/safe_upload_finalization.py` defines:

- `SafeUploadFinalizationRequest`;
- `SafeUploadFinalizationReceipt`;
- sealed `SafeUploadFinalizationDecision`;
- `finalize_safe_upload_session()`;
- stable fail-closed E.4B error categories.

The finalization request contains no payload bytes or filename. The accepted decision contains only bounded identity, SHA-256, format/size/page-or-image evidence, finalization time, replay state, and explicit false runtime-authority flags.

## Explicit exclusions

E.4B does not add or enable:

- an HTTP upload/session finalization route;
- public data-plane activation;
- database, object-store, filesystem, or durable provider selection;
- storage writes or source artifact creation;
- job creation or lifecycle transition;
- E.4C immutable source/job binding;
- engine network dispatch;
- orchestration execution;
- Teacher Review or publication;
- workflow or dependency changes.

## E.4 sequence

```text
E.4A Safe Upload Session Reservation        ✅ main
E.4B Safe Intake Session Finalization       🟡 PR #86
E.4C Immutable Source / Job Binding          ❌ next
E.4 convergence / regression closure         ❌
        ↓
minimum staging vertical slice               ❌
```

After E.4A–E.4C convergence closes, the default direction remains the minimum staging vertical slice. New E.4D/E.4E-style contract slices require a concrete P1/P2 finding or a mandatory trust boundary rather than documentation-only decomposition.
