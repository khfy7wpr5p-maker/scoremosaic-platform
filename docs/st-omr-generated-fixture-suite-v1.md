# ST-OMR Phase 19 — Generated Fixture Suite v1

## Purpose

Expand the Phase 18 closed deterministic execution proof from one repository-owned generated fixture into a small versioned suite of synthetic fixtures without enabling a real OMR model, user input, or production inference.

## Allowed scope

- repository-owned generated fixtures only
- versioned fixture registry v1
- multiple synthetic notation-shape categories represented as deterministic bytes/metadata
- pinned SHA-256 for every input and golden output
- deterministic repeated execution evidence
- suite-level summary containing counts and hashes only
- fail-closed rejection of duplicate IDs, unknown schema versions, unsafe paths, symlinks, tampered inputs, tampered golden outputs, and non-deterministic results
- CPU-only, one worker, bounded timeout and memory policy inherited from earlier phases
- dedicated tests and CI

## Fixed exclusions

- no AI or OMR model runtime
- no real notation recognition or accuracy claim
- no PDF, image, upload, or user-provided file
- no HTTP inference route
- no MusicXML candidate generation
- no Gateway or Ensemble integration
- no external network, GPU/CUDA, persistence, training, teacher workflow, publication, or production deployment

## Acceptance gates

1. Every registry entry has a unique ID and supported schema version.
2. Every fixture and golden output is a direct non-symlink child of the allowed fixture root.
3. Every pinned SHA-256 matches before execution.
4. Running the complete suite twice produces byte-identical canonical evidence.
5. Any malformed, duplicated, tampered, unsafe, or non-deterministic case fails closed.
6. `/health` remains 200, `/ready` remains 503, and mutating routes remain unavailable.
7. All Phase 15–18 regression tests and Phase 19 CI pass before explicit squash-merge approval.
