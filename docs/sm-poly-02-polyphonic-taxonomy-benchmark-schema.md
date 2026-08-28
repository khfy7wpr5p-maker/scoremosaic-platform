# SM-POLY-02 — Polyphonic Error Taxonomy and Benchmark Schema

Status: **research/evaluation contract only**  
Production behavior change: **none**

## Purpose

SM-POLY-02 establishes a shared vocabulary and fixture metadata contract for future polyphonic teacher-gold evaluation without changing the existing Stage 7 comparator, Canonical Score, quorum, Teacher Review authority, or production locks.

The two contracts are:

- `contracts/polyphonic-error-taxonomy-v1.json`
- `contracts/polyphonic-benchmark-fixture-v1.schema.json`

The existing frozen `evaluation/fixed-v1` regression dataset remains unchanged. It is still a one-case regression foundation and is not reclassified as a broad polyphonic benchmark.

## Error taxonomy

The taxonomy includes the required shared categories:

`PITCH`, `DURATION`, `ONSET`, `VOICE`, `STAFF`, `REST`, `ACCIDENTAL`, `TIE`, `SLUR`, `TUPLET`, `BEAM`, `STEM`, `CHORD_GROUPING`, `CROSS_STAFF`, `METER`, `MEASURE_BOUNDARY`, `GRACE`, `ORNAMENT`, `OTHER`, `AMBIGUOUS`.

`DOT` and `TAB_POSITION` are retained as explicit additional categories so current ScoreMosaic comparator evidence is not forced into a lossy `OTHER` mapping.

The current Stage 7 comparator vocabulary is preserved. `legacyComparatorCompatibility` documents how current categories may be translated for research reporting. The legacy `measure` category is intentionally marked `requiresRefinement=true` because it can represent measure-boundary, meter, or another structural distinction and must not be guessed into a narrower category.

`AMBIGUOUS` is a valid scientific outcome. It does not grant correction or winner authority.

## Benchmark fixture schema

The fixture schema describes one `page`, `system`, or `measure` evaluation unit and requires:

- immutable source identity and SHA-256;
- source provenance and media type;
- dataset/source license metadata;
- redistribution, training, evaluation, and commercial-use status;
- teacher-gold identity and SHA-256;
- explicit gold verification status;
- notation-class labels;
- notation-feature labels;
- scan-condition labels;
- explicit research-only authority boundaries.

Supported notation classes cover monophonic, 2/3/4+ voices, piano grand staff, dense piano chords, classical-guitar polyphony, independent guitar voices, and cross-staff notation.

Supported notation features cover ties, slurs, tuplets, grace notes, pickup/irregular measures, multi-voice rests, overlapping durations, accidentals, beaming, stem-direction ambiguity, voice reassignment, and staff reassignment.

Supported scan conditions cover clean/high-quality input, low-quality scan, skew, rotation, phone photograph, perspective distortion, low contrast, and damaged/dirty score.

## Teacher-gold and training boundary

Teacher-gold metadata is deliberately separate from engine outputs. This schema contains no engine-output field.

The following are fixed invariants:

```text
separateFromEngineOutputs = true
teacherCorrectionAutomaticallyTrainingData = false
engineOutputsStoredSeparately = true
productionDecisionAuthority = false
```

A teacher correction may become training material only through a separate authorization and dataset-governance process. Benchmark verification alone does not authorize training use.

## Relationship to Stage 7

This package does not modify:

- `scoremosaic_ensemble` comparison behavior;
- Audiveris/HOMR/Clarity engine membership;
- the `>=2` Canonical candidate rule;
- Stage 7 evidence authority;
- automatic winner/merge/correction locks;
- Teacher Review revisions or approval;
- production deployment or API behavior.

SM-POLY-03 may build a teacher-gold benchmark harness on these contracts. Engine outputs should be attached through a separate evaluation-result contract rather than inserted into the teacher-gold fixture record.
