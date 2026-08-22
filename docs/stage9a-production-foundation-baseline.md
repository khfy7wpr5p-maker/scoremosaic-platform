# Stage 9-A — Production Foundation Baseline

## Status

**Repository-only production architecture baseline. No production resource, credential, route, provider write, public API, Teacher Review write API, or publication execution is activated by this stage.**

Stage 8-O remains the authoritative external side-effect boundary. Stage 9-A records concrete provider and architecture choices so later production slices do not invent infrastructure facts, while preserving every Stage 8-O runtime lock.

## Approved baseline

### 1. Hosting and deployment control

- provider: Hetzner;
- country: Germany;
- primary location: `nbg1` (Nuremberg);
- deployment control: Coolify;
- compute SKU is deliberately not selected yet;
- compute sizing must follow measured ST-OMR inference CPU/RAM/GPU behavior rather than an architectural guess.

### 2. Production database

- PostgreSQL major version 18;
- use a current supported PostgreSQL 18 minor release at deployment time;
- production database must run on a separate private host from OMR compute workloads;
- no direct public-Internet database exposure;
- backups must leave the database host and land in an independently controlled S3-compatible target;
- backup existence alone is insufficient: restore evidence is required before production activation.

### 3. Object and artifact storage

- Hetzner Object Storage;
- primary location `nbg1`;
- S3-compatible access;
- versioning required;
- published artifacts require immutability/Object Lock policy;
- secondary backup location `fsn1`;
- no native cross-location replication is assumed;
- a separately implemented and verified scheduled copy/backup process must create the secondary copy.

Object storage holds source documents, safe candidate artifacts, corrected MusicXML derivatives, published artifacts, and approved model artifacts where applicable. Database rows carry identity, lifecycle, authorization, hashes, and storage references rather than replacing object storage with large binary payloads.

### 4. Identity and authentication

- Authentik self-hosted is the target identity provider;
- OIDC is the application authentication protocol boundary;
- OAuth2 interoperability is permitted;
- MFA and passkey/WebAuthn support are expected capabilities;
- Authentik proves identity but does not own ScoreMosaic musical/resource authorization;
- tenant, score, review, approval, and publication authorization remains a deny-by-default ScoreMosaic responsibility.

An authenticated identity must never be reinterpreted as permission to edit, approve, publish, or access another tenant/resource.

### 5. Secrets and credentials

- Infisical self-hosted is the target centralized secret manager;
- Coolify may retain only the minimum bootstrap secrets needed to reach the secret-management boundary;
- DEV, STAGING, and PRODUCTION secret domains must remain separated;
- no paid Infisical capability is assumed merely because the product is selected;
- licensing and actual required capabilities must be verified before production activation;
- secrets, credentials, tokens, private keys, HMAC material, database passwords, and S3 credentials must never be committed to the repository.

If required least-privilege, audit, rotation, machine-identity, or recovery capabilities cannot be proved for the selected Infisical deployment/license, production secret activation stops and the secret-manager choice must be revisited rather than silently weakened.

### 6. Publication destination

The first production publication destination is ScoreMosaic itself.

- publication record: PostgreSQL;
- immutable published MusicXML artifact: Hetzner Object Storage;
- default visibility: `private`;
- `PUBLISHED` does not mean `PUBLIC`;
- approval and publication permissions remain separate;
- publication must bind the exact approved revision, exact MusicXML SHA-256, exact publisher identity, immutable artifact identity, timestamp, and audit lineage;
- later public visibility or external-platform export is a separate explicitly authorized transition.

## Stage 8-O compatibility

Stage 9-A must not weaken the existing Stage 8-O request semantics. The existing handoff continues to require an external execution step and continues to expose:

```text
canExecutePublication=false
canWriteExternal=false
canPersistProduction=false
publicationGranted=false
authoritativeMusicalTruth=false
```

Stage 9-A only answers **which production architecture is intended**. It does not create the provider resources or authorize the effect.

## Runtime activation locks

The following remain false after Stage 9-A:

```text
providerResourcesCreatedByThisBaseline=false
productionCredentialsProvisioned=false
productionNetworkActivated=false
productionDatabaseActivated=false
productionObjectStorageWritesActivated=false
productionIdentityRuntimeActivated=false
productionSecretsRuntimeActivated=false
publicApiActivated=false
teacherReviewWriteApiActivated=false
publicationExecutionActivated=false
externalWriteActivated=false
productionDeploymentAuthorizedByThisBaselineAlone=false
```

## Required gates before later production slices

Before any later Stage 9 runtime slice may activate one real provider capability, that exact slice must provide fresh evidence for the relevant subset of:

1. current provider capability/pricing/region verification;
2. concrete provider resource identities and private-network topology;
3. credential bootstrap, storage, rotation, revocation, and recovery semantics;
4. least-privilege service identity and resource/RBAC mapping;
5. PostgreSQL backup and tested restore behavior;
6. object-storage versioning/Object Lock and independent `nbg1 -> fsn1` copy evidence;
7. Infisical licensing and required-capability verification;
8. monitoring, incident response, and rollback for the activated surface;
9. hostile/negative security tests and regression tests;
10. exact-head CI and clean diff;
11. an explicit activation scope limited to that provider/runtime slice.

A passing architecture baseline is not permission to create infrastructure, provision credentials, expose public routes, or publish an artifact.

## Safe next slice

After Stage 9-A merges, the next safe repository-only work is to define the **provider-neutral production resource identity and network-topology contract** for the selected Hetzner/Coolify architecture. That contract may describe exact resource roles, trust zones, private/public boundaries, and required evidence, but must still create no real Hetzner resources and contain no credentials.
