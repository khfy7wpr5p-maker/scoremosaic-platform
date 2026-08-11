# Teacher Review Workflow

## 1. Goal

The teacher-review workflow turns engine disagreements and structural checks into an auditable correction process. It must help a teacher locate and edit suspected errors without presenting an engine recommendation as established fact.

This document describes product-level review behavior. The authoritative trust boundaries, adapter authority rules, immutable revision direction, and secure implementation/activation order are defined in [`teacher-review-score-editor-architecture-contract.md`](teacher-review-score-editor-architecture-contract.md). This workflow does not activate a Teacher Review API, writable editor, persistence, playback, approval, or publication capability.

## 2. Review states

```text
needs_review
→ under_review
→ corrected
→ approved
→ published
```

Alternative terminal path:

```text
needs_review or under_review
→ rejected
```

A job may return to `under_review` when an approved revision is reopened. Reopening creates a new revision cycle; it does not erase the previous approval record.

Save/correction state, approval, and publication remain distinct transitions. Approval is never inferred merely because a revision was saved or validated.

## 3. Review-panel responsibilities

The future editor should present:

- original immutable PDF/image page and bounded cropped-measure/source-region evidence
- notation/TAB representation of the active revision
- engine-by-engine values and confidence evidence when that evidence actually exists
- a filterable issue list
- playback or note audition where available
- validation results after every edit
- revision history and append-only undo/redo activity

Selecting an issue should focus the corresponding source page/region, measure, staff, voice, and stable musical event identity without changing review state by itself.

Source-page rendering and measure cropping are presentation-evidence responsibilities. They are not part of Safe Intake B.4 and must remain bound to immutable source identity/hash plus a reviewed source-region contract.

The score renderer and playback/cursor adapters are presentation-only. Their internal score, audio, timing, or cursor state must never become the source of musical truth or silently mutate Canonical Score or a teacher revision.

## 4. Issue categories

The platform may report at least:

- missing, extra, reordered, or structurally invalid measure
- time-signature or measure-duration mismatch
- pitch, octave, accidental, or missing/extra note disagreement
- note-value, dot, rest, tuplet, tie, beam, or onset disagreement
- chord grouping or simultaneity disagreement
- staff or voice assignment disagreement
- `backup`/`forward` timing inconsistency
- guitar string, fret, or pitch-to-TAB inconsistency
- unsafe or invalid MusicXML structure

A warning must identify what was observed and where it came from. It must not claim certainty that the source image does not support and must not synthesize confidence when an engine or validator did not provide one.

Issue reporting support does not imply editability. For example, beam, clef, slur, key-signature, and other notation/engraving structures may be reported or rendered while remaining read-only until an explicit reviewed musical contract safely represents them.

## 5. Teacher decisions

For each issue, the teacher can eventually:

- accept an engine or Ensemble suggestion as a proposed correction
- reject the suggestion and retain the current value
- enter a corrected value through an allowlisted structured edit operation
- mark the issue unresolved
- add a review note

An engine or Ensemble suggestion is evidence only. Accepting a suggestion must create a new immutable teacher revision; it must not promote an upstream engine candidate or Ensemble recommendation into approved truth in place.

Blocking issues must be resolved or explicitly waived by an authorized reviewer before approval.

## 6. Editing model

The primary editor modifies bounded musical fields, not raw XML text. Planned editable fields, subject to separately reviewed contracts, include:

- pitch step, accidental, and octave
- effective/written duration, written type, dots, tuplets, ties, and note/rest state
- chord membership and onset
- measure and time signature
- staff and voice
- guitar string and fret
- event insertion and removal

The initial writable allowlist must be limited to fields represented safely by the approved revision/canonical contracts. Unsupported notation structures such as beam, clef, slur, key-signature, and other engraving-specific semantics remain read-only or deferred until a separate contract explicitly supports them.

Advanced XML inspection may be added later as a read-only diagnostic view. Direct unrestricted XML editing is not the default workflow and must not be accepted as a generic edit-command path.

Every live write request must be server-authorized and independently validate the target revision/hash, stable musical location, allowlisted operation, old-value precondition, and new-value domain. Stale-parent edits fail safely rather than using last-write-wins behavior.

A live writable TR-4 correction panel must not be activated before Gate D durable state, Gate E API security, and TR-8A reviewer RBAC/audit authorization have passed their separately approved evidence gates.

## 7. Immutable revisions

The following remain distinct logical artifacts/evidence:

```text
immutable source
raw engine candidates
Canonical Score derivatives
Ensemble recommendation/report evidence
TeacherScoreRevision 0001
TeacherScoreRevision 0002
corrected MusicXML derivative
approved revision/artifact
```

Every accepted edit creates a new immutable `TeacherScoreRevision`. Undo/redo is append-only revision activity; undo creates a new inverse revision rather than deleting history.

Every edit record includes or binds, as applicable:

- reviewer identity
- job and parent/created revision identity
- issue ID, when applicable
- stable musical location
- old value
- new value
- allowlisted operation
- reason or note
- timestamp
- source candidate/evidence references
- relevant artifact/revision hashes

Original PDF/image, raw engine candidates, Canonical artifacts, Ensemble evidence, and prior teacher revisions are never overwritten.

The exact future revision and edit-command schema remains a separately approved implementation contract; this workflow does not create that schema.

## 8. Validation and corrected MusicXML

A teacher edit must not trigger hidden guessing or silent self-repair. After each accepted edit, validation should cover the musical/structural invariants represented by the approved contracts, including measure/meter duration, note/rest duration, voice timing, staff/voice placement, chord/onset simultaneity, backup/forward consistency where represented, ties, tuplets, unresolved blocking issues, and MusicXML safety for materialized derivatives.

A corrected MusicXML artifact is derived from one exact immutable teacher revision. It never overwrites the OMR candidate. The safe direction is:

```text
TeacherScoreRevision
→ deterministic MusicXML materialization
→ MusicXML structural/security validation
→ Canonical re-normalization
→ revision/semantic consistency verification
→ immutable corrected MusicXML artifact
```

Failure at any validation or round-trip step blocks approval eligibility and is surfaced to the reviewer rather than silently corrected.

## 9. Approval record

Approval must record or bind:

- approved revision ID and exact artifact hash
- teacher/reviewer identity
- approval timestamp
- unresolved warning/blocking-issue state
- explicit authorized waivers, if any
- publication eligibility

A boolean such as `teacherApproved` is insufficient on its own because it does not identify who approved which immutable revision/artifact.

Approval must reject stale or ambiguous state such as “latest revision” without exact identity/hash binding.

## 10. Publication rule

A learner-facing application receives only a specifically approved and publication-eligible artifact. Raw engine outputs, unreviewed Ensemble selections, draft teacher revisions, stale approved hashes, and revisions with unresolved blocking issues are not publishable unless a separately reviewed authorized-waiver rule explicitly permits the blocking state.

Publication is a separate transition from approval so that an approved revision can be held, withdrawn, or republished without changing its musical content.

## 11. Playback and cursor boundary

Future review playback may provide Play, Pause, Stop, bounded tempo, selected-measure playback/looping, and measure/beat/note-or-chord cursor feedback.

Playback and cursor must consume the same validated immutable revision snapshot and the same platform-defined musical timeline. Exact rational musical timing and stable platform event identity remain authoritative; renderer/player floating-point timing or cursor coordinates do not.

Playback is review assistance only. Audio output cannot decide correctness, resolve an issue, create an edit, approve a score, or mutate a revision. Audio/render initialization failures must remain isolated from revision validity.

## 12. Accessibility requirements

The future review interface must support:

- full keyboard operation
- visible and programmatic focus
- semantic labels for measure, issue, event, and transport navigation
- screen-reader-readable issue descriptions
- no color-only error indication
- icon/text/category cues for errors and warnings
- scalable text and responsive panels
- textual alternatives for confidence and comparison graphics
- accessible transport controls and playback-state announcements

## 13. Ensemble v1 restriction

The first Ensemble release only compares, scores, and reports candidates. It does not silently merge raw XML, choose an editable truth, automatically create a teacher correction, or automatically publish a selected result.

A future Teacher Review revision must bind to an explicitly authorized safe base-candidate/revision strategy. Ensemble recommendation alone must not silently select the authoritative editing base.

## 14. Secure implementation dependency

Teacher Review remains Gate F work and does not reorder the project security sequence. The authoritative implementation/activation order is maintained in the TR-0A architecture contract and includes Gate D and Gate E before live writable review behavior, plus TR-8A authorization/audit before TR-4 is activated.

A repository-owned static renderer compatibility experiment may be performed separately for technology evaluation, but such a demo does not activate Teacher Review runtime, does not advance Gate F on its own, and does not authorize live user data.
