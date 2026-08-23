# Stage 11-D — Application State + Error Model

## Status

**Pure local state reduction only. No adapter invocation, network request, server authority, persistence, playback, approval, publication, or production infrastructure is activated.**

Stage 11-D defines one fail-closed UI application state model shared by Stage 11 read and edit-intent responses.

## Phases

```text
idle
loading
ready
empty
rejected
unavailable
```

Only a valid known request may enter `loading`. A response may settle that loading state only when request ID, kind, document ID, revision, and expected response schema all match exactly.

## Correlation

A mismatched response is never silently rendered. These mismatches become protocol rejection:

- response schema mismatch;
- request ID mismatch;
- request kind mismatch;
- document mismatch;
- revision mismatch;
- unsupported response state;
- `empty` returned for edit-intent prepare.

## Envelope invariants

`success` requires non-null object data and `error=null`.

`empty` requires `data=null` and `error=null`.

`rejected` / `unavailable` require a bounded error object.

Violations become a local `rejected` protocol state.

## Error categories

The UI normalizes bounded error codes into presentation categories:

```text
invalid_request
stale_context
not_found
protocol
unavailable
unknown
```

These categories are display/state semantics only. They do not grant retry, write, authorization, approval, publication, or musical authority.

## Authority

Every state carries:

```text
authoritative=false
canWrite=false
canApprove=false
canPublish=false
canPlayback=false
```

The reducer cannot manufacture server authorization or a successful musical edit.

## Security preservation

The reducer is pure local JavaScript. It does not invoke adapters, network APIs, storage, cookies, clipboard/download, navigation, dynamic HTML/code, credentials, or production artifacts.

## Next slice

Stage 11-E may integrate the Stage 10 UI with Stage 11 local adapters through this state reducer. That integration remains disconnected and fixture-backed; live API/auth/server-write activation stays locked.
