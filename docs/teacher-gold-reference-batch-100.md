# Teacher-Gold Reference Batch 100 v1

## Status

This package records a deterministic, non-counting 100-example OpenScore Lieder reference batch for research/evaluation preparation.

It is **not** Teacher-Gold admission.

Current verified Teacher-Gold state remains:

```text
verifiedFixtureCount=10
minimumVerifiedFixtures=500
targetVerifiedFixtures=1000
readiness=NOT_READY
```

No model training, Stage 7 engine/quorum change, automatic correction/merge, or production decision authority is authorized by this batch.

## Source and renderer lineage

- source repository: `OpenScore/Lieder`
- source commit: `38c5db510224d9facdc4b08d741fc788cfb58ea8`
- license: `CC0-1.0`
- license SHA-256: `a2010f343487d3f7618affe54f789f5487602331c0a8d03f49e9a7c547cf0499`
- renderer: MuseScore 3.6.2
- renderer AppImage SHA-256: `c59a41ee88bc7c565a939b9c73498ac0451bbd86574e95cb6e359302c1465290`
- first-page render resolution: 150 dpi
- rendered review pages are flattened onto opaque white.

The five previously admitted OpenScore Lieder Teacher-Gold paths are excluded before selection.

## Deterministic selection

The discovery workflow lists pinned `.mxl` paths and ranks them with `SHA256_PATH_ASC_V1`. It oversamples 180 candidates and accepts the first 100 that successfully produce a bounded, nonblank first-page render.

Each accepted pair receives:

- exact MusicXML/MXL SHA-256;
- exact rendered first-page PNG SHA-256;
- byte sizes;
- structural observations from the symbolic source;
- explicit `CLEAR_CC0` rights state;
- `DRAFT` human-review state;
- `countTowardTeacherGoldMinimum=false`;
- `trainingAuthorization=NOT_AUTHORIZED`.

Temporary corpus and renderer bytes are deleted at the end of the workflow.

## 10% human audit policy

The 100 automatically prevalidated pairs are **not** sent one-by-one for manual review. A deterministic `GREEDY_STRUCTURAL_TOKEN_COVERAGE_V1` selector chooses 10 examples (10%) intended to maximize notation/structure diversity.

Selected review IDs:

```text
ref_075
ref_059
ref_005
ref_004
ref_007
ref_020
ref_027
ref_008
ref_032
ref_065
```

Teacher review remains `PENDING`. No selected or non-selected item becomes Teacher-Gold without a separate explicit teacher decision and normal fixture admission evidence.

## Coverage observed in the 100-pair batch

```text
score parts:
  1 part  = 4
  2 parts = 86
  3 parts = 3
  4 parts = 4
  5 parts = 2
  6 parts = 1

max staves per part:
  1 staff  = 7
  2 staves = 93

notation features:
  chord elements = 93
  tie/tied       = 89
  slur           = 99
  tuplet         = 37
  grace          = 54
  accidental     = 99

direction@system:
  only-top = 92
  absent   = 8
  also-top = 0
  none     = 0
  invalid  = 0

note element count:
  min    = 132
  median = 819
  max    = 6149
```

The `direction@system` result is useful as additional symbolic coverage for the renderer-independent semantic gate, but it does not turn renderer output into a fidelity oracle.

## Discovery evidence

- workflow run: `34939313877`
- discovery head: `9a6fbac69d7e5ddfe1cfc9148ef1575ec115943c`
- artifact: `10384459686`
- artifact name: `teacher-gold-reference-batch-100-v1`
- artifact ZIP SHA-256: `f7ab7c508f4ec5717394a9230e1f8badf05dfe06fb6d6d1d07b985665e8bb6bf`
- artifact size: `1,138,061` bytes
- discovery manifest SHA-256: `4afd456a763a7eacc0c02bc62202dd507b4d4f15324f7c2b16beeba3fdef0bc8`
- discovery manifest size: `153,299` bytes
- artifact retention: 14 days; current artifact expires `2026-09-29T07:00:51Z`.

The retained review packet contains the discovery manifest, the 10 selected MXL files, their 10 first-page PNGs, and the pinned CC0 license. The full 100-pair media set is intentionally not retained as bulk storage; exact source commit, deterministic selection policy, renderer binary and artifact hashes make regeneration possible.

## Technical render sanity

The 10 selected review renders were inspected only for technical sanity (blank/corrupt/render failure). No such failure was observed. This is **not** teacher verification and does not assert score fidelity.

## Authority boundary

This batch must remain beside the verified Teacher-Gold registry until explicit human decisions exist. It cannot:

- auto-verify a teacher decision;
- auto-admit fixtures;
- increase the 10/500 Teacher-Gold counter;
- authorize training;
- change Stage 7 engines or quorum;
- repair MusicXML automatically;
- enable automatic winner/merge/correction behavior;
- grant production decision authority.
