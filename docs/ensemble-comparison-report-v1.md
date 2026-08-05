# Ensemble Comparison Report v1

## Purpose

This phase adds a stable, versioned, deterministic report around one existing neutral `ComparisonResult`. It does not change Canonical normalization or comparator behavior.

Contract:

- JSON Schema: `contracts/ensemble-comparison-report-v1.schema.json`
- report schema version: `1.0`
- report type: `scoremosaic.ensemble.comparison-report`
- nested comparator format: `0.1-foundation`

## Deterministic identity

The report has no wall-clock timestamp, random identifier, host name, job identifier, or mutable storage reference.

- `reportId` is derived from the report version, report type, and nested comparison-result SHA-256.
- `comparisonResultSha256` must equal the nested comparator `resultSha256`.
- `reportSha256` covers every report field except itself using canonical sorted compact JSON.
- validation recomputes both hashes and rejects changed counts, boundaries, versions, or content.

The same Canonical candidates produce the same compact JSON, `reportId`, and `reportSha256` regardless of caller candidate order.

## Preserved evidence

The report embeds the complete neutral comparator payload. Candidate summaries and every difference observation retain:

- engine and engine version,
- model version,
- immutable artifact reference and artifact SHA-256,
- Canonical Score SHA-256,
- part, measure, and event identifiers,
- MusicXML path,
- source event index,
- observed value and presence state.

No provenance is replaced with a derived confidence or winner label.

## Explicit neutrality boundaries

The v1 report states that it is read-only and provenance-preserving. It explicitly makes no accuracy claim and provides no:

- engine ranking,
- winner selection,
- preferred candidate,
- automatic MusicXML merge,
- automatic correction.

The nested comparator also keeps teacher approval and publication disabled.

## Validation limits

The report inherits the Comparator v1 limits:

- two to eight candidates,
- at most 250,000 total Canonical events,
- at most 200,000 differences.

The schema is closed at the report top level. Runtime validation additionally checks exact top-level fields, report identity, both SHA-256 values, candidate and difference counts, the `identical` flag, and all disabled decision boundaries.

## Out of scope

This phase does not add Gateway orchestration, uploads, persistence, artifact mutation, motor ranking, confidence voting, final candidate selection, teacher approval, publication, or ST-OMR implementation/integration.
