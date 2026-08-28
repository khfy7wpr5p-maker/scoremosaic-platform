# SM-POLY-04 — Per-Engine Semantic Metrics

Status: **research/evaluation metrics foundation**  
Production behavior change: **none**

## Purpose

SM-POLY-04 adds a versioned per-engine semantic observation and aggregation layer without creating a single overall accuracy percentage, engine ranking, winner, merge, or correction authority.

The package deliberately reuses the existing frozen evaluator result contract where possible. `evaluation/fixed-v1` remains unchanged and is treated only as manually reviewed compatibility evidence, not as the new broad Teacher-Gold benchmark.

New contracts:

- `contracts/polyphonic-engine-semantic-observation-v1.schema.json`
- `contracts/polyphonic-engine-semantic-report-v1.schema.json`
- `services/ensemble-service/src/scoremosaic_ensemble/polyphonic_metrics.py`

## Metric families

Each engine is reported independently for:

- MusicXML parse success;
- structural validity;
- pitch exactness;
- effective-duration exactness;
- onset exactness;
- voice exactness;
- staff exactness;
- tie exactness;
- tuplet exactness;
- measure consistency;
- relation correctness;
- normalized structural distance;
- teacher edits per measure/page when that evidence later becomes available.

Every exactness metric is retained as integer `correct/total` evidence and aggregated as an exact rational value. No floating-point percentage is required for authority or comparison.

## Compatibility with the existing evaluator

The existing `scoremosaic_ensemble.evaluation` implementation already emits deterministic exact metrics for:

```text
eventPresence
onset
kind
effectiveDuration
writtenDuration
writtenType
pitch
chord
voice
staff
ties
dots
tuplet
tab
```

`observation_from_fixed_evaluation_result()` maps only compatible fields:

```text
pitch    <- pitch
duration <- effectiveDuration
onset    <- onset
voice    <- voice
staff    <- staff
tie      <- ties
tuplet   <- tuplet
```

The adapter preserves the source evaluation result SHA-256 and candidate/canonical provenance. It does not modify the existing v1 evaluator output.

A parse-failure helper exists so failed MusicXML normalization is recorded as a failed parse rather than silently disappearing from the denominator. When parsing fails, structural/semantic/distance evidence is explicitly unavailable.

## Measure consistency v1

The compatibility adapter uses:

`EXACT_MEASURE_COUNT_V1`

This is intentionally narrow: one observation records whether candidate and reviewed reference have the same measure count. It must not be described as full measure-boundary alignment. A later richer measure-alignment method requires a new version/method identifier rather than silently changing this definition.

## Relation correctness v1

The compatibility relation metric uses:

`TIE_TUPLET_CHORD_EXACT_V1`

It sums exact evidence for ties, tuplets, and chord membership/index from the current canonical evaluator. Slur, beam, cross-staff and other relationship classes are not falsely claimed as covered by this v1 method. Future relation coverage must use a versioned method extension.

## Structural distance

SM-POLY-04 does **not** claim TEDn implementation.

The initial method is explicitly named:

`CANONICAL_STRUCTURE_DISTANCE_V1`

For one compatible fixed-evaluation result:

```text
numerator =
  abs(referencePartCount - candidatePartCount)
  + abs(referenceMeasureCount - candidateMeasureCount)
  + eventPresenceIncorrect

denominator =
  max(1,
      referencePartCount
      + referenceMeasureCount
      + eventPresenceTotal)
```

The reduced rational is stored per observation; the report computes its exact arithmetic mean. Lower is better.

This is a bounded ScoreMosaic canonical structural-distance baseline, not TEDn. A true TEDn implementation may be added later only with its exact algorithm, version and test evidence.

## Teacher edit evidence

Teacher edit fields are part of the observation/report vocabulary so the multi-engine benchmark can eventually report:

- edits / measure;
- edits / page.

SM-POLY-04 does not derive those values from Teacher Review. Compatibility observations therefore set teacher-edit evidence to `UNAVAILABLE`, not zero.

SM-POLY-13 owns the later teacher-workload extraction/instrumentation and may populate the already-versioned fields with method:

`TEACHER_REVISION_COMMAND_COUNT_V1`

Availability does not change teacher authority.

## Current engine scope

SM-POLY-04 v1 accepts only the current Stage 7 engines:

```text
audiveris
homr
clarity
```

ST-OMR is intentionally absent. SM-POLY-09 must introduce shadow ST-OMR evidence through an explicit versioned extension rather than smuggling ST-OMR into the current engine set here.

## Aggregation rules

Observations are grouped by engine. One engine may have at most one observation for the same fixture in a report; duplicate engine/fixture evidence fails closed.

The report contains no cross-engine ranking and no overall score:

```text
singleAggregateAccuracyScore = null
engineRanking = false
winnerSelection = false
tednClaimed = false
```

Missing evidence remains unavailable and is excluded from that metric's denominator rather than converted to an incorrect zero.

## Authority boundaries

SM-POLY-04 does not:

- modify Canonical Score;
- change Stage 7 quorum;
- integrate ST-OMR;
- rank engines;
- select a winner;
- merge MusicXML;
- apply semantic repair;
- modify TeacherScoreRevision;
- approve or publish;
- make a general accuracy claim;
- activate production behavior.

SM-POLY-05 may add visual/localization evidence separately. Those fields must not be inferred from semantic metrics.
