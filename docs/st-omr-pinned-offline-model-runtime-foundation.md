# ST-OMR Pinned Offline Model Runtime Foundation

## Status

Phase 21 is implemented on PR #26. Phase 20 was squash-merged into `main`, and PR #26 now targets `main` directly.

## Phase 21 boundary

Phase 21 introduces the first explicitly loaded repository-controlled test model for ST-OMR. The model is loaded only after manifest, path, provenance, and SHA-256 validation and is executed only against repository-owned synthetic fixtures.

This phase proves model lifecycle, deterministic loading, bounded CPU execution, and fail-closed behavior. It does not introduce a real OMR model or an accuracy claim.

## Allowed scope

- repository-owned hand-authored test model only
- pinned model artifact and manifest
- SHA-256 verification before model parsing or loading
- closed manifest, provenance, and boundary validation
- deterministic integer-only linear runtime
- repository-owned synthetic fixtures only
- deterministic feature extraction and output evidence
- CPU-only, one worker, bounded memory and timeout policy inherited from prior phases
- model loading and inference only through an explicit offline function
- dedicated tests and CI

## Fixed exclusions

- no trained or externally sourced model weights
- no real notation recognition or OMR accuracy claim
- no PDF, image, upload, or user-provided input
- no HTTP inference or model-loading endpoint
- no MusicXML candidate generation
- no Gateway or Ensemble integration
- no external network, GPU/CUDA, persistence, training, self-training, teacher workflow, publication, or production deployment
- no service readiness promotion; `/ready` remains `503`

## Acceptance criteria

1. The model artifact is a direct non-symlink child of the allowed `models` root.
2. The artifact SHA-256 matches the pinned manifest before parsing or loading.
3. The manifest proves that the model is repository-owned, hand-authored, untrained, externally unweighted, and not production eligible.
4. The runtime accepts only the closed deterministic integer-linear v1 format.
5. A repository synthetic fixture produces byte-identical evidence across repeated runs.
6. Tampered artifacts, invalid manifests, unsafe paths, malformed weights, ties, tampered fixtures, and unsupported runtime versions fail closed.
7. `/health` exposes the capability as available but not requested; it does not load a model.
8. `/ready` remains `503`, mutating routes remain unavailable, and no HTTP inference route exists.
9. All Phase 15-20 regression and Phase 21 CI gates pass.

## Verification sequence

1. PR #25 was squash-merged into `main`.
2. The Phase 21 branch was rebuilt on the Phase 20 merge commit.
3. PR #26 was retargeted to `main`.
4. Final `main`-targeted regression checks must pass before the PR is marked ready for review.

## Non-claim

A passing Phase 21 run proves only that a pinned repository test model can be safely loaded and executed offline against synthetic fixtures. It does not prove music knowledge, notation recognition, MusicXML correctness, generalization, or production readiness.
