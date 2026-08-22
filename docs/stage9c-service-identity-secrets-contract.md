# Stage 9-C — Service Identity, Bootstrap, Rotation and Secret-Scope Contract

## Status

**Repository-only credential policy. No real service identity, secret, token, key, password, OIDC client secret, S3 credential, database credential, Infisical runtime, Coolify production bootstrap, rotation job, or revocation action is created by this stage.**

Stage 9-C consumes the Stage 9-A production baseline and Stage 9-B trust-zone topology. It defines which logical service may receive which class of secret before any production credential exists.

## Core rule

Every production service receives a separate machine identity and the smallest purpose-specific secret scope needed for its role.

The following are forbidden:

- one shared production machine identity;
- wildcard secret access;
- cross-environment secret access;
- browser-visible machine/provider credentials;
- database-admin credentials in ordinary application services;
- using possession of a secret as proof of tenant, review, approval, or publication authority;
- storing production secret values in the repository.

## Environment isolation

Development, staging, and production are separate credential domains.

```text
DEV      != STAGING      != PRODUCTION
```

A credential from one environment must not authenticate or authorize access in another. Production secrets must not be injected into CI or developer machines merely for convenience.

## Service scopes

### ScoreMosaic application

May receive only application-scoped database access, its Authentik OIDC client material, application object-storage access, and application-specific signing material.

It must not receive database-admin, provider-account-admin, all-engine OMR dispatch, published-object deletion, or Infisical root credentials.

### Gateway orchestrator

Receives purpose-separated engine-dispatch and result-verification credentials plus source-artifact read access. It must not receive publication authority or database/provider administration.

### OMR compute

Receives an engine-specific receiver identity and an engine-specific result-return identity. One engine identity must not authenticate as another engine. OMR compute receives no database administration, publication, provider administration, or general application database credentials.

### Publication service

Receives a publication-specific database role, published-object write capability, and publication-specific signing material. It must not receive source-object deletion, OMR dispatch authority, database admin, or provider administration.

Publication credentials remain insufficient by themselves to publish: the ScoreMosaic authorization and Stage 8 approval/publication lineage must also pass.

### Backup worker

Receives only the database backup role, primary-object read, and secondary-backup-object write scope. It must not receive publication signing, user-auth administration, source deletion, database admin, or provider administration.

### Authentik

Receives its own database role and identity-service bootstrap/encryption material. Authentik must not receive ScoreMosaic musical/resource authorization or publication signing authority.

### Infisical

Infisical holds centralized application secret material after a later activation gate. Its own self-host bootstrap does not grant access to ScoreMosaic user data or musical authority.

### Coolify control plane

Coolify may hold only the minimum bootstrap reference needed to reach the centralized secret-management boundary. It must not become the general production application secret store.

## Bootstrap boundary

A small bootstrap secret may be operationally unavoidable. That does not justify duplicating the full production secret set into Coolify.

Bootstrap material must be:

- minimal;
- purpose-bound;
- rotatable;
- recoverable;
- isolated from application/user data;
- absent from repository source, test fixtures, logs, browser responses, and build artifacts.

## Rotation and revocation

Credential rotation uses explicit generation identity.

A bounded overlap between one current and one previous generation may be permitted only when the later runtime design proves a finite grace window. Indefinite grace is prohibited.

```text
current generation -> accepted
previous generation -> accepted only inside bounded grace
revoked generation -> rejected
unknown generation -> rejected
```

Rotation must not widen secret scope. A replacement credential inherits the same or narrower authority unless a separately reviewed authorization change explicitly changes it.

Revocation must fail closed. A revoked generation must never regain authority because of process restart, stale cache, fallback configuration, or rollback to older application code.

## Infisical capability gate

Selection of Infisical does not imply that every required production feature is available under the chosen deployment or license.

Before activation, the project must verify the exact required capabilities for machine identity, least privilege, audit evidence, rotation, revocation, backup/recovery, and operational access. If those requirements cannot be proved, production secret activation stops rather than silently weakening this contract.

## Authority separation

These statements remain false:

```text
authenticated identity == musical authorization
machine secret possession == tenant authorization
publication credential possession == publication approval
private network membership == service authentication
```

Stage 8 human approval and publication lineage remains authoritative for publication eligibility. Stage 9-C only constrains how production credentials may later be provisioned.

## Activation locks

All real credential effects remain disabled:

```text
machineIdentitiesCreated=false
productionSecretsGenerated=false
productionSecretsProvisioned=false
coolifyProductionBootstrapConfigured=false
infisicalProductionRuntimeActivated=false
rotationRuntimeActivated=false
revocationRuntimeActivated=false
providerCredentialsProvisioned=false
databaseCredentialsProvisioned=false
objectStorageCredentialsProvisioned=false
oidcClientCredentialsProvisioned=false
publicationCredentialsProvisioned=false
omrDispatchCredentialsProvisioned=false
```

## Safe next slice

After Stage 9-C merges, the next safe repository-only slice is the production PostgreSQL persistence, backup and restore contract. It may define schemas/provider boundaries, backup identities, recovery objectives and restore evidence, but must not create a database server or production credentials.
