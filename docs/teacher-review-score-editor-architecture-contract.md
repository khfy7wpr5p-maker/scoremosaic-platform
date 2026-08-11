# Teacher Review Score Editor — Architecture Contract

## Status

TR-0A documentation/architecture contract only.

This document defines the intended architectural position, trust boundaries, authority rules, data contracts, validation obligations, accessibility requirements, and secure development sequence for a future Teacher Review Score Editor.

This document does **not** implement or activate the editor, Teacher Review API, storage, engine dispatch, upload, playback, publication, or production capability.

## 1. Purpose

The Teacher Review Score Editor is a future authorized-review surface for inspecting OMR disagreements, comparing source evidence, entering bounded musical corrections, validating those corrections, and producing immutable teacher revisions that may later be approved and published through a separate barrier.

The editor is a review-support capability. It must not convert an OMR engine, renderer, playback system, or Ensemble recommendation into an authority over musical truth.

ScoreMosaic remains an OMR and teacher-review platform, not a learner-facing playback, narration, or lesson application. Playback inside this editor is limited to review assistance.

## 2. Architectural position

The target flow is:

```text
PDF / image
    |
    v
Safe Intake
    |
    v
Immutable source artifact
    |
    v
OMR engine candidates
    |
    v
Candidate Safety
    |
    v
Canonical Score
    |
    v
Ensemble comparison
    |
    v
Review Report
    |
    v
+--------------------------------------+
| Teacher Review Score Editor          |
| - source evidence                    |
| - read-only notation rendering       |
| - structured musical edit requests   |
| - validation feedback                |
| - review-only cursor/playback        |
+--------------------------------------+
    |
    v
Immutable TeacherScoreRevision
    |
    v
Musical + structural validation
    |
    v
Corrected MusicXML derivative
    |
    v
MusicXML safety validation
    |
    v
Canonical round-trip verification
    |
    v
Teacher approval bound to exact revision/hash
    |
    v
Publication barrier
```

The Teacher Review Score Editor must remain outside:

- OMR engine services;
- OMR Gateway engine execution logic;
- Candidate Safety validation;
- Canonical normalization authority;
- Ensemble comparison authority.

It consumes immutable outputs from those stages and creates new teacher-owned revision artifacts. It never mutates upstream source artifacts, engine candidates, Canonical Score artifacts, or Ensemble evidence in place.

## 3. Existing foundations and preserved authority

The editor may rely on existing foundations only as evidence:

- immutable source and candidate identities;
- Candidate Safety results;
- Canonical Score event/timing/provenance data;
- Ensemble comparison/report evidence;
- Review Report issue identity and location fields.

These inputs remain authoritative only for the facts their contracts establish. In particular:

- Candidate Safety establishes structural/security acceptability, not musical correctness;
- Canonical Score is a deterministic derived representation of one accepted candidate, not an approved score;
- Ensemble produces comparison evidence and recommendations, not a final merged truth;
- Review Report identifies review issues and evidence, not approved corrections.

## 4. Non-goals and explicit non-activation

TR-0A does not:

- add or expose a Teacher Review API;
- enable external upload;
- enable Gateway orchestration or network engine dispatch;
- add production persistence or object storage;
- modify OMR engine behavior;
- modify Candidate Safety behavior;
- modify the Canonical Score schema or normalizer;
- modify Ensemble comparison, ranking, or recommendation behavior;
- allow unrestricted raw MusicXML editing;
- implement corrected MusicXML generation;
- implement a renderer, editor, cursor, MIDI, SoundFont, or playback engine;
- implement RBAC or approval endpoints;
- enable publication;
- change the Gate C -> D -> E -> F -> G security sequence.

## 5. Review workspace layout

The future interface is divided into four principal regions.

### 5.1 Source Evidence panel

Read-only responsibilities:

- original immutable PDF/image page;
- selected measure crop or source region;
- page and measure identity;
- engine-specific evidence for the same musical location;
- engine identity/version where available;
- disagreement/confidence evidence without overstating certainty;
- source artifact and evidence provenance.

A source crop is a presentation derivative. It must be tied to the immutable source artifact identity/hash and a bounded source-region contract. Source-region rendering/cropping is not part of Safe Intake B.4 and must not weaken or replace Safe Intake.

### 5.2 Score View panel

Read-only rendering responsibilities:

- staves and measures;
- supported clefs/notation as available from the selected rendering input;
- notes, rests, durations, dots, tuplets, ties, chords, staff/voice structure, onset/timing evidence, and TAB evidence where supported;
- issue markers that are not color-only;
- synchronized focus for selected page/measure/staff/voice/event.

A renderer is a presentation adapter. Its internal score model is never the platform source of record.

### 5.3 Structured Edit panel

The primary editor operates on bounded musical fields, not unrestricted raw XML text.

A future edit-command allowlist may include only fields backed by an explicitly reviewed musical contract. Initial fields are expected to include:

- pitch step, accidental/alter, octave;
- effective/written duration and written note type;
- dots;
- note/rest state;
- ties;
- tuplets;
- time signature;
- staff and voice;
- chord membership and onset;
- event insertion/removal;
- guitar string and fret.

Fields not represented safely by the then-current revision/canonical contracts must remain read-only or deferred. In particular, engraving-specific structures such as beam, clef, slur, key-signature, and other unsupported notation must not be made editable merely because a renderer can display them.

### 5.4 Review Transport panel

Future controls may include:

- beginning;
- Play;
- Pause;
- Stop;
- bounded tempo control;
- start from a selected measure;
- play selected measure;
- loop selected measure;
- measure cursor;
- beat cursor;
- active note/chord cursor.

Playback is a presentation/audition adapter only. Playback output must never determine whether a pitch, rhythm, voice, chord, TAB position, or other musical value is correct.

## 6. Issue focus and musical location

The existing Review Report location is useful for review navigation, but a future editable revision requires a stronger stable-location contract.

A future issue/edit location should be able to bind, where applicable:

- source artifact ID and SHA-256;
- page number;
- source region identity and bounded geometry;
- candidate ID/artifact hash;
- Canonical Score SHA-256;
- part ID;
- measure ID and displayed measure number;
- staff;
- voice;
- stable event ID;
- exact rational onset;
- source XML path/source event index where applicable.

UI list indices alone are insufficient as durable edit identities because insertion/removal can shift positions between revisions.

Selecting an issue should focus the corresponding source evidence, score location, staff/voice, and event without changing any review state by itself.

## 7. Immutable TeacherScoreRevision direction

Every accepted teacher edit must create a new immutable revision state. Upstream artifacts and earlier revisions remain unchanged.

The future `TeacherScoreRevision` contract should bind at minimum:

- revision ID;
- parent revision ID, when any;
- job ID;
- reviewer identity;
- source/review-report identity;
- base candidate identity/hash;
- base Canonical Score SHA-256;
- edit command identity/hash;
- resulting musical-state identity/hash;
- validation report identity/hash;
- unresolved/blocking issue counts;
- creation timestamp;
- immutable status.

Undo/redo must be append-only revision activity. Undo must create a new inverse revision and must not erase a prior edit or audit event.

Concurrent edits must fail safely when based on a stale parent revision/hash unless an explicitly reviewed conflict-resolution contract exists.

## 8. ScoreEditCommand direction

The future `ScoreEditCommand` contract must be closed and allowlisted. It must not accept arbitrary XML fragments, arbitrary object paths, executable expressions, or renderer-native mutation objects.

Each command should bind:

- command ID;
- target parent revision ID/hash;
- reviewer ID;
- job ID;
- issue ID when applicable;
- stable musical location;
- operation type;
- old value;
- new value;
- reason/reviewer note;
- source evidence references;
- timestamp.

Server-side validation must independently verify the target revision, target location, allowed operation, value domain, and old-value precondition before creating a new revision.

## 9. Validation after every edit

A revision may not silently self-correct, infer missing musical content, or suppress validator failure.

After each accepted edit, the future validation pipeline must cover at least:

- measure duration versus active time signature;
- note/rest durations;
- voice timing;
- staff/voice placement;
- chord/onset simultaneity;
- backup/forward consistency where represented;
- tie structure;
- tuplet structure;
- supported beam rules only after an explicit beam contract exists;
- missing/extra event or measure evidence where deterministically detectable;
- MusicXML structural safety for materialized derivatives;
- revision-to-Canonical consistency;
- unresolved blocking issue count.

Validation failures are evidence. They must be surfaced to the reviewer and must not be automatically converted into hidden corrections.

## 10. Corrected MusicXML derivative direction

A corrected MusicXML artifact is a derivative of one exact immutable teacher revision. It never overwrites a raw engine result.

The future corrected-MusicXML contract should bind:

- corrected artifact ID;
- job ID;
- exact revision ID/hash;
- source candidate ID/hash;
- source Canonical Score SHA-256;
- MusicXML artifact SHA-256;
- byte size/media type;
- structural/security validation result identity/hash;
- regenerated Canonical Score SHA-256;
- provenance chain;
- draft-versus-approved state;
- approval record identity only when actually approved.

A safe materialization sequence is:

```text
TeacherScoreRevision
    -> deterministic MusicXML materialization
    -> MusicXML safety validation
    -> Canonical re-normalization
    -> semantic/revision consistency verification
    -> immutable corrected MusicXML artifact
```

Failure at any step blocks approval eligibility. A failed renderer or playback adapter must not change the validity of a successfully validated revision or artifact.

## 11. Approval and publication separation

Save, issue-resolution state, corrected state, teacher approval, and publication are separate transitions.

Approval must bind to an exact immutable revision and corrected-artifact hash. A boolean such as `approved=true` without exact identity is insufficient.

Publication must remain a later explicit transition and must reject:

- raw engine candidates;
- Ensemble recommendations;
- draft teacher revisions;
- stale approved hashes;
- revisions with unresolved blocking issues unless an explicit authorized waiver contract permits otherwise.

## 12. Adapter authority matrix

| Component | Permitted authority | Prohibited authority |
|---|---|---|
| Source-evidence viewer | display immutable source-derived evidence | mutate source or create musical truth |
| Score renderer | render validated review input and focus locations | mutate Canonical/revision state or approve values |
| Structured editor UI | request typed edit commands | write arbitrary XML or bypass server validation |
| Revision materializer | derive one new immutable revision | overwrite source/candidate/previous revision |
| Musical validator | report/pass/fail reviewed invariants | guess ambiguous music or silently repair |
| MusicXML materializer | derive MusicXML from exact revision | modify the revision while exporting |
| Cursor adapter | display position on a validated timeline | alter musical timing/state |
| Playback adapter | audition the same validated timeline | decide correctness or approval |
| Approval service | approve exact authorized revision/hash | approve "latest" or ambiguous state |
| Publisher | publish only explicitly eligible approved artifacts | publish machine-only or draft artifacts |

## 13. Renderer boundary

A browser-based notation renderer may be evaluated later, but technology selection is not made by TR-0A.

Any renderer integration must satisfy:

- one-way presentation input from an explicitly selected review snapshot;
- no authority to rewrite Canonical Score or TeacherScoreRevision;
- deterministic mapping back to stable platform measure/event identities where cursor/edit focus is required;
- failure isolation: renderer failure cannot invalidate upstream OMR, Candidate Safety, Canonical, Ensemble, or revision evidence;
- bounded score/document size and browser-resource behavior;
- safe text/metadata rendering and XSS-resistant integration;
- accessibility and keyboard focus requirements.

Technology compatibility experiments are evidence only. A successful rendering demo is not a production-ready Teacher Review feature.

If a future renderer requires an external executable or conversion process, that adapter additionally requires a separate security review covering:

- fixed executable identity/version/hash where applicable;
- no shell interpolation;
- fixed/allowlisted arguments;
- server-controlled temporary directories and paths;
- timeout/cancellation;
- CPU/memory/output-size limits;
- network behavior;
- validated output type/structure;
- cleanup and crash recovery.

## 14. Cursor and playback boundary

Cursor, renderer, and playback must consume the same validated revision snapshot and the same server-defined musical timeline.

The platform timeline should preserve exact rational timing rather than renderer/player floating-point state as the source of truth.

Playback/cursor integration requires a separate evidence gate covering at least:

- measure/beat/event mapping;
- simultaneous chord events;
- seek and measure-loop behavior;
- tempo limits;
- stale-revision rejection;
- pause/stop state convergence;
- audio/render failures without revision mutation;
- pinned/approved SoundFont or audio assets when used;
- no arbitrary user-supplied executable, MIDI program, or SoundFont trust path.

## 15. Accessibility requirements

The future editor must preserve and extend the existing Teacher Review accessibility direction:

- full keyboard operation;
- visible and programmatic focus;
- semantic measure/issue/event navigation;
- screen-reader-readable issue descriptions;
- no color-only issue indication;
- icon/text/category cues for errors and warnings;
- scalable text and responsive panels;
- textual alternatives for confidence/comparison graphics;
- accessible transport controls and playback state announcements.

## 16. Security-gate dependencies

The Teacher Review Score Editor is Gate F work and does not reorder the security sequence.

### Gate C dependency

Remaining internal-dispatch controls and any later dispatch activation remain independent prerequisites for live OMR orchestration. Teacher Review work does not activate them.

### Gate D dependency

Writable revisions require durable job/artifact state, immutable storage semantics, SHA-256/provenance persistence, idempotency, cancellation/recovery, and crash-window behavior before live review data can be trusted across restarts.

### Gate E dependency

A live Teacher Review API requires authenticated/authorized API boundaries, request scoping, abuse/rate controls where applicable, idempotency, and privacy-safe error/logging behavior.

### Gate F dependency

Gate F should be split conceptually so authorization exists before writable editing:

- **TR-8A / Gate F authorization foundation:** reviewer RBAC, audit identity, authorized read/write scope, and stale-target protection before TR-4 writable editing is activated;
- **TR-8B / Gate F approval-publication barrier:** exact revision/hash approval, blocking-issue/waiver rules, and separate publication eligibility after corrected-export validation exists.

This split does not move Gate F before Gate E. It only prevents an editor write surface from preceding its authorization boundary.

### Gate G dependency

Production readiness still requires supply-chain evidence, secrets, monitoring, resource/concurrency limits, backup/restore, rollback, staging soak, and production acceptance.

## 17. Safe development sequence

The proposed Teacher Review sequence is:

1. **TR-0 — Documentation/Architecture Contract**
2. **TR-1 — Immutable TeacherScoreRevision and ScoreEditCommand contracts**
3. **TR-2 — Revision validation and MusicXML regeneration contract**
4. **TR-3 — Read-only score viewer and issue-focus mapping**
5. **TR-4 — Draft structured teacher correction panel**
6. **TR-5 — Measure/beat/event cursor**
7. **TR-6 — Isolated playback adapter and Play/Pause/Stop**
8. **TR-7 — Corrected MusicXML export contract**
9. **TR-8 — RBAC, audit, approval, and publication barrier**
10. **TR-9 — Controlled staging E2E and teacher acceptance**

Security dependency refinement:

- Gate D and Gate E must precede activation of persistent/writable Teacher Review behavior.
- TR-8A authorization/audit must be demonstrated before TR-4 is enabled as a live write surface.
- TR-8B approval/publication remains after validated export capability.
- TR-3 may use repository-owned static fixtures for a non-production compatibility experiment before live API/storage dependencies exist, but such an experiment does not count as a completed Gate F runtime capability.

## 18. Minimum evidence expectations by stage

Every implementation stage after TR-0 requires scoped evidence appropriate to the changed boundary.

- **TR-1:** schema/runtime invariants, immutable parent chain, invalid operation/value/location rejection, stale parent rejection, append-only undo.
- **TR-2:** duration/meter, voice timing, chord/onset, tie/tuplet, backup/forward, structural MusicXML safety, deterministic regeneration and round-trip mismatch rejection.
- **TR-3:** repository-owned notation/TAB fixtures, issue-to-event focus, renderer failure isolation, hostile metadata/XSS coverage, keyboard/accessibility checks.
- **TR-4:** typed edit requests, authorization, stale revision, duplicate/idempotent request behavior, visible validator failures, unrestricted XML-edit rejection.
- **TR-5:** rational timeline mapping, measure/beat/event cursor, chord simultaneity, seek/loop, stale-snapshot rejection.
- **TR-6:** Play/Pause/Stop, measure loop, bounded tempo, audio failure isolation, approved assets, no revision mutation.
- **TR-7:** immutable export, provenance/hash binding, MusicXML safety, Canonical round-trip equality/expected-difference rules, draft/approved separation.
- **TR-8:** unauthorized read/write/approve/publish negatives, exact hash approval, blocking issue and waiver rules, append-only audit evidence.
- **TR-9:** controlled staging E2E, restart/failure injection, concurrency, artifact lineage, browser/accessibility evidence, teacher acceptance.

For each implementation package, completion requires fresh focused tests, affected regression suites, relevant broader regression/build validation, GitHub-hosted CI evidence, and final diff/scope review. A technology proof-of-concept alone is never completion evidence.

## 19. Deferred contract gaps

TR-0A deliberately does not change Canonical Score v1.

Before later editor stages can safely expose some notation fields, separate reviewed contracts may be required for concepts not currently represented as first-class editable Canonical data, including for example:

- beam structure;
- clef changes;
- key signatures;
- slurs and broader engraving semantics;
- source-page bounding geometry;
- stable cross-revision event identity rules.

These gaps must not be solved implicitly inside a renderer or raw XML editor.

## 20. Planned future contract families

Subject to separate approval, later stages may introduce closed versioned contracts such as:

- `TeacherScoreRevision`;
- `ScoreEditCommand`;
- stable issue/source-region location;
- revision validation report;
- corrected MusicXML artifact/provenance;
- approval record and publication eligibility.

TR-0A does not create those schemas.

## 21. Exit rule for TR-0A

TR-0A is complete only when this architecture contract is reviewed and accepted as documentation evidence without claiming any runtime capability.

Its acceptance has **no activation effect**. External upload, engine dispatch, persistence, Teacher Review API, editing, playback, approval, and publication remain disabled or unimplemented until their existing security gates and separately approved implementation packages pass.
