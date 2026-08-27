# H7-C — ST-Orchestration local / preview adapter

Status: **HUMAN APPROVED / LOCAL PREVIEW ACTIVE / PRODUCTION DISABLED**  
Date: 2026-08-27

## Decision

H7-C authorizes the first real working ScoreMosaic ↔ ST-Orchestration connection only as a local, non-authoritative preview path.

The exact ST-Orchestration target is pinned to `f5ee0e605e62c41af86255712941305b2a8c7afb`. The only admitted capability remains `string-seat-ranking-v0` with model fingerprint `15cd94722a0ba2724ceea6f450f16a87ef455fa8bc21d4b619f0bda6d880ca14` and frozen threshold `0.55`.

## Runtime path

```text
validated-preview synthetic Teacher Review fixture
        ↓
ScoreMosaic local-process adapter
        ↓
exact pinned ST-Orchestration Python CLI
        ↓
deterministic string feasibility veto
        ↓
exact O5-C local model inference
        ↓
proposal / alternatives / abstain / unsupported
        ↓
validated generated preview evidence
        ↓
Teacher Review Orchestration Preview panel
```

The local process adapter is the transport owner. It verifies the exact ST Git HEAD and clean working tree before execution, invokes Python without a shell, applies a bounded timeout/output size, and validates the returned model identity, request lineage, status domain and deterministic-validation boundary.

The browser does **not** execute Python, spawn a process, or call ST-Orchestration. `connect-src 'none'` remains in force. It reads only repository-generated preview evidence through a non-authoritative, non-persistent, non-mutating browser adapter.

## Teacher Review authority

The Orchestration Preview panel is evidence only:

- it can show the model's top suggestion, confidence and alternatives;
- it shows deterministic PASS/VETO and exact lineage fingerprints;
- it has no Apply action;
- it cannot mutate Canonical Score;
- it cannot create or overwrite TeacherScoreRevision;
- it cannot approve or publish;
- it cannot train from teacher corrections.

Failure is fail-closed: if preview evidence or lineage validation fails, the panel shows unavailable rather than fabricating a suggestion.

## Evidence fixture

The H7-C CI fixture is synthetic and non-production. The connection and model invocation are real, but the musical input is controlled repository evidence rather than a production Teacher Review document.

Expected evidence:

- preview input SHA-256: `232896f7af0b1fde5261c6a8a2359ff2e4082574b9b4559d97050d2359c63fdf`
- result status: `proposal`
- top suggestion: `violin-1`
- result SHA-256: `2ee992b14ce19a0a4d326b05b6ad7c737dcf69a973626e207f1ca8fb33f109af`

## Parallel Teacher Review Core work

H7-C is intentionally separated from the open Real Score Intake / Teacher Review Core work. It does not modify the Core bridge, intake schemas, Teacher Review service, canonical projection, or semantic-address files changed by PR #185. The preview panel remains downstream evidence and cannot become a Core edit command or revision mutation path.

## Still closed

Network transport, authenticated staging, production credentials, production inference, Canonical/TeacherRevision mutation, approval/publication, ST-OMR integration, H4 rerun, post-H4 retuning, automatic learning and broader/full orchestration claims remain closed.

The next gate is **H7-D authenticated staging transport**, requiring a separate explicit human decision.
