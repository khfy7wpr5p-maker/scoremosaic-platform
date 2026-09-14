# SM-POLY-13 — Teacher Review Workload Evidence

Status: **research/evaluation evidence package**  
Method: `TEACHER_REVISION_COMMAND_COUNT_V1`  
Production behavior change: **none**

## Purpose

SM-POLY-13 turns an already-validated immutable Teacher Review revision history into deterministic workload evidence. It does not change Teacher Review authority, Stage 7 quorum, engine selection, MusicXML correction behavior, approval, publication, model training, or production activation.

The package consumes the existing Stage 8 lineage:

```text
ScoreEditCommand
  -> TeacherScoreRevision
  -> exact parent revision chain
  -> exact audit-event chain
  -> SM-POLY-13 read-only workload evidence
```

No new write path is introduced.

## Counting semantics

`TEACHER_REVISION_COMMAND_COUNT_V1` means:

```text
one validated TeacherScoreRevision / ScoreEditCommand pair = one teacher edit
```

If a teacher changes the same event or measure several times, each accepted revision-command pair remains a separate edit. SM-POLY-13 measures teacher actions; it does not collapse repeated work into a unique-event count.

An empty revision history is **not** interpreted as zero edits. The current contracts do not contain an independent completed-review assertion that proves a teacher reviewed the score and made zero changes. Therefore an empty history remains unprovable rather than becoming a misleading zero.

## Required lineage validation

The builder fails closed unless all supplied evidence forms one complete chain from the Canonical base:

- each `ScoreEditCommand` passes the existing Stage 8 command validator, including its command SHA-256;
- each `TeacherScoreRevision` has the exact closed v1 shape;
- revision audit-event SHA-256 is recomputed;
- revision SHA-256 and revision ID are recomputed;
- the first revision has no parent and later revisions bind the exact preceding revision ID/SHA;
- `previousAuditEventSha256` binds the exact preceding audit event;
- revision `commandId` / `commandSha256` match the exact validated command;
- command parent identity matches revision parent identity;
- job, reviewer, review report, review-report SHA and base Canonical SHA remain constant across the chain;
- duplicate/replayed revisions or commands are rejected;
- extra unreferenced commands are rejected.

SM-POLY-13 does not trust timestamps to reconstruct authority order. The parent/audit chain is the order.

## Denominator policy

### Measures

`editsPerMeasure` is available only when a positive measure count is supplied and its source artifact SHA-256 is exactly the edited `baseCanonicalSha256`.

The v1 package does not infer full score measure count from edited command locations because those locations contain only changed measures.

### Pages

`ScoreEditCommand.location` contains part, measure, event, staff, voice and onset, but no page identity. Therefore SM-POLY-13 never guesses page count from command evidence.

`editsPerPage` is available only when an explicit positive page count and source artifact SHA-256 are supplied. Otherwise:

```text
page.available = false
page.count = null
editsPerPage = null
```

Measure-level evidence can still remain valid.

## SM-POLY-04 adapter boundary

SM-POLY-04 v1 already contains the `teacherEdits` vocabulary, but its available form requires both `measureCount` and `pageCount`.

`project_teacher_workload_to_sm_poly_04()` therefore requires:

- exact `fixtureId` match;
- exact SM-POLY-04 `engine.canonicalSha256 == SM-POLY-13 baseCanonicalSha256`;
- an empty/unavailable SM-POLY-04 teacher-edit slot;
- both measure and page denominators.

If page evidence is unavailable, SM-POLY-13 remains valid on its own but is not forced into the older all-or-nothing SM-POLY-04 field. This preserves unavailable evidence as unavailable.

The adapter returns a new observation and does not mutate the caller-owned observation.

## Evidence artifact

Contract:

`contracts/polyphonic-teacher-workload-evidence-v1.schema.json`

Implementation:

`services/teacher-review-service/src/scoremosaic_teacher_review/teacher_workload.py`

The evidence includes:

- exact research fixture identity;
- job/reviewer/review-report/base-Canonical scope;
- ordered revision SHA list;
- ordered command SHA list;
- head revision identity;
- sorted distinct edited measure IDs as descriptive evidence;
- exact edit count;
- exact rational edits/measure;
- exact rational edits/page when page denominator evidence exists;
- immutable boundary flags;
- deterministic evidence ID and SHA-256.

## Authority boundaries

SM-POLY-13 is explicitly:

```text
researchEvaluationOnly = true
readOnly = true
modelTrainingSideEffect = false
engineRanking = false
winnerSelection = false
automaticCorrection = false
teacherApproval = false
publicationAuthority = false
productionDecisionAuthority = false
```

It does not:

- add ST-OMR to the Gateway;
- change the Stage 7 minimum Canonical candidate count;
- rank Audiveris/HOMR/Clarity;
- select a winner;
- automatically repair or merge MusicXML;
- create or mutate TeacherScoreRevision;
- approve or publish a score;
- train or update a model;
- activate live Teacher Review writes;
- authorize H7-E or production infrastructure.

## Next evidence gate after SM-POLY-13

After this package, the priority is to populate and qualify the real Teacher-Gold corpus toward the existing minimum readiness gate:

```text
>= 500 eligible verified fixtures
+ required notation-category coverage
+ required scan-quality coverage
+ verified provenance/license eligibility
```

A direct cross-artifact join, selective-prediction threshold, or ST-OMR promotion decision still requires later separately versioned evidence and authorization. No missing SM-POLY number is assigned by this document.
