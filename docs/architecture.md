# ScoreMosaic Architecture

## 1. Purpose

ScoreMosaic receives an untrusted score document, runs one or more isolated OMR engines, preserves every candidate result, compares the musical content, and emits a structured review report. A teacher-facing application may later use that report to correct and approve a final score.

ScoreMosaic is an OMR and review-support platform. It is not the learner-facing playback, narration, or lesson application.

## 2. Initial service boundaries

```text
External application
        |
        | authenticated HTTPS
        v
ensemble-service
   |             |
   | private     | private
   v             v
homr-service   clarity-service
```

Planned later:

```text
ensemble-service
├── homr-service
├── clarity-service
└── audiveris-service
```

Only the platform API is intended to receive external traffic. Engine services remain private inside the container network.

## 3. Responsibilities

### homr-service

- Accept a validated internal job request.
- Run one pinned HOMR version in an isolated runtime.
- Return immutable candidate artifacts and diagnostics.
- Never decide that its own output is the final approved score.

### clarity-service

- Accept a validated internal job request.
- Run one pinned Clarity-OMR and model version in an isolated runtime.
- Return immutable candidate artifacts and diagnostics.
- Never decide that its own output is the final approved score.

### ensemble-service

- Own the external job lifecycle.
- Dispatch work to enabled engines.
- Preserve engine identity, version, timing, errors, and artifact references.
- Normalize safe MusicXML into a common event representation.
- Compare measure, pitch, rhythm, rest, chord, voice, staff, and TAB evidence.
- Produce a review report with uncertainty and provenance.
- Never silently overwrite an engine result.

## 4. Data flow

1. Receive PDF and create a job.
2. Validate file type, size, page count, and document safety limits.
3. Store the original input as an immutable artifact.
4. Dispatch independent engine runs.
5. Store each raw engine output separately.
6. Validate every MusicXML output before parsing.
7. Normalize candidates into a common musical event model.
8. Compare candidates and detect disagreements or structural errors.
9. Produce a review report.
10. Wait for a separate teacher-review workflow to approve or reject a revision.

## 5. Artifact policy

The following artifacts must remain distinct:

```text
input.pdf
homr/original.musicxml
clarity/original.musicxml
audiveris/original.musicxml        # future
ensemble/review-report.json
revisions/revision-0001.musicxml
approved/approved.musicxml
```

Raw outputs are immutable. Corrections create new revisions.

## 6. Common musical event model

The exact schema will be defined in a later package. It must preserve at least:

- part, staff, voice, measure, and event position
- pitch step, alteration, octave
- written and effective duration
- rest and chord membership
- ties, tuplets, dots, backup, and forward timing
- time signature and divisions
- guitar string and fret when available
- source engine and source artifact location

No comparison algorithm should discard provenance.

## 7. Job lifecycle

Initial lifecycle vocabulary:

```text
received
validated
queued
processing
candidates_ready
needs_review
under_review
corrected
approved
rejected
published
failed
expired
```

Implementation may introduce internal substates, but public transitions must remain explicit and auditable.

## 8. Integration boundary

External applications integrate through a versioned API and do not access engine containers, storage paths, or model files directly. API authentication, rate limiting, idempotency, and cancellation semantics must be defined before staging exposure.

## 9. Deployment environments

- Development: GitHub Codespaces
- Automated verification: GitHub Actions
- Integration environment: Coolify `staging`
- Live environment: Coolify `production` after acceptance gates

Render remains outside this repository and may temporarily continue as an independent Audiveris reference environment.

## 10. Phase 0 non-goals

- Installing HOMR or Clarity-OMR
- Downloading model weights
- Running production OMR jobs
- Automatically merging MusicXML candidates
- Publishing results to learners
- Connecting the existing application
