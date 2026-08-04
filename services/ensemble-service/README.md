# Ensemble Service

## Current status

**Canonical Score Model v1 foundation only.**

The package now contains a deterministic, provenance-preserving MusicXML normalizer and executable model tests. It does not yet compare candidates, run jobs, expose an API, rank engines, merge MusicXML, or approve a score.

## Implemented foundation

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

See `docs/canonical-score-model.md` for the detailed boundary.

## Planned responsibility

The Ensemble service will own candidate normalization and later comparison. It will preserve each candidate, validate outputs, compare normalized musical events, and create a structured teacher-review report.

## Explicit current non-goals

- No candidate comparison or measure alignment
- No engine ranking or winner selection
- No silent MusicXML merge
- No automatic correction of pitch or rhythm
- No HTTP upload or job endpoint
- No persistence or artifact mutation
- No teacher approval
- No learner-facing publication

## Local verification

```bash
python -m compileall -q services/ensemble-service/src
python -m unittest discover -s services/ensemble-service/tests -v
```

The fixed fixture must produce the pinned canonical SHA-256 recorded in the test suite.

## Future comparison domains

- measure presence, ordering, and duration balance
- time signature and divisions
- pitch, octave, and accidental
- note/rest duration, dots, tuplets, ties, and onset
- chord grouping and simultaneity
- staff and voice assignment
- MusicXML timing structure, including backup/forward semantics
- guitar string, fret, and pitch consistency when present

## Acceptance gate before comparator work

Comparator implementation remains blocked until the canonical contract, hostile XML tests, deterministic fixture hash, and provenance checks pass in GitHub Actions and the feature PR is explicitly approved.
