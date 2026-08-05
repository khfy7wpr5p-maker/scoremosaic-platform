# ST-OMR fixed evaluation integration

This package is the isolated shell for a future ScoreMosaic-native OMR candidate engine. Phase 20 adds deterministic evaluation of repository-owned synthetic fixtures. It does not load a model, perform real OMR inference, accept user files, create MusicXML, connect to Gateway or Ensemble, persist artifacts, train, or publish.

## Closed evaluation flow

```text
generated fixture suite v1
        ↓
fixed evaluation manifest v1
        ↓
per-fixture closed pass evidence
        ↓
deterministic aggregate counts and SHA-256
```

The fixed evaluation proves only deterministic execution against repository-owned synthetic fixtures. It does not measure real OMR accuracy and does not support a general accuracy claim.

## Endpoints

- `GET /health` returns `200` and exposes disabled runtime plus fixed-evaluation capability evidence.
- `GET /ready` returns `503` with `modelLoaded: false`, `inferenceEnabled: false`, and `reason: model_runtime_disabled`.
- Unknown routes return `404`.
- `POST`, `PUT`, `PATCH`, and `DELETE` return `405`.

## Local verification

```bash
cd services/st-omr-service
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python - <<'PY'
from pathlib import Path
from scoremosaic_st_omr.fixed_evaluation import run_fixed_evaluation

root = Path('.')
result = run_fixed_evaluation(
    evaluation_manifest_path=root / 'evaluations' / 'fixed-evaluation-v1.json',
    evaluation_root=root / 'evaluations',
    fixture_root=root / 'fixtures',
)
print(result.as_dict())
PY
```

## Fixed exclusions

The service is not listed in the repository Compose topology and is not selectable by the current Gateway orchestration contract. No model framework, model loading, real OMR inference, upload route, evaluation route, inference route, outbound dispatch, persistent storage, public route, Gateway integration, Ensemble integration, teacher approval, training, publication, or production deployment is enabled in this phase.
