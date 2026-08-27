# ScoreMosaic ↔ ST Score Editor Core Integration v1

Status: **repository integration bridge ready; runtime host and live API activation deferred**

This workstream connects the existing ScoreMosaic Teacher Review product shell to the shared `st-score-editor-core` contract without granting browser, renderer, network, approval, publication, or production authority.

## Exact upstream core

- repository: `khfy7wpr5p-maker/st-score-editor-core`
- exact commit: `70c884fcc0f4c51f3baecf0bf057c78e1ca87f9b`
- browser runtime contract: `1.0.0`
- core package remains private/not published as an npm package
- ScoreMosaic does not copy core source into this repository
- ScoreMosaic does not load core code from GitHub/raw HTTP at browser runtime

The exact commit is verified by cross-repository CI before integration is accepted.

## Current repository flow

```text
ScoreMosaic Teacher Review Stage 10/11
        ↓
Score Editor Core bridge
        ↓
[host-injected ST Score Editor Core runtime]
        ↓
semantic render manifest / selection
        ↓
typed local score or notation intent
        ↓
immutable local editor revision
        ↓
regenerated render request
```

The bracketed runtime is deliberately not bundled into the public GitHub Pages fixture preview in v1. When it is absent, the bridge fails closed and the existing Stage 11 disconnected local-intent preview remains available.

## Authority boundary

A local ST Score Editor Core revision is **not** a ScoreMosaic server `TeacherScoreRevision` and does not satisfy production write authorization. The browser still cannot mint or persist an authoritative server command/revision.

Future live mutation must continue through the existing ScoreMosaic Stage 8 server boundary:

```text
browser local editor intent
  -> authenticated server request
  -> reviewer / tenant / resource authorization
  -> exact-current revision check
  -> old-value precondition
  -> closed ScoreEditCommand
  -> deterministic validation
  -> immutable TeacherScoreRevision
```

The E7-G repository bridge does not bypass this chain.

## Operation mapping v1

| ScoreMosaic local operation | ST Score Editor Core intent | State |
|---|---|---|
| `set_pitch` | `SET_PITCH` | admitted |
| `set_effective_duration` | `SET_DURATION` | admitted |
| `set_dots` | `SET_DOTS` | admitted; core bound 0–3 |
| `remove_event` | none | fail-closed |

`remove_event` is intentionally not translated to `REPLACE_WITH_REST`; those operations have different semantics.

## Renderer boundary

OSMD `2.1.1` remains the admitted classical-score renderer target, but OSMD runtime activation is not part of this repository gate. Renderer state, SVG/DOM ids, glyphs and coordinates never become edit authority. Selection must resolve through the core revision-bound semantic manifest.

## Public preview behavior

The public fixture preview may contain the local bridge script, but it contains no core runtime and no OSMD bundle. Therefore:

- no external runtime fetch;
- no network API;
- no browser persistence;
- no server write;
- no approval or publication execution;
- existing fixture/local-intent behavior remains the safe fallback.

## Deferred gates

Separate evidence and authorization are still required for:

1. browser-safe core packaging/bundling;
2. exact OSMD host installation and lockfile/provenance evidence;
3. real MusicXML/Teacher Review artifact reads;
4. authenticated live Teacher Review API;
5. server write and persistence;
6. production approval persistence;
7. publication execution;
8. production deployment/traffic.
