# ST-OMR Architecture and Contract v1

## Status

This document defines phase 14 of ScoreMosaic: the architecture and closed contracts for a future isolated ST-OMR candidate engine.

This phase is architecture-only. It does not create an ST-OMR service, model, container, endpoint, runtime, Gateway integration, Ensemble integration, training pipeline, or production deployment.

## Purpose

ST-OMR is the planned ScoreMosaic-native optical music recognition engine. It is designed as a general-purpose, modular, AI-assisted OMR candidate engine rather than a guitar-only recognizer.

The long-term capability map includes:

- single-staff notation
- piano and multi-staff notation
- chamber music
- orchestra scores
- separate orchestra parts
- guitar and TAB
- choir notation and lyric alignment
- percussion notation

A listed capability is not a claim that a working or accurate model exists. Every profile begins as planned and must later earn experimental and validated status through named frozen evaluation sets.

## Unchanged system boundaries

The existing responsibility split remains authoritative:

- **OMR Gateway** owns job lifecycle, safe input preparation, bounded engine invocation, timeout policy, cancellation, and artifact lifecycle.
- **Audiveris, HOMR, Clarity, and future ST-OMR** are independent candidate engines.
- **Canonical Score Model** is the deterministic, provenance-preserving common musical representation.
- **Ensemble Comparator/Engine** compares Canonical candidates and reports differences.
- **Teacher review** owns correction and final approval.
- **Music Intelligence Engine** may later analyse only approved scores.
- **SesliTab and other clients** consume approved data through accessible user experiences.

ST-OMR is not embedded in Gateway or Ensemble. It has its own dependencies, container, model files, checksums, resource limits, tests, and versioning.

## Internal service position

The future service name is `st-omr-service` and its fixed role is `candidate_omr_engine`.

```text
prepared immutable page set
          |
          | private engine adapter
          v
    st-omr-service
          |
          +-- immutable raw engine output
          +-- immutable MusicXML candidate
          +-- immutable diagnostics
          +-- optional confidence evidence
```

The service never decides that its own output is correct, preferred, approved, or publishable.

The symbolic future Gateway endpoint key is `st-omr`. Phase 14 does not add that key to the current Gateway engine enum and does not change an orchestration plan.

## Input contract

ST-OMR receives only a server-controlled prepared page-set descriptor.

The future Gateway remains responsible for:

- validating the external source
- decoding PDF pages
- normalising page order and orientation
- applying bounded image preparation
- creating immutable page artifacts
- recording SHA-256 and media type
- passing only server-controlled artifact references

The engine contract accepts prepared JPEG and PNG page artifacts. It rejects raw external uploads, arbitrary URLs, caller credentials, caller-selected commands, and direct storage paths.

No phase-14 code opens, decodes, copies, stores, uploads, or dispatches a source file.

## Output and provenance contract

Every future ST-OMR run must preserve separate immutable artifacts:

1. raw engine output
2. MusicXML candidate
3. diagnostics
4. optional confidence evidence

Every artifact requires an identity, engine version, model version, SHA-256, media type, and source relationship when runtime implementation begins.

ST-OMR does not write a Canonical Score directly. Safe MusicXML normalisation remains owned by `ensemble-service`. Raw artifacts are never overwritten, cross-engine writes are forbidden, and corrections create later teacher-controlled revisions rather than changing the candidate.

Confidence evidence is advisory provenance. It is not a winner score, engine ranking, automatic correction instruction, or final-truth signal.

## Model manifest

`contracts/st-omr-model-manifest-v1.schema.json` defines the required provenance envelope for every future model release.

A model manifest records:

- independent model identity and semantic version
- immutable model artifact reference, SHA-256, size, and media type
- compatible engine-contract and minimum engine versions
- framework, framework version, device policy, and dependency-lock checksum
- training code revision and training-environment digest
- base-model provenance when applicable
- training, validation, test, and regression dataset manifests
- dataset consent and licence verification status
- model licence record
- named frozen evaluation evidence
- explicit promotion gates
- a self-hash field for the canonical manifest

A manifest is evidence, not deployment authority. `deployableFromThisManifestAlone` is always false. Deployment requires a separate reviewed release decision and a later runtime phase.

## Model release gates

A future model version cannot be promoted merely because training completed.

Required gates are:

1. model checksum verified
2. training provenance verified
3. dataset consent and licence verified
4. fixed evaluation completed
5. regression tests passed
6. manual release approval recorded

Automatic promotion is forbidden. Evaluation evidence can only describe the named dataset and profile. `generalAccuracyClaim` remains false unless a later separately reviewed benchmark policy defines otherwise.

## Teacher-correction and training boundary

The live ScoreMosaic system does not train itself.

Teacher corrections may enter a future training corpus only when all of these conditions are satisfied:

- explicit permission exists
- personal and sensitive data handling is reviewed
- quality control is completed
- training occurs in a separate environment
- datasets are versioned and immutable
- a frozen evaluation set is preserved
- regression tests pass
- a new model version and checksum are created
- manual release approval is recorded

A live correction never modifies a deployed model in place.

## Runtime security requirements

A future health-only and later experimental service must use:

- a separate container
- a separate dependency lock
- a pinned engine version
- a pinned model version and checksum
- non-root execution
- read-only root filesystem
- temporary bounded workspaces
- outbound-network default deny
- CPU, memory, disk, page-count, and timeout limits
- no public route
- no caller-controlled command options
- no secrets or credentials in model or engine contracts

These are future implementation gates, not enabled runtime behavior in phase 14.

## Contract files

```text
contracts/st-omr-engine-contract-v1.schema.json
contracts/st-omr-model-manifest-v1.schema.json
docs/st-omr-architecture-contract-v1.md
tests/test_st_omr_contract_v1.py
```

## Versioning

Engine contract, engine runtime, and model versions are independent.

- Contract breaking change: new major contract version.
- Runtime change: new engine semantic version and immutable build provenance.
- Model change: new model semantic version, artifact checksum, manifest, and evaluation evidence.
- Dataset change: new frozen dataset version; an existing frozen manifest is never silently edited.

## Fixed phase-14 boundaries

Every valid phase-14 engine contract keeps these values fixed:

```json
{
  "architectureOnly": true,
  "serviceImplementationEnabled": false,
  "gatewayIntegrationEnabled": false,
  "ensembleIntegrationEnabled": false,
  "publicEndpointEnabled": false,
  "uploadEnabled": false,
  "networkDispatchEnabled": false,
  "persistentStorageEnabled": false,
  "automaticMergeEnabled": false,
  "automaticCorrectionEnabled": false,
  "engineRankingEnabled": false,
  "winnerSelectionEnabled": false,
  "teacherApprovalEnabled": false,
  "publicationEnabled": false,
  "liveTrainingEnabled": false,
  "selfTrainingEnabled": false,
  "productionDeploymentEnabled": false
}
```

The current Audiveris, HOMR, and Clarity contracts, Gateway plan, candidate lifecycle, Canonical Score Model, Ensemble Comparator, comparison report, and fixed evaluation dataset remain unchanged.

## Acceptance gates

Phase 14 is accepted only when:

- both JSON Schema files parse and remain closed
- contract type and version are fixed
- all eight long-term notation profiles are named once
- ST-OMR is candidate-only and has no final-truth authority
- prepared input and Gateway PDF-decoding ownership are explicit
- raw output, MusicXML, diagnostics, and confidence evidence remain distinct
- Canonical normalisation remains outside ST-OMR
- model checksum and provenance are mandatory
- live training, self-training, and automatic model promotion are forbidden
- all execution, integration, ranking, correction, approval, publication, and deployment flags remain disabled
- no `services/st-omr-service` directory is created
- the current Gateway engine selection remains Audiveris, HOMR, and Clarity only

## Next gated phase

The next approved sequence item is **ST-OMR health-only service foundation**.

That later phase may create an isolated service skeleton with health/readiness behavior, non-root container controls, and no model execution. It must not load an AI model, process user files, join Gateway orchestration, enter Ensemble comparison, train from teacher corrections, or expose a public endpoint without separate approval.
