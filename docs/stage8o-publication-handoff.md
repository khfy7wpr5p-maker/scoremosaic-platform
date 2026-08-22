# Stage 8-O — Publication Handoff Foundation

## Status

Final repository-only, non-executing handoff before an external production publication effect. No artifact is uploaded, persisted to production, published, or exposed through a live route.

## Purpose

Stage 8-O converts one exact, freshly revalidated Stage 8-N evidence object into an immutable request that may be presented to one exact publisher identity.

This is **not publication authorization for an external write**. The purpose-separated grant authorizes only the action:

```text
present_for_publication_execution
```

## Trust chain

```text
exact current durable revision/state/artifact
  -> exact Stage 8-L human handoff
  -> exact Stage 8-M explicit-human approval record
  -> fresh Stage 8-N publication eligibility evidence
  -> purpose-separated Stage 8-O handoff grant
  -> exact publisher + revision + artifact + approval + eligibility binding
  -> immutable PublicationHandoffRequest
  -> status=awaiting_external_publication_execution
  -> canPresentForPublicationExecution=true
  -> canExecutePublication=false
  -> [EXTERNAL SIDE-EFFECT BOUNDARY]
  -> [LOCKED] production storage/write
  -> [LOCKED] actual publication execution
  -> [LOCKED] published artifact record
```

## Exact binding

The Stage 8-O HMAC grant binds one exact:

- request ID;
- publisher identity;
- tenant/job/report/base Canonical identity;
- current revision ID/SHA-256;
- corrected artifact ID/record SHA-256/MusicXML SHA-256;
- immutable human approval record ID/SHA-256;
- Stage 8-N publication-eligibility evidence SHA-256.

A different publisher, key, revision, artifact, approval record, or eligibility object fails closed.

## Fresh revalidation

The public request builder never trusts a caller-supplied statement that an artifact is publishable. It recomputes Stage 8-N from the exact current chain. As a result, stale or substituted upstream evidence fails before the Stage 8-O grant can create a request.

## Capabilities

The request fixes:

```text
canPresentForPublicationExecution=true
canExecutePublication=false
canWriteExternal=false
canPersistProduction=false
canMutate=false
publicationGranted=false
authoritativeMusicalTruth=false
```

Its state contains no publication record or published artifact ID.

## Activation locks

`publication-handoff-foundation-enabled=true` means only the non-executing contract exists. These remain locked:

```text
publication-enabled=false
write-api-enabled=false
public-api-enabled=false
production-durable-store-enabled=false
```

No provider SDK, network transport, database/object-store writer, public endpoint, queue worker, or publisher runtime is introduced.

## Autonomous stop condition

After Stage 8-O passes and merges, the safe repository-only Teacher Review/publication preparation path has reached the external side-effect boundary.

The next action would have to actually persist or publish the exact approved MusicXML to a production destination. That requires a concrete production identity/RBAC/provider/target plus explicit execution authority and must not be inferred from the repository handoff contract.
