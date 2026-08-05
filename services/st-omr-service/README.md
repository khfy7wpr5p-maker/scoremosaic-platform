# ST-OMR health-only service foundation

This package is the isolated shell for a future ScoreMosaic-native OMR candidate engine. It does not load a model, run inference, accept user files, create MusicXML, connect to Gateway or Ensemble, persist artifacts, train, or publish.

## Endpoints

- `GET /health` returns `200` while the process is healthy.
- `GET /ready` returns `503` with `modelLoaded: false`, `inferenceEnabled: false`, and `reason: model_runtime_disabled`.
- Unknown routes return `404`.
- `POST`, `PUT`, `PATCH`, and `DELETE` return `405`.

## Local verification

```bash
cd services/st-omr-service
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python -m scoremosaic_st_omr.app
```

## Fixed exclusions

The service is not listed in the repository Compose topology and is not selectable by the current Gateway orchestration contract. No model framework, model artifact, upload route, inference route, outbound dispatch, persistent storage, public route, Gateway integration, Ensemble integration, teacher approval, or production deployment is enabled in this phase.
