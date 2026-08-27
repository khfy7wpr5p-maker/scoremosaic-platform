# Teacher Review Product Workflow v1

Status: **fixture product UI active; production approval remains locked**

This slice turns the previously separate Teacher Review surfaces into one visible product workflow:

```text
Teacher Review Workspace
        ↓
Score View
        ↓
Structured Edit
        ↓
Mark selected issue reviewed
        ↓
Local readiness validation
        ↓
Prepare approval
        ↓
Approve score — visible but fail-closed
```

## What is active

The browser experience can select a fixture issue, inspect the rendered score and source evidence, perform the already-bounded local structured edit flow, mark the issue reviewed in browser memory, recompute unresolved blocking issues, run a local readiness check once all blocking issues are reviewed, and prepare the approval UI state.

The status bar reflects approval readiness so the product flow is visible as one continuous workspace rather than disconnected mock panels.

## What remains intentionally locked

The final `Approve score` control is displayed but disabled. This interface does not create or claim any of the following:

- authenticated teacher identity;
- RBAC authorization;
- server `ScoreEditCommand`;
- `TeacherScoreRevision`;
- durable validation evidence;
- database or object-storage persistence;
- production approval;
- publication.

Local reviewed markers, validation PASS, and approval preparation disappear on reload and are explicitly non-authoritative.

## Production unlock requirements

Production approval must remain fail-closed until a separate narrow security gate proves, at minimum:

1. authenticated teacher identity and RBAC;
2. authoritative server revision with old-value/precondition checks;
3. deterministic validation evidence bound to the exact revision;
4. durable audit/provenance storage;
5. idempotent approval command semantics;
6. publication separated from approval;
7. CI and threat-model evidence for the live API path.

No part of this slice grants those permissions.
