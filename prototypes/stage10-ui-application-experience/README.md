# Stage 10 — UI / Application Experience Prototype

## Stage 10-B status

This directory contains the integrated ScoreMosaic product shell for Stage 10. It is repository-owned, dependency-free, and non-production.

Stage 10-B is presentation-only. It has no JavaScript, no fixtures, no network, no upload, no authentication, no durable state, no Teacher Review write, no approval/publication, and no playback.

## Regions

The shell integrates the established ScoreMosaic review workspace into one coherent application experience:

- application header and document/revision context;
- Issues panel;
- primary Score View;
- Source Evidence comparison panel;
- Structured Edit panel;
- Review Transport presentation area;
- Validation / revision status bar.

## Security isolation

The page uses a fail-closed Content Security Policy with scripts and network connections disabled. All future-action controls are visibly disabled and textual status labels make the disconnected state explicit.

Stage 10-B does not replace UI-0B or the Stage 8 prototypes as security evidence. It is the new integrated Stage 10 experience surface, still subordinate to the Stage 8/9 authority model.

## Next slice

Stage 10-C may add deterministic checked-in fixture data and local read-only interactions. It must keep `connect-src 'none'`, avoid browser persistence, and must not create runtime authority.
