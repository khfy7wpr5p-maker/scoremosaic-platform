# Teacher Review Workflow

## 1. Goal

The teacher-review workflow turns engine disagreements and structural checks into an auditable correction process. It must help a teacher locate and edit suspected errors without presenting an engine recommendation as established fact.

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

## 3. Review-panel responsibilities

The future editor should present:

- original PDF page and cropped measure evidence
- notation/TAB representation of the active revision
- engine-by-engine values and confidence evidence
- a filterable issue list
- playback or note audition where available
- validation results after every edit
- revision history and undo

Selecting an issue should focus the corresponding page, measure, staff, voice, and event.

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

A warning must identify what was observed and where it came from. It must not claim certainty that the source image does not support.

## 5. Teacher decisions

For each issue, the teacher can:

- accept an engine or ensemble suggestion
- reject the suggestion and retain the current value
- enter a corrected value
- mark the issue unresolved
- add a review note

Blocking issues must be resolved or explicitly waived by an authorized reviewer before approval.

## 6. Editing model

The primary editor modifies musical fields, not raw XML text. Planned editable fields include:

- pitch step, accidental, and octave
- duration, type, dots, tuplets, ties, and rests
- chord membership and onset
- measure and time signature
- staff and voice
- guitar string and fret
- event insertion and removal

Advanced XML inspection may be added later as a read-only diagnostic view. Direct unrestricted XML editing is not the default workflow.

## 7. Immutable revisions

The following are distinct artifacts:

```text
engine candidates
ensemble recommendation
teacher revision 0001
teacher revision 0002
approved revision
```

Every edit record includes:

- reviewer identity
- job and revision ID
- issue ID, when applicable
- musical location
- old value
- new value
- reason or note
- timestamp
- source candidate or evidence used

Original PDF and engine candidates are never overwritten.

## 8. Approval record

Approval must record:

- approved revision ID and artifact hash
- teacher identity
- approval timestamp
- unresolved warning count
- explicit waivers, if any
- publication eligibility

A boolean such as `teacherApproved` is insufficient on its own because it does not identify who approved which immutable revision.

## 9. Publication rule

A learner-facing application receives only a specifically approved revision. Raw engine outputs, unreviewed ensemble selections, and revisions with unresolved blocking issues are not publishable.

Publication is a separate transition from approval so that an approved revision can be held, withdrawn, or republished without changing its musical content.

## 10. Accessibility requirements

The future review interface must support:

- full keyboard operation
- visible and programmatic focus
- semantic labels for measure and issue navigation
- screen-reader-readable issue descriptions
- no color-only error indication
- scalable text and responsive panels
- textual alternatives for confidence and comparison graphics

## 11. Ensemble v1 restriction

The first Ensemble release only compares, scores, and reports candidates. It does not silently merge raw XML or automatically publish a selected result.
