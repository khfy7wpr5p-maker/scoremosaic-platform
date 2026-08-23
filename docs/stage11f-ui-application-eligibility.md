# Stage 11-F — UI ↔ Application Exit Eligibility

## Status

**Stage 11 repository-only typed UI↔application scope is complete. Live API integration and every production side effect remain locked.**

Stage 11-F aggregates Stage 11-A through 11-E and closes the local contract-integration phase without granting production authority.

## Completed repository scope

```text
Stage 11-A  ✅ fail-closed UI/application boundary
Stage 11-B  ✅ typed read contracts + local read adapter
Stage 11-C  ✅ typed edit-intent contract + local intent adapter
Stage 11-D  ✅ application state + error/correlation model
Stage 11-E  ✅ Stage 10 UI integrated through typed local application
Stage 11-F  ✅ exit eligibility
```

The Stage 10 product UI now consumes repository-local typed application contracts rather than treating checked-in fixture data as an application API.

## What is ready

Repository evidence now exists for:

- closed request vocabulary;
- typed read request/response models;
- typed bounded edit-intent request/response models;
- exact local document/revision/issue/target binding;
- fail-closed response correlation;
- deterministic local adapters;
- disconnected UI↔application integration;
- non-authoritative loading/ready/empty/rejected/unavailable states;
- regression preservation of Stage 8-H, Stage 9-I and Stage 10 boundaries.

This is enough to design a later live-integration security gate without changing the UI contract model.

## What is not eligible

```text
liveApiIntegrationEligible=false
productionFrontendEligible=false
realUploadEligible=false
authRuntimeEligible=false
sessionRuntimeEligible=false
rbacRuntimeEligible=false
productionArtifactReadEligible=false
teacherReviewServerWriteEligible=false
scoreEditCommandCreationEligible=false
teacherScoreRevisionCreationEligible=false
approvalExecutionEligible=false
publicationExecutionEligible=false
playbackEligible=false
productionInfrastructureEligible=false
```

## Authority preservation

These implications remain invalid:

```text
browser == authority
fixture == production truth
local application == production server
local adapter == authenticated API
local edit intent == ScoreEditCommand
UI validation == authoritative musical validation
ready state == approval
published label == public publication
```

No Stage 11 component may manufacture server authorization, old-value preconditions, command identity, revision identity, approval authority or publication authority.

## Preserved browser isolation

The Stage 10 UI still uses a fail-closed CSP including `connect-src 'none'`. Stage 11 adds only repository-local scripts. There is no network fallback, browser persistence, credential use, production artifact access, service worker, dynamic HTML/code execution, or external resource dependency.

## Later live-integration security boundary

A future live integration requires a separate narrow security gate that defines and proves at minimum:

- authenticated principal/session semantics;
- tenant and resource authorization;
- exact API transport and endpoint scope;
- origin, CSRF and production CSP policy;
- failure/retry/idempotency behavior;
- audit evidence;
- rollback/disable boundary;
- production credential handling;
- exact server-side authorization and mutation chain.

Stage 11 grants no permission to activate any of those items.

## Stage 9 remains deferred

Real Hetzner provisioning, PostgreSQL, Object Storage, Authentik, Infisical, DNS/TLS, public traffic, production credentials and actual publication execution remain deferred behind the existing Stage 9 boundary.

## Result

```text
Repository UI↔Application contracts complete ✅
Disconnected local integration complete ✅
Ready for later live-integration security design ✅
Live API / production activation ❌
Stage 9 provisioning ❌ deferred
```
