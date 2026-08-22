# Stage 8-H — Disconnected Structured Edit Intent Composer

## Purpose

Stage 8-H evaluates the structured teacher-correction UX without crossing Gate E or granting browser write authority.

The browser remains a presentation/input adapter. It may express one typed proposed musical change, but it cannot decide that the change is authorized, current, valid, accepted, persisted, approved, or publishable.

## Trust boundary

```text
Stage 8-D read-only projection
  -> fail-closed browser projection validation
  -> selected present event focus
  -> bounded typed local operation fields
  -> non-authoritative BrowserEditIntent
  -> local text preview only
  -> [LOCKED] live Gate E transport
  -> [LOCKED] server-side current-state resolution
  -> [LOCKED] Stage 8-G authorized write boundary
```

Stage 8-H does not transform the projection's `canEdit=false` into server authority. The phrase “edit intent” means a local UX draft only.

## Browser intent contract

`contracts/teacher-review-browser-edit-intent-v1.schema.json` is closed. It binds:

- exact `projectionSha256`;
- exact base/revision snapshot identity and state SHA-256;
- exact Stage 7 `differenceId` as evidence context, not a Stage 8 edit-issue authority;
- part/measure/event focus identifiers;
- one typed operation reusing the existing ScoreEditCommand operation schema;
- optional reviewer note bounded to 500 characters;
- explicit authority markers fixed to false.

The intent intentionally omits:

- tenant/job/reviewer/report authority fields;
- authorization decision/grant/signature;
- Stage 8 `issueId`;
- staff/voice/onset current-state location proof;
- `oldValueSha256`;
- command ID/SHA;
- idempotency slot/receipt;
- revision identity;
- corrected artifact identity.

Those values must come only from future server-side resolution and security gates. A browser intent can never be passed directly to `submit_score_edit_request` as a `ScoreEditCommand`.

## Typed operation UX

The prototype exposes only the existing allowlisted operation vocabulary:

- `set_pitch`;
- `set_effective_duration`;
- `set_written_type`;
- `set_dots`;
- `set_staff_voice`;
- `set_time_signature`;
- `set_tab`;
- `remove_event`.

Inputs are bounded more tightly where practical. No raw XML, JSON Patch, arbitrary object path, script/expression, renderer-native mutation object, or free-form operation name exists.

Operation choice is still a proposal. Server-side Stage 8-C remains the musical value/location validator.

## Stale/absent evidence behavior

If the selected projection difference points to an event that is absent from the exact snapshot, Stage 8-H disables intent preparation. Comparison evidence remains visible.

This is intentionally conservative. The browser does not invent a replacement event, search for a “nearby” target, or silently retarget stale evidence.

## Isolation

The prototype keeps:

- `connect-src 'none'`;
- `form-action 'none'`;
- no network APIs;
- no cookies/localStorage/sessionStorage/IndexedDB;
- no navigation writes;
- no dynamic code evaluation;
- no `innerHTML` or HTML string injection;
- local repository CSS/JS only.

User and projection content reaches the preview through `textContent`.

## Accessibility

Stage 8-H preserves:

- keyboard issue navigation with Arrow Up/Down, Home and End;
- programmatic selected state;
- labelled typed controls;
- visible status for local-draft versus blocked targets;
- readable text preview of the exact draft intent;
- disabled controls that clearly distinguish local preparation from submit/approve/publish authority;
- no color-only indication requirement.

## Activation effect

None.

Stage 8-H adds no runtime service flag, route, dependency, credential, production persistence, network request, revision append, corrected MusicXML generation, playback, approval, or publication.

## Exit gate

Stage 8-H may merge only when exact-head CI proves:

1. Stage 8-E read-only browser behavior remains unchanged;
2. Stage 8-G server boundary regressions remain green;
3. Browser projection capability expansion still fails closed;
4. absent events cannot produce an intent;
5. only the allowlisted typed operation vocabulary appears;
6. generated intent authority markers are all false;
7. submit/approve/publish controls remain disabled;
8. CSP blocks network/form submission;
9. no browser storage/network/dynamic HTML sink is introduced;
10. intent schema is closed and foundation-validator compatible;
11. original UI-0B and Stage 8-E prototypes remain untouched.
