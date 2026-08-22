# ST-OMR Static Synthetic Reading Order Contract

## Status

Phase 24 is developed on a dedicated feature branch from verified `main` commit `143b1727ae9d6e95e3a0667b61e90a8fbd6743f3`.

## Objective

Define and verify a closed, versioned and deterministic repository-owned static reading-order contract derived only from the already pinned Phase 23 synthetic membership evidence.

The phase records ordered symbol identifiers per staff and per measure. It does not perform real OMR, visual inference, musical interpretation or accuracy evaluation.

## Required contract boundary

- closed JSON Schema 2020-12 subset
- repository-owned static reading-order artifact
- pinned schema, artifact and source membership manifest hashes
- mandatory Phase 23 membership trust-chain verification
- ordered `symbolId` lists per staff and measure
- exact source-symbol coverage: every source symbol appears exactly once
- staff and measure references constrained by Phase 23 membership
- canonical deterministic ordering and canonical SHA-256
- byte-identical repeated verification
- fail-closed path, symlink, filename, JSON, schema, hash and tamper handling
- positive and negative tests
- dedicated Phase 24 CI plus all historical ST-OMR regressions

## Fixed exclusions

- no real or trained OMR model or external weights
- no PDF, image or user input
- no pitch, duration or voice
- no notehead–stem attachment
- no beam or chord relations
- no notation graph
- no MusicXML
- no HTTP upload, inference or model-loading endpoint
- no Gateway or Ensemble integration
- no training or self-training
- no network, GPU, persistent storage or production
- no readiness promotion; `/ready` remains 503

## Merge policy

The pull request remains draft. It must not be marked ready or merged without a separate architectural review and explicit approval.
