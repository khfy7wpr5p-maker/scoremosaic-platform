# Teacher Review Score Editor — Architecture Contract

Status: **historical foundation contract plus current Stage 8-11 alignment**  
Current architecture state contract: `contracts/architecture-current-state-v1.json`

TR-0A originally defined the intended trust and authority boundaries before implementation. Those boundaries remain authoritative, but the old statement that Teacher Review is only a future architecture is no longer current. Repository-only Teacher Review foundations were subsequently implemented through Stage 8-A..8-O, then presented through the disconnected Stage 10 UI and typed Stage 11 local application layer.

## 1. Purpose

Teacher Review is the authorized human-review layer for inspecting OMR evidence, entering bounded musical corrections, validating exact revisions, recording explicit human approval and preparing an exact approved artifact for a later publication effect.

It remains a review-support capability. OMR engines, AI confidence, renderers, playback and Ensemble comparison do not become musical authority.

## 2. Current architectural position

```text
immutable Stage 7 evidence
  -> Review Report + Canonical identity
  -> reviewer/resource authorization
  -> closed ScoreEditCommand
  -> exact parent + old-value precondition
  -> deterministic post-edit validation
  -> immutable TeacherScoreRevision
  -> corrected MusicXML derivative
  -> MusicXML safety + Canonical semantic round-trip
  -> approval-candidate evidence
  -> exact human-approval handoff
  -> explicit human approval record
  -> publication eligibility
  -> publisher-bound non-executing handoff
  -> [EXTERNAL PUBLICATION EFFECT LOCKED]
```

The editor consumes immutable upstream evidence and creates new teacher-owned lineage. It never overwrites source artifacts, engine candidates, Stage 7 Canonical artifacts or Ensemble evidence.

## 3. Current implemented repository foundations

Stage 8 now provides repository evidence for:

- purpose-separated reviewer authorization;
- exact resource/parent scope;
- closed typed ScoreEditCommand operations;
- old-value and stable-location preconditions;
- immutable TeacherScoreRevision lineage;
- append-only durable exact-parent storage;
- deterministic Canonical-derived review state;
- visible validation with no silent repair;
- authorization-first read-only review projection;
- corrected MusicXML derivation and safety validation;
- Canonical semantic round-trip verification;
- non-network server-authorized write-boundary foundation;
- disconnected BrowserEditIntent;
- exact-current review timeline/presentation state;
- approval eligibility;
- human approval handoff and explicit approval record;
- publication eligibility;
- publisher-bound non-executing PublicationHandoffRequest.

These are repository/preparation foundations. They do not activate production persistence, public write APIs or actual publication execution.

## 4. UI relationship

Stage 10 and Stage 11 add a disconnected product/UI layer over checked-in fixtures:

```text
Teacher Review UI
  -> typed local application requests
  -> fail-closed state/correlation model
  -> typed local read/edit-intent adapters
  -> non-production fixture
```

The browser cannot create a ScoreEditCommand or TeacherScoreRevision. `editIntent.prepare` is local non-authoritative intent only.

A future live editor must route mutations through authenticated server-side authorization and the existing Stage 8 exact-current/old-value/immutable-revision chain.

## 5. Authority rules

| Component | Permitted authority | Prohibited authority |
|---|---|---|
| Source-evidence viewer | display immutable evidence | mutate source or declare truth |
| Score renderer | render exact review snapshot | mutate revision/Canonical state |
| Browser structured editor | prepare bounded local intent | create server command/revision |
| Server ScoreEditCommand boundary | validate exact authorized typed command | accept arbitrary XML/path/code |
| Revision materializer | derive immutable revision | overwrite previous lineage |
| Musical validator | report deterministic validity evidence | silently guess/repair ambiguous music |
| MusicXML materializer | derive from exact revision | mutate revision while exporting |
| Playback/cursor | presentation/audition only | decide correctness or approval |
| Approval boundary | capture explicit human decision on exact identity | infer/default approval |
| Publisher | execute only separately authorized eligible artifact | publish draft/machine-only state |

## 6. Structured edit boundary

ScoreEditCommand remains closed and allowlisted. Arbitrary XML, arbitrary object paths, executable expressions and renderer-native mutation objects are forbidden.

Server-side command acceptance must bind exact reviewer/job/report/Canonical/parent/issue/location/operation and old-value evidence. Stale target, mismatched old value or unsupported operation fails closed.

## 7. Validation boundary

Every accepted revision must surface deterministic validation evidence. Validation may cover duration/meter, voice timing, staff/voice placement, chord/onset simultaneity, tie/tuplet structure, supported notation rules, MusicXML structural safety and revision-to-Canonical consistency.

Validator failure is evidence; it must not be hidden by automatic repair.

## 8. Corrected MusicXML and approval

Corrected MusicXML is a derivative of one exact immutable TeacherScoreRevision. The safe chain remains:

```text
TeacherScoreRevision
  -> deterministic MusicXML materialization
  -> MusicXML safety validation
  -> Canonical re-normalization
  -> semantic/revision consistency verification
  -> immutable corrected artifact
```

Approval is separate from save/edit/issue state. Approval must be an explicit human action bound to exact revision/artifact identity. Publication is a further separate transition.

## 9. Current production locks

```text
liveTeacherReviewApiActivated=false
productionWriteActivated=false
productionApprovalPersistenceActivated=false
publicationExecutionActivated=false
productionArtifactReadActivated=false
productionAuthSessionRbacActivated=false
browserServerMutationActivated=false
playbackActivated=false
```

Stage 8-O may present an exact eligible artifact for publication execution, but it does not execute publication.

## 10. Future live-integration gate

Connecting Stage 10/11 UI to real Teacher Review data requires a separate narrow security gate proving:

- authenticated principal/session semantics;
- tenant/resource authorization;
- origin/CSRF/production CSP policy;
- exact versioned API transport;
- exact-current revision checks;
- old-value preconditions;
- idempotency/failure/retry behavior;
- privacy-safe errors/logs;
- append-only audit evidence;
- rollback/disable boundary;
- production persistence and credential handling.

No local fixture or successful UI render is evidence that these production requirements are satisfied.
