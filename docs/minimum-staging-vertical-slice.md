# Minimum Staging Vertical Slice

Status: implemented on `main` by PR #89.

## Purpose

This slice is the first bounded runtime integration after Gate E.4 contract/convergence closure. It converts the existing external-admission and upload-to-source contracts into one real **private staging source-ingest flow** without opening the public data plane or engine execution.

The authoritative path is:

```text
exact E.3C admission evidence
        ↓
stateful E.4A staging session reservation
        ↓
E.4B Safe Intake finalization
        ↓
E.4C immutable source/job binding
        ↓
independent E.4C verification
        ↓
create-once immutable staging source write
```

## Activated staging behavior

The slice provides one repository-owned staging filesystem provider with bounded state for:

- E.4A session reservation and exact replay;
- E.4B finalization reservation, exact replay, and same-session/different-document conflict;
- the accepted source bytes after exact E.4C re-verification;
- create-once source semantics: an existing different source is never overwritten;
- replay convergence to the same session, finalization, job, source artifact, and storage key.

The provider stores only bounded server-derived session/finalization evidence plus the exact accepted source bytes. Raw document bytes are still not passed into the E.4A or E.4B state callbacks; only the final source-write step receives bytes, after Gate B and E.4C verification have succeeded.

Persisted E.4A/E.4B staging state is authenticated with HMAC-SHA256 before replay evidence is trusted. `StagingUploadProvider` requires one exact 32-byte integrity key supplied by its private caller. That key is not written beside the state records and is not derived from user input. A provider restart must receive the same key to verify and replay existing state; a missing, different, or invalid key does not grant replay authority. Production secret provisioning or environment-variable wiring is deliberately outside this slice.

## Fail-closed guarantees

The focused regressions require:

- production-environment evidence to be rejected before provider state is touched;
- invalid/mutable document inputs to remain governed by the existing Gate B/E.4 contracts;
- exact replay to preserve the original session/finalization identities and source bytes;
- same-session different-document input to fail as a finalization conflict;
- persisted session/finalization state to pass its HMAC integrity check before identity or timestamp evidence is trusted;
- coherent timestamp substitution in a persisted session record to fail closed;
- bounded persisted-state reads and bounded immutable-source replay reads;
- a payload that does not match the verified E.4C hash/size to be rejected before a write;
- a pre-existing different source at the immutable key to fail as a collision, never overwrite;
- malformed persisted session state to fail closed;
- symlinks in provider-owned state/source parent paths to fail closed rather than escape the staging root;
- filesystem failures to map to stable bounded slice errors rather than leak provider details;
- temporary file descriptors to be closed even when setup fails before file-object ownership transfers.

## Explicit non-activation

This slice does **not** activate:

- a public HTTP login, upload, job, review, or mutation route;
- production authentication-provider wiring;
- production rate-limit or request-idempotency state providers;
- production database, S3, MinIO, or general-purpose filesystem object storage;
- queue/worker execution;
- engine network dispatch;
- orchestration runtime;
- Candidate Safety execution over live engine results;
- Teacher Review writes, approval, or publication.

The existing Gateway runtime flags and readiness semantics remain fail-closed. This slice is an internal/private staging integration seam, not a public upload API.

## Scope boundary

This work is intentionally not a new E.4D/E.4E gate. E.4 remains closed at the contract/convergence layer. The slice is the first implementation step that uses those foundations in real staging state and storage.

Further staging activation must extend this path in small evidence-backed steps. Public routes and engine dispatch require separate review and negative-test evidence; they are not implied by successful source ingestion.
