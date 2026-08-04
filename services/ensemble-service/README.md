# Ensemble Service

## Current status

**Canonical Score Model v1 plus Ensemble Comparator v1 foundation.**

The package contains a deterministic, provenance-preserving MusicXML normalizer and a read-only comparator for two to eight Canonical Score Model candidates. The comparator reports disagreements without ranking engines, selecting a winner, merging MusicXML, or changing any candidate.

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

See `docs/canonical-score-model.md` for the Canonical Score Model boundary.

## Implemented Comparator v1 foundation

- accepts only in-memory immutable `CanonicalScore` objects
- compares two to eight candidates in a neutral all-candidates pass
- deterministic candidate ordering independent of caller order
- ordinal part and measure alignment
- conservative XML event-ordinal alignment inside each measure
- measure presence, number, implicit state, duration, and time-signature differences
- event onset, pitch, effective/written duration, note/rest kind, chord membership, voice, staff, ties, dots, tuplets, and TAB differences
- one aggregated difference per field and location rather than pairwise winner votes
- source engine, artifact hash, canonical hash, event identifier, XML path, and source event index on every available observation
- deterministic difference identifiers and comparison-result SHA-256
- explicit read-only, no-ranking, no-winner, no-merge, and no-correction boundaries
- bounded candidate, event, and difference counts

The serialized `0.1-foundation` comparison shape is an internal deterministic test format. It is **not** the final versioned Ensemble comparison-report contract. That contract remains a later gated phase after real Audiveris, HOMR, and Clarity Canonical fixtures are validated.

See `docs/ensemble-comparator-v1-foundation.md` for the detailed comparison boundary.

## Explicit current non-goals

- No fuzzy or semantic event alignment
- No engine ranking, confidence scoring, or winner selection
- No silent MusicXML merge
- No automatic correction of pitch, rhythm, or any other value
- No HTTP upload, Gateway orchestration, or job endpoint
- No persistence or artifact mutation
- No final external comparison-report JSON Schema
- No teacher approval
- No learner-facing publication
- No ST-OMR implementation or integration in this phase

## Local verification

```bash
python -m compileall -q services/ensemble-service/src
python -m unittest discover -s services/ensemble-service/tests -v
```

## Comparator foundation acceptance gate

- identical musical content produces no differences even when sources differ
- candidate input order does not change serialized output or result hash
- requested measure and event domains produce deterministic differences
- missing parts, measures, and events are reported without cascading field noise
- all available observations retain source and event provenance
- three or more candidates produce neutral aggregated observations, not pairwise votes
- candidate objects and raw artifacts remain unchanged
- ranking, winner selection, merging, correction, teacher approval, and publication remain disabled

The next gated step is validation against fixed real Canonical fixtures from Audiveris, HOMR, and Clarity. It does not broaden this foundation into Gateway orchestration or a public API.
