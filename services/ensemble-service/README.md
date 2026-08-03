# Ensemble Service

## Status

Specification placeholder only. No public API or comparison implementation exists in Phase 0.

## Planned responsibility

The Ensemble service owns the external job lifecycle and coordinates private engine services. It preserves each candidate, validates outputs, compares normalized musical events, and creates a structured teacher-review report.

## Ensemble v1 behavior

- Dispatch a job to enabled engines independently.
- Record engine, code version, model version, timing, failures, and artifact hashes.
- Validate MusicXML before parsing.
- Normalize candidates without discarding provenance.
- Detect structural and musical disagreements.
- Produce issue evidence, severity, and an optional recommendation.
- Keep ambiguous cases unresolved rather than guessing.

## Explicit v1 non-goals

- No silent MusicXML merge
- No automatic correction of pitch or rhythm
- No teacher approval performed by the engine
- No learner-facing publication
- No direct access to engine volumes or model files from external clients

## Planned external capabilities

The versioned API contract will be finalized in Phase 1. Expected capabilities:

```text
GET    /health
GET    /ready
POST   /api/v1/jobs
GET    /api/v1/jobs/{jobId}
GET    /api/v1/jobs/{jobId}/report
GET    /api/v1/jobs/{jobId}/artifacts/{artifactId}
POST   /api/v1/jobs/{jobId}/cancel
DELETE /api/v1/jobs/{jobId}
```

## Comparison domains

- measure presence, ordering, and duration balance
- time signature and divisions
- pitch, octave, and accidental
- note/rest duration, dots, tuplets, ties, and onset
- chord grouping and simultaneity
- staff and voice assignment
- MusicXML timing structure, including backup/forward semantics
- guitar string, fret, and pitch consistency when present

## Acceptance gate

Implementation starts only after the job state machine, secure MusicXML gate, artifact policy, authentication boundary, and review-report contract have executable tests.
