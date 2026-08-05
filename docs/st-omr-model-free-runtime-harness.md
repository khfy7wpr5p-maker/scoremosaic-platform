# ST-OMR Model-Free Runtime Harness Foundation

## Status

This document defines phase 16. The service proves deterministic runtime configuration and resource-policy behavior without loading or executing an OMR model.

## Enabled behavior

- Python 3.12 runtime evidence
- CPU-only device policy
- explicit dependency lock with no runtime dependencies
- bounded worker, memory, temporary-disk and operation-timeout configuration
- fail-closed validation for invalid limits
- `/health` remains 200 and reports runtime evidence
- `/ready` remains 503 because model loading and inference are disabled

## Fixed exclusions

- no AI or OMR framework
- no GPU/CUDA execution
- no model artifact or model loader
- no inference, upload, PDF/image processing or MusicXML generation
- no outbound network dispatch
- no Gateway or Ensemble integration
- no persistence, training, teacher approval, publication or deployment

## Default limits

| Setting | Default | Allowed range |
|---|---:|---:|
| workers | 1 | 1–4 |
| memory | 512 MB | 128–4096 MB |
| temporary workspace | 256 MB | 32–2048 MB |
| operation timeout | 30 s | 1–300 s |

These values describe the internal harness policy. They do not replace container or deployment-level enforcement, which remains required in later phases.

## Acceptance gates

- dependency lock exists and declares no runtime/model dependency
- CPU-only policy is deterministic
- all resource settings are bounded and malformed values fail closed
- model loading, inference, GPU and outbound networking remain false
- `/health` is 200 and `/ready` is 503
- no upload, inference or prediction endpoint exists
- Gateway, Ensemble and current candidate engines remain unchanged
- all focused and foundation CI checks pass

## Next gated phase

The next sequence item is **Pinned Model Loader Contract and Checksum Harness**. That phase may validate a local, repository-controlled model manifest and checksum boundary, but must not execute inference or download a model from the network without separate approval.
