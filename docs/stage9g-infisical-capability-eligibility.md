# Stage 9-G — Infisical Production Capability Eligibility Gate

## Status

**Repository-only eligibility policy. Infisical remains the selected target, but production eligibility is explicitly false until the exact self-hosted deployment and selected license prove the required capabilities. No installation, project, machine identity, secret import, Coolify bootstrap, rotation, audit integration, or backup is activated by this stage.**

## Why this gate exists

Selecting a product does not prove that every needed security feature is present in the chosen deployment or license. ScoreMosaic therefore does not infer production readiness from the product name `Infisical`.

## Required evidence

Before production secret activation, current provider/product evidence must prove the exact deployment can support the required operating model, including:

- machine identity authentication;
- least-privilege secret scopes;
- DEV/STAGING/PRODUCTION isolation;
- version history;
- safe rotation, either native or through a separately reviewed integration;
- revocation;
- bounded audit evidence;
- backup and recovery;
- protected administrative access;
- a documented self-host upgrade path.

The exact current product documentation and selected license must be checked at activation time. Earlier assumptions or cached pricing/feature pages are insufficient.

## Fail-closed rule

A missing capability is not silently waived. The project must either prove an equivalent safe design or revisit the secret-manager provider/architecture.

## Bootstrap

Coolify may retain only minimum bootstrap material. It does not become the general production secret store. Production secret values remain forbidden from repository source, browser payloads, and logs.

## Current eligibility

All live-provider evidence fields remain false:

```text
machineIdentityVerified=false
leastPrivilegeVerified=false
environmentIsolationVerified=false
rotationRevocationVerified=false
auditVerified=false
backupRecoveryVerified=false
licenseCompatibilityVerified=false
productionEligible=false
```

This is intentional. Stage 9-G defines the proof required; it does not invent that proof.

## Runtime locks

```text
infisicalInstalled=false
productionProjectCreated=false
machineIdentityCreated=false
productionSecretsImported=false
coolifyBootstrapConfigured=false
rotationConfigured=false
auditIntegrationActivated=false
backupConfigured=false
```

## Safe next slice

After Stage 9-G merges, the next safe repository-only slice is ScoreMosaic internal publication persistence/exactly-once execution semantics. It may define how a future production publication writes PostgreSQL + immutable object storage safely across crash windows, but must not execute a real publication or provider write.
