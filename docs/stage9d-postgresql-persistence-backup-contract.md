# Stage 9-D — PostgreSQL Production Persistence, Backup and Restore Contract

## Status

**Repository-only database policy. No PostgreSQL server, production database, role, connection string, backup schedule, WAL archive, migration, or production restore is created or executed by this stage.**

Stage 9-D binds the approved PostgreSQL 18 choice to fail-closed durability, data-placement, least-privilege, backup, restore, and migration requirements before any production database exists.

## Database boundary

Production uses PostgreSQL 18 on a private host separate from OMR compute. The exact supported 18.x minor is selected at deployment time. Direct public database ingress remains forbidden.

Durability safeguards such as `fsync` and `full_page_writes` must not be disabled. Authoritative Teacher Review, approval, publication, job-state, and audit transactions must not deliberately trade durability for asynchronous performance.

## Data placement

PostgreSQL stores relational identities, lifecycle state, hashes, authorization state, revision lineage, approval records, publication records, audit data, and object-storage references.

Large immutable bytes remain in object storage:

- source PDF/PNG/JPEG;
- OMR candidate artifacts;
- corrected MusicXML bytes;
- published MusicXML bytes;
- model artifacts.

Database records bind those artifacts by immutable identity, SHA-256, size/type where applicable, and server-owned storage reference.

## Least-privilege database roles

The application, publication service, backup worker, and Authentik use distinct database roles. Ordinary services never receive the PostgreSQL administrator role.

A publication database role does not grant publication approval. A backup role does not grant application mutation authority.

## Integrity

Production persistence must preserve:

- exact TeacherScoreRevision parent lineage;
- append-only audit predecessor binding;
- human approval record identity;
- publication record identity;
- artifact SHA-256 bindings;
- stale-write rejection;
- no silent musical repair.

A stale request must never overwrite the current revision head merely because the database connection is valid.

## Backup

A production backup is not useful if it exists only on the primary database host. Backup material must leave that host and land in a private S3-compatible destination.

Requirements include:

- scheduled logical backup;
- encrypted backup material;
- explicit retention policy before activation;
- point-in-time recovery or equivalent recovery coverage before GA;
- explicit RPO and RTO before activation;
- no public backup bucket.

This stage intentionally does not invent RPO/RTO numbers. They must be chosen with real workload and business requirements before activation.

## Restore proof

A successful backup command is **not** recovery proof.

Before production activation, a restore drill must:

1. restore into a fresh isolated target;
2. validate schema/version state;
3. verify revision/approval/publication lineage;
4. validate stored artifact references and hashes against available evidence;
5. avoid overwriting production;
6. produce retained recovery evidence.

## Schema migrations

Migrations are versioned and reviewed. Destructive migrations require a separate approval boundary plus fresh backup/restore evidence. An unreviewed branch must never run a production schema migration automatically.

## Runtime locks

```text
postgresqlServerCreated=false
productionDatabaseCreated=false
productionRolesCreated=false
productionListenerActivated=false
productionConnectionStringProvisioned=false
backupScheduleActivated=false
walArchiveActivated=false
restoreExecutedAgainstProduction=false
schemaMigrationExecutedInProduction=false
```

## Safe next slice

After Stage 9-D merges, the next safe repository-only slice is object-storage immutability and independent NBG1-to-FSN1 backup-copy semantics. It must not create a bucket, S3 key, object, or scheduled copy job.
