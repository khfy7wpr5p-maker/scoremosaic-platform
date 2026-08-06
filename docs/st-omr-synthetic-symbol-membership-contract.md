# ST-OMR Synthetic Symbol Membership Contract

## Status

Phase 23 is implemented on draft PR #28 from verified `main` commit `0e5b46cea1cb64677dc6dd2ec6f7b387030a6e6a`.

## Objective

Validate a closed, deterministic, repository-owned static membership sample. No producer, detection, musical interpretation, or accuracy measurement runs.

## Source trust chain

The membership verifier first validates the Phase 22 structured-symbol artifact through the existing repository verifier. That chain enforces the Phase 22 manifest, raw SHA-256, canonical SHA-256, closed semantic contract, allowed `contracts` root, direct-child paths, and symlink rejection. Only the resulting verified symbol records are used by Phase 23.

The Phase 23 manifest pins:

- membership artifact name, raw SHA-256 and canonical SHA-256
- membership schema name and raw SHA-256
- Phase 22 source artifact and manifest names
- Phase 22 source canonical SHA-256
- the static repository sample purpose

## Membership semantics

- every source symbol has exactly one membership record
- each staff has a unique `sourceSymbolId` whose Phase 22 type is `staff`
- each measure has a unique `sourceSymbolId` whose Phase 22 type is `measure`
- staff and measure bounding boxes exactly equal their source-symbol bounding boxes
- every measure fits within its staff
- every symbol fits within its assigned staff and, when present, referenced measure
- staff, measure, membership, and lineage identifiers are unique and canonically ordered

## Fail-closed coverage

The verifier rejects source artifact or source manifest tampering, canonical mismatch, schema hash mismatch, wrong file names, missing files, non-file paths, nested paths, root or file symlinks, unknown or duplicate symbols, wrong source types, lineage bbox mismatches, spatial containment failures, closed-schema violations, and nondeterministic canonical output. Low-level I/O, JSON, key, and type failures are converted to `SyntheticSymbolMembershipError`.

## Fixed exclusions

- no real or trained OMR model or external weights
- no PDF, image, upload, or user input
- no HTTP inference or model-loading endpoint
- no pitch, duration, voice, attachment, beam, chord, reading-order, or notation graph
- no MusicXML, Gateway, Ensemble, correction, ranking, winner selection, or merge
- no training, self-training, teacher publication, network, GPU, persistence, or production
- `/health` remains 200 and `/ready` remains 503

## Merge policy

PR #28 remains draft until all tests and ten CI workflows pass, review threads are clear, architectural re-review is complete, and a separate explicit merge approval is provided.
