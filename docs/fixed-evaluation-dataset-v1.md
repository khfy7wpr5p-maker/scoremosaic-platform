# Fixed OMR Evaluation Dataset and Success Metrics v1

## Status

This document defines phase 13 of ScoreMosaic: a frozen, deterministic evaluation dataset and exact success metrics for the current Audiveris, HOMR, and Clarity Canonical Score candidates.

It is a regression foundation, not a general OMR accuracy benchmark.

## Purpose

The fixed dataset provides a stable answer to three questions:

1. Which source, reference, engine versions, model versions, and candidate artifacts were evaluated?
2. Which musical fields matched the manually reviewed reference exactly?
3. Did a later code or model change alter a previously pinned result?

The dataset manifest is stored at `evaluation/fixed-v1/manifest.json`. It is frozen, self-hashed with SHA-256, and contains repository-relative paths and SHA-256 values for every reference and candidate artifact.

## Initial fixed case

Version 1 starts with one deliberately small regression case:

- one part
- one treble-clef staff
- C major
- 4/4
- four measures
- sixteen quarter notes
- no rests, chords, tuplets, dots, or TAB

The reference MusicXML is manually reviewed and is separate from all engine outputs. The three candidate MusicXML files are the already captured real Audiveris, HOMR, and Clarity fixtures.

This narrow case verifies the evaluation machinery and current baseline. It does not support claims about broad score types, handwriting, scanning quality, piano, orchestra, guitar TAB, lyrics, percussion, or general OMR accuracy.

## Exact metrics

Metrics are integer counts only. No floating-point percentage and no aggregate score is used.

The fixed metric order is:

1. event presence
2. onset
3. event kind
4. effective duration
5. written duration
6. written type
7. pitch
8. chord membership and index
9. voice
10. staff
11. ties
12. dots
13. tuplet
14. TAB

`eventPresence` uses the union of reference and candidate event locations as its denominator. All other field metrics use the number of reference events; a missing candidate event is incorrect for every applicable field.

Alignment remains conservative and deterministic: part ordinal, measure ordinal, and event ordinal. Fuzzy or semantic alignment is not introduced in this phase.

## Success gates

`exactCounts` requires exact part, measure, and event counts.

`coreSuccess` requires `exactCounts` plus perfect event presence, onset, kind, effective duration, and pitch.

`allFieldsPerfect` requires `exactCounts` plus every fixed metric to be perfect.

These gates describe performance only on the named frozen case. `generalAccuracyClaim` is always false.

## Pinned initial baseline

For the initial case:

- Audiveris: core success and all-fields perfect
- HOMR: core success and all-fields perfect
- Clarity: core success; two tie observations differ from the manually reviewed reference, so all-fields perfect is false

The baseline is descriptive. It does not rank engines, choose a preferred engine, select a winner, or change Ensemble behavior.

## Integrity and reproducibility

The evaluator:

- validates the closed versioned dataset contract
- rejects extra fields and unsafe paths
- rejects symlinks and repository path traversal
- verifies reference and candidate SHA-256 values
- rejects DTD and entity declarations in the reference MusicXML
- evaluates immutable `CanonicalScore` objects only
- emits a deterministic result with its own SHA-256
- recomputes counts, gates, boundaries, and result hash during validation

Changes to the reference, truth events, metrics, cases, baselines, engine versions, or model versions require a new reviewed dataset version. The frozen v1 manifest must not be edited silently.

## Explicit exclusions

This phase does not enable:

- live file upload
- live engine execution
- Gateway dispatch or queues
- persistent artifact storage
- aggregate accuracy scoring
- engine ranking or winner selection
- automatic MusicXML merge or correction
- teacher approval or learner publication
- live or self-directed model training
- ST-OMR implementation or integration

The next gated phase is **ST-OMR Architecture and Contract**. It must remain a separate architecture and contract step before any ST-OMR service code is created.
