# ST-OMR Offline Generated-Fixture Inference

## Purpose

Phase 18 introduces a deterministic closed execution core for repository-owned generated fixtures. It does not load an AI model and does not claim OMR capability or accuracy.

## Execution boundary

The runner accepts only a manifest that is a direct, non-symlink child of `services/st-omr-service/fixtures`. The manifest pins the generated input SHA-256 and deterministic golden-output SHA-256. Path escape, symlinks, malformed manifests, changed inputs, and changed golden output fail closed.

The closed core computes reproducible structural evidence from fixture bytes. It is a lifecycle and isolation proof, not a notation-recognition algorithm.

## Fixed exclusions

- no user files, PDF, image, upload, or HTTP inference endpoint
- no model deserialization, model runtime, neural inference, or accuracy claim
- no Gateway or Ensemble integration
- no external network, GPU, CUDA, persistence, training, teacher workflow, or publication
- no MusicXML candidate generation

## Preserved service behavior

- `GET /health` returns 200 and exposes closed fixture capability evidence
- `GET /ready` returns 503 because production model inference remains disabled
- mutating HTTP methods remain unavailable
- CPU-only, bounded-resource, single-worker policies remain in force

## Promotion gate

A later phase may introduce an actual pinned runtime only after deterministic repetition, fixture/golden integrity, timeout behavior, prior-phase regression, and CI all pass. This phase must not be interpreted as permission to process user data.
