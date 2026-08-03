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

The following assets are fetched from the upstream `onnx_checkpoints` release and verified before installation.

| Asset | Archive SHA-256 | Installed ONNX SHA-256 |
|---|---|---|
| `segnet_308-3296ccd40960f90ca6ab9c035cca945675d30a0f.zip` | `1d4277354a8397a6830ef1279232e6d989c2d254b7451525e53ff3d3754b1f70` | `6ed36640db4ef5d223098b6d5efe4eda97c66b24a2c72faab8a018c749003a8d` |
| `encoder_pytorch_model_426-b6fd20809a8dcaf10dfd39a4ca4f64c6f056e644.zip` | `10128de32aad243cb8b85e7b6bc059b9e376f33d85a6d442974b86c2b7f2b847` | `1513e83ae281ef06cdb8f08451b59f06c56536f13bd3418b4fd13227543dc4ff` |
| `decoder_pytorch_model_426-b6fd20809a8dcaf10dfd39a4ca4f64c6f056e644.zip` | `c28801d95ff062190b00d84d73e73cbca13df2fdeb01886ba82363e20ebe83da` | `8652b5c2e3129775ca9109eb180c16c3615413ce38005adc8ce5966c3c76737c` |

## Runtime dependencies

Exact Python dependency versions are recorded in `requirements-runtime.txt`. Each dependency remains subject to its own upstream license and notice requirements.
