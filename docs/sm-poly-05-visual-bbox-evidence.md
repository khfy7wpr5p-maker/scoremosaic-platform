# SM-POLY-05 — Polyphonic Visual / BBox Evidence Sidecar v1

Status: **research-only contract and validator**.

SM-POLY-05 introduces a separate visual-evidence sidecar for linking an existing OMR candidate and Canonical event to bounded page geometry. It does **not** modify the Stage 6 candidate handoff or Stage 7 convergence behavior.

## Why a sidecar

Current Stage 7 intentionally reports:

- `visualConfidence.available = false`
- `sourceQuality.available = false`
- `localizationReliability.bboxEvidenceAvailable = false`

because the existing candidate contract does not carry trustworthy page-localization evidence. SM-POLY-05 preserves that truthful behavior instead of pretending bbox evidence exists.

The new sidecar can be produced only when a separate evidence producer has real localization evidence. A future stage can consume the sidecar through an explicitly versioned integration. Until then Stage 7 remains unchanged.

## Evidence chain

A v1 sidecar binds:

`source document SHA`
→ `source page image SHA`
→ `engine run`
→ `candidate id / candidate SHA`
→ `MusicXML SHA`
→ `Canonical Score SHA`
→ `partId / measureId / eventId`
→ `MusicXML xmlPath / sourceEventIndex`
→ `page bbox`
→ optional `symbolRegions`
→ optional immutable crop ref + SHA

This permits later teacher review or benchmark tooling to trace a semantic event back to visual evidence without mutating the source score.

## Geometry rules

Page geometry is pixel-based and bounded.

- width/height: `1..50,000 px`
- maximum page area: `200,000,000 px`
- page index: `0..9999`
- bbox coordinates are non-negative integers
- width/height must be positive
- bbox must fit fully inside the declared page
- each symbol region must fit inside the event bbox
- at most 64 symbol regions per event

The sidecar never clips or repairs invalid geometry. Invalid geometry fails closed.

## Localization states

`localization.available = false` is a first-class state.

When unavailable:

- `evidenceSource = UNAVAILABLE`
- bbox is `null`
- staff/system/measure-region ids are `null`
- symbol regions are empty
- crop evidence is unavailable

Any hidden geometry inside an unavailable record is rejected.

When available, evidence source must be one of:

- `ENGINE_NATIVE_BBOX`
- `ENGINE_AUXILIARY_VISUAL_OUTPUT`
- `DETERMINISTIC_GEOMETRY`
- `TEACHER_ANNOTATION`
- `IMPORTED_DATASET_ANNOTATION`

The source describes provenance, not correctness or authority.

## Confidence

`engineConfidence` and `visualConfidence` are deliberately separate.

SM-POLY-05 stores only raw confidence evidence plus its declared scale. `calibratedProbability` is fixed to `null` in v1. Calibration belongs to SM-POLY-08; this package must not make calibration claims early.

Missing confidence is explicit and cannot contain a hidden raw value.

## Source quality

SM-POLY-05 does not define source-quality metrics. It only permits a SHA-pinned, non-authoritative `sourceQuality` profile reference so SM-POLY-06 can define that evidence separately without changing this visual localization identity model.

## Crops and private assets

A crop is optional and represented only by a safe relative artifact reference plus SHA-256. The contract does not require source images or private crops to be committed to the public repository.

Path traversal, absolute paths, backslashes, doubled separators, and incomplete ref/hash pairs fail closed.

## Determinism

`build_visual_evidence_sidecar()`:

1. validates the entire unhashed payload,
2. creates a detached canonical JSON copy,
3. computes a deterministic SHA-256,
4. returns the sidecar with `sidecarSha256`.

`validate_visual_evidence_sidecar()` recomputes the hash and rejects mutation.

## Authority boundaries

The sidecar is:

- research-only,
- read-only,
- non-authoritative,
- not an engine rank,
- not a winner,
- not a MusicXML merge,
- not a semantic correction,
- not Teacher Review approval,
- not a Stage 7 evidence mutation,
- not an ST-OMR quorum change.

This package does not change the current production engines, quorum, source immutability, Teacher Review authority, or production readiness.

## Files

- `contracts/polyphonic-visual-evidence-sidecar-v1.schema.json`
- `services/ensemble-service/src/scoremosaic_ensemble/visual_evidence.py`
- `services/ensemble-service/tests/test_visual_evidence.py`
- `.github/workflows/sm-poly-05-visual-bbox-evidence-ci.yml`

## Deferred work

- source-quality measurement: SM-POLY-06
- engine reliability calibration: SM-POLY-08
- ST-OMR shadow candidate: SM-POLY-09
- Convergence Evidence Vector v2 integration: SM-POLY-11

No future package is implicitly authorized by this contract.
