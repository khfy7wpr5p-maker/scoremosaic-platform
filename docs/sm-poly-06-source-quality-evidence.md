# SM-POLY-06 — Source Quality Evidence

## Purpose

SM-POLY-06 adds a research-only source-page quality evidence profile for polyphonic OMR benchmarking. Source quality is evidence about the scanned or photographed page itself; it is deliberately separate from any OMR engine confidence, semantic correctness metric, winner selection, or production decision.

This package does not modify Stage 6 candidate contracts or Stage 7 convergence behavior. Stage 7 continues to report `sourceQuality.available=false` until a later explicitly versioned evidence-vector integration.

## Quality dimensions

The v1 profile keeps ten degradation dimensions separate:

- `blur`
- `skew`
- `rotation`
- `contrast`
- `resolution`
- `perspective`
- `crop`
- `staffVisibility`
- `illumination`
- `compression`

A missing measurement is represented as `available=false`. Missing evidence is never interpreted as good quality.

## Normalized degradation evidence

Each available dimension carries:

- `riskBasisPoints`: integer `0..10000`; higher means more observed degradation risk.
- `rawValue`: bounded producer-native measurement text.
- `unit`: bounded producer-native unit/scale description.
- `method`: versioned measurement method.

The common v1 measurement policy is `DEGRADATION_RISK_BASIS_POINTS_V1`. These values are research evidence, not calibrated probabilities. Calibration belongs to SM-POLY-08.

The profile accepts evidence from explicitly identified producers such as deterministic heuristics, engine preprocessing telemetry, imported dataset annotations, or teacher annotations. SM-POLY-06 itself introduces no image-processing dependency and does not invent measurements when a producer has no evidence.

## Derived state

No average, aggregate, or single quality score is created. `singleQualityScore` is always `null`.

For research stratification only, the validator derives a transparent worst-observed severity from the maximum available degradation risk:

| Maximum degradation risk | Severity |
| --- | --- |
| no measured dimension | `UNAVAILABLE` |
| `0..1999` | `LOW` |
| `2000..3999` | `MODERATE` |
| `4000..6999` | `HIGH` |
| `7000..10000` | `SEVERE` |

`dominantDimensions` records every dimension tied for the maximum risk. The rule is deterministic and intentionally conservative; it is not a production threshold or accuracy claim.

## Independence from engine confidence

The source-quality profile contains no engine identity and no engine-confidence field. A single source page can therefore be referenced consistently by multiple candidate/evaluation records without turning page condition into engine-specific confidence.

SM-POLY-05 already provides the compatible non-authoritative link:

- `profileRef`
- `profileSha256`
- `authoritative=false`

The profile is SHA-pinned to exact source-page provenance and a deterministic canonical JSON representation.

## Safety boundaries

SM-POLY-06 is research-only and read-only. It grants no authority to:

- mutate the source or Canonical score;
- change Stage 7 evidence or quorum;
- rank engines or select a winner;
- merge MusicXML candidates;
- perform semantic correction;
- override Teacher Review;
- promote ST-OMR;
- make a production-readiness or calibrated-probability claim.

## Files

- `contracts/polyphonic-source-quality-profile-v1.schema.json`
- `services/ensemble-service/src/scoremosaic_ensemble/source_quality.py`
- `services/ensemble-service/tests/test_source_quality.py`
- `.github/workflows/sm-poly-06-source-quality-evidence-ci.yml`
- `docs/sm-poly-06-source-quality-evidence.md`
