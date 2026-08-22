# Stage 10-A — UI / Application Experience Contract

## Status

**Repository-only UI experience scope. Production infrastructure remains deferred and every live runtime side effect remains locked.**

Stage 10 builds the ScoreMosaic product interface as a deterministic local prototype using only repository-owned HTML, CSS, JavaScript and checked-in fixtures. It deliberately stops before the Stage 11 UI↔application/API integration boundary.

## Inputs

Stage 10 consumes the existing UI-0A visual foundation, UI-0B static shell, Stage 8-E read-only review workspace, Stage 8-H disconnected edit-intent prototype, and Stage 9-I production-foundation stop boundary.

It must not reinterpret any browser state, fixture, renderer output, validation presentation, or local draft as musical authority.

## Stage 10 slices

```text
10-A  UI/application experience contract
10-B  integrated product shell
10-C  deterministic fixture-driven read-only review
10-D  disconnected bounded edit-intent UX
10-E  accessibility + responsive hardening
10-F  exit/eligibility report
```

Each slice is independently reviewed and CI-gated.

## Allowed behavior

Stage 10 may provide:

- a polished repository-owned application shell;
- checked-in deterministic review fixtures;
- in-memory presentation state only;
- keyboard-accessible filtering and issue focus;
- read-only score/evidence/revision presentation;
- a disconnected bounded edit-intent draft consistent with Stage 8-H;
- validation/status presentation;
- disabled future upload/auth/approve/publish/playback affordances where useful for layout testing.

## Explicitly forbidden behavior

Stage 10 does not:

- make network requests or add an HTTP client;
- upload files or read production artifacts;
- connect to PostgreSQL, Object Storage, Authentik, Infisical, OMR engines, or any service;
- create authentication/session/RBAC runtime;
- create ScoreEditCommand, TeacherScoreRevision, approval, publication, or durable state;
- activate audio/MIDI/playback;
- use localStorage, sessionStorage, IndexedDB, cookies, or service workers;
- add external fonts, scripts, images, analytics, CDNs, or other remote assets;
- use dynamic code evaluation or HTML injection APIs;
- expose unrestricted raw MusicXML editing.

## Browser isolation

Every Stage 10 prototype must preserve a restrictive CSP with the effective intent:

```text
default-src 'none'
style-src 'self'
script-src 'self'
img-src 'self' data:
connect-src 'none'
object-src 'none'
frame-src 'none'
base-uri 'none'
form-action 'none'
```

Local scripts must not use `fetch`, XHR, WebSocket, EventSource, browser persistence APIs, cookies, `innerHTML`, `insertAdjacentHTML`, `eval`, or the Function constructor.

## Authority rules

These implications are always false:

```text
fixture data == production truth
renderer output == musical truth
browser selection == server authorization
local edit intent == ScoreEditCommand
validation pass == human approval
published label == public visibility
```

The Stage 8 and Stage 9 security chains remain authoritative.

## Accessibility baseline

Stage 10 requires keyboard reachability, visible focus, programmatic labels, textual status meaning, no color-only error semantics, reduced-motion safety, and responsive preservation of Score View as the primary workspace.

## Production deferral

Stage 9 provisioning remains intentionally deferred. Stage 10 therefore does not need real Hetzner, PostgreSQL, S3, Authentik, Infisical, DNS, TLS, or credentials.

This is a design advantage: the product experience can mature while infrastructure choices remain frozen behind Stage 9-I.

## Exit boundary

Stage 10 is complete only when 10-A through 10-F merge and the final eligibility report proves:

- the product shell and local review experience are coherent;
- all fixture and interaction behavior is deterministic and local;
- accessibility/responsive requirements are covered;
- no network, persistence, auth, upload, write, approval, publication, playback, or production infrastructure was activated;
- Stage 11 remains the first place where a real UI↔application boundary may be designed.
