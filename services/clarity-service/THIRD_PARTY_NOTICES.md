# Third-party notices for the ScoreMosaic Clarity image

## Clarity-OMR

- Upstream repository: `clquwu/Clarity-OMR`
- Pinned source commit: `c6bb8a4d2a5b52842a9c41bd0f761f58d02f6f82`
- Source archive SHA-256: `feee5f0f9bfe0211d3385736371e6e6bff05c496e000c9166777bd7db89c5748`
- License declared by upstream: GNU General Public License v3.0

The image includes an unmodified snapshot of the pinned upstream source. Any distribution of the image must preserve the GPL notice and provide the corresponding source as required by the license.

## Pinned model assets

Model repository: `clquwu/Clarity-OMR` on Hugging Face.
Pinned model revision: `ee14c1e41ab371fe27bf8a2707ea588560077e73`.

| File | Size | SHA-256 |
|---|---:|---|
| `yolo.pt` | 155,970,512 bytes | `94610a2749022edd6938146505812544fece2983740fe8523907d2c855e4da73` |
| `model.safetensors` | 667,583,320 bytes | `5138f11acd1b89d780e65fbb363dae992e8c6d3e514f0e2a01062b0ea99edb43` |

The upstream repository does not provide a separate model license file in the runtime download path. Model redistribution and public-service use therefore require an explicit provenance and licensing review before deployment beyond private staging.

## Runtime dependencies

The CPU-only PyTorch runtime is pinned to `torch==2.13.0+cpu` and `torchvision==0.28.0+cpu` from the official PyTorch CPU wheel index. Other exact Python dependency versions are recorded in `requirements-runtime.txt`. Each dependency remains subject to its own upstream license and notice requirements.
