# Canonical Score Model v1 Foundation

## Purpose

The Canonical Score Model converts one already-isolated OMR MusicXML candidate into a deterministic, provenance-preserving event representation. It gives later Ensemble stages a common basis for comparison without selecting a winner, merging files, or correcting notation.

The raw MusicXML candidate remains the source of record. Canonical JSON is a derived artifact and never replaces the engine output.

## Foundation scope

This stage provides:

- immutable Python model objects
- deterministic JSON serialization and SHA-256 identity
- safe `score-partwise` MusicXML normalization
- exact rational timing in quarter-note units
- part, measure, staff, voice, event, pitch, rest, chord, tie, tuplet, and TAB evidence
- explicit `backup` and `forward` cursor movements
- source engine, version, model, artifact hash, and XML-location provenance
- bounded diagnostics for elements retained only in raw MusicXML
- executable unit and fixture tests
- a JSON Schema contract at `contracts/canonical-score.schema.json`

## Security boundary

The normalizer accepts bytes, not paths or URLs. It does not open files, follow links, download resources, or extract MXL archives.

The foundation rejects:

- DTD and entity declarations
- NUL bytes
- malformed XML
- unsupported roots such as `score-timewise`
- oversized documents, excessive element counts, and excessive nesting
- unsafe artifact references
- notes before `divisions`
- negative cursor movement
- malformed chords, tuplets, time signatures, or TAB positions

Python's XML parser is used only after the byte-level DTD/entity gate. No external entity or network resolution is enabled.

## Timing representation

All onsets and durations use reduced rational numbers:

```json
{ "numerator": 1, "denominator": 3 }
```

Values are measured in quarter-note units. Floating-point values are never used.

For each event the model preserves both:

- `effectiveDuration`: MusicXML cursor duration derived from `<duration>` and the active `<divisions>`
- `writtenDuration`: visual duration derived from `<type>` and dots, before tuplet scaling

A triplet eighth note can therefore retain written duration `1/2` and effective duration `1/3` without silently reconciling them.

## Provenance

The score-level source identifies the engine and immutable candidate artifact. Every event also records its deterministic XML path and zero-based source event index.

Normalization does not remove raw evidence. Unsupported MusicXML elements remain in the original candidate and produce bounded diagnostics when relevant.

## Explicit non-goals

This foundation does not:

- compare two candidates
- align measures between engines
- rank or select an engine output
- merge MusicXML
- infer missing values
- correct pitch, rhythm, voice, staff, chord, or TAB data
- expose an HTTP API
- create jobs or persistent artifacts
- approve or publish a score

## Supported input in v1 foundation

- uncompressed MusicXML bytes
- `score-partwise` root
- pitched notes, unpitched notes, and rests
- inherited or changed divisions and simple/composite additive meters represented by one `<beats>` and one `<beat-type>` pair
- backup/forward timing
- chord notes
- ties, dots, and time-modification tuplets
- technical string/fret pairs

`score-timewise`, compressed MXL, senza-misura, multiple simultaneous time-signature pairs, and engine-specific confidence extensions remain unresolved rather than guessed.

## Acceptance gate

The stage is acceptable only when:

1. the fixed MusicXML fixture always produces the same canonical SHA-256;
2. written and effective durations remain distinct;
3. backup/forward, chord, voice, staff, tie, tuplet, and TAB evidence survive normalization;
4. every event points back to source evidence;
5. hostile or ambiguous XML fails safely;
6. comparison, automatic merge, teacher approval, and publication remain disabled.
