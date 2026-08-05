# ScoreMosaic Current Status

**Snapshot date:** 2026-08-05  
**Source branch reviewed:** `main`  
**Source commit:** `fcff4f237ab4034297ffcd58c20b54f09d377fea`  
**Latest merged milestone at this snapshot:** Candidate and Artifact Lifecycle Contract v1

This document describes the real repository state. It separates target architecture, implemented foundations, enabled runtime behavior, and future work.

## Executive status

ScoreMosaic is currently a **test-evidenced architecture and contract foundation before persistent end-to-end execution**.

The most recent documented project stage is **Phase 12: Candidate and Artifact Lifecycle Contract v1**. Phase 12 adds a deterministic, append-only, in-memory lifecycle for source artifacts, per-engine candidates, raw engine results, MusicXML artifacts, diagnostics, hashes, and state transitions.

Phase 12 does **not** enable uploads, storage writes, queues, live engine dispatch, persistence, Ensemble execution, teacher approval, learner publication, or ST-OMR.

The project is therefore beyond the original Phase 0 description, but it is not yet an operational public OMR platform.

## Current maturity summary

| Area | Real status |
|---|---|
| Architecture and security boundaries | Defined in detail; some older overview documents are stale |
| Audiveris runtime | Real private runtime and CI transcription smoke test exist |
| HOMR runtime | Real private CPU runtime and CI transcription smoke test exist |
| Clarity-OMR runtime | Real private CPU runtime and CI transcription smoke test exist |
| OMR Gateway | Health-only runtime; deterministic orchestration and artifact-lifecycle libraries implemented |
| Gateway live execution | Disabled |
| Canonical Score Model | Implemented and unit tested |
| Ensemble comparison | Neutral deterministic comparator implemented and unit tested |
| Comparison report | Versioned deterministic report contract implemented and unit tested |
| Real three-engine fixture validation | Implemented for one bounded generated score fixture |
| Persistent jobs and artifacts | Not implemented |
| Teacher review API/editor | Specified only |
| Learner publication | Not implemented |
| ST-OMR | Reserved future capability; no package, model, dataset, or contract |
| Production readiness | Not achieved |

## Implemented foundations

### 1. Private OMR engine runtimes

The repository contains private runtime foundations for:

- Audiveris `5.11.0`;
- HOMR `0.7.0` in CPU mode;
- Clarity-OMR at pinned source and model revisions in CPU mode.

The engine adapters expose health and readiness boundaries. Their real runtime images are tested in GitHub Actions with generated, non-copyrighted fixtures. They do not expose public upload or conversion APIs.

### 2. OMR Gateway contracts

`services/omr-gateway` is version `0.3.0` at this snapshot.

Implemented as deterministic libraries:

- Orchestration Plan Contract v1;
- Candidate and Artifact Lifecycle Contract v1;
- per-engine run identities;
- isolated candidate namespaces;
- bounded timeouts and explicit lifecycle states;
- immutable source references;
- separate raw result, MusicXML, and diagnostic artifact identities;
- append-only transition events with a hash chain;
- exact replay verification of lifecycle snapshots.

The HTTP service remains health-only. The contract libraries are not connected to job endpoints or live execution.

### 3. Canonical Score Model

The Ensemble package can normalize bounded, safe `score-partwise` MusicXML into a deterministic Canonical Score Model while preserving:

- parts, measures, staff, and voice;
- notes, rests, chords, ties, dots, and tuplets;
- exact rational written and effective durations;
- `backup` and `forward` timing evidence;
- guitar string and fret evidence when present;
- source engine, artifact, XML path, and event-index provenance.

Unsafe XML declarations and bounded-resource violations are rejected.

### 4. Neutral Ensemble comparison

The comparator accepts two to eight immutable Canonical Score candidates and reports disagreements without ranking engines or selecting a winner.

It compares structural and musical evidence including:

- measure presence and duration;
- time signatures;
- event onset;
- pitch;
- written and effective duration;
- note/rest identity;
- chord membership;
- staff and voice;
- ties, dots, and tuplets;
- TAB string and fret evidence.

The current alignment strategy is conservative and primarily ordinal. It is a foundation, not a final semantic alignment engine.

### 5. Versioned comparison report

The repository contains a deterministic Ensemble Comparison Report v1 with:

- schema version `1.0`;
- preserved nested comparison evidence;
- deterministic identifiers and SHA-256 integrity;
- explicit disabled decision boundaries;
- no ranking, winner, preferred candidate, merge, correction, approval, or publication claim.

### 6. Candidate and artifact lifecycle

Phase 12 reserves and validates one isolated candidate per engine and three distinct output artifacts per candidate:

```text
raw_engine_result
musicxml
diagnostic
```

The lifecycle is append-only and requires content hash, size, and media type before an artifact can be sealed. It prevents overwrite, cross-engine writes, reopening terminal states, and candidate sealing before all candidate artifacts are sealed.

This is a pure in-memory contract. It does not write files or database records.

## Actual runtime topology

The current container topology contains:

```text
private OMR Gateway foundation
private Audiveris service
private HOMR service
private Clarity-OMR service
```

The services are placed on a private internal network with no intended direct public engine access.

The Ensemble component is currently a Python library and test package. It is not an active container in the end-to-end Compose runtime.

## Capabilities intentionally disabled

The following remain disabled or absent:

- public or authenticated PDF/image upload;
- job creation through the Gateway HTTP API;
- live Gateway-to-engine dispatch;
- queue workers and retry execution;
- cancellation execution and deadline enforcement against running containers;
- database persistence;
- content-addressed artifact storage;
- storage writes and runtime artifact mutation;
- restart recovery and idempotent replay across processes;
- automatic validation of live engine outputs;
- automatic Gateway-to-Canonical-to-Ensemble execution;
- engine ranking and winner selection;
- automatic MusicXML merge or correction;
- teacher review API, editor, revisions, and authorization;
- teacher approval and learner publication;
- SesliTab delivery integration;
- ST-OMR training, inference, or integration.

## CI evidence at the snapshot

The following relevant `main` workflow runs were observed as completed successfully:

| Evidence | Workflow run | Source commit |
|---|---:|---|
| Candidate and Artifact Lifecycle v1 | `30989083442` | `fcff4f237ab4034297ffcd58c20b54f09d377fea` |
| Gateway Orchestration Contract v1 | `30989083440` | `fcff4f237ab4034297ffcd58c20b54f09d377fea` |
| Foundation CI | `30989083414` | `fcff4f237ab4034297ffcd58c20b54f09d377fea` |
| Ensemble Canonical Score Model | `30980291996` | `e9b1b24843217205a7d9a2217a128d159a8cae8b` |
| Audiveris Runtime Integration | `30888668253` | `e2edbf061a45ae9045d7500a78b34d07f9cf965e` |
| HOMR Runtime Integration | `30888668233` | `e2edbf061a45ae9045d7500a78b34d07f9cf965e` |
| Clarity Runtime Integration | `30888668242` | `e2edbf061a45ae9045d7500a78b34d07f9cf965e` |

A successful workflow proves only the behavior exercised by that workflow. It does not prove production readiness, general OMR accuracy, or a complete end-to-end platform.

See [`package-status.md`](package-status.md) for package-level evidence and limits.

## Known documentation drift

Several older documents describe an earlier architecture or phase:

- the original root README still described Phase 0 before the documentation branch update;
- `docs/architecture.md` assigns external job lifecycle and engine dispatch to Ensemble, while the implemented direction now places orchestration contracts in the Gateway;
- `docs/roadmap.md` ends at the older Phase 7 sequence;
- some service READMEs describe their next step even though that step has since been completed.

Until those files are reconciled, use this document, package metadata, contracts, source, tests, and CI as the current-state evidence.

## Important gaps and risks

### End-to-end execution gap

The largest gap is the absence of a persistent, restart-safe execution path from secure intake to engine candidates, Canonical normalization, Ensemble comparison, and review report generation.

### Guitar and TAB benchmark gap

The real cross-engine fixture proves bounded deterministic processing for a simple generated score. It does not establish accuracy for representative guitar material such as:

- staff plus TAB;
- TAB-only scores;
- rhythm beams in TAB;
- chords;
- multiple voices;
- ties, tuplets, rests, and dotted rhythms;
- poor scans;
- mobile-phone photographs.

### Comparator alignment limitation

The current comparator uses conservative ordinal alignment. Missing or extra events may cause cascading differences. Future alignment should consider measure, onset, voice, staff, chord group, pitch, duration, and TAB evidence without erasing provenance.

### Licensing gate

Audiveris and HOMR have AGPL obligations. Clarity source is GPL-3.0, and the pinned model repository does not expose a separate model license in the current runtime path. Public distribution or service exposure requires a separate licensing review.

### Package metadata inconsistency

The Audiveris service README and container workflow describe a real installed runtime, while its Python `pyproject.toml` still contains foundation-era flags indicating that the engine and Java runtime are not installed. This should be reconciled before package metadata is treated as an authoritative runtime inventory.

## Recommended next implementation order

1. Reconcile current architecture and phase documentation.
2. Define secure authenticated intake and preprocessing boundaries.
3. Add isolated content-addressed artifact storage that preserves the Phase 12 lifecycle contract.
4. Add persistent jobs, idempotency, cleanup, and restart recovery.
5. Enable live private engine dispatch with explicit timeouts and cancellation.
6. Validate and seal real engine outputs as immutable artifacts.
7. Connect sealed MusicXML candidates to Canonical normalization and Ensemble reporting.
8. Implement the teacher-review API, immutable revisions, approval, and authorization.
9. Build a teacher-verified guitar and TAB benchmark package.
10. Deliver only approved MusicXML to the separate learner-facing application.
11. Evaluate ST-OMR recommendations only after sufficient verified correction data exists.

## Current verdict

The architecture direction is coherent and safety-conscious. The repository has meaningful executable and CI-verified foundations, especially around isolated engines, provenance, deterministic contracts, Canonical normalization, neutral comparison, and append-only artifact state.

The project should not be rebuilt. It should now progress from **in-memory verified contracts** to a **secure, persistent, restart-safe, end-to-end Gateway execution path** while preserving all existing immutable evidence and teacher-approval boundaries.