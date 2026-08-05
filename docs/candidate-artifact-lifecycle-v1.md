# Candidate and Artifact Lifecycle Contract v1

## Status

This document defines phase 12 of the ScoreMosaic OMR platform: a controlled, deterministic, append-only candidate and artifact lifecycle contract.

The contract is a pure in-memory library. It does not accept uploads, dispatch engines, write files, create database rows, publish events to a queue, or persist artifacts. The private Gateway HTTP service remains health-only.

## Purpose

The lifecycle contract sits after the versioned Gateway orchestration plan and before any future storage or execution implementation. It provides a stable rule set for:

- preserving the immutable source artifact
- creating one isolated candidate per engine run
- preserving an opaque raw engine result separately from normalized MusicXML
- reserving MusicXML and diagnostic artifact identities
- validating explicit candidate and artifact state transitions
- sealing content only after SHA-256, byte size, and media type are known
- preventing overwrite, reopening, or cross-engine writes
- recording every transition in an append-only hash chain
- verifying the exact final snapshot by replaying all events against the pinned orchestration plan

## Contract files

```text
contracts/candidate-artifact-lifecycle.schema.json
services/omr-gateway/src/scoremosaic_gateway/artifact_lifecycle.py
```

The contract type is:

```text
scoremosaic-gateway-candidate-artifact-lifecycle
```

The schema version is `1.0`.

## Relationship to the orchestration plan

`build_artifact_lifecycle()` accepts only an already valid orchestration-plan payload. The lifecycle pins:

- `planId`
- `planSha256`
- `jobId`
- source artifact identity and content hash
- run, engine, candidate, namespace, MusicXML artifact, and diagnostic artifact relationships

The source orchestration plan is verified before the lifecycle is created. A modified plan, altered boundary, changed hash, unsupported engine, or extra orchestration field is rejected.

The lifecycle adds one deterministic raw-result artifact per candidate:

```text
candidates/{jobId}/{engine}/{candidateId}/raw-engine-result
```

This opaque artifact preserves the engine-native result independently of the MusicXML and diagnostic outputs. It does not interpret or execute the result.

## Candidate states

```text
reserved
collecting
sealed
failed
cancelled
timed_out
```

Allowed transitions:

```text
reserved   -> collecting | failed | cancelled | timed_out
collecting -> sealed | failed | cancelled | timed_out
sealed     -> terminal
failed     -> terminal
cancelled  -> terminal
timed_out  -> terminal
```

A candidate can become `sealed` only after all three candidate artifacts are sealed. A failed, cancelled, or timed-out candidate can become terminal only after all of its artifacts are already terminal.

No terminal candidate can be reopened.

## Artifact states

```text
reserved
writing
sealed
rejected
abandoned
```

Allowed transitions:

```text
reserved -> writing | rejected | abandoned
writing  -> sealed | rejected | abandoned
sealed   -> terminal
rejected -> terminal
abandoned -> terminal
```

The source artifact is created in `sealed` state and cannot transition.

Candidate artifacts can enter `writing` or `sealed` only while their owning candidate is `collecting`. A sealed artifact requires:

- lowercase SHA-256
- positive bounded byte size
- exact media type for its kind

The fixed output media types are:

```text
raw_engine_result -> application/octet-stream
musicxml           -> application/vnd.recordare.musicxml+xml
diagnostic         -> application/json
```

Rejected and abandoned artifacts require a normalized reason code and cannot contain content metadata.

## Append-only event chain

Each transition produces one immutable event containing:

- contiguous sequence number
- deterministic `eventId`
- transition target
- previous and next state
- optional normalized reason code
- optional sealed-content metadata
- `previousEventSha256`
- deterministic `eventSha256`

The first event points to 64 zeroes. Every later event points to the preceding event hash. The serialized lifecycle contains a stable `lifecycleId` and a snapshot-specific `lifecycleSha256`.

`verify_artifact_lifecycle()` rebuilds the initial lifecycle from the pinned orchestration plan, replays every event through the same state machine, verifies each event hash, and requires the reconstructed payload to match the supplied snapshot exactly.

## Fixed policies

```json
{
  "appendOnlyEvents": true,
  "sourceImmutable": true,
  "rawEngineResultPreserved": true,
  "hashRequiredBeforeSeal": true,
  "overwriteAllowed": false,
  "crossEngineWriteAllowed": false,
  "terminalStateReopenAllowed": false,
  "candidateSealRequiresAllArtifactsSealed": true
}
```

## Disabled boundaries

```json
{
  "executionEnabled": false,
  "uploadEnabled": false,
  "networkDispatchEnabled": false,
  "queueEnabled": false,
  "persistenceEnabled": false,
  "storageWritesEnabled": false,
  "runtimeMutationEnabled": false,
  "engineRanking": false,
  "winnerSelection": false,
  "automaticMerge": false,
  "automaticCorrection": false,
  "teacherApproval": false,
  "publication": false
}
```

## Explicit exclusions

Phase 12 does not add:

- file upload or decoded input handling
- live engine dispatch
- queue processing
- storage adapters or database persistence
- automatic retry or recovery
- automatic Ensemble invocation
- engine ranking or winner selection
- MusicXML merging or correction
- teacher approval or publication
- ST-OMR code or integration

A future implementation must preserve this contract while adding authenticated, isolated, content-addressed storage and restart-safe execution in separate reviewed phases.
