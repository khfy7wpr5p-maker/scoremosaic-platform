# Stage 9-B — Production Resource Identity and Network Topology Contract

## Status

**Repository-only topology contract. No Hetzner network, VM, firewall, DNS record, TLS certificate, database listener, Authentik service, Infisical service, object-storage writer, OMR production runtime, public API, or publication execution is created or activated.**

Stage 9-B consumes the approved Stage 9-A production baseline and defines logical resource roles, trust zones, and fail-closed network expectations before any real provider resource exists.

## Purpose

The goal is to prevent later production work from inventing connectivity or authority ad hoc. A service being on a private network is never enough to authenticate it, and a user being authenticated is never enough to authorize a score operation.

## Trust zones

```text
Internet
  |
  v
PUBLIC EDGE
  - ScoreMosaic HTTPS ingress only
  |
  +----> IDENTITY CONTROLLED
  |       - Authentik user login surface
  |       - admin surface restricted
  |
  v
APPLICATION PRIVATE
  - application/API
  - publication service
  |
  +----> DATA PRIVATE
  |       - PostgreSQL 18
  |
  +----> SECURITY PRIVATE
  |       - Infisical
  |       - Coolify control plane
  |
  +----> COMPUTE PRIVATE
  |       - OMR workers / future ST-OMR production runtime
  |
  +----> PROVIDER OBJECT STORAGE
          - NBG1 primary
          - FSN1 independent backup target
```

## Public edge

Only the ScoreMosaic edge may be a normal user-facing application ingress. The intended public protocol is HTTPS on port 443.

The browser must never receive:

- PostgreSQL credentials;
- S3 access/secret keys;
- Infisical machine credentials;
- internal service HMAC material;
- OMR dispatch credentials;
- provider API credentials.

The browser must never connect directly to PostgreSQL, Infisical, or OMR workers.

## Identity boundary

Authentik may expose the user-login flow through the controlled edge. Its administrative surface is not a normal public application endpoint and must be separately restricted.

Authentik proves identity. ScoreMosaic remains responsible for tenant/resource authorization, including read, edit, review, approve, and publish permissions.

## Database boundary

PostgreSQL remains in the data-private zone:

- no direct public ingress;
- separate host from OMR compute;
- application access only through a least-privilege database identity;
- production listener activation requires a later explicit runtime slice;
- backup and restore evidence remains mandatory before production promotion.

## Secrets boundary

Infisical remains in the security-private zone. Application services may receive only the secret scope required for their role. No browser-facing secret-manager access is allowed.

Coolify is a management/control-plane service, not part of the public application data plane. Administrative access must be restricted and must not be treated as user application ingress.

## OMR compute boundary

OMR compute remains private and may not expose a public listener. This applies to legacy HOMR/Clarity/Audiveris during any transition and to future ST-OMR production compute.

The selected compute SKU remains deferred until ST-OMR inference benchmarking supplies measured CPU/RAM/GPU evidence.

Private networking never replaces the existing purpose-separated service authentication requirements. Dispatch and result-return flows must remain authenticated and identity-bound.

## Object storage boundary

Hetzner Object Storage is reached through authenticated TLS/S3 requests. Buckets are private by default.

Primary artifacts reside in NBG1. The FSN1 copy is an independently executed backup/copy path; Stage 9-B does not assume native location replication.

Published artifacts require the later persistence layer to prove versioning/immutability/Object Lock behavior before publication execution can be activated.

## Planned connectivity, not active connectivity

The machine-readable contract lists planned edges such as:

```text
Internet -> ScoreMosaic edge
ScoreMosaic edge -> application
ScoreMosaic edge -> Authentik user login
application -> PostgreSQL
application -> Authentik OIDC
application -> Infisical
application -> NBG1 object storage
gateway -> OMR compute
OMR compute -> gateway result return
backup worker -> NBG1 read -> FSN1 write
```

These strings describe the maximum intended topology. They do **not** authorize creating firewall rules or making the connections live.

## Fail-closed rules

The following invariants are mandatory:

```text
defaultDenyBetweenTrustZones=true
privateNetworkAloneCountsAsAuthentication=false
browserMayReachDatabaseDirectly=false
browserMayReachSecretsManagerDirectly=false
browserMayReachOmrComputeDirectly=false
browserMayReceiveProviderCredentials=false
databaseMayExposePublicListener=false
omrComputeMayExposePublicListener=false
objectStorageBucketsPublicByDefault=false
serviceToServiceAuthenticationRequired=true
```

## Runtime locks

Stage 9-B keeps all real provider side effects false:

```text
networkCreated=false
firewallRulesApplied=false
dnsCreated=false
tlsCertificatesProvisioned=false
providerResourcesCreated=false
credentialsProvisioned=false
databaseListenerActivated=false
objectStorageWriteActivated=false
authentikRuntimeActivated=false
infisicalRuntimeActivated=false
omrProductionRuntimeActivated=false
publicApiActivated=false
publicationExecutionActivated=false
```

## Safe next slice

After Stage 9-B merges, the next repository-only safe slice is the **credential/bootstrap and service-identity contract**. It may define which logical service identity can obtain which class of secret and how rotation/revocation must work, but it must contain no real credential material and must not provision any production secret.
