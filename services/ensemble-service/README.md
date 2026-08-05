# Ensemble Service

## Current status

**Canonical Score Model v1, Ensemble Comparator v1 foundation, Ensemble Comparison Report v1, and Fixed OMR Evaluation Dataset v1.**

The package contains a deterministic, provenance-preserving MusicXML normalizer, a read-only comparator for two to eight Canonical Score Model candidates, a stable versioned report wrapper for one neutral comparison result, and a frozen-dataset evaluator with exact field metrics.

## Implemented Canonical Score Model foundation

- strict byte-only `score-partwise` MusicXML input
- DTD/entity, size, element-count, nesting, and cursor-safety gates
- exact rational onsets and durations in quarter-note units
- part, measure, staff, voice, note, rest, chord, tie, dot, tuplet, and TAB structures
- explicit `backup` and `forward` timing evidence
- written versus effective duration preservation
- immutable source engine and artifact provenance
- event XML paths and source event indexes
- deterministic JSON serialization and canonical SHA-256
- bounded diagnostics for data retained only in the immutable raw candidate
- JSON Schema contract: `contracts/canonical-score.schema.json`

See `docs/canonical-score-model.md`.

## Implemented Comparator v1 foundation

- accepts only in-memory immutable `CanonicalScore` objects
- compares two to eight candidates in a neutral all-candidates pass
- deterministic candidate ordering independent of caller order
- ordinal part and measure alignment
- conservative XML event-ordinal alignment inside each measure
- measure presence, number, implicit state, duration, and time-signature differences
- event onset, pitch, effective/written duration, note/rest kind, chord membership, voice, staff, ties, dots, tuplets, and TAB differences
- one aggregated difference per field and location rather than pairwise winner votes
- source engine, artifact hash, Canonical hash, event identifier, XML path, and source event index on every available observation
- deterministic difference identifiers and comparison-result SHA-256
- bounded candidate, event, and difference counts

The nested comparator format remains `0.1-foundation`. See `docs/ensemble-comparator-v1-foundation.md`.

## Implemented Ensemble Comparison Report v1

- stable schema version `1.0`
- fixed report type `scoremosaic.ensemble.comparison-report`
- complete nested neutral comparator payload
- deterministic report identifier derived from the comparison hash
- independent report SHA-256 covering all report fields except itself
- runtime verification of both hashes, versions, counts, identity, and disabled decision boundaries
- preserved candidate and event provenance
- no timestamp, random ID, machine identity, or mutable storage reference
- explicit no-accuracy-claim, no-ranking, no-winner, no-preferred-candidate, no-merge, and no-correction flags
- JSON Schema: `contracts/ensemble-comparison-report-v1.schema.json`

See `docs/ensemble-comparison-report-v1.md`.

## Implemented Fixed OMR Evaluation Dataset v1

- frozen and self-hashed dataset manifest
- one manually reviewed reference MusicXML independent of engine output
- pinned Audiveris, HOMR, and Clarity candidate artifacts, versions, model provenance, and SHA-256 values
- exact integer metrics for event presence, onset, kind, effective/written duration, written type, pitch, chord, voice, staff, ties, dots, tuplets, and TAB
- deterministic part/measure/event ordinal alignment
- separate `exactCounts`, `coreSuccess`, and `allFieldsPerfect` gates
- deterministic evaluation-result SHA-256 with full runtime verification
- closed JSON Schemas for dataset and result version `1.0`
- no aggregate score and no general accuracy claim

See `docs/fixed-evaluation-dataset-v1.md`.

## Explicit current non-goals

- No fuzzy or semantic event alignment
- No engine ranking, confidence scoring, winner selection, or preferred candidate
- No silent MusicXML merge
- No automatic correction of pitch, rhythm, or any other value
- No HTTP upload, Gateway orchestration, or job endpoint
- No persistence or artifact mutation
- No teacher approval
- No learner-facing publication
- No live or self-directed model training
- No ST-OMR implementation or integration in this phase

## Local verification

```bash
python -m compileall -q services/ensemble-service/src
python -m unittest discover -s services/ensemble-service/tests -v
```

## Acceptance gate

- the frozen dataset and every referenced artifact verify against pinned SHA-256 values
- identical candidates and manifests produce deterministic result hashes
- all metric counts, exact-count gates, and success gates are recomputed during result validation
- current real engine candidates match their pinned v1 baseline
- candidate objects and raw artifacts remain unchanged
- aggregate scoring, ranking, winner selection, merging, correction, teacher approval, publication, live training, and ST-OMR remain disabled

The next gated project step is **ST-OMR Architecture and Contract**. It does not create an ST-OMR service or activate Gateway and Ensemble integration.
