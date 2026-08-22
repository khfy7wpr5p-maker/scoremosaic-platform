# Stage 8-E — Read-Only Teacher Review Browser Workspace

## Status

Non-production browser-adapter proof over the merged Stage 8-D projection contract.

This prototype binds the existing UI-0B visual shell to one already-authorized `scoremosaic-teacher-review-projection-v1` payload without adding a Teacher Review HTTP route or any browser write authority.

## Security boundary

The workspace:

- consumes only the bounded Stage 8-D projection shape;
- requires capabilities to remain exactly read-only, non-editable, non-approvable, non-publishable and non-authoritative;
- rejects unknown top-level, scope, snapshot, page, capability, difference, focus or observation fields;
- uses a restrictive CSP with `connect-src 'none'` and local scripts/styles only;
- performs no network, storage, cookie, navigation or form operation;
- writes projection-originated content only through `textContent`;
- never uses HTML injection sinks such as `innerHTML`;
- keeps edit, approval, publication and playback controls disabled;
- does not create `ScoreEditCommand`, `TeacherScoreRevision`, corrected MusicXML or publication state.

## Deterministic focus behavior

The first projected difference is selected deterministically. Native buttons provide pointer access and the Issues list supports Arrow Up, Arrow Down, Home and End navigation. Selection changes only browser focus and the displayed read-only observation evidence.

If the exact revision snapshot no longer contains the referenced event, the evidence remains visible and the UI states that the event is absent rather than inventing or repairing a location.

## Fixture

`index.html` embeds one repository-owned projection fixture. CI recomputes its `projectionSha256` from canonical JSON and verifies that the fixture contains no server-only source-artifact, credential or action fields.

The fixture is evidence for the browser adapter only. It is not production data and it does not establish a public or internal HTTP endpoint.

## Viewing

Open `index.html` directly in a browser. The only executable script is the local dependency-free `adapter.js`; the CSP prevents network connections.

## Verification

`tests/test_stage8e_readonly_browser_workspace.py` checks the projection hash and capability lock, CSP/network isolation, server-only field stripping, disabled mutation/playback controls, safe DOM sinks, fail-closed capability checks and keyboard focus contract.

UI-0B remains untouched and continues to prove the fully disconnected no-script shell baseline.
