# Ensemble Comparator v1 Foundation

## Purpose

The 10A comparator foundation compares immutable Canonical Score Model candidates and reports neutral, provenance-preserving disagreements. It does not decide which engine is correct.

This phase uses only the existing Canonical Score Model. It does not alter the OMR Gateway, engine services, raw artifacts, teacher-review workflow, publication flow, or future ST-OMR scope.

## Inputs

`compare_candidates` accepts two to eight in-memory `CanonicalScore` objects.

It does not accept:

- file paths
- URLs
- MusicXML bytes
- MXL archives
- uploads
- database records
- mutable artifact handles
- engine commands

Candidates are sorted by a deterministic identifier derived from their immutable `SourceIdentity`. Caller order cannot influence the comparison result.

## Alignment rules

Foundation alignment is intentionally conservative and deterministic:

1. Parts align by `ordinal`.
2. Measures align by `ordinal` inside an aligned part.
3. Events align by their tuple position in preserved XML event order inside an aligned measure.

The result declares this as `xml-event-ordinal` alignment and states that fuzzy alignment is disabled.

This foundation does not guess whether inserted, deleted, or reordered events represent the same musical event. A missing event produces one `event.presence` difference at that ordinal; it does not create a cascade of field differences.

## Compared domains

### Measure structure

- part presence
- measure presence
- measure number
- implicit-measure state
- expected duration
- observed duration
- time signature at measure start

### Event structure and musical values

- onset
- note, rest, or unpitched kind
- effective duration
- written duration
- written type
- pitch step, alteration, and octave
- chord membership and chord index
- voice
- staff
- ties
- dots
- tuplet ratio
- guitar string and fret when present

Canonical `divisions`, raw XML ordering instructions, and source-specific identifiers are retained as provenance but are not treated as winner evidence. The comparator evaluates normalized musical values rather than rewarding one engine's internal MusicXML representation.

## Difference model

A difference contains:

- deterministic difference identifier
- neutral category and field
- ordinal comparison location
- one observation for every candidate
- source engine and artifact identity
- Canonical Score hash
- part, measure, and event identifiers when available
- event XML path and source event index when available
- candidate-specific observed value

A multi-candidate disagreement is represented once with all observations. The foundation does not create pairwise votes, scores, confidence totals, recommendations, or a preferred value.

## Determinism

The following are deterministic for identical inputs:

- candidate order
- difference order
- difference identifiers
- compact JSON serialization
- comparison-result SHA-256

No timestamp or random identifier is included.

## Resource limits

- maximum candidates: 8
- maximum total events across candidates: 250,000
- maximum reported differences: 200,000

Exceeding a limit fails closed with `ComparisonError`.

## Immutable and disabled boundaries

The result explicitly records:

- read-only comparison: enabled
- engine ranking: disabled
- winner selection: disabled
- automatic MusicXML merge: disabled
- automatic correction: disabled
- teacher approval: disabled
- publication: disabled

The comparator does not mutate Canonical candidates or raw engine artifacts.

## Internal format status

`0.1-foundation` is an internal deterministic comparison shape used for executable tests. It is not the final external, versioned Ensemble comparison-report contract.

The final report contract remains a later gated step after the comparator is validated with fixed real Canonical fixtures from Audiveris, HOMR, and Clarity.

## Acceptance tests

The foundation must prove that:

- musically identical candidates produce no differences
- candidate input order does not affect output
- all requested comparison domains are detected
- missing measures and events do not cause cascading noise
- provenance remains attached to every available observation
- three candidates create one aggregated disagreement per field and location
- no ranking, recommendation, winner, merge, or correction field appears
- candidate Canonical hashes remain unchanged after comparison
- duplicate source identities and resource-limit violations fail closed
