# Stage 8-M — Explicit Human Approval Record Foundation

## Status

Repository-only contract foundation. It records no live production approval, exposes no route, and persists nothing to a production provider.

## Purpose

Stage 8-M captures an **explicit human approval action** for one exact Stage 8-L handoff as immutable approval evidence. It does not infer, recommend, or manufacture the human decision.

A decision grant can be created only when the caller explicitly supplies:

- `decision="approved"`;
- the exact human approver ID from the Stage 8-L handoff;
- an explicit human-action provenance SHA-256;
- a caller-supplied UTC decision timestamp;
- a purpose-separated human-approval decision signing key.

## Trust chain

```text
exact current Stage 8-L handoff
  -> fresh Stage 8-L rebuild from current durable revision/state/artifact
  -> exact supplied-vs-rebuilt handoff equality
  -> explicit human action: decision=approved
  -> purpose-separated decision grant
  -> exact approver + handoff + revision + artifact + MusicXML binding
  -> immutable HumanApprovalRecord
  -> status=approved
  -> publication eligible=false
  -> publication granted=false
  -> production persistence=false
  -> [LOCKED] publication eligibility
  -> [LOCKED] publication grant/runtime
```

## Security properties

The record builder fails closed when:

- the revision is no longer the exact current durable head;
- corrected MusicXML bytes or artifact evidence are substituted;
- the Stage 8-L handoff no longer reconstructs exactly;
- the human approver differs;
- the decision key is wrong;
- the decision grant is tampered;
- human-action provenance is missing or malformed;
- the caller attempts any decision other than explicit `approved`.

Exact replay with the same immutable inputs converges to the same approval record ID and SHA-256.

## Human authority semantics

The positive fact produced by Stage 8-M is narrowly scoped:

```text
humanApprovalCaptured=true
approval.status=approved
approval.exactHumanDecision=true
```

This means the approval decision was explicitly supplied through the human-action seam. It does **not** mean that AI has declared the musical content true.

Therefore:

```text
authoritativeMusicalTruth=false
canPublish=false
canMutate=false
canWrite=false
productionPersistence=false
```

## Explicit non-activation

The following remain locked:

- `approval-enabled=false` — no live approval endpoint/runtime;
- `publication-enabled=false`;
- `public-api-enabled=false`;
- `write-api-enabled=false`;
- `production-durable-store-enabled=false`;
- production approval persistence;
- publication eligibility and publication;
- browser mutation authority;
- audio/playback execution.

`human-approval-record-foundation-enabled=true` means only that the repository contract exists and is tested.

## Next safe boundary

After Stage 8-M passes and merges, a later repository-only slice may derive **publication eligibility evidence** from one exact immutable human approval record. Publication execution itself remains a separate external authority/effect and must not be implied by approval.
