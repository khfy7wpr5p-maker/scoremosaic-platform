# ST-OMR pinned offline model runtime foundation

This package is the isolated shell for a future ScoreMosaic-native OMR candidate engine. Phase 21 adds the first explicitly loaded repository-controlled test model after path, provenance, boundary, and SHA-256 validation.

The included model is hand-authored, integer-only, untrained, and limited to repository synthetic fixtures. It is not a real OMR model and makes no music-recognition or accuracy claim.

## Closed offline model flow

```text
repository test model manifest
        ↓
path + provenance + boundary validation
        ↓
pinned artifact SHA-256 verification
        ↓
closed integer-only model parsing
        ↓
repository synthetic fixture validation
        ↓
deterministic offline evidence
```

The service process does not load this model. Loading and execution happen only through the explicit offline function used by tests and CI.

## Endpoints

- `GET /health` returns `200` and reports that the pinned offline runtime is available but not requested; `modelLoaded` and `inferenceEnabled` remain `false` in health evidence.
- `GET /ready` returns `503` with `modelLoaded: false`, `inferenceEnabled: false`, and `reason: model_runtime_disabled`.
- Unknown routes, including `/infer`, return `404`.
- `POST`, `PUT`, `PATCH`, and `DELETE` return `405`.

## Local verification

```bash
cd services/st-omr-service
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python - <<'PY'
from pathlib import Path
from scoremosaic_st_omr.offline_model_runtime import run_pinned_offline_test_model

root = Path('.')
result = run_pinned_offline_test_model(
    model_manifest_path=root / 'models' / 'st-omr-test-linear-v1.manifest.json',
    model_root=root / 'models',
    fixture_manifest_path=root / 'fixtures' / 'generated-single-staff-v1.manifest.json',
    fixture_root=root / 'fixtures',
)
print(result.as_dict())
PY
```

## Fixed exclusions

The service is not listed in the repository Compose topology and is not selectable by the current Gateway orchestration contract. No trained or externally sourced model, real OMR inference, PDF/image/user input, upload route, HTTP inference route, MusicXML generation, outbound dispatch, persistent storage, public route, Gateway integration, Ensemble integration, teacher approval, training, self-training, publication, or production deployment is enabled in this phase.

The repository test model is not copied into the service container and cannot make the service ready.
