# Gateway Orchestration Contract v1

## Purpose

This phase defines the deterministic contract that a future private OMR Gateway will use to describe one bounded multi-engine transcription plan. It does not enable uploads, network dispatch, queue processing, persistent artifacts, or engine execution.

The contract is intentionally separate from:

- OMR engine runtime implementations
- the Canonical Score Model
- the Ensemble Comparator and comparison report
- teacher review and approval
- learner-facing publication
- future ST-OMR development

## Contract files

```text
contracts/omr-orchestration-plan.schema.json
services/omr-gateway/src/scoremosaic_gateway/orchestration.py
```

The JSON Schema defines the closed external shape. The Python library constructs and verifies the exact deterministic shape without third-party dependencies.

## Plan identity and integrity

Every plan includes:

- `schemaVersion: 1.0`
- a fixed contract type
- one existing `jobId`
- a deterministic `planId`
- a deterministic `planSha256`

`planId` is derived from the canonical plan body. `planSha256` covers the canonical plan body plus `planId`. Any changed field, additional field, reordered engine selection, changed timeout, changed artifact relationship, or enabled boundary causes verification to fail.

The verifier reconstructs the complete expected plan from its allowed source inputs and requires byte-equivalent canonical content. JSON Schema validation alone is not treated as sufficient for cross-field integrity.

## Source artifact

The plan references one already prepared immutable source artifact. The contract accepts only:

- `application/pdf`
- `image/jpeg`
- `image/png`

The source descriptor contains a server-controlled relative artifact reference, lowercase SHA-256, bounded size, media type, and deterministic artifact identifier.

The contract does not open, decode, upload, copy, delete, or store the referenced file. Those operations require later security and storage phases.

Artifact references must be normalized relative keys. Absolute paths, backslashes, repeated separators, and `.` or `..` path segments are rejected.

## Engine selection and endpoint isolation

A plan contains one to three unique runs selected from:

```text
audiveris
homr
clarity
```

Caller order does not affect serialization. Runs are always emitted in canonical engine order.

The plan never accepts a URL, hostname, port, path, token, header, credential, or arbitrary upstream target. Each run contains only a symbolic `endpointKey` equal to its engine name. Deployment-owned engine addresses remain in validated Gateway configuration.

`transportProfile: private-engine-adapter-v1` is a future interface label only. No adapter request endpoint exists in this phase.

## Candidate and artifact relationships

Every engine run receives the same immutable source artifact identifier and receives its own deterministic:

- run identifier
- candidate identifier
- candidate namespace
- expected MusicXML artifact slot
- expected diagnostic artifact slot

Candidate namespaces use this form:

```text
candidates/{jobId}/{engine}/{candidateId}
```

The artifact policy fixes these rules:

- source artifacts are immutable
- candidate namespaces are isolated
- result hashes are required
- overwrite is forbidden
- cross-engine writes are forbidden

The contract reserves artifact locations only. It does not create directories or persistent objects.

## Engine-run lifecycle

The v1 contract defines these states:

```text
planned
queued
dispatching
running
completed
failed
cancelled
timed_out
```

Allowed transitions are explicit:

```text
planned     -> queued | cancelled
queued      -> dispatching | cancelled | timed_out
dispatching -> running | failed | cancelled | timed_out
running     -> completed | failed | cancelled | timed_out
```

`completed`, `failed`, `cancelled`, and `timed_out` are terminal.

The contract defines state vocabulary and transition rules only. It does not implement a state store, scheduler, worker, retry queue, cancellation signal, or recovery procedure.

## Timeout policy

Each engine run has a bounded timeout from 30 to 7200 seconds. The plan also defines a cancellation grace period from 0 to 300 seconds.

Timeout accounting is specified as:

- monotonic clock
- starts when dispatch begins
- total plan deadline equals the maximum engine timeout plus cancellation grace
- timeout is terminal
- no automatic retry after timeout
- attempt limit is one

Later execution work must implement and test these semantics before orchestration can be enabled.

## Fixed disabled boundaries

Every valid v1 plan must contain:

```json
{
  "executionEnabled": false,
  "uploadEnabled": false,
  "persistenceEnabled": false,
  "networkDispatchEnabled": false,
  "engineRanking": false,
  "winnerSelection": false,
  "automaticMerge": false,
  "automaticCorrection": false,
  "teacherApproval": false,
  "publication": false
}
```

A payload that changes any of these values is invalid even if its hash fields are replaced.

## Relationship to existing contracts

`contracts/omr-job.schema.json` remains the broader long-term job and review record. The orchestration plan is a narrower immutable execution-plan description for a future Gateway implementation.

The orchestration plan does not replace or modify:

- OMR job review states
- engine output MusicXML
- Canonical Score Model candidates
- Ensemble comparison reports
- approved revisions

A later controlled lifecycle phase may define how an accepted orchestration plan is attached to an OMR job and how immutable run events are persisted.

## Acceptance gates

This phase is accepted only when:

- plan generation is deterministic
- plan generation does not mutate caller inputs
- serialized output mutation cannot alter future plans
- source and candidate relationships are unique and isolated
- arbitrary upstream URLs cannot enter the plan
- lifecycle and timeout policies are exact
- modified hashes, identifiers, timeouts, namespaces, policies, boundaries, and extra fields are rejected
- all existing Gateway health-only behavior remains unchanged
- no execution endpoint is introduced
- no ST-OMR service or integration is introduced

## Next phase boundary

The next controlled stage is the candidate and artifact lifecycle design. That work may define immutable event records, retention states, cancellation records, and restart recovery rules. It must not enable real uploads or engine dispatch without separate approval and security gates.
