# ScoreMosaic ↔ ST Score Editor Core Integration v1

Status: **E7-H fixture-preview browser runtime and presentation-only OSMD host ready; live/production activation remains locked**

This workstream connects the existing ScoreMosaic Teacher Review product shell to the shared `st-score-editor-core` without granting browser, renderer, network, server revision, approval, publication, AI, or production authority.

## Exact upstream core

- repository: `khfy7wpr5p-maker/st-score-editor-core`
- exact commit: `b317abef915d1e16b37572221a38feb3e504450d`
- browser runtime contract: `1.0.0`
- browser artifact: `dist/browser/st-score-editor-core.runtime.js`
- browser artifact manifest: `dist/browser/st-score-editor-core.runtime.manifest.json`
- global: `STScoreEditorCoreRuntime`
- core package remains private/not published as an npm package
- ScoreMosaic does not copy core source into this repository
- ScoreMosaic does not load core code from GitHub/raw HTTP at browser runtime

Cross-repository CI checks out the exact commit, runs the core's own CI and builds the browser artifact. The ScoreMosaic preview builder independently verifies the artifact manifest, byte length and SHA-256 before copying it into the generated fixture preview.

## E7-H fixture-preview flow

```text
ScoreMosaic Teacher Review fixture
        ↓
local bundled ST Score Editor Core runtime
        ↓
Score Editor Core bridge
        ↓
revision-bound semantic render manifest
        ↓
issue-driven semantic selection
        ↓
typed local score / notation intent
        ↓
immutable local editor revision
        ↓
regenerated MusicXML render request
        ↓
OSMD 2.1.1 presentation host
        ↓
real notation display in Score View
```

The original Stage 10 score mock remains in the generated preview as a fail-closed fallback. It is hidden only after OSMD successfully loads and renders the MusicXML string from the current core session.

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

E7-H does not bypass this chain.

## Operation mapping v1

| ScoreMosaic local operation | ST Score Editor Core intent | State |
|---|---|---|
| `set_pitch` | `SET_PITCH` | admitted |
| `set_effective_duration` | `SET_DURATION` | admitted |
| `set_dots` | `SET_DOTS` | admitted; core bound 0–3 |
| `remove_event` | none | fail-closed |

`remove_event` is intentionally not translated to `REPLACE_WITH_REST`; those operations have different semantics.

## OSMD renderer boundary

The admitted fixture renderer is exactly:

- package: `opensheetmusicdisplay`
- version: `2.1.1`
- license: `BSD-3-Clause`
- distribution entry: `build/opensheetmusicdisplay.min.js`

The preview builder accepts only the verified local npm package artifact and carries its BSD license file into the generated preview. No CDN or runtime remote fetch is used.

OSMD itself supports URL-oriented loading paths, so the safety claim is deliberately narrower: the ScoreMosaic host accepts only a MusicXML string from the current core session, never a URL, and the preview CSP retains `connect-src 'none'`. Renderer SVG coordinates, DOM ids, glyph objects and renderer internals are presentation data only and never become edit targets or authority.

## Selection and rerender

E7-H keeps selection semantic and revision-bound:

```text
Teacher Review issue
  -> fixture event id
  -> core render manifest token
  -> semantic note address
```

Direct SVG hit-testing is not authoritative in this stage. After an accepted local core edit, ScoreMosaic asks the presentation host to render the newly accepted core revision. A renderer failure does not undo or reinterpret the accepted local core edit; it restores the fixture visual fallback and reports no new authority.

## Public preview behavior

The generated fixture-only GitHub Pages artifact now carries local copies of:

- the exact ST Score Editor Core browser bundle and integrity manifest;
- OSMD `2.1.1`;
- the OSMD BSD license text;
- a generated immutable renderer profile;
- the ScoreMosaic core bridge and OSMD host.

It still carries no real user data and grants no network API, authentication, browser persistence, server write, approval, publication, or production authority.

## Still-deferred gates

Separate evidence and authorization are still required for:

1. real MusicXML / Teacher Review artifact reads;
2. score-to-source evidence synchronization against real review data;
3. authoritative server edit submission;
4. authenticated live Teacher Review API;
5. server persistence;
6. production approval persistence;
7. publication execution;
8. production renderer/runtime activation;
9. production deployment/traffic.
