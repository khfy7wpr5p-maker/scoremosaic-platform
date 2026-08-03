# Third-party notices for the ScoreMosaic HOMR image

## HOMR

- Project: HOMR (Handwritten Optical Music Recognition)
- Upstream repository: `liebharc/homr`
- Runtime package: `homr==0.7.0`
- Package source: Python Package Index
- Package wheel SHA-256: `84c6028df06e60b1aff158c9049d1876b22137144e319b61bacc41518842c4a9`
- License declared by upstream: GNU Affero General Public License v3.0

The ScoreMosaic image includes the unmodified upstream HOMR package and its runtime dependencies. Source and license obligations must be reviewed before any public network service or distribution beyond private infrastructure.

## Pinned ONNX model assets

The following HOMR `0.7.0` assets are fetched from the upstream `onnx_checkpoints` release and verified before installation.

| Asset | Archive SHA-256 | Installed ONNX SHA-256 |
|---|---|---|
| `segnet_308-3296ccd40960f90ca6ab9c035cca945675d30a0f.zip` | `1d4277354a8397a6830ef1279232e6d989c2d254b7451525e53ff3d3754b1f70` | `6ed36640db4ef5d223098b6d5efe4eda97c66b24a2c72faab8a018c749003a8d` |
| `encoder_pytorch_model_396-f6feedb42ff90087d898b0941a55d040fa6b2903.zip` | `9d9bc44da68c1180c85173d739edb2d703d90c0dbbdfadc9ebf6636685a5489b` | `4c16df852b3789f2676b0d49f0545dab0740e4005f7b472c5252add642f5d5eb` |
| `decoder_pytorch_model_396-f6feedb42ff90087d898b0941a55d040fa6b2903.zip` | `0a2f023e1ecf41f5f969f2ed4ef80c050ce29a4996c6655056cf36c6104677e8` | `3e10fd5ae52d0b86792721922fcd954c283a7ed365de7446425bdabe38f3e57d` |

## Runtime dependencies

Exact Python dependency versions are recorded in `requirements-runtime.txt`. Each dependency remains subject to its own upstream license and notice requirements.
