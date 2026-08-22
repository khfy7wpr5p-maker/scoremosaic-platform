# Stage 9-I — Production Foundation Eligibility and External Provisioning Boundary

## Status

**Stage 9 repository preparation is complete, but production runtime eligibility remains false. No provider resource, credential, network, database, object-storage runtime, identity runtime, secret-manager runtime, public API, Teacher Review write API, publication execution, public visibility, or production traffic is activated by this stage.**

Stage 9-I aggregates Stage 9-A through 9-H and establishes the next deliberate stop boundary: real external infrastructure provisioning.

## What is complete

The repository now contains security-first production contracts for:

- Hetzner Germany/NBG1 + Coolify baseline;
- production trust zones and maximum planned connectivity;
- purpose-separated machine identities and secret scopes;
- PostgreSQL 18 durability, backup, restore, and migration requirements;
- Hetzner Object Storage immutability and independent NBG1-to-FSN1 copy semantics;
- Authentik OIDC identity mapping and deny-by-default ScoreMosaic RBAC;
- Infisical live capability/license eligibility requirements;
- crash-safe internal publication persistence semantics.

This is sufficient to hand the design to an external provisioning phase without inventing provider facts.

## What is not complete

`productionRuntimeEligible=false`, `publicTrafficEligible=false`, and `publicationExecutionEligible=false` remain authoritative.

Real provider evidence is still required, including concrete Hetzner project/resource identities, compute sizing after ST-OMR inference benchmarking, production database/backup/restore evidence, object-storage immutability/copy evidence, Authentik configuration, Infisical license/capability proof, real machine identities/secrets, monitoring/rollback, and exact provider-adapter integration tests.

Before public traffic, later hardening must also cover repository-owned vulnerability/dependency/secret scanning, base-image digest pinning, SBOM/provenance policy, privacy-safe production logging/errors, and load/failure-recovery validation.

## Why autonomous repository-only development stops here

The next meaningful step is not another abstract contract. It creates or configures real external infrastructure and may incur cost, establish privileged credentials, change DNS/TLS, or create persistent production state.

Those facts cannot be safely invented by the repository.

The Stage 9 stop boundary is therefore:

```text
Stage 9-A ... Stage 9-I
        ✅ repository preparation
                |
                v
EXTERNAL PRODUCTION PROVISIONING BOUNDARY
                |
                +-- Hetzner project/resources
                +-- actual private network/firewalls
                +-- actual PostgreSQL
                +-- actual Object Storage
                +-- Authentik runtime
                +-- Infisical runtime/license
                +-- real credentials
                +-- DNS/TLS when public traffic is intended
```

## Human/external inputs required

The next phase requires concrete authority/facts for at least:

1. Hetzner account/project and resource-purchase authority;
2. the compute SKU after ST-OMR inference benchmark evidence;
3. production domain choice before public traffic;
4. Infisical deployment/license capability decision;
5. real credential/bootstrap creation.

These inputs are operational facts, not architecture guesses.

## Preserved locks

```text
providerResourcesCreated=false
productionCredentialsProvisioned=false
productionNetworkActivated=false
productionDatabaseActivated=false
productionObjectStorageActivated=false
productionIdentityActivated=false
productionSecretsActivated=false
publicApiActivated=false
teacherReviewWriteApiActivated=false
publicationExecutionActivated=false
publicVisibilityActivated=false
realProductionTrafficAccepted=false
```

## Next phase

Once the concrete external inputs are supplied, development can resume in small provider-backed slices. Each slice must fresh-read provider state, use least privilege, produce negative tests and runtime evidence, preserve rollback, and activate only the exact capability under review.
