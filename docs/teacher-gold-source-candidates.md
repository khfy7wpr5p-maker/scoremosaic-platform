# Teacher-Gold Source Candidates

## Purpose

This catalogue records external sources worth qualifying for the real Teacher-Gold corpus without confusing source discovery with verified benchmark evidence.

Candidate records live in:

`evaluation/polyphonic-teacher-gold-v1/source-candidates.json`

They are deliberately separate from:

`evaluation/polyphonic-teacher-gold-v1/registry.json`

A source candidate is not a Teacher-Gold fixture.

## Current truthful state

```text
sourceCandidateCount=3
verifiedTeacherGoldFixtureCount=0
eligibleVerifiedTeacherGoldFixtureCount=0
minimumVerifiedFixtures=500
targetVerifiedFixtures=1000
```

No candidate in this catalogue counts toward the minimum.

## First candidates

### DoReMi v1

Role: clean digital image + symbolic pair source.

The published release exposes PNG pages together with MusicXML, MEI, MIDI, OMR metadata and Dorico project material. The dataset documentation says the final published dataset contains openly distributable scores, but this qualification pass did not establish a sufficiently explicit dataset-wide license grant for ScoreMosaic's evaluation record.

Therefore:

```text
licenseState=REVIEW_REQUIRED
teacherVerified=false
countTowardTeacherGoldMinimum=false
```

### OpenScore Lieder — Schubert, Ständchen D.889

Role: voice + piano polyphonic symbolic source suitable for deterministic rendering.

The inspected score directory contains MuseScore source and compressed MusicXML. OpenScore Lieder declares its scores CC0 and documents professional proofreading at corpus level.

That makes the source promising, but not Teacher-Gold yet. Before fixture admission ScoreMosaic still needs a concrete rendered/input artifact, real SHA-256 hashes, exact source/gold pairing and Teacher-Gold verification.

```text
licenseState=CLEAR_CC0
teacherVerified=false
countTowardTeacherGoldMinimum=false
```

### OSSQ-OMR ISMIR 2026 benchmark corpus

Role: polyphonic string-quartet benchmark source with symbolic targets and synthetic/scanned image paths.

OSSQ-OMR declares CC0 for its annotation sources and bulk-distributed derived formats. Its scanned path can depend on external per-score scan provenance, so ScoreMosaic intentionally keeps the mixed scanned candidate at `REVIEW_REQUIRED` until each intended scan is checked individually.

```text
licenseState=REVIEW_REQUIRED
teacherVerified=false
countTowardTeacherGoldMinimum=false
```

## Admission sequence

A candidate can move into the existing Teacher-Gold fixture registry only after all required evidence exists:

1. choose a specific score/page/system/measure;
2. obtain or render the actual OMR input artifact on demand;
3. compute the real SHA-256 of the input artifact;
4. obtain the exact symbolic gold artifact and compute its real SHA-256;
5. record source provenance and evaluation permission;
6. classify notation and scan conditions using the existing SM-POLY-03 contract;
7. perform teacher or review-panel verification;
8. only then add a fixture record to the verified registry.

Git object SHAs, repository paths, dataset reputation or corpus-level proofreading are not substitutes for the required artifact SHA-256 and Teacher-Gold verification.

## Storage policy

The candidate catalogue itself is small public metadata and belongs in GitHub. Large score images/PDFs do not. When a candidate is actually qualified, the existing external-storage manifest determines where retained artifacts may live. Temporary downloads should be removed after benchmark work unless retention is justified.

## Authority boundary

Source discovery does not authorize:

- automatic fixture admission;
- teacher verification;
- automatic downloads;
- training use;
- engine ranking or winner selection;
- Stage 7 changes;
- production decisions.

The next concrete development step is a very small real intake batch, not bulk corpus ingestion.
