# ScoreMosaic Package Status

**Status date:** 2026-08-05  
**Verified repository baseline:** `main` at `fcff4f237ab4034297ffcd58c20b54f09d377fea`

This document records package and infrastructure status using repository code, package metadata, tests, and successful GitHub Actions runs. It does not treat plans, documentation alone, or disabled contract libraries as proof of an enabled service.

## Evidence policy

A package is described as **CI-verified** only when a relevant workflow has completed successfully on a recorded commit.

A successful workflow proves only the bounded behavior exercised by that workflow. It does not prove production readiness, general OMR accuracy, external API availability, persistence, scaling, or recovery.

Status labels:

- **Runtime-integrated** — a pinned engine/runtime is built and exercised by integration or smoke tests.
- **Library implemented** — executable package behavior exists and unit tests exercise it.
- **Contract-only** — deterministic contracts exist, but runtime execution remains disabled.
- **Configuration-verified** — deployment or Compose configuration is checked, but no production deployment is proven.
- **Disabled by design** — configuration and tests explicitly prevent the capability.
- **Not implemented** — no executable package or capability exists.

## Summary matrix

| Package or area | Version or pin | Evidence-backed status | Important boundary |
|---|---:|---|---|
| `services/omr-gateway` | `0.3.0` | Contract-only, unit-tested, CI-verified | Upload, dispatch, persistence, storage writes, and orchestration execution disabled |
| `services/ensemble-service` | `0.2.0` | Library implemented, unit-tested, real-fixture tested, CI-verified | No ranking, winner, merge, correction, teacher approval, or public API |
| `services/audiveris-service` | package `0.1.0`; Audiveris `5.11.0` | Runtime-integrated and CI-verified | No HTTP upload or public conversion API |
| `services/homr-service` | package `0.2.0`; HOMR `0.7.0` | Runtime-integrated and CI-verified | CPU mode; no HTTP upload or conversion endpoint |
| `services/clarity-service` | package `0.2.0`; pinned source/model revisions | Runtime-integrated and CI-verified | PDF-only internal runtime; no HTTP upload or conversion endpoint |
| `contracts/` | versioned schemas | Schema/contract checks covered by package CI | Schemas do not enable runtime behavior |
| root and Coolify Compose | configuration | Configuration-verified in CI | Private networks and disabled external execution; no production deployment proof |
| Teacher-review package | none | Not implemented | Workflow is documentation/schema only |
| ST-OMR package | none | Not implemented | No service, model, data pipeline, contract, or workflow |

## `services/omr-gateway`

### Package metadata

- Package: `scoremosaic-omr-gateway`
- Version: `0.3.0`
- Python: `>=3.12,<3.13`
- Runtime dependencies: none
- Accepted source media represented by the contract: PDF, JPEG, PNG
- Engines represented by the contract: Audiveris, HOMR, Clarity

### Implemented behavior

- health and readiness boundary;
- deterministic orchestration-plan v1 builder and verifier;
- deterministic job, run, candidate, artifact, and namespace identifiers;
- engine-run state and transition policy;
- timeout and cancellation policy representation;
- candidate isolation and immutable source policy;
- candidate/artifact lifecycle v1 builder and verifier;
- append-only lifecycle events;
- artifact state transitions with hash and metadata requirements before sealing;
- prevention of overwrite, cross-engine writes, and terminal-state reopening in the contract model.

### Test inventory

The package currently contains these unit-test modules:

- `tests/test_app.py`
- `tests/test_config.py`
- `tests/test_engine_client.py`
- `tests/test_models.py`
- `tests/test_orchestration.py`
- `tests/test_artifact_lifecycle.py`

Primary local verification commands used by CI:

```bash
python -m compileall -q services/omr-gateway/src
python -m unittest discover -s services/omr-gateway/tests -v
```

### CI evidence

| Workflow | Latest observed successful main run | Commit |
|---|---:|---|
| `gateway-orchestration-contract-ci.yml` | `30989083440` | `fcff4f237ab4034297ffcd58c20b54f09d377fea` |
| `candidate-artifact-lifecycle-v1-ci.yml` | `30989083442` | `fcff4f237ab4034297ffcd58c20b54f09d377fea` |

The candidate/artifact lifecycle workflow compiles the package, runs all Gateway unit tests, validates schema constants and lifecycle transitions, and verifies that upload, dispatch, persistence, artifact storage, runtime mutation, Ensemble execution, automatic correction, teacher approval, publication, and ST-OMR remain disabled.

### Not proven or enabled

- external job creation;
- file upload;
- live engine dispatch;
- queue workers;
- persistent jobs;
- object storage writes;
- recovery after process restart;
- automatic Ensemble execution;
- production readiness.

## `services/ensemble-service`

### Package metadata

- Package: `scoremosaic-ensemble-service`
- Version: `0.2.0`
- Python: `>=3.12,<3.13`
- Runtime dependencies: none
- Canonical Score Model: `1.0`
- Comparison report: `1.0`

### Implemented behavior

- bounded safe MusicXML parsing;
- deterministic Canonical Score Model generation;
- exact rational written and effective durations;
- preservation of part, measure, staff, voice, note, rest, chord, tie, dot, tuplet, backup, forward, and TAB evidence;
- source-engine, source-artifact, and source-location provenance;
- neutral comparison of two to eight canonical candidates;
- structured disagreement evidence;
- versioned deterministic comparison-report generation;
- fixed Audiveris, HOMR, and Clarity real-engine fixtures.

### Test inventory

- `tests/test_canonical.py`
- `tests/test_musicxml.py`
- `tests/test_comparator.py`
- `tests/test_report.py`
- `tests/test_real_engine_fixtures.py`
- `tests/test_real_fixture_capture.py`

Fixtures include:

- bounded canonical smoke MusicXML;
- captured Audiveris MusicXML and metadata;
- captured HOMR MusicXML and metadata;
- captured Clarity MusicXML and metadata;
- shared generated-score source and fixture manifest.

Primary package test command:

```bash
python -m unittest discover -s services/ensemble-service/tests -v
```

### CI evidence

| Workflow | Latest observed successful main run | Commit |
|---|---:|---|
| `ensemble-canonical-model-ci.yml` | `30980291996` | `e9b1b24843217205a7d9a2217a128d159a8cae8b` |
| `ensemble-comparator-foundation-ci.yml` | `30980292078` | `e9b1b24843217205a7d9a2217a128d159a8cae8b` |
| `ensemble-real-canonical-fixtures-ci.yml` | `30980291974` | `e9b1b24843217205a7d9a2217a128d159a8cae8b` |
| `ensemble-comparison-report-v1-ci.yml` | `30980292061` | `e9b1b24843217205a7d9a2217a128d159a8cae8b` |

### Evidence limitation

The real-engine fixture is a bounded generated score. It proves deterministic processing and provenance preservation for that fixture. It does not prove broad OMR accuracy or representative guitar/TAB performance.

### Disabled by design

- engine ranking;
- preferred-engine selection;
- winner selection;
- automatic MusicXML merge;
- automatic correction;
- teacher approval;
- public API;
- direct publication.

## `services/audiveris-service`

### Package and runtime metadata

- Python package version: `0.1.0`
- Audiveris runtime: `5.11.0`
- Official Ubuntu 24.04 x86_64 package pinned by SHA-256
- Private container runtime
- Non-root execution and read-only-root controls
- Fixed server-controlled batch command

The Python package metadata still describes a health-only adapter boundary, while the service README and CI verify that the container includes and exercises the real Audiveris runtime. Upload and conversion capability flags remain false because no HTTP conversion API exists.

### Test and CI evidence

Local checks:

```bash
python -m compileall -q services/audiveris-service/src
python -m unittest discover -s services/audiveris-service/tests -v
```

The runtime workflow additionally builds the image, verifies `/health` and `/ready`, performs a real bounded batch transcription, requires generated `.mxl` and `.omr` artifacts, parses MusicXML structure, and validates private-container boundaries.

| Workflow | Latest observed successful main run | Commit |
|---|---:|---|
| `audiveris-foundation-ci.yml` | `30888668253` | `e2edbf061a45ae9045d7500a78b34d07f9cf965e` |

### Not enabled

- HTTP upload;
- public conversion route;
- Gateway dispatch;
- persistence;
- automatic Ensemble comparison;
- teacher approval.

## `services/homr-service`

### Package and runtime metadata

- Package version: `0.2.0`
- HOMR runtime: `0.7.0`
- Compute mode: CPU
- Engine installed in the private runtime image
- HTTP upload disabled
- HTTP conversion disabled

### Test and CI evidence

The HOMR runtime-integration workflow builds and verifies the private runtime and exercises its bounded conversion path and security boundaries.

| Workflow | Latest observed successful main run | Commit |
|---|---:|---|
| `homr-foundation-ci.yml` | `30888668233` | `e2edbf061a45ae9045d7500a78b34d07f9cf965e` |

### Input limitation

The current HOMR service is image-oriented. PDF rasterization belongs in a controlled upstream preprocessing boundary and is not an enabled service capability.

### Not enabled

- external upload;
- public conversion route;
- Gateway dispatch;
- persistence;
- teacher approval.

## `services/clarity-service`

### Package and runtime metadata

- Package version: `0.2.0`
- Compute mode: CPU
- Source revision: `c6bb8a4d2a5b52842a9c41bd0f761f58d02f6f82`
- Model revision: `ee14c1e41ab371fe27bf8a2707ea588560077e73`
- Verified model count: `2`
- Accepted internal format: PDF
- HTTP upload disabled
- HTTP conversion disabled

### Test and CI evidence

The Clarity runtime-integration workflow validates the pinned source and model assets, builds the private CPU runtime, performs a real generated-score PDF transcription smoke test, and validates safe MusicXML handling and container boundaries.

| Workflow | Latest observed successful main run | Commit |
|---|---:|---|
| `clarity-foundation-ci.yml` | `30888668242` | `e2edbf061a45ae9045d7500a78b34d07f9cf965e` |

### Not enabled

- external upload;
- public conversion route;
- Gateway dispatch;
- persistence;
- teacher approval.

## `contracts/`

Current schema files include:

- `canonical-score.schema.json`
- `ensemble-comparison-report-v1.schema.json`
- `omr-job.schema.json`
- `omr-orchestration-plan.schema.json`
- `candidate-artifact-lifecycle.schema.json`
- `review-report.schema.json`

These schemas are checked by their related Gateway, Ensemble, foundation, and deployment workflows.

A schema proves the accepted data shape and invariants. It does not prove that the full producer, storage layer, API, or consumer is implemented.

## Compose and Coolify staging configuration

The root and staging Compose foundations define private service placement and keep engine services without published host ports.

| Workflow | Latest observed successful main run | Commit |
|---|---:|---|
| `coolify-staging-ci.yml` | `30989083511` | `fcff4f237ab4034297ffcd58c20b54f09d377fea` |

This is configuration verification only. It does not prove that a live staging or production deployment is currently available, healthy, persistent, monitored, or recoverable.

## No package currently exists for

- authenticated external platform API;
- secure upload/quarantine service;
- durable queue worker;
- database-backed job lifecycle;
- object-storage adapter;
- teacher-review API;
- teacher editor;
- approved-result publisher;
- SesliTab integration;
- ST-OMR training or inference.

## Claims that the current evidence does not support

Do not describe the repository as:

- production-ready;
- fully deployed;
- end-to-end operational;
- able to accept user PDFs through a public API;
- persistently processing jobs;
- automatically choosing the correct engine;
- automatically correcting MusicXML;
- teacher-approved by automation;
- generally accurate for guitar or TAB;
- self-learning;
- ST-OMR enabled.

## Maintenance rule

Update this file in the same change whenever a package version, runtime pin, test inventory, CI workflow, enabled capability, disabled boundary, or evidence baseline changes.

For each update:

1. record the package or runtime version;
2. identify the tests that exercise the claim;
3. record the successful workflow and commit;
4. state the exact limitation of that evidence;
5. keep planned behavior separate from verified behavior.