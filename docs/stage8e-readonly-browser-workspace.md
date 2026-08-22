# Stage 8-E — Read-Only Browser Workspace Gate

## Purpose

Stage 8-E proves that the merged Stage 8-D Teacher Review projection can be consumed by a browser workspace without converting browser state into musical authority and without activating Teacher Review writes, approval, publication or playback.

## Upstream authority

The browser adapter is subordinate to the Stage 8-D projection contract. It does not re-create Stage 7 comparison logic, authorization, revision validation or Canonical materialization in the browser.

The accepted browser payload remains exactly:

`scoremosaic-teacher-review-projection-v1`

with capabilities fixed to:

- `readOnly=true`;
- `canEdit=false`;
- `canApprove=false`;
- `canPublish=false`;
- `authoritativeTruth=false`.

Any capability expansion or structural deviation fails closed.

## Browser isolation

Stage 8-E intentionally has no HTTP client or Teacher Review route. The proof uses one embedded repository-owned projection fixture and a dependency-free local adapter.

The Content Security Policy keeps:

- `connect-src 'none'`;
- `object-src 'none'`;
- `frame-src 'none'`;
- `base-uri 'none'`;
- `form-action 'none'`.

Only local styles and the local read-only adapter script are executable resources.

The adapter does not use fetch/XHR/WebSocket/EventSource, browser storage, cookies, navigation, forms, HTML injection sinks or dynamic code execution.

## Deterministic issue focus

The adapter preserves the Stage 8-D difference order and selects the first difference deterministically. Arrow Up, Arrow Down, Home and End move only the selected browser issue. The selection updates textual exact-snapshot focus and read-only candidate observations.

Focus does not mutate Canonical state or a TeacherScoreRevision. When a referenced event is absent from an exact revision snapshot, the UI presents the absence explicitly and keeps the immutable comparison evidence visible.

## Accessibility

The proof includes:

- semantic Issues, Score View, Structured Edit, Source Evidence, Review Transport and Validation regions;
- a listbox/option relationship for issue focus;
- roving keyboard focus;
- visible selected/focus state;
- `aria-live` review status and evidence updates;
- textual presence/absence semantics instead of color-only meaning;
- disabled mutation, approval, publication and playback controls.

## Non-authority boundaries

Stage 8-E does **not**:

- expose a public or internal Teacher Review HTTP route;
- accept browser-supplied authorization or revision writes;
- generate or submit ScoreEditCommand objects;
- create TeacherScoreRevision records;
- generate corrected MusicXML;
- activate a notation renderer as musical authority;
- activate audio, MIDI, cursor or playback authority;
- approve or publish any revision;
- enable a production durable revision store.

## Exit evidence

Stage 8-E can merge only when exact-head CI demonstrates:

- all Stage 8-A/B/C/D suites remain green;
- UI-0B static-shell isolation remains green;
- Stage 8-E projection checksum and read-only capability locks pass;
- CSP/network/storage/DOM-injection checks pass;
- keyboard/accessibility contract checks pass;
- mutation/approval/publication/playback controls remain disabled;
- repository diff formatting passes;
- no unresolved review thread or incompatible `main` drift exists.

After Stage 8-E, corrected MusicXML remains a separate deterministic derivative and round-trip safety gate. Browser mutation remains locked until that derivative path and its protecting write-transport contract are independently proved.
