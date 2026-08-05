# ST-OMR Fixed Evaluation Integration

## Phase 20 boundary

Phase 20 integrates the closed Generated Fixture Suite v1 with a fixed, repository-owned evaluation contract. It does not introduce a real OMR model, user input, PDF/image processing, MusicXML generation, Gateway, Ensemble, external network access, GPU/CUDA, training, persistence, publication, or production traffic.

## Objective

Produce deterministic, suite-level evaluation evidence from synthetic fixtures using explicit metric contracts and fail-closed validation.

## Allowed scope

- repository-owned synthetic fixtures only
- versioned fixed evaluation manifest
- immutable fixture IDs and expected outcome categories
- deterministic per-fixture pass/fail records
- deterministic aggregate counts and canonical SHA-256 evidence
- schema, duplicate, unknown fixture, tamper, ordering, and non-determinism checks
- CPU-only, one worker, bounded memory and timeout policy inherited from prior phases

## Fixed exclusions

- no real notation recognition or accuracy claim
- no AI/model runtime or model loading
- no PDF, image, or user-supplied input
- no HTTP evaluation or inference endpoint
- no MusicXML candidate generation
- no Gateway or Ensemble integration
- no external network, GPU, persistence, training, teacher workflow, publication, or production deployment

## Acceptance criteria

1. The evaluation manifest is versioned and validated fail-closed.
2. Every referenced fixture exists in Generated Fixture Suite v1 exactly once.
3. Evaluation output is deterministic across repeated runs.
4. Aggregate totals equal the per-fixture records.
5. The canonical evaluation SHA-256 is stable.
6. Tampered, duplicate, unknown, unsafe, or malformed inputs fail closed.
7. `/health` remains 200, `/ready` remains 503, and mutating routes remain unavailable.
8. All Phase 15-19 regression and CI gates remain green.

## Non-claim

A passing fixed evaluation only proves deterministic execution against repository-owned synthetic fixtures. It does not prove OMR accuracy, MusicXML correctness, real-score support, or production readiness.
