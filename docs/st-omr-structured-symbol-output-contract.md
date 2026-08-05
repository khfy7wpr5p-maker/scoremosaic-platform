# ST-OMR Structured Synthetic Symbol Output Contract

## Status

Phase 22 starts from `main` commit `8796a8896b6868a67ab7812b807578e03485e7c6` on the isolated branch `feature/st-omr-structured-symbol-output-contract`.

This first commit freezes scope only. It does not enable new runtime behavior, service readiness, user input, production inference, MusicXML generation, Gateway, or Ensemble integration.

## Objective

Define a closed, versioned, deterministic JSON contract for repository-owned synthetic symbol output produced only from repository-owned synthetic fixtures and the repository-only Phase 21 test runtime.

## Allowed scope

- versioned closed JSON Schema
- repository-owned synthetic symbol output only
- bounded symbol kinds: staff, measure, clef, time signature, notehead, stem, beam, rest, barline
- immutable stable IDs and canonical ordering
- integer or explicitly bounded coordinate fields
- bounded confidence values with an explicit representation
- provenance containing model ID/version and fixture ID/version
- immutable output evidence and canonical SHA-256
- byte-identical repeated execution evidence
- positive tests and fail-closed negative tests
- dedicated Phase 22 CI plus all previous ST-OMR regression suites

## Required negative tests

- duplicate symbol ID
- unknown symbol type
- invalid or out-of-range coordinate
- invalid confidence
- malformed fixture or model provenance
- ordering change
- schema version mismatch
- missing required field
- artifact tampering
- nondeterministic output

## Fixed exclusions

- no real or trained OMR model
- no externally sourced model weights
- no PDF, photograph, image, upload, or user file
- no HTTP inference, upload, or model-loading endpoint
- no MusicXML generation
- no Gateway integration
- no Ensemble integration
- no automatic correction, ranking, winner selection, or merge
- no training or self-training
- no teacher approval or publication workflow
- no external network, GPU/CUDA, persistent storage, or production deployment
- no readiness promotion; `/ready` remains 503

## Merge policy

The pull request remains draft until implementation is complete, all local tests pass, all historical and Phase 22 CI checks are green, scope is re-audited, and explicit merge approval is given.
