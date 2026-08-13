# Gate E.4C — Immutable Source / Job Binding

## Status

Gate E.4C is the final bounded foundation slice in the E.4 upload-intake chain and is present on `main`. It consumes only exact Gate E.4B Safe Intake finalization evidence and binds that accepted source identity to existing server-owned job, artifact-lifecycle, and Gate D.3 immutable storage-authority contracts.

This document describes a contract foundation. It does **not** activate a public upload route, storage writes, a database/object-store provider, queue/worker execution, engine dispatch, or orchestration.

## Required trust chain

```text
E.3C exact external admission
        |
        v
E.4A Safe Upload Session reservation
        |
        v
E.4B Safe Intake Session Finalization
        |
        | exact session + document SHA-256
        | exact Safe Intake policy/format/size/structure evidence
        v
E.4C Immutable Source / Job Binding
        |
        +--> deterministic server-owned job identity
        +--> normalized source artifact reference
        +--> existing orchestration-plan contract evidence
        +--> existing artifact-lifecycle contract evidence
        +--> Gate D.3 immutable source storage-authority evidence
```

Every earlier boundary remains authoritative. E.4C must never reinterpret a structurally valid but tampered E.4B object as source/job authority.

## Normative requirements

1. Only the exact `SafeUploadFinalizationDecision` type may enter E.4C.
2. E.4B evidence must be independently reverified before any E.4C identity is derived.
3. The E.4B session identity must remain bound to the exact environment, principal, canonical `platform.safe_upload_session` operation, and admission binding.
4. The E.4B finalization identity must remain bound to the exact document SHA-256 and all current Safe Intake evidence used by the finalization contract, including policy version, format/media type, observed bytes, PDF page count or image width/height/pixel count as applicable.
5. Job identity is server-derived. The caller cannot supply a job ID, source artifact ID, source path, storage key, orchestration plan ID, lifecycle ID, or storage-manifest hash.
6. Source identity is bound to the exact E.4B document SHA-256, observed byte size, and media type.
7. Existing orchestration, artifact-lifecycle, and Gate D.3 contracts remain authoritative; E.4C must not invent a parallel source-storage authority model.
8. Exact replay of the same E.4B finalization evidence derives the same E.4C job/source/storage identity.
9. Cross-source or tampered principal/session/content/intake evidence fails closed before usable E.4C evidence is returned.
10. E.4C safe evidence remains bounded and grants no upload, storage-write, persistence, job-execution, network-dispatch, or orchestration authority.

## Deliberate non-authority

E.4C may derive a deterministic job identifier and immutable source storage-authority evidence, but these are **identity and contract evidence only**.

The following remain disabled:

- HTTP upload/public mutation routes;
- database writes;
- S3/MinIO/filesystem object writes;
- production session/rate/idempotency providers;
- durable queue/worker runtime;
- process execution or automatic recovery;
- live engine receiver/network dispatch;
- orchestration activation;
- Teacher Review writes, approval, and publication.

A storage key in E.4C evidence does not mean that an object exists at that key. A job ID does not mean that a runnable job has been persisted or scheduled.

## E.4B integrity hardening required by this handoff

E.4C is the first later boundary that consumes E.4B evidence to derive new source/job identity. Therefore E.4C review hardened E.4B verification so that:

- the Safe Upload Session ID is independently recomputed from the E.4A contract version, environment, principal, operation, and admission binding;
- the finalization ID binds the complete current Safe Intake structural evidence, not only document hash/format/size;
- valid-shape mutation of principal/session or page/pixel evidence cannot be accepted merely because individual fields remain structurally valid.

This is an E.4 trust-handoff correction, not a new micro-gate.

## Relationship to Gate D

Gate D.3 already defines deterministic immutable artifact storage-authority records and normalized server-derived storage keys. E.4C reuses that authority model by constructing existing orchestration/lifecycle evidence from the exact E.4B source identity and requiring the resulting D.3 source record to match the E.4B SHA-256, size, and media type.

No concrete persistence provider is selected by E.4C. Gate D remains a contract/convergence foundation until provider-backed persistence is separately activated and verified.

## Exit criteria

E.4C itself is complete when:

- focused E.4C positive, replay, cross-source, pre-tamper, direct-construction, and no-runtime-authority tests pass;
- all existing OMR Gateway regression tests pass;
- relevant repository CI is green on the exact PR head;
- documentation still states that upload, persistence, storage writes, dispatch, and orchestration are disabled;
- no unresolved P1/P2 finding remains.

E.4C completion does **not** by itself activate runtime capability. The final E.4A–E.4C convergence/regression closure is defined in [`gate-e4-closure-convergence.md`](gate-e4-closure-convergence.md). Once that closure is merged with fresh CI evidence, E.4 may be recorded as a completed contract/convergence foundation and the default next direction becomes the minimum staging vertical slice rather than another abstract E.4 sub-gate unless a concrete P1/P2 or mandatory trust boundary proves otherwise.