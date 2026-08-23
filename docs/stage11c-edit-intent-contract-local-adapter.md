# Stage 11-C — Typed Edit Intent Contract + Local Adapter

## Status

**Local intent preparation only. No ScoreEditCommand, TeacherScoreRevision, server write, approval, or publication authority is introduced.**

Stage 11-C defines `editIntent.prepare` as a closed UI↔application contract. The local adapter validates one exact fixture issue target and one bounded operation, then returns a frozen non-authoritative local intent.

## Request binding

Every request is bound to:

- `requestId`
- `documentId`
- exact `revision`
- exact `issueId`
- exact target location
- one bounded operation
- optional bounded reason
- an explicit all-false authority object

Unknown fields, stale revisions, wrong documents, missing issues, target mismatch, unsupported operations, invalid values, or any authority claim are rejected fail-closed.

## Operation subset

Stage 11-C preserves the Stage 10 UI subset of the existing ScoreEditCommand operation vocabulary:

```text
set_pitch
set_effective_duration
set_dots
remove_event
```

The JSON schemas reference the canonical `score-edit-command-v1.schema.json` operation definitions rather than inventing a second musical mutation format.

## Non-authority

A successful local intent always states:

```text
authoritativeCapability=false
serverAuthorizationIncluded=false
oldValuePreconditionIncluded=false
commandIdentityIncluded=false
networkSubmissionAllowed=false
canCreateScoreEditCommand=false
canCreateRevision=false
canApprove=false
canPublish=false
```

A local intent is evidence of user intent only. A future live server must independently authorize, resolve exact-current state, verify old-value preconditions, validate the operation, and create any command/revision identity.

## Security preservation

The adapter is non-production, non-authoritative, non-networked and non-persistent. It may not use browser storage, cookies, navigation authority, clipboard/download, dynamic HTML/code, production credentials, or production artifacts.

## Next slice

Stage 11-D may define a closed error/loading/application-state model shared by read and edit-intent flows. Live networking remains disabled.
