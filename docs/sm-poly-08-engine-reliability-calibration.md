# SM-POLY-08 — Engine Reliability Calibration Research

Status: **research-only calibration evidence**  
Production behavior change: **none**

## Purpose

SM-POLY-08 measures how an engine's explicitly reported confidence relates to
Teacher-Gold correctness while preserving ScoreMosaic's evidence-first authority
boundaries.

The package does **not** create a new winner score and does not rewrite engine
confidence. It answers research questions such as:

`P(correct | engine, reported confidence, category, complexity context, source quality context)`

with deterministic descriptive evidence only.

## Critical boundary: confidence is evidence, not authority

Stage 7 currently has no comparable opaque engine-confidence score. SM-POLY-08
therefore does not invent confidence from agreement, source quality, complexity,
semantic metrics, or Stage 7 differences.

A reliability observation may use confidence only when its producer supplies an
explicit bounded `0..10000` correctness-confidence value with provenance and a
versioned method. Missing confidence remains `available=false`; it never becomes
zero.

Allowed v1 evidence sources are:

- `ENGINE_NATIVE_REPORTED`
- `IMPORTED_BENCHMARK_TELEMETRY`
- `REPOSITORY_RESEARCH_FIXTURE` for hermetic test evidence

Every available confidence value is marked `calibratedInput=false`. SM-POLY-08
measures reliability of the reported value; it does not claim the input was
already calibrated.

## Observation unit

One observation represents one binary Teacher-Gold target unit for one engine
and one semantic category. The correctness method is fixed to:

`TEACHER_GOLD_BINARY_CORRECTNESS_V1`

Supported v1 categories remain separate:

- parse
- structural validity
- pitch
- duration
- onset
- voice
- staff
- tie
- tuplet
- measure consistency
- relation correctness

No cross-category aggregate accuracy or reliability score is created.

## Context from SM-POLY-06 and SM-POLY-07

Complexity and source quality are **conditioning context only**. They never
modify the reported confidence.

The SM-POLY-07 context remains componentized:

- voice count
- maximum simultaneous voice count when available
- multi-staff presence
- tuplet presence
- overlap density

There is no `complexityScore` and no complexity-derived production threshold.

SM-POLY-06 context retains the deterministic source-quality severity and maximum
observed degradation risk when available. Missing measurements remain explicit.

Helpers validate full SM-POLY-06/07 profiles before extracting the small
research context used by calibration observations.

## Reliability measurements

Reports group evidence by:

- engine
- semantic category
- confidence method version

No cross-engine ranking is produced.

### Fixed reliability bins

Method: `FIXED_10_BIN_BASIS_POINTS_V1`

The reported-confidence range is split deterministically into ten bins:

- 0–999
- 1000–1999
- ...
- 9000–10000

Each bin reports observation count, correct count, empirical accuracy, mean
reported confidence, and absolute calibration gap. Empty bins remain explicit.

### Brier score

Method: `BINARY_BRIER_EXACT_RATIONAL_V1`

Brier score is computed with integer basis-point arithmetic and emitted as a
reduced exact rational. No floating point or NaN is required.

Lower is better, but SM-POLY-08 does not rank engines from this value.

### Expected Calibration Error

Method: `FIXED_BIN_ECE_EXACT_RATIONAL_V1`

ECE uses the fixed ten-bin policy and exact rational arithmetic. The method is
versioned because changing binning changes the statistic.

SM-POLY-08 does not claim ECE is a universal correctness metric or production
threshold.

## Context slices

For subgroup regression research, reports expose deterministic slices for
available context:

- exact voice count
- exact maximum simultaneous voice count when available
- multi-staff presence
- tuplet presence
- fixed overlap-density band
- source-quality severity

These are descriptive subgroup views. They do not alter confidence, predict a
winner, or authorize abstention.

## Determinism and tamper resistance

Each observation has a deterministic ID and SHA-256. Each report contains:

- deterministic report ID
- deterministic SHA-256 of the sorted source observation hashes
- deterministic report SHA-256

`validate_reliability_report_against_observations()` rebuilds the complete report
from source observations. A forged metric that is rehashed still fails the
recompute check.

Bounds include:

- at most 100,000 observations per report
- at most 2,048 engine/category/method groups
- at most 8,192 context slices
- confidence only in integer `0..10000`
- no floats/NaN in confidence evidence

## Explicit non-goals

SM-POLY-08 does not:

- fit Platt scaling, isotonic regression, temperature scaling, or any other calibration model;
- output recalibrated probabilities;
- implement selective prediction or abstention thresholds;
- rank engines;
- choose a winner;
- change Stage 7 evidence or quorum;
- merge or correct MusicXML;
- override Teacher Review;
- promote ST-OMR;
- create production thresholds or production decision authority.

Those boundaries are represented in every observation/report and validated
fail-closed.

## Files

- `contracts/engine-reliability-observation-v1.schema.json`
- `contracts/engine-reliability-report-v1.schema.json`
- `services/ensemble-service/src/scoremosaic_ensemble/reliability_calibration.py`
- `services/ensemble-service/tests/test_reliability_calibration.py`
- `.github/workflows/sm-poly-08-engine-reliability-calibration-ci.yml`
- `docs/sm-poly-08-engine-reliability-calibration.md`
