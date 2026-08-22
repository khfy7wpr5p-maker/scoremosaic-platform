# Stage 10 — UI / Application Experience Prototype

## Current status — Stage 10-D

This directory contains the integrated ScoreMosaic product experience for Stage 10. It is repository-owned, dependency-free, disconnected, and non-production.

Current capabilities are deliberately local:

- checked-in deterministic fixture review;
- in-memory issue filtering and focus;
- synthetic source-evidence presentation;
- a bounded disconnected edit-intent draft.

There is still no network, upload, authentication/session runtime, durable browser state, no Teacher Review write, approval/publication execution, audio/MIDI playback, database/object-storage access, or production infrastructure.

## Regions

The shell integrates:

- application header and document/revision context;
- Issues panel;
- primary Score View;
- Source Evidence comparison panel;
- Structured Edit / local intent panel;
- Review Transport presentation area;
- Validation / revision status bar.

## Fixture boundary

`fixture.js` is repository-owned test/demo evidence only. It declares `productionArtifact=false` and `authoritativeTruth=false` and is deep-frozen before use.

Issue selection and filtering modify presentation state only in browser memory. Nothing is saved across reloads.

## Local edit-intent boundary

Stage 10-D reuses a closed subset of the existing Stage 8-H operation vocabulary:

```text
set_pitch
set_effective_duration
set_dots
remove_event
```

A prepared local intent contains a bounded fixture target and proposed operation, but explicitly carries no server authority. It cannot contain or create a server authorization, old-value precondition, command identity, ScoreEditCommand, TeacherScoreRevision, approval, or publication.

The intent is displayed only with `textContent`; it is not submitted, downloaded, copied to persistent storage, or sent over a network.

## Security isolation

The page keeps `connect-src 'none'`, `form-action 'none'`, `object-src 'none'`, `frame-src 'none'`, and `base-uri 'none'`. Scripts and styles are repository-local only.

Local scripts are prohibited from using network APIs, browser persistent storage, cookies, dynamic HTML injection, dynamic code evaluation, or navigation authority.

Stage 10 does not replace Stage 8/9 security evidence. Browser state, fixture data, local intent, and UI validation labels remain non-authoritative.

## Next slice

Stage 10-E hardens accessibility and responsive behavior. It may improve keyboard flow, live status semantics, high-contrast/forced-colors behavior, touch sizing, and mobile layout, but must preserve every disconnected security boundary above.
