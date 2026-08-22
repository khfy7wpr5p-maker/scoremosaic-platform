# Stage 8-H Disconnected Edit Intent Composer

This repository-owned browser prototype extends the Teacher Review evaluation path without activating a write surface.

It consumes only one embedded, already-bounded `scoremosaic-teacher-review-projection-v1` payload. The projection must remain explicitly read-only: `canEdit=false`, `canApprove=false`, `canPublish=false`, and `authoritativeTruth=false`.

The prototype can prepare one local `scoremosaic-teacher-review-browser-edit-intent-v1` draft for a selected event that is present in the exact snapshot. The draft contains only:

- exact projection and snapshot identity;
- Stage 7 difference evidence identity;
- part/measure/event focus identifiers;
- one typed operation from the existing Stage 8 operation vocabulary;
- an optional bounded reviewer note;
- explicit false authority markers.

It deliberately cannot create or claim:

- a `ScoreEditCommand`;
- authorization decision or grant;
- `oldValueSha256`;
- staff/voice/onset current-location proof;
- command SHA-256 or command ID;
- idempotency reservation;
- `TeacherScoreRevision`;
- corrected MusicXML;
- approval or publication authority.

The CSP keeps `connect-src 'none'` and `form-action 'none'`. The script uses no fetch/XHR/WebSocket, cookies, browser storage, navigation, dynamic code evaluation, `innerHTML`, or external assets. Prepared intent JSON is rendered only with `textContent`.

An absent target event disables local intent preparation. This prevents the browser from pretending that stale comparison evidence is a current editable event.

The intent is a UX/accessibility artifact, not a transport capability. Any future live edit must be re-resolved against server-trusted current state and independently pass Stage 8-G under the live Gate E authentication/authorization/idempotency/privacy boundary.
