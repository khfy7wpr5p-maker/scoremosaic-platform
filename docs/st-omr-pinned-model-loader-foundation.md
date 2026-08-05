# ST-OMR Pinned Model Loader Foundation

## Purpose

This phase verifies that a future ST-OMR model artifact is pinned by an explicit manifest, constrained to an allowed local directory, and protected by SHA-256 integrity checks. Verification does not load or execute the artifact.

## Security boundary

The validator fails closed when:

- the allowed root is not the local `models` directory;
- the manifest is missing, malformed, unsupported, or a symlink;
- the artifact escapes the allowed root;
- the artifact is missing or a symlink;
- the SHA-256 value is malformed or does not match.

A successful result is `verified_not_loaded`. It is not evidence that the model is usable, accurate, trusted, or ready for inference.

## Fixed exclusions

- no model framework or runtime dependency;
- no model deserialization or memory loading;
- no inference, PDF/image processing, or MusicXML generation;
- no upload endpoint;
- no GPU/CUDA behavior;
- no outbound network access;
- no Gateway or Ensemble integration;
- no persistence, training, promotion, teacher approval, or publication.

## Endpoint behavior

- `GET /health` remains `200` and reports validation as not requested by default;
- `GET /ready` remains explanatory `503`;
- mutating methods remain `405`;
- unknown inference or upload routes remain unavailable.
