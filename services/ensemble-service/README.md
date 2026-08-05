# Ensemble Service

## Current status

**Canonical Score Model v1, Ensemble Comparator v1 foundation, and Ensemble Comparison Report v1.**

The package contains a deterministic, provenance-preserving MusicXML normalizer, a read-only comparator for two to eight Canonical Score Model candidates, and a stable versioned report wrapper for one neutral comparison result.

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

## Explicit current non-goals

- No fuzzy or semantic event alignment
- No engine ranking, confidence scoring, winner selection, or preferred candidate
- No silent MusicXML merge
- No automatic correction of pitch, rhythm, or any other value
- No HTTP upload, Gateway orchestration, or job endpoint
- No persistence or artifact mutation
- No teacher approval
- No learner-facing publication
- No ST-OMR implementation or integration in this phase

## Local verification

```bash
python -m compileall -q services/ensemble-service/src
python -m unittest discover -s services/ensemble-service/tests -v
```

## Acceptance gate

- identical inputs produce deterministic comparison and report hashes
- candidate input order does not change compact report JSON
- report and comparison hashes are independently verified
- changed counts, content, versions, identity, or boundaries are rejected
- all difference observations retain source and event provenance
- candidate objects and raw artifacts remain unchanged
- ranking, winner selection, merging, correction, teacher approval, publication, and ST-OMR remain disabled

The next gated project step is the Gateway orchestration contract. It does not activate uploads, jobs, persistence, or real orchestration.
