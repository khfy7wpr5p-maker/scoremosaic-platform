# Stage 10 — UI / Application Experience Prototype

## Current status — Stage 10-F complete

The Stage 10 repository-only UI/Application Experience is complete. This directory contains the integrated ScoreMosaic product experience as a dependency-free, disconnected, non-production prototype.

Completed capabilities are deliberately local:

- checked-in deterministic fixture review;
- in-memory issue filtering and focus;
- keyboard issue navigation with Arrow Up/Down, Home, and End;
- synthetic source-evidence presentation;
- a bounded disconnected edit-intent draft;
- responsive, reduced-motion, increased-contrast, forced-colors, long-identifier, and touch-target hardening.

There is still no network, upload, authentication/session/RBAC runtime, durable browser state, no Teacher Review write, ScoreEditCommand, TeacherScoreRevision, approval/publication execution, audio/MIDI playback, database/object-storage access, credentials, or production infrastructure.

## Regions

The shell integrates:

- application header and document/revision context;
- Issues panel;
- primary Score View;
- Source Evidence comparison panel;
- Structured Edit / local intent panel;
- Review Transport presentation area;
- Validation / revision status bar.

Score View remains the first application workspace on narrow layouts.

## Fixture boundary

`fixture.js` is repository-owned test/demo evidence only. It declares `productionArtifact=false` and `authoritativeTruth=false` and is deep-frozen before use.

Issue selection and filtering modify presentation state only in browser memory. Nothing is saved across reloads.

## Local edit-intent boundary

The experience reuses a closed subset of the existing Stage 8-H operation vocabulary:

```text
set_pitch
set_effective_duration
set_dots
remove_event
```

A prepared local intent contains a bounded fixture target and proposed operation, but explicitly carries no server authority. It cannot contain or create a server authorization, old-value precondition, command identity, ScoreEditCommand, TeacherScoreRevision, approval, or publication.

The intent is displayed only with `textContent`; it is not submitted, downloaded, copied to persistent storage, or sent over a network.

## Accessibility and responsive baseline

The Stage 10 experience provides a skip link, visible focus, keyboard issue traversal, programmatic labels/descriptions, textual severity, live local status, minimum 44px enabled targets, identifier wrapping, reduced-motion handling, increased contrast, forced-colors support, and responsive Score View priority.

These are repository/static guarantees, not cross-browser or assistive-technology certification.

## Security isolation

The page keeps `connect-src 'none'`, `form-action 'none'`, `object-src 'none'`, `frame-src 'none'`, and `base-uri 'none'`. Scripts and styles are repository-local only.

Local scripts are prohibited from network APIs, browser persistent storage, cookies, dynamic HTML injection, dynamic code evaluation, and browser navigation authority.

Browser state, fixture data, local intent, renderer output, and UI validation labels remain non-authoritative. Stage 8/9 security evidence remains authoritative.

## Next boundary

Stage 11 may design typed UI↔application contracts and local adapters. It does not inherit permission to activate networking, server writes, credentials, or production infrastructure. Any live integration requires a separate narrow security gate.
