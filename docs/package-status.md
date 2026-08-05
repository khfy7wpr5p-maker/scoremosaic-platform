# ScoreMosaic Package Status

**Snapshot date:** 2026-08-05  
**Repository baseline:** `main` at `fcff4f237ab4034297ffcd58c20b54f09d377fea`

This document records what each package is, which behavior has executable test evidence, which CI run was observed, and which capabilities remain disabled.

A green test proves only the behavior exercised by that test. It does not prove OMR accuracy on arbitrary scores, production readiness, licensing clearance, or an enabled end-to-end workflow.

## Status vocabulary

| Status | Meaning |
|---|---|
| Specified | Documentation or schema exists, but no executable implementation is available |
| Unit-tested foundation | Source-level behavior is implemented and covered by unit tests |
| Integration-tested foundation | CI builds or runs the real container/runtime with a bounded fixture |
| Contract-verified foundation | Deterministic contract code, schemas, and disabled boundaries are tested |
| Enabled | Connected to the intended runtime path and callable through the supported interface |
| Production ready | Security, persistence, recovery, authorization, licensing, operations, and acceptance gates are complete |

No package in this repository is currently a production-ready public OMR service.

## Package summary

| Package | Package version | Runtime/model version | Evidence status | Enabled in end-to-end workflow? |
|---|---:|---|---|---|
| `scoremosaic-audiveris-service` | `0.1.0` | Audiveris `5.11.0` | Integration-tested private runtime foundation | No |
| `scoremosaic-homr-service` | `0.2.0` | HOMR `0.7.0`, CPU | Integration-tested private runtime foundation | No |
| `scoremosaic-clarity-service` | `0.2.0` | Pinned source and model revisions, CPU | Integration-tested private runtime foundation | No |
| `scoremosaic-omr-gateway` | `0.3.0` | Orchestration `1.0`, artifact lifecycle `1.0` | Contract-verified health-only foundation | No |
| `scoremosaic-ensemble-service` | `0.2.0` | Canonical `1.0`, comparator `0.1-foundation`, report `1.0` | Unit- and fixture-tested deterministic library foundation | No |
| Teacher review | None | Review schema/workflow documents | Specified only | No |
| ST-OMR | None | None | Not implemented | No |

## 1. Audiveris service

### Identity

```text
Path: services/audiveris-service
Python package: scoremosaic-audiveris-service
Package version: 0.1.0
Pinned runtime: Audiveris 5.11.0
Input scope in private helper: PDF, JPG/JPEG, PNG
```

### Implemented behavior with evidence

- private health and readiness endpoints;
- exact pinned Audiveris release asset and SHA-256 verification;
- bounded `audiveris -version` readiness probe;
- fixed server-controlled batch transcription command;
- workspace containment and symbolic-link rejection;
- generated score fixture;
- real CI batch transcription producing `.mxl` and `.omr` artifacts;
- parsed MusicXML structure checks;
- non-root, read-only, capability-dropped private container boundary.

### Source-level test modules

```text
services/audiveris-service/tests/test_app.py
services/audiveris-service/tests/test_config.py
services/audiveris-service/tests/test_runtime.py
services/audiveris-service/tests/fixtures/
```

### Local verification command

```bash
python -m compileall -q services/audiveris-service/src
python -m unittest discover -s services/audiveris-service/tests -v
```

### Latest observed relevant CI evidence

```text
Workflow: Audiveris Runtime Integration CI
Run ID: 30888668253
Conclusion: success
Head commit: e2edbf061a45ae9045d7500a78b34d07f9cf965e
Observed date: 2026-08-04
```

### Verified limit

This evidence verifies a bounded generated-fixture runtime path. It does not verify a public upload route, Gateway dispatch, persistent artifacts, broad score accuracy, teacher approval, or production readiness.

### Metadata inconsistency

The service README and CI describe a real installed Audiveris container runtime, but `services/audiveris-service/pyproject.toml` still reports:

```text
engine-installed = false
java-runtime-enabled = false
```

Treat this as stale package metadata that should be reconciled. Do not use those two flags alone to deny the tested container runtime, and do not use the tested runtime to claim that upload or HTTP conversion is enabled.

## 2. HOMR service

### Identity

```text
Path: services/homr-service
Python package: scoremosaic-homr-service
Package version: 0.2.0
Pinned runtime: homr 0.7.0
Compute mode: CPU
Native input scope: JPG/JPEG, PNG
```

### Implemented behavior with evidence

- pinned HOMR wheel and exact runtime dependencies;
- pinned CPU ONNX model assets with checksum verification;
- health and readiness endpoints;
- package, executable, model, and CPU readiness checks;
- fixed `homr --gpu no` private command boundary;
- path containment, suffix, symbolic-link, and stale-output rejection;
- generated score image transcription to MusicXML in CI;
- offline/private non-root container checks.

### Source-level test modules

```text
services/homr-service/tests/test_app.py
services/homr-service/tests/test_config.py
services/homr-service/tests/test_runtime.py
services/homr-service/tests/fixtures/
```

### Local verification command

```bash
python -m compileall -q services/homr-service/src
python -m unittest discover -s services/homr-service/tests -v
```

### Latest observed relevant CI evidence

```text
Workflow: HOMR Runtime Integration CI
Run ID: 30888668233
Conclusion: success
Head commit: e2edbf061a45ae9045d7500a78b34d07f9cf965e
Observed date: 2026-08-04
```

### Verified limit

HOMR is a private image runtime. PDF rasterization, upload, Gateway dispatch, persistence, public routing, authentication, Ensemble execution, and teacher approval are not implemented.

## 3. Clarity-OMR service

### Identity

```text
Path: services/clarity-service
Python package: scoremosaic-clarity-service
Package version: 0.2.0
Source revision: c6bb8a4d2a5b52842a9c41bd0f761f58d02f6f82
Model revision: ee14c1e41ab371fe27bf8a2707ea588560077e73
Compute mode: CPU
Native input scope: PDF
```

### Implemented behavior with evidence

- pinned source archive and model assets with checksum verification;
- exact CPU dependency lock;
- health and readiness endpoints;
- source, model, dependency, and CPU readiness checks;
- fixed private PDF-to-MusicXML command boundary;
- offline model execution;
- workspace containment and symbolic-link rejection;
- MusicXML size, XML, root-element, and unsafe-declaration validation;
- generated PDF fixture and real CI transcription;
- private non-root and read-only container checks.

### Source-level test modules

```text
services/clarity-service/tests/test_app.py
services/clarity-service/tests/test_config.py
services/clarity-service/tests/test_musicxml_safety.py
services/clarity-service/tests/test_runtime.py
services/clarity-service/tests/fixtures/
```

### Local verification command

```bash
python -m compileall -q services/clarity-service/src
python -m unittest discover -s services/clarity-service/tests -v
```

### Latest observed relevant CI evidence

```text
Workflow: Clarity Runtime Integration CI
Run ID: 30888668242
Conclusion: success
Head commit: e2edbf061a45ae9045d7500a78b34d07f9cf965e
Observed date: 2026-08-04
```

### Verified limit

The evidence verifies a private CPU PDF smoke path. HTTP conversion, images as native input, Gateway orchestration, storage, public routing, Ensemble execution, and teacher approval remain disabled.

### Licensing gate

The upstream source declares GPL-3.0. The pinned model repository does not expose a separate model license in the current runtime path. Public service or image distribution requires a separate model provenance and licensing review.

## 4. OMR Gateway

### Identity

```text
Path: services/omr-gateway
Python package: scoremosaic-omr-gateway
Package version: 0.3.0
Orchestration contract: 1.0
Candidate/artifact lifecycle contract: 1.0
Accepted source media types in contracts: PDF, JPEG, PNG
```

### Implemented behavior with evidence

- health-only HTTP boundary;
- fail-closed readiness while orchestration is disabled;
- deterministic versioned orchestration plans;
- per-engine run, candidate, namespace, timeout, and expected-artifact identities;
- exact orchestration-plan verification;
- deterministic append-only candidate/artifact lifecycle;
- immutable sealed source artifact;
- separate raw engine result, MusicXML, and diagnostic artifacts;
- candidate and artifact state machines;
- hash-before-seal requirements;
- append-only event hash chain;
- exact lifecycle replay verification;
- schema checks and explicit disabled decision boundaries.

### Source-level test modules

```text
services/omr-gateway/tests/test_app.py
services/omr-gateway/tests/test_artifact_lifecycle.py
services/omr-gateway/tests/test_config.py
services/omr-gateway/tests/test_engine_client.py
services/omr-gateway/tests/test_models.py
services/omr-gateway/tests/test_orchestration.py
```

### Local verification command

```bash
python -m compileall -q services/omr-gateway/src
python -m unittest discover -s services/omr-gateway/tests -v
```

### Latest observed relevant CI evidence

```text
Workflow: Candidate and Artifact Lifecycle v1 CI
Run ID: 30989083442
Conclusion: success
Head commit: fcff4f237ab4034297ffcd58c20b54f09d377fea

Workflow: Gateway Orchestration Contract v1 CI
Run ID: 30989083440
Conclusion: success
Head commit: fcff4f237ab4034297ffcd58c20b54f09d377fea

Workflow: Foundation CI
Run ID: 30989083414
Conclusion: success
Head commit: fcff4f237ab4034297ffcd58c20b54f09d377fea
```

### Verified limit

The following configuration remains false:

```text
upload-enabled
orchestration-enabled
orchestration-execution-enabled
network-dispatch-enabled
persistence-enabled
artifact-storage-enabled
artifact-runtime-mutation-enabled
```

The lifecycle is an in-memory verified contract. It does not write files, create database rows, publish queue messages, dispatch engines, or recover jobs after restart.

## 5. Ensemble service

### Identity

```text
Path: services/ensemble-service
Python package: scoremosaic-ensemble-service
Package version: 0.2.0
Canonical Score Model: 1.0
Comparator: 0.1-foundation
Comparison report: 1.0
```

### Implemented behavior with evidence

- safe byte-only `score-partwise` MusicXML normalization;
- DTD/entity and bounded-resource rejection;
- exact rational musical timing;
- part, measure, staff, voice, note, rest, chord, tie, dot, tuplet, and TAB structures;
- source and XML-location provenance;
- deterministic Canonical JSON and SHA-256;
- neutral comparison of two to eight candidates;
- deterministic candidate ordering;
- structural, timing, pitch, duration, chord, voice/staff, tie/dot/tuplet, and TAB differences;
- deterministic comparison identifiers and hash;
- versioned comparison report with independent report hash;
- real Audiveris, HOMR, and Clarity fixture capture and validation for one bounded generated score.

### Source-level test modules

```text
services/ensemble-service/tests/test_canonical.py
services/ensemble-service/tests/test_comparator.py
services/ensemble-service/tests/test_musicxml.py
services/ensemble-service/tests/test_real_engine_fixtures.py
services/ensemble-service/tests/test_real_fixture_capture.py
services/ensemble-service/tests/test_report.py
services/ensemble-service/tests/fixtures/
```

### Local verification command

```bash
python -m compileall -q services/ensemble-service/src
python -m unittest discover -s services/ensemble-service/tests -v
```

### Latest observed relevant CI evidence

```text
Workflow: Ensemble Canonical Score Model CI
Run ID: 30980291996
Conclusion: success
Head commit: e9b1b24843217205a7d9a2217a128d159a8cae8b

Workflow: Ensemble Comparator v1 Foundation CI
Run ID: 30980292078
Conclusion: success
Head commit: e9b1b24843217205a7d9a2217a128d159a8cae8b

Workflow: Ensemble Comparison Report v1 CI
Run ID: 30980292061
Conclusion: success
Head commit: e9b1b24843217205a7d9a2217a128d159a8cae8b

Workflow: Ensemble Real Canonical Fixtures CI
Run ID: 30980291974
Conclusion: success
Head commit: e9b1b24843217205a7d9a2217a128d159a8cae8b
```

### Verified limit

The package is a deterministic library foundation, not an enabled orchestration service. It has no public API, job endpoint, persistence, automatic merge, correction, ranking, winner selection, teacher approval, or learner publication.

The real fixture is intentionally bounded and simple. It does not prove representative guitar, TAB, multi-voice, scan, or phone-photo accuracy.

The comparator currently uses conservative ordinal alignment rather than fuzzy or semantic event alignment.

## 6. Contracts

### Implemented schemas at the snapshot

```text
contracts/candidate-artifact-lifecycle.schema.json
contracts/canonical-score.schema.json
contracts/ensemble-comparison-report-v1.schema.json
contracts/omr-job.schema.json
contracts/omr-orchestration-plan.schema.json
contracts/review-report.schema.json
```

### Evidence status

The Canonical, Ensemble report, orchestration, and candidate/artifact lifecycle schemas are exercised by their related package tests and CI workflows.

The presence of `omr-job.schema.json` and `review-report.schema.json` does not mean persistent jobs or a teacher-review API are implemented.

## 7. Deployment foundations

### Present

- root private Compose topology;
- Coolify staging Compose foundation;
- private network and no intended direct engine exposure;
- container hardening checks in engine workflows;
- staging configuration documentation and CI validation.

### Not established

- a live production deployment acceptance record;
- public authenticated Gateway routing;
- persistent database or object storage;
- backup and restore;
- restart-safe queue workers;
- operational monitoring and alerting;
- production incident and rollback procedures.

## 8. Teacher review

### Evidence status

**Specified only.**

The repository documents a review lifecycle and contains a review-report schema, but it does not contain an implemented teacher-review API, editor, authorization layer, immutable revision store, approval endpoint, or publication endpoint.

## 9. ST-OMR

### Evidence status

**Not implemented.**

There is no:

```text
services/st-omr-service
ST-OMR package metadata
ST-OMR model
training dataset
training pipeline
inference API
versioned ST-OMR contract
active Gateway or Ensemble integration
```

Current CI explicitly checks that an ST-OMR service has not been introduced in the Gateway contract phases.

## Evidence freshness rule

Package-specific CI workflows use path filters. A later repository commit may not rerun an unchanged package workflow. Therefore:

- use the package's latest observed successful workflow as evidence for that package revision;
- confirm that the package files have not materially changed since that workflow before reusing the result;
- rerun the relevant workflow after any package, contract, fixture, Dockerfile, dependency, or security-boundary change;
- never treat an older green run as proof for changed code.

## Overall package verdict

The packages form a coherent, test-evidenced foundation:

- the three engines have real private runtime smoke evidence;
- the Gateway has deterministic orchestration and append-only artifact lifecycle evidence;
- Ensemble has deterministic Canonical, comparison, report, and bounded real-fixture evidence.

The missing link is operational integration. None of these packages currently provides the secure, persistent, restart-safe, teacher-approved end-to-end platform by itself or in combination.