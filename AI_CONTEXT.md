# ScoreMosaic AI Context

This file is the single starting point for AI-assisted work in this repository.

It does not replace technical specifications. It tells an AI agent what ScoreMosaic is, which documents are authoritative, what is actually implemented, and which boundaries must not be crossed without an explicit approved task.

## Required reading order

Before proposing or making changes, read these files in order:

1. [`AI_CONTEXT.md`](AI_CONTEXT.md) — project identity, working rules, and source-of-truth order.
2. [`docs/current-status.md`](docs/current-status.md) — the real implementation state and current system boundary.
3. [`docs/package-status.md`](docs/package-status.md) — package versions and test/CI-backed evidence.
4. [`README.md`](README.md) — public repository overview.
5. [`docs/architecture.md`](docs/architecture.md) — architectural intent; verify it against `current-status.md` because older sections may describe an earlier phase.
6. [`docs/security-boundaries.md`](docs/security-boundaries.md) — mandatory trust and isolation rules.
7. Relevant component documentation, contracts, tests, and workflows for the requested scope.

When documents disagree, use this priority:

1. Executable code, schemas, tests, and current configuration.
2. Passing CI evidence tied to a known commit.
3. `docs/package-status.md`.
4. `docs/current-status.md`.
5. Component-specific documentation.
6. Root `README.md` and roadmap documents.

Do not resolve contradictions by guessing. Report the contradiction and use the highest-priority evidence.

## Project identity

ScoreMosaic is an independent, multi-engine optical music recognition platform and teacher-review support system.

Its intended responsibilities are:

- accept an untrusted score document through a future secured platform API;
- run isolated OMR engines;
- preserve every raw engine result and its provenance;
- normalize safe MusicXML into a shared Canonical Score Model;
- compare musical evidence without silently selecting a winner;
- produce structured disagreement and review evidence;
- support immutable teacher revisions and explicit approval;
- release only approved MusicXML to a separate learner-facing application.

ScoreMosaic is not the learner-facing application. Playback, Turkish narration, lesson delivery, MIDI interaction, and accessible learner presentation belong outside this repository.

## Current architectural model

```text
Teacher or external application
              |
              | future versioned authenticated API
              v
         OMR Gateway
              |
      immutable source artifact
              |
       +------+------+------+
       |             |      |
       v             v      v
  Audiveris         HOMR  Clarity
       |             |      |
       +------+------+------+
              |
     immutable engine candidates
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
 learner-facing application outside this repository
```

This is the target system shape. The complete enabled runtime path is not yet implemented.

## Current implementation facts

At the status baseline recorded in `docs/current-status.md`:

- Audiveris, HOMR, and Clarity have private runtime foundations and runtime-integration CI evidence.
- OMR Gateway has deterministic orchestration-plan and append-only candidate/artifact lifecycle libraries.
- Gateway upload, live network dispatch, queues, persistence, and storage writes remain disabled.
- Ensemble has a Canonical Score Model, neutral comparator, real-engine fixtures, and a versioned comparison report.
- Engine ranking, winner selection, automatic merge, automatic correction, teacher approval, and learner publication remain disabled or unimplemented.
- ST-OMR is not implemented. There is no ST-OMR service, model, dataset, active contract, training pipeline, or inference path.

Always verify the latest statement in [`docs/current-status.md`](docs/current-status.md) before acting.

## Non-negotiable boundaries

Unless an explicitly approved task changes a boundary through reviewed contracts, tests, and security analysis:

- Treat PDFs, images, MusicXML, archives, filenames, model files, and engine responses as untrusted.
- Keep engine services private.
- Do not expose container paths, model files, or internal engine endpoints to external clients.
- Do not overwrite original input or raw engine artifacts.
- Keep engine identity, version, hashes, diagnostics, and source provenance.
- Do not silently rank engines or select a preferred winner.
- Do not automatically merge or correct MusicXML.
- Do not mark a score approved without a teacher-review decision.
- Do not publish directly to a learner-facing application.
- Do not enable uploads, execution, persistence, storage writes, or public routing merely because a contract library exists.
- Do not add ST-OMR integration before its role, data governance, evaluation metrics, contract, and security boundary are explicitly approved.

## Status vocabulary

Use the following labels precisely:

- **Implemented** — executable repository behavior exists.
- **Tested** — relevant automated tests exist and have been run successfully.
- **CI-verified** — a named GitHub Actions workflow completed successfully on a recorded commit.
- **Runtime-integrated** — a pinned engine/runtime is built and exercised by integration or smoke tests.
- **Contract-only** — deterministic data structures or lifecycle rules exist, but runtime execution is disabled.
- **Specified** — documentation or schema exists without complete executable behavior.
- **Disabled by design** — code/configuration explicitly prevents the capability.
- **Not implemented** — no executable capability exists.
- **Not verified** — evidence is insufficient; do not describe the capability as working.

Never use “production-ready,” “complete,” “end-to-end,” or “working” unless the exact full path has fresh evidence.

## AI working rules

For every task:

1. Identify the exact requested outcome and allowed files.
2. Inspect the current branch, latest `main`, relevant code, tests, schemas, and workflows.
3. Preserve unrelated work and current security boundaries.
4. Make the smallest coherent change.
5. Add or update tests when behavior changes.
6. Run the narrowest relevant verification, then broader proportionate checks.
7. Report what was changed, what was verified, and what remains unverified.
8. Update status documentation when a package capability or boundary changes.

For read-only architecture requests, do not create branches, commits, issues, pull requests, or file changes.

For authorized changes, use a feature branch and do not modify `main` directly.

## Documentation maintenance rule

A change must update these status documents when it alters any of the following:

- package version;
- implemented capability;
- enabled or disabled boundary;
- contract version;
- test coverage or CI workflow;
- engine/runtime version;
- deployment status;
- teacher-review status;
- ST-OMR status.

Update [`docs/package-status.md`](docs/package-status.md) from executable and CI evidence first. Then update [`docs/current-status.md`](docs/current-status.md) to reflect the platform-level effect.

Do not update status documents from plans, intentions, or unmerged proposals.