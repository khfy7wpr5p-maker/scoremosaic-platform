# UI-0A — Visual Foundation and Application Shell Contract

## Status

Documentation-only isolated UI foundation.

This document defines the visual identity, application-shell regions, presentation states, accessibility baseline, responsive behavior, and non-activation boundaries for future ScoreMosaic web work.

UI-0A does **not** create a frontend runtime, select a framework, add dependencies, enable upload, connect to APIs, create Teacher Review writes, enable playback, or activate any production capability.

## 1. Purpose

ScoreMosaic is an OMR and teacher-review platform. Its web interface must help an authorized teacher inspect source evidence, review OMR disagreements, understand validation findings, and later enter bounded corrections without turning any renderer, OMR engine, Ensemble recommendation, or browser state into musical authority.

The interface must remain consistent with the existing Teacher Review Score Editor architecture contract and the Gate C -> D -> E -> F -> G security sequence.

## 2. Visual identity

The approved ScoreMosaic logo is the visual reference for the future interface.

The interface should derive its visual language from the logo:

- primary canvas: white or near-white;
- primary text: deep navy;
- primary accent: turquoise/teal;
- secondary accent: green;
- optional supporting accent: blue-to-purple range used sparingly;
- restrained borders and shadows;
- high information density only where review work requires it;
- professional, technical, music-focused appearance without decorative complexity.

The logo asset itself is not committed by UI-0A. Asset packaging, variants, sizing, and licensing/provenance metadata are a separate reviewed UI package.

## 3. Core application shell

The target desktop review shell contains these presentation regions:

```text
+------------------------------------------------------------------+
| ScoreMosaic | document/revision context | reviewer/account area   |
+-------------+----------------------------------+-------------------+
|             |                                  |                   |
| Issues      | Score View                       | Structured Edit   |
|             |                                  |                   |
|             |                                  |                   |
|             +----------------------------------+                   |
|             | Source Evidence                  |                   |
+-------------+----------------------------------+-------------------+
| Review Transport: beginning / play / pause / stop / tempo / loop |
+------------------------------------------------------------------+
| Validation / unresolved issues / revision status                 |
+------------------------------------------------------------------+
```

The Score View is the primary workspace and should receive the largest visual area.

## 4. Region responsibilities

### 4.1 Header / context bar

Presentation-only responsibilities:

- ScoreMosaic identity;
- current document or job label when available;
- current revision label when available;
- reviewer/account affordance when authorization exists later.

UI-0A defines appearance only. It does not define authentication or account behavior.

### 4.2 Issues panel

Future presentation responsibilities:

- filterable issue list;
- measure/page/staff/voice/event location labels where available;
- blocking/warning/informational distinction;
- source/engine evidence cues;
- unresolved/resolved presentation state.

Issue state must not be communicated by color alone.

### 4.3 Score View

Future presentation responsibilities:

- notation rendering;
- measure and event focus;
- issue markers;
- selected location state;
- review cursor state when later authorized by the implementation sequence.

The renderer is presentation-only and must never become a source of musical truth.

### 4.4 Structured Edit panel

UI-0A reserves visual space for future bounded structured edit controls.

In UI-0A and later static mock work, these controls are non-functional.

A live writable panel must not be activated before Gate D, Gate E, TR-8A, and the separately approved revision/edit contracts required by the Teacher Review architecture.

No unrestricted raw MusicXML editing surface is introduced by this contract.

### 4.5 Source Evidence panel

Future presentation responsibilities:

- immutable source PDF/image page;
- bounded source-region or measure crop;
- source identity/provenance labels;
- engine-specific evidence for the same musical location.

Source Evidence should be visually comparable with Score View without requiring excessive vertical navigation. Desktop layouts should prefer adjacent or quickly resizable comparison behavior where practical.

Source rendering/cropping remains a presentation derivative and does not weaken Safe Intake.

### 4.6 Review Transport

Reserved future presentation controls:

- beginning;
- Play;
- Pause;
- Stop;
- bounded tempo;
- selected-measure playback;
- selected-measure loop;
- cursor feedback.

Until the separately approved playback/cursor stages are reached, these controls may appear only in static/non-production prototypes and must not create real audio, timing authority, edits, approvals, or state transitions.

### 4.7 Validation / revision status bar

Future presentation responsibilities:

- validation pass/fail summary;
- unresolved and blocking issue counts;
- current revision identity/status;
- stale or read-only state;
- save/approval/publication eligibility only when corresponding server-side contracts exist.

The UI must never infer approval merely from a successful validation or save state.

## 5. Presentation state vocabulary

The initial visual vocabulary should cover:

- neutral;
- hover/focus;
- selected;
- read-only;
- disabled;
- informational;
- warning;
- blocking error;
- validated/pass;
- unresolved;
- stale revision;
- loading/processing placeholder for later use.

Icons, text, shape, and semantic labels must accompany color where meaning is important.

## 6. Accessibility baseline

All later UI work must preserve:

- full keyboard reachability for interactive controls;
- visible keyboard focus;
- programmatic labels;
- screen-reader-readable issue and validation text;
- no color-only status communication;
- scalable text;
- adequate contrast;
- logical focus order;
- responsive panel behavior;
- textual alternatives for confidence/comparison graphics;
- accessible transport labels and playback-state announcements when playback is later implemented.

## 7. Responsive direction

Desktop is the primary review workspace because simultaneous score, source, issue, and edit comparison benefits from horizontal space.

Responsive behavior should follow this hierarchy:

1. preserve Score View as the primary region;
2. collapse Issues and Structured Edit into accessible side drawers or tabs when width becomes limited;
3. allow Source Evidence to switch between adjacent and stacked presentation;
4. preserve validation and blocking-state visibility;
5. never hide critical error meaning behind hover-only behavior.

No exact breakpoints or CSS framework are selected by UI-0A.

## 8. Explicit isolation / non-activation

UI-0A does not:

- add `frontend`, `web`, `ui`, or application runtime directories;
- add JavaScript/TypeScript packages or lockfiles;
- select React, Vue, Svelte, Next.js, Vite, or another framework;
- add an HTTP client;
- connect to OMR Gateway or engine services;
- add a real PDF/image upload control;
- create jobs or durable state;
- read production artifacts;
- implement authentication, RBAC, sessions, or reviewer identity;
- implement TeacherScoreRevision or ScoreEditCommand;
- implement renderer, editor, cursor, MIDI, SoundFont, or playback behavior;
- implement approval or publication;
- change service runtime code, schemas, tests, deployment, or workflows;
- change the existing security-gate order.

Any visible future upload/edit/play/approve control in a static prototype is presentation-only until its protecting gate and contract are separately approved.

## 9. Safe UI development sequence

The UI track should advance in small isolated packages:

1. **UI-0A — Visual Foundation and Application Shell Contract** — this document.
2. **UI-0B — Static Application Shell** — repository-owned, non-production visual shell with no network/API/runtime authority.
3. **UI-0C — Mock Teacher Review Workspace** — fixed local/mock data only; no real source upload, job, reviewer write, or backend connection.
4. **UI-0D — Renderer Compatibility Experiment** — fixed repository-owned fixture only; presentation evidence, not production Teacher Review.
5. **TR-3 — Real read-only Score Viewer / issue focus** — only after its upstream architecture/security prerequisites are met.
6. **TR-4 and later writable/playback stages** — only in the authoritative Teacher Review implementation order.

UI-0B, UI-0C, and UI-0D must remain removable/replaceable experiments and must not create a hidden parallel application architecture.

## 10. UI-0A exit criteria

UI-0A is complete only when review confirms:

- one documentation file is the only changed repository path;
- no runtime/frontend/dependency/workflow change exists;
- no API, upload, renderer, playback, or write capability was activated;
- the shell regions align with the Teacher Review architecture contract;
- accessibility and responsive requirements are explicit;
- future UI packages remain subordinate to the established security gates;
- relevant documentation CI is green.

Merge remains a separate approval gate.
