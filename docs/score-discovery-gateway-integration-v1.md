# Score Discovery Gateway Integration v1

Current architecture state contract: `contracts/architecture-current-state-v1.json`

## Status

**Repository-only disconnected consumer baseline. Live Gateway networking and production import remain locked.**

This workstream does not consume or reserve Stage 12 numbering.

## Purpose

ScoreMosaic may discover classical scores through the independent ST Score Discovery Gateway without importing provider-specific code or granting discovery metadata any OMR, Canonical, Teacher Review, approval or publication authority.

The Gateway repository is `khfy7wpr5p-maker/st-score-discovery-gateway`. Its stable production runtime is separately verified, but ScoreMosaic live use remains subject to ScoreMosaic's own production/security activation gates.

## Safe Flow

```text
non-authoritative ScoreMosaic search intent
  -> bounded classical discovery request
  -> [server-configured Gateway origin; live networking currently locked]
  -> normalized Gateway response
  -> ScoreMosaic response sanitizer
  -> browser-safe discovery view
       +--> external-open / web / source locator -> source navigation only
       `--> import-request affordance only when server evidence says direct-import
                    |
                    v
          server-side discovery handoff
                    |
                    v
          existing ScoreMosaic Safe Intake
                    |
                    v
          OMR -> Candidate Safety -> Canonical/Ensemble
                    |
                    v
                Teacher Review
```

No discovery result can jump directly to OMR, Candidate Safety, Canonical, Teacher Review, approval or publication.

## Request Boundary

`tools/score-discovery-consumer-v1.cjs` builds a bounded provider-neutral request.

Rules:

- query is required and capped at 256 characters;
- `repertoireFamily` is forced to `classical`;
- result limit defaults to 25 and is capped at 50;
- only controlled format/instrument/ensemble/score-role/content-feature values are forwarded;
- arbitrary Gateway or provider origins supplied by a browser/input object are ignored;
- provider selection remains Gateway-owned.

## Response Boundary

Gateway data remains untrusted at the ScoreMosaic boundary.

Browser-facing sanitization:

- caps results at 50 and locators at 10;
- accepts only controlled result formats and handoff modes;
- accepts only HTTPS source URLs without embedded credentials;
- strips `assetUrl` from browser-facing results;
- drops unknown fields rather than forwarding provider payloads wholesale;
- treats Gateway work/version grouping as discovery metadata only;
- never emits Canonical, Teacher Review or approval authority fields.

`sourceLocators` must retain `availability: search-unverified`. A locator is a source-search destination, not proof that a requested score exists.

## Intake Handoff Boundary

A server-side intake handoff may be constructed only when all of the following are true:

1. `handoffMode === direct-import`;
2. `accessPolicy === public`;
3. format is `pdf`, `musicxml` or `mxl`;
4. `assetUrl` is valid HTTPS without credentials.

Even then, the handoff has only `authority: discovery-handoff-only`.

It does **not** mean the asset is safe, musically valid or teacher approved. The existing ScoreMosaic intake validation remains mandatory before any OMR or MusicXML processing.

The following can never enter intake through this contract:

- `external-open` results;
- `web` results;
- source locators;
- blocked results;
- entitlement/provider-auth/unknown-access resources;
- HTTP or malformed asset URLs.

## Authority Invariants

This workstream cannot:

- mutate Canonical Score;
- create TeacherScoreRevision;
- approve or publish;
- change the Stage 7 Audiveris/HOMR/Clarity candidate set or quorum;
- promote ST-OMR;
- bypass Candidate Safety;
- activate browser networking;
- activate production persistence or production import.

The independent ST-OMR draft track remains untouched and separately gated.

## Activation State

Repository code and tests prove the consumer boundary only. They do not register a public route and do not make a live Gateway request.

Before live activation, ScoreMosaic must separately satisfy its existing security and production gates, including server-side origin configuration, authenticated resource authorization where applicable, audit/observability, rollback/kill-switch behavior and operational validation.

## Verification

Contract: `contracts/score-discovery-consumer-v1.json`

Implementation: `tools/score-discovery-consumer-v1.cjs`

Tests: `tests/score-discovery-consumer-v1.test.cjs`

CI: `.github/workflows/score-discovery-consumer-v1-ci.yml`
