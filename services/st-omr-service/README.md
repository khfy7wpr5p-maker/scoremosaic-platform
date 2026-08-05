# ST-OMR structured synthetic symbol output contract

Phase 22 validates a static repository-owned synthetic contract sample. It does not run a symbol-producing model, perform real symbol detection, interpret music, or claim inference accuracy.

The static sample contains only symbol type, bounding box, and confidence. It does not contain staff/measure membership, notehead–stem attachment, beam membership, pitch, duration, voice, chord relations, reading-order semantics, or a notation graph.

## Closed validation flow

```text
closed JSON Schema 2020-12
        ↓
manual semantic contract validation
        ↓
allowed contracts root + direct-child checks
        ↓
manifest-pinned raw SHA-256
        ↓
canonical SHA-256
        ↓
repeated validation/canonicalization evidence
```

The general contract validator is independent of a specific artifact hash. Repository ownership and artifact integrity are enforced separately through the pinned manifest and allowed-root verifier.

## Endpoints

- `GET /health` returns `200` and reports that the static repository sample capability is available but not requested.
- `GET /ready` returns `503`; service readiness is not promoted.
- Unknown routes return `404`.
- `POST`, `PUT`, `PATCH`, and `DELETE` return `405`.

## Closed boundaries

No real/trained model, external weights, PDF/image/user input, HTTP inference/upload/model-loading, MusicXML, Gateway, Ensemble, automatic correction/ranking/winner selection, training/self-training, teacher approval/publication, network, GPU, persistence, or production behavior is enabled.

The Phase 21 repository test model remains available only to the explicit offline test function. It does not produce the Phase 22 symbol sample and is not copied into the service container.

## Local verification

```bash
PYTHONPATH=services/st-omr-service/src \
python -m unittest discover -s services/st-omr-service/tests -v
```
