# ScoreMosaic Stage 8 Current Architecture

Status: **Stage 8-A through Stage 8-K merged; Stage 8-D authorization-first hardening merged; Stage 8-L human approval handoff foundation in review**.

Current main before Stage 8-L: `a235d0ddba7db50baa83d7be35f9aa1a79aaaf7e`.

## Current trust chain

```text
Stage 7 immutable read-only evidence
  -> Review Report + exact Canonical SHA-256
  -> HMAC-sealed reviewer/tenant/resource authorization
  -> closed bounded ScoreEditCommand
  -> exact parent + stable musical location
  -> old-value SHA-256 precondition
  -> deterministic Canonical-derived review musical state
  -> deterministic post-edit validation evidence
  -> immutable draft TeacherScoreRevision
  -> controlled durable exact-parent append
  -> authorization-first read-only review projection
  -> disconnected read-only browser review
  -> exact revision/state corrected-MusicXML derivative
  -> generated-XML safety + Canonical semantic round-trip
  -> server-authorized non-network write boundary
  -> disconnected local BrowserEditIntent
  -> exact-current revision:read Stage 8-I timeline
  -> exact rational beat/event/simultaneity timing
  -> Stage 8-J non-executing presentation transport state
  -> exact current durable head re-verification
  -> exact supplied-vs-rebuilt corrected artifact equality
  -> validation-count equality
  -> deterministic Stage 8-K approval-candidate evidence
  -> purpose-separated Stage 8-L handoff authorization
  -> exact approver + revision + artifact + eligibility binding
  -> immutable deterministic HumanApprovalHandoffRequest
  -> state=awaiting_human_decision
  -> [HUMAN AUTHORITY BOUNDARY]
  -> [LOCKED] actual teacher approval decision
  -> [LOCKED] immutable approval record
  -> [LOCKED] publication
  -> [LOCKED] loop/audio/playback execution
  -> [LOCKED] live Gate E transport/server resolution
  -> [LOCKED] live/public write API and browser mutation
```

Teacher Review never mutates source artifacts, engine candidates, Stage 7 Canonical artifacts, or Ensemble evidence in place. Teacher work forms a separate immutable lineage.

## Stage 8-A through Stage 8-C — merged

- purpose-separated HMAC reviewer authorization and exact resource/parent scope;
- closed typed edit commands with no arbitrary XML/patch/path execution;
- immutable draft revisions and append-only audit lineage;
- controlled durable exact-parent storage with HMAC integrity and crash/restart verification;
- deterministic Canonical-derived review state;
- exact target and old-value preconditions;
- visible musical validation without silent repair.

## Stage 8-D — merged and hardened

The read-only server projection binds exact `revision:read` authorization, snapshot identity, Stage 7 report evidence, deterministic pagination/focus, and minimized non-authoritative output.

Security hardening moves sealed authorization ahead of state/base/revision/report processing and catches only expected `Stage8ContractError`; unexpected runtime/programming faults are not masked as authorization failures.

No HTTP route is activated.

## Stage 8-E — merged

Disconnected read-only browser workspace with CSP `connect-src 'none'`, no storage/forms/navigation/dynamic HTML injection, deterministic keyboard issue navigation, and disabled mutation/approval/publication/playback controls.

## Stage 8-F — merged

Exact revision/state corrected-MusicXML derivative with bounded deterministic generation, independent structural-safety validation, explicit Teacher Review provenance, semantic Canonical round-trip equality, and immutable draft corrected-artifact evidence.

Production corrected-artifact persistence/transport remains locked.

## Stage 8-G — merged

Server-authorized in-process write foundation:

- fresh durable head before caller request parsing;
- sealed `revision:propose` authorization against exact current scope/parent;
- closed hashed request envelope;
- exact current-state and Stage 8-C old-value/location validation;
- provider-neutral idempotency;
- exact-parent CAS append and duplicate convergence;
- no raw XML/arbitrary patches;
- no live route activation.

`write-api-enabled=false` and `public-api-enabled=false` remain locked.

## Stage 8-H — merged

Disconnected typed BrowserEditIntent composer. It can prepare local structured musical intent for a present event but carries no authorization, old-value hash, command/revision identity, idempotency, or server authority. Network submission, approval, and publication remain disabled.

## Stage 8-I — merged

The rational read-only timeline proves exact current durable-head authorization, independent validation equality, exact rational event/beat/simultaneity mapping, minimized cursor data, and no audio/network/runtime authority.

## Stage 8-J — merged

The non-executing transport state-machine foundation proves deterministic current-snapshot cursor plans and start/pause/seek/stop/advance convergence while loop/audio/MIDI/SoundFont/network/process/mutation/approval/publication authority remains false.

`transport-state-machine-foundation-enabled=true` does not mean playback is enabled; `audio-playback-enabled=false` remains explicit.

## Stage 8-K — merged

The approval-eligibility foundation proves:

- exact current durable revision/head identity;
- independently rebuilt corrected MusicXML bytes and artifact-record equality;
- structural safety and semantic round-trip equality;
- exact revision/artifact/state/validation binding;
- candidate eligibility only when blocking and unresolved issue counts are zero;
- bounded ineligibility reasons without silent repair;
- deterministic sealed evidence;
- approval/publication/mutation/write/authoritative-truth authority fixed false.

Stage 8-K is approval-candidate evidence only. `approval-eligibility-foundation-enabled=true` does not activate approval.

## Stage 8-L — proof target

Stage 8-L is the final autonomous repository-only handoff before a real human approval decision. It must prove:

- Stage 8-K eligibility is freshly recomputed inside the public handoff builder;
- historical revisions and substituted artifacts fail before handoff authority;
- an ineligible candidate cannot receive handoff authorization;
- handoff authorization uses a purpose-separated HMAC domain;
- one exact grant binds request ID, approver ID, tenant/job/report/base Canonical, revision ID/SHA, corrected artifact ID/record SHA, MusicXML SHA, and eligibility-evidence SHA;
- wrong approver, wrong key, tampered grant, stale head, and substituted artifact fail closed;
- exact repeated construction converges deterministically;
- the resulting request is sealed and immutable;
- the request state is exactly `awaiting_human_decision`;
- `humanDecisionRequired=true`;
- `approvalDecision=null`, `approvalRecordId=null`, and `publicationRecordId=null`;
- `canPresentForHumanApproval=true` is the only positive capability;
- `canRecordApproval=false`, `canPublish=false`, `canMutate=false`, `canWrite=false`, and `authoritativeTruth=false`;
- no live route, production provider, approval record, publication behavior, audio runtime, or mutation authority is introduced.

`approval-handoff-foundation-enabled=true` must not change `approval-enabled=false`.

## Still locked / not proved

- actual teacher approval decision;
- immutable approval record/signature/persistence;
- publication eligibility and publication;
- production identity/session provider and production RBAC source;
- live Gate E Teacher Review transport binding;
- public/internal Teacher Review HTTP routes;
- production DB/object-store deployment;
- multi-host distributed consensus/full-store anti-rollback authority;
- corrected MusicXML production persistence/transport;
- browser writable editor activation;
- real-time clock/audio/MIDI/SoundFont playback execution;
- loop execution.

## Autonomous stop after Stage 8-L

If Stage 8-L passes all exact-head, security, determinism, regression, schema and activation-lock gates and merges, autonomous Teacher Review development stops at the semantic boundary shown above.

The next transition is a real human teacher decision that changes the meaning from "safe to present for approval" to "approved". That decision must not be generated autonomously on behalf of the teacher. Publication remains later and separately authorized.
