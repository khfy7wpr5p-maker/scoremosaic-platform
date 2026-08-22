# Stage 9-E — Object Storage Immutability and Independent Backup-Copy Contract

## Status

**Repository-only storage policy. No Hetzner bucket, S3 credential, object, versioning flag, Object Lock setting, backup schedule, public bucket policy, or production deletion capability is created or activated by this stage.**

Stage 9-E binds the approved Hetzner Object Storage choice to immutable artifact identity, private access, least privilege, and independently verified NBG1-to-FSN1 backup-copy semantics.

## Provider boundary

Primary object storage is NBG1. FSN1 is an independent secondary backup target. The architecture does not assume native cross-location replication.

All provider access must use authenticated TLS/S3 requests. Buckets are private by default.

## Artifact classes

### Source artifacts

Accepted PDF/PNG/JPEG source bytes are create-once under server-derived keys and bound to SHA-256. Caller-controlled filesystem/storage paths are forbidden.

### OMR candidates

Candidate artifacts are create-once and hash-bound. Different bytes must never overwrite an existing candidate identity.

### Corrected MusicXML

Corrected derivatives are revision-bound and versioned. A new revision creates new immutable evidence rather than silently replacing prior musical state.

### Published MusicXML

Published artifacts require versioning, Object Lock/immutability policy, exact publication-record binding, and SHA-256 binding. `PUBLISHED` remains separate from `PUBLIC`; a published object is private by default.

### Model artifacts

ST-OMR model artifacts must have a version identity and SHA-256. A mutable `latest` alias can never be treated as authoritative model identity for production execution.

### Database backups

Database backups are private and encrypted, and their existence does not replace Stage 9-D restore evidence.

## Independent NBG1 -> FSN1 copy

The backup worker receives only primary-read and secondary-write credentials.

For each copy it must verify:

1. source identity and SHA-256;
2. source size;
3. destination identity;
4. destination size;
5. destination SHA-256 after copy.

Exact replay is idempotent. If the same backup identity already exists with different bytes, the operation fails closed instead of overwriting it.

The secondary backup path is one-way for this workflow. The FSN1 writer does not gain authority to write back into NBG1 primary storage.

## Access restrictions

The browser never receives S3 credentials and never chooses buckets or storage roots. OMR compute cannot delete source artifacts. Backup workers cannot delete primary objects. The application cannot routinely delete published artifacts.

## Retention

Retention policy must be explicit before runtime activation. Routine cleanup cannot remove protected published artifacts or break live database-to-artifact bindings.

Legal/privacy deletion semantics require a separate reviewed contract because they may legitimately override normal retention; Stage 9-E does not invent them.

## Runtime locks

```text
primaryBucketCreated=false
secondaryBucketCreated=false
s3CredentialsProvisioned=false
versioningEnabledOnProvider=false
objectLockEnabledOnProvider=false
productionObjectWriteActivated=false
backupCopyScheduleActivated=false
productionObjectDeletionActivated=false
publicBucketPolicyActivated=false
```

## Safe next slice

After Stage 9-E merges, the next safe repository-only slice is Authentik-to-ScoreMosaic identity and RBAC binding. It must not create a real user, OIDC client, session, role assignment, or public login route.
