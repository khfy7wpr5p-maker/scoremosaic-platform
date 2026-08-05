# ScoreMosaic AI Context

This is the single starting file for AI assistants, automation tools, and new contributors working in this repository.

Read this file first. Then read:

1. [`docs/current-status.md`](docs/current-status.md) for the real implementation state.
2. [`docs/package-status.md`](docs/package-status.md) for package versions, test evidence, and verified limits.
3. The relevant service README, contract, tests, and CI workflow before proposing or making a change.

## Project identity

ScoreMosaic is an independent, multi-engine optical music recognition (OMR) and teacher-review support platform.

It is intended to:

- run isolated OMR engines;
- preserve every raw candidate and its provenance;
- normalize safe MusicXML into a shared Canonical Score Model;
- compare candidates without silently choosing a winner;
- produce structured disagreement evidence for teacher review;
- allow only an explicitly approved revision to reach a learner-facing application.

ScoreMosaic is **not** the learner-facing playback, Turkish narration, MIDI interaction, accessibility presentation, or lesson-delivery application. Those responsibilities belong to a separate application such as SesliTab.

## Source-of-truth order

When documents disagree, use this order:

1. Executable source, tests, contracts, package metadata, Compose configuration, and current CI workflows.
2. `docs/current-status.md` and `docs/package-status.md`.
3. Service-specific README files and current contract documents.
4. General architecture and roadmap documents.
5. Historical phase descriptions, old issue text, or old pull-request descriptions.

Do not describe a capability as implemented merely because it appears in a target architecture or roadmap.

## Current architecture boundary

The target flow is:

```text
Teacher or external application
              |
              v
         OMR Gateway
              |
       secure immutable input
              |
       +------+------+------+
       |             |      |
       v             v      v
  Audiveris         HOMR  Clarity
       |             |      |
       +------+------+------+
              |
     immutable candidates
              |
              v
     Canonical Score Model
              |
              v
      Ensemble Comparator
              |
              v
   versioned comparison report
              |
              v
 teacher review and revisions
              |
              v
      approved MusicXML only
              |
              v
 learner-facing application
```

The complete enabled flow does not exist yet. The repository currently contains tested engine runtime foundations, deterministic Gateway contracts, Canonical normalization, neutral comparison, and report foundations.

## Capabilities that are currently disabled or absent

Do not assume any of the following exists:

- public PDF or image upload;
- authenticated job creation;
- live Gateway-to-engine network dispatch;
- queues, retries, cancellation execution, or restart recovery;
- database persistence or artifact storage writes;
- automatic Gateway-to-Canonical-to-Ensemble execution;
- engine ranking, preferred-engine selection, or winner selection;
- automatic MusicXML merge or correction;
- teacher-review API or editor;
- approval and learner publication;
- ST-OMR service, model, dataset, training, inference, or integration.

The Gateway HTTP boundary remains health-only. Contract libraries being enabled does not mean runtime execution is enabled.

## Non-negotiable invariants

Any design or implementation must preserve these rules unless the project owner explicitly changes the architecture:

1. Original inputs and raw engine outputs are immutable.
2. Each engine candidate remains isolated and keeps its engine identity, version, hashes, diagnostics, and provenance.
3. No component silently overwrites another engine result.
4. Comparison remains neutral until a separately reviewed decision policy exists.
5. No automatic result is treated as teacher-approved truth.
6. Corrections create new auditable revisions.
7. Only an explicitly approved revision may cross the learner-publication boundary.
8. Engine services remain private and must not receive direct browser traffic.
9. Untrusted PDF, image, archive, filename, MusicXML, model, and remote-response data must be bounded and validated.
10. Disabled security and execution flags must fail closed.

## ST-OMR boundary

ST-OMR is a reserved future capability, not an existing package or active development phase.

A safe first role would be an explainable recommendation system that consumes immutable candidates, Ensemble disagreement evidence, and teacher-verified revisions. It must not:

- mutate raw candidates;
- hide provenance;
- automatically approve a score;
- publish directly to learners;
- begin training before a representative, teacher-verified guitar and TAB dataset exists.

Do not create `services/st-omr-service`, model code, training pipelines, or ST-OMR contracts unless the task explicitly authorizes a separately scoped ST-OMR design phase.

## Repository map

```text
AI_CONTEXT.md                  Single AI/contributor entry point
README.md                      Project overview and target architecture
contracts/                     Versioned schemas and platform contracts
docs/current-status.md         Real project state snapshot
docs/package-status.md         Test-evidenced package status
docs/                          Architecture, security, review, and contract documents
services/omr-gateway/          Health boundary and deterministic Gateway contracts
services/audiveris-service/    Private Audiveris runtime adapter
services/homr-service/         Private HOMR runtime adapter
services/clarity-service/      Private Clarity-OMR runtime adapter
services/ensemble-service/     Canonical normalization, comparison, and report libraries
compose.yaml                   Private local container topology
deploy/coolify/staging/        Staging deployment foundation
.github/workflows/             Automated verification
```

## Required workflow for changes

Before changing a package:

1. Read its `pyproject.toml`, README, tests, Dockerfile, and related contracts.
2. Confirm its current status in `docs/package-status.md`.
3. Identify which disabled boundaries must remain disabled.
4. Work on a feature branch; do not change `main` directly.
5. Make the smallest scoped change.
6. Run the package compile and unit-test commands.
7. Run or inspect the relevant contract, container, integration, and security checks.
8. Review the diff for unrelated changes, enabled capability flags, secret material, public ports, mutable artifacts, and weakened validation.
9. Use a pull request and require green checks before merge.

Documentation-only tasks must not alter code, runtime flags, contracts, deployment, issues, or repository settings unless separately authorized.

## Evidence language

Use these terms consistently:

- **Specified:** documented but not implemented.
- **Foundation implemented:** executable library or private boundary exists, but the end-to-end feature is disabled.
- **Unit tested:** source-level tests pass for the covered behavior.
- **Integration tested:** CI exercises the real container/runtime or cross-component fixture path.
- **Enabled:** reachable in the intended runtime path.
- **Production ready:** security, persistence, recovery, authorization, operations, licensing, and acceptance gates are complete.

No package in this repository should currently be described as a production-ready public OMR service.

## Next gated direction

The next architectural direction is not another OMR engine and not automatic winner selection. The next work must preserve the existing orchestration and append-only artifact lifecycle contracts while introducing, in separately reviewed phases:

1. secure authenticated intake;
2. isolated content-addressed artifact storage;
3. persistent jobs and restart-safe execution;
4. live private engine dispatch with timeouts and cancellation;
5. automatic candidate validation, Canonical normalization, and Ensemble reporting;
6. teacher-review revisions and approval.

Always re-check `docs/current-status.md` before acting, because the repository may advance beyond this file's last edit.