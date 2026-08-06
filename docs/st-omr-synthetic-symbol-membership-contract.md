# ST-OMR Synthetic Symbol Membership Contract

## Status

Phase 23 scope foundation. This phase starts from verified `main` commit `0e5b46cea1cb64677dc6dd2ec6f7b387030a6e6a` on branch `feature/st-omr-synthetic-symbol-membership-contract`.

## Objective

Define a closed, versioned and deterministic contract that assigns repository-owned synthetic symbols to repository-owned synthetic staff and measure records.

This phase is limited to membership references. It does not perform detection, interpretation or inference.

## Proposed contract boundary

Phase 23 may add:

- a closed JSON Schema for synthetic staff and measure membership
- stable `staffId` and `measureId` records
- explicit symbol-to-staff membership
- explicit symbol-to-measure membership where applicable
- canonical ordering of staff, measure and membership records
- bounded integer geometry inherited from Phase 22
- repository-owned fixture/model provenance
- immutable evidence and canonical SHA-256
- byte-identical repeated validation/canonicalization
- positive and fail-closed negative tests
- a dedicated Phase 23 CI while preserving all historical ST-OMR CI invariants

## Required fail-closed cases

- duplicate staff ID
- duplicate measure ID
- unknown symbol reference
- unknown staff reference
- unknown measure reference
- invalid staff or measure geometry
- symbol assigned outside its staff or measure bounds
- non-canonical ordering
- schema version mismatch
- missing required field
- nested additional property
- provenance mismatch
- artifact tampering
- nondeterministic canonical output
- outside-root artifact, path escape or symlink

## Explicit non-goals

Phase 23 does not add or imply:

- a real or trained OMR model
- external model weights
- PDF, image or user input
- a symbol-producing model
- real symbol detection
- pitch, duration or voice
- notehead–stem attachment
- beam membership
- chord relations
- reading-order semantics
- notation graph construction
- MusicXML generation
- HTTP upload, inference or model-loading endpoints
- Gateway or Ensemble integration
- automatic correction, ranking, winner selection or merge
- training or self-training
- teacher approval or publication
- network, GPU, persistent storage or production
- readiness promotion; `/ready` remains 503

## Safety invariants

- `/health` remains 200
- `/ready` remains 503
- real OMR remains disabled
- user input remains disabled
- HTTP inference remains disabled
- Gateway and Ensemble remain disabled
- network, GPU, persistence and production remain disabled
- the Phase 21 repository test model remains outside the service container
- all existing ST-OMR regression tests remain enabled

## Merge policy

The pull request must remain draft until implementation, negative tests, all historical CI workflows, the dedicated Phase 23 CI and a separate architectural review are complete. Merge requires separate explicit approval.
