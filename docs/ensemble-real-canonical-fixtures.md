# Real Canonical Fixture Validation

## Purpose

Phase 10B validates the existing Canonical Score Model and Ensemble Comparator v1 foundation against outputs produced by the pinned, isolated Audiveris, HOMR, and Clarity runtimes.

The phase does not rank engines, select a winner, merge MusicXML, correct musical values, run Gateway jobs, approve a score, publish learner data, or implement ST-OMR.

## One shared musical source

All three engines receive renderings of the same bounded LilyPond source:

`services/ensemble-service/tests/fixtures/real-engines/shared-score.ly`

The source contains one treble-clef part, a C-major key signature, a 4/4 time signature, four measures, and sixteen quarter notes. CI renders:

- PDF for Clarity
- PNG from that same PDF for Audiveris and HOMR

The SHA-256 of the LilyPond source is attached to every capture record. This proves that the candidate artifacts came from one fixed musical test source; it does not claim that the engines recognized it correctly.

## Runtime identities

The capture workflow uses only the already verified runtime containers:

- Audiveris 5.11.0
- HOMR 0.7.0 with its three pinned model checksums
- Clarity source revision `c6bb8a4d2a5b52842a9c41bd0f761f58d02f6f82` and model revision `ee14c1e41ab371fe27bf8a2707ea588560077e73`

Each runtime remains non-root, read-only, network-isolated, capability-dropped, resource-bounded, and private. No upload or HTTP conversion endpoint is enabled.

## Safe capture boundary

Real engine output is first retained as an immutable workflow artifact. The capture helper then creates a bounded uncompressed `score-partwise` MusicXML fixture for the existing byte-only Canonical normalizer.

For MXL input, capture requires:

- a valid bounded ZIP container
- no encryption, symbolic links, traversal paths, duplicate members, or excessive expansion
- one `META-INF/container.xml`
- exactly one declared MusicXML rootfile

For XML input, capture:

- rejects entity declarations
- removes only the canonical Recordare MusicXML partwise DTD declaration without resolving it
- rejects noncanonical or multiple DTD declarations
- requires well-formed `score-partwise` MusicXML

Capture does not alter notes, rests, pitches, durations, voices, staves, ties, tuplets, chords, TAB values, measures, or ordering. The original artifact SHA-256, extracted XML SHA-256, captured XML SHA-256, engine identity, model identity, and shared-source SHA-256 are recorded deterministically.

## Canonical and comparator validation

CI normalizes all three captured MusicXML candidates with the existing Canonical Score Model. It then verifies:

- every candidate has the expected engine and artifact provenance
- every event retains XML path and source-event index provenance
- each candidate has at least one measure and event
- candidate hashes remain unchanged through comparison
- input order does not change the serialized comparison or result hash
- one neutral three-candidate comparison is produced
- all ranking, winner, merge, correction, teacher-approval, and publication boundaries remain disabled

Differences are evidence for later review. They are not scores, votes, confidence values, recommendations, or corrections.

## Fixture promotion gate

The first successful real-engine run produces a temporary validation bundle. Fixed MusicXML fixtures and a deterministic manifest may be committed only after that bundle is inspected and its hashes, counts, provenance, and disabled boundaries are pinned in tests.

A successful runtime capture does not by itself prove musical accuracy. It proves only that the pinned engines can produce bounded candidate artifacts that the Canonical model and neutral comparator can process reproducibly.

## Explicit non-goals

- no engine ranking or preferred candidate
- no winner selection or confidence voting
- no fuzzy or semantic event alignment
- no automatic MusicXML merge
- no automatic pitch, rhythm, or notation correction
- no final external versioned comparison-report contract
- no Gateway orchestration, upload, persistence, or public API
- no teacher approval or publication
- no ST-OMR service, model, contract, or integration
