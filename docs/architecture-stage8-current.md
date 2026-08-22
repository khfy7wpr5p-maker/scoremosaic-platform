# ScoreMosaic Stage 8 Current Architecture

Status: **Stage 8-A through Stage 8-O merged. The repository-only Teacher Review and publication-preparation path has reached the external production publication side-effect boundary.**

Current implementation merge: `43de764fee788d3ae20b59b87d52a08e25c5be3d`.

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
  -> server-authorized non-network write boundary foundation
  -> disconnected local BrowserEditIntent
  -> exact-current rational review timeline
  -> non-executing presentation transport state
  -> exact-current approval-candidate evidence
  -> exact human-approval handoff
  -> [HUMAN DECISION]
  -> explicit-human immutable approval record foundation
  -> fresh publication-handoff eligibility evidence
  -> exact publisher-bound non-executing PublicationHandoffRequest
  -> state=awaiting_external_publication_execution
  -> [EXTERNAL PRODUCTION SIDE-EFFECT BOUNDARY]
  -> [LOCKED] production persistence/write
  -> [LOCKED] actual publication execution
  -> [LOCKED] published-artifact record
```

Engine/AI evidence never becomes authoritative musical truth. Teacher work remains an immutable lineage separate from source artifacts, engine candidates, Stage 7 Canonical artifacts, and Ensemble evidence.

## Stage 8-A through Stage 8-C — merged

- purpose-separated HMAC reviewer authorization and exact resource/parent scope;
- closed typed edit commands with no arbitrary XML/patch/path execution;
- immutable draft revisions and append-only audit lineage;
- controlled durable exact-parent storage with HMAC integrity and crash/restart verification;
- deterministic Canonical-derived review state;
- exact target and old-value preconditions;
- visible musical validation without silent repair.

## Stage 8-D — merged and hardened

Authorization-first read-only review projection. Sealed `revision:read` authority is checked before state/base/report processing. No HTTP route is activated.

## Stage 8-E — merged

Disconnected fail-closed browser review workspace with restrictive CSP, deterministic navigation, and no mutation/approval/publication/playback authority.

## Stage 8-F — merged

Exact revision/state corrected-MusicXML derivative with structural safety validation, explicit Teacher Review provenance, and semantic Canonical round-trip equality. Production artifact persistence remains locked.

## Stage 8-G — merged

Server-authorized in-process write-boundary foundation with exact current parent, sealed `revision:propose` authorization, bounded request envelope, old-value/location validation, idempotency, and exact-parent append. `write-api-enabled=false` and `public-api-enabled=false` remain locked.

## Stage 8-H — merged

Disconnected typed BrowserEditIntent composer. It prepares structured local intent only; it carries no server authority.

## Stage 8-I — merged

Exact-current rational timeline with independent validation equality, exact event/beat/simultaneity mapping, minimized cursor data, and no audio/network/runtime authority.

## Stage 8-J — merged

Non-executing deterministic transport state for start/pause/seek/stop/advance presentation behavior. Audio, loop execution, mutation, approval, and publication remain false.

## Stage 8-K — merged

Approval-eligibility evidence proves exact current durable head, independently rebuilt corrected MusicXML, structural safety, semantic round-trip equality, and zero blocking/unresolved issues before `candidateEligible=true`. It grants no approval or publication authority.

## Stage 8-L — merged

Human approval handoff foundation:

- fresh Stage 8-K recomputation;
- purpose-separated HMAC handoff authorization;
- exact approver + revision + artifact + eligibility binding;
- immutable `HumanApprovalHandoffRequest`;
- `state=awaiting_human_decision`;
- only `canPresentForHumanApproval=true` is positive;
- no approval decision, approval record, publication, route, or production provider.

Stage 8-L established the human authority boundary.

## Stage 8-M — merged

Explicit-human approval-record foundation:

- no inferred/default approval exists;
- the caller must explicitly supply `decision="approved"` through the human-action seam;
- explicit human-action provenance SHA-256 and decision time are required;
- the complete Stage 8-L chain is freshly rebuilt before the decision is accepted;
- stale head, wrong approver/key, tampered grant, and artifact substitution fail closed;
- exact replay converges to one immutable approval record;
- the record may state `approval.status=approved` and `humanApprovalCaptured=true` because an explicit human decision was supplied;
- `authoritativeMusicalTruth=false` remains explicit;
- production approval persistence and publication remain disabled.

`human-approval-record-foundation-enabled=true` does not activate a live approval endpoint or production persistence.

## Stage 8-N — merged

Publication-eligibility evidence foundation:

- the complete Stage 8-M approval record is freshly rebuilt from exact current durable inputs;
- supplied-vs-rebuilt approval record equality is mandatory;
- stale revisions, substituted artifacts/decision evidence, and substituted approval records fail closed;
- `candidateEligibleForPublicationHandoff=true` means only that the exact approved artifact may proceed to a later publisher-bound handoff;
- `productionPublicationEligible=false` remains fixed;
- blockers remain `PRODUCTION_PUBLICATION_AUTHORIZATION_REQUIRED` and `PRODUCTION_PERSISTENCE_REQUIRED`;
- publication/write/mutation/publisher/production authority remains false.

## Stage 8-O — merged: final non-executing publication handoff

Stage 8-O is the final repository-only preparation layer before an external production publication effect.

It proves:

- Stage 8-N is freshly recomputed from the exact current revision/state/artifact and approval chain;
- a purpose-separated HMAC grant binds one exact publisher identity, request, scope, revision, artifact/MusicXML, approval record, and publication-eligibility evidence;
- wrong publisher/key, grant tampering, and artifact substitution fail closed;
- exact replay is deterministic;
- the immutable request state is `awaiting_external_publication_execution`;
- `canPresentForPublicationExecution=true` is the only publication-facing positive capability;
- `canExecutePublication=false`;
- `canWriteExternal=false`;
- `canPersistProduction=false`;
- `publicationGranted=false`;
- `authoritativeMusicalTruth=false`.

`publication-handoff-foundation-enabled=true` does not activate publication. `publication-enabled=false` remains authoritative.

## External production side-effect boundary reached

Autonomous repository-only development stops here by design.

The next transition would actually write/persist/publish the exact approved MusicXML to a concrete production destination. That action requires concrete operational facts and authority that the repository contracts intentionally do not invent:

- production identity/session provider and production RBAC source;
- exact production publisher identity and destination;
- production durable/object-store provider;
- live authenticated transport and provider credentials;
- explicit external execution authority;
- published-artifact/audit persistence semantics verified against the real provider.

Without those concrete production inputs, no repository contract may reinterpret the Stage 8-O handoff as permission to publish.

## Still locked / not proved

- actual production publication execution;
- production publication persistence and published-artifact record;
- production identity/session provider and RBAC wiring;
- live Gate E Teacher Review transport/public HTTP routes;
- production DB/object-store deployment;
- multi-host distributed consensus/full-store anti-rollback authority;
- corrected MusicXML production persistence/transport;
- browser writable editor activation;
- real-time audio/MIDI/SoundFont playback and loop execution.

The ScoreMosaic repository now safely prepares an exact human-approved MusicXML lineage up to a publisher-bound, non-executing handoff. The external production effect remains intentionally separate.
