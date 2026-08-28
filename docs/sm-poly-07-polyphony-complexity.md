# SM-POLY-07 — Polyphony Complexity Profile

Status: research-only evidence sidecar.

SM-POLY-07 describes the structural/rhythmic complexity of notation without
estimating engine correctness and without changing Stage 7, Teacher Review, or
production authority.

## Boundary

The profile is derived only from an already admitted `CanonicalScore`.
It does not read image/bbox evidence, source-quality evidence, engine confidence,
or engine identity as an input to the complexity calculation.

The sidecar cannot:

- rank engines or select a winner;
- merge/correct MusicXML;
- mutate Canonical Score or source artifacts;
- change the Stage 7 candidate minimum/quorum;
- promote ST-OMR;
- override Teacher Review;
- create an aggregate production complexity score.

`aggregateComplexityScore` and `complexityClass` are deliberately `null` in v1.

## V1 scope

Canonical Score v1 has deterministic measure timing but does not expose stable
page/system topology. Therefore calculation method
`polyphony-complexity-measure-v1` supports `MEASURE` scope only.

`PAGE` and `SYSTEM` scopes are intentionally deferred rather than inferred from
visual layout. A future version may add them only after a versioned Canonical or
layout-evidence contract supplies deterministic region membership.

The profile is pinned to:

- `canonicalScoreSha256`
- `partId`
- `measureId`
- calculation method version
- deterministic `profileId`
- deterministic `profileSha256`

## Complexity dimensions

### Voice

- `voiceCount`: distinct Canonical voice labels.
- `independentVoiceCount`: distinct `(staff, voice)` streams. Notes in one chord
  and one voice therefore remain one independent voice stream.
- `maxSimultaneousVoiceCount`: maximum timed Canonical voice streams active at
  the same instant.

### Simultaneous note density

Three measurements remain separate:

- `simultaneousNoteDensity`: sounding note events participating in a shared
  onset / all sounding note events.
- `chordDensity`: Canonical chord-member note events / all sounding note events.
- `independentVoiceOnsetDensity`: sounding note events at onsets containing
  multiple `(staff, voice)` streams / all sounding note events.

All density values are integer basis points (`0..10000`) and carry explicit
numerator and denominator.

### Staff

- `staffCount`: distinct staff identifiers observed in Canonical events.
- `multiStaffPresent`: derived from observed staff identifiers.
- `crossStaffPresent`: **unavailable in v1** because Canonical Score v1 has no
  cross-staff attachment relation. It is never guessed as `false`.

### Tuplet

- `tupletPresent`
- `tupletEventCount`
- `nestedTupletAvailable=false`
- `nestedTupletPresent=unavailable`

Canonical Score v1 carries one tuplet ratio per event but no nested-tuples
structure, so nested presence is not invented.

### Tie

- `tieCount`: sounding events carrying at least one Canonical tie marker.
- `tieDensity`: tie-bearing sounding events / all sounding events.

The metric counts tie-bearing events, not inferred tie arcs.

### Grace

- `gracePresent`
- `graceEventCount`

Grace timing or duration is never invented. Grace events are excluded from timed
density/overlap calculations.

### Overlap

`overlapDensity` measures interval overlap only between sounding events on the
same staff that belong to different Canonical voice streams.

Denominator: all eligible distinct-voice sounding event pairs on the same staff.
Numerator: pairs whose `[onset, end)` intervals overlap.

A monophonic measure with no eligible cross-voice pair is deterministically
reported as zero overlap with numerator/denominator `0/0`; this is a documented
structural zero, not missing evidence.

### Rhythmic components

No hidden rhythmic score is produced. V1 exposes:

- `distinctDurationCount`
- `dottedEventDensity`
- `onsetSubdivisionDiversity` (count of distinct reduced onset denominators)
- `overlappingRhythmPresent`
- `tupletPresent`

These remain descriptive components.

## Availability / fail-closed

Unavailable evidence uses:

```json
{
  "available": false,
  "value": null,
  "numerator": null,
  "denominator": null,
  "unit": null,
  "method": null,
  "reason": "..."
}
```

Missing information must not be rewritten as `0`, `false`, `LOW`, or another
apparently authoritative value.

The runtime also rejects:

- unknown/extra fields;
- malformed IDs and SHA-256 values;
- malformed metric types, including floats/NaN-like substitutions;
- density values outside `0..10000`;
- unavailable metrics that smuggle values;
- more than 4096 events in one measure-scope profile;
- more than 512 observed `(staff, voice)` streams;
- modified authority boundaries;
- modified derived state;
- hash tampering.

`validate_polyphony_complexity_profile_against_score()` additionally recomputes
the complete profile from the referenced `CanonicalScore`, so a forged metric
with a newly calculated profile hash still fails.

## Authority invariants

SM-POLY-07 keeps all of the following unchanged:

- Stage 7 production candidates: Audiveris, HOMR, Clarity.
- Stage 7 minimum Canonical candidates: 2.
- `winnerSelection=false`.
- `automaticMerge=false`.
- `automaticCorrection=false`.
- Teacher Review production writes remain locked.
- ST-OMR remains outside the Gateway/Stage 7 quorum.
- Source quality (SM-POLY-06) remains independent.
- Visual/bbox evidence (SM-POLY-05) remains independent.

The next research package may correlate this evidence with engine outcomes, but
SM-POLY-07 itself performs no calibration, ECE/Brier calculation, selective
prediction, reliability curve, or production thresholding.
