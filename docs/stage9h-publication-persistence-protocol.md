# Stage 9-H — Internal Publication Persistence and Crash-Recovery Protocol

## Status

**Repository-only execution protocol. No publication database write, object-storage write, route, public visibility change, or real publication is activated by this stage.**

Stage 9-H defines how a future production publication must safely cross PostgreSQL and immutable object storage without converting partial failure into duplicate, stale, or conflicting publication.

## Preconditions

Before any future publication execution:

1. rebuild and freshly verify the complete Stage 8-O handoff from current durable inputs;
2. require exact equality with the supplied handoff;
3. require the exact current revision and exact approved corrected MusicXML;
4. require exact publisher principal + tenant + resource + `publication:execute` authorization;
5. never infer human approval.

A valid credential or old handoff alone is insufficient.

## Deterministic execution identity

The server derives one publication identity from exact bounded publication inputs. The request binds the Stage 8-O handoff hash, approval-record hash, MusicXML hash, publisher principal, tenant, and resource. The caller never chooses the storage object key.

## Three-state persistence protocol

```text
prepared
   ↓
artifact-written
   ↓
published
```

Only `published` is a completed publication. `prepared` and `artifact-written` are internal crash-recovery states and must never be presented as published.

### 1. prepared

Create one immutable/idempotent PostgreSQL preparation record. Exact replay converges; the same publication identity with a different request conflicts.

The prepared record contains no raw credentials and defaults to private visibility.

### 2. artifact-written

Write the exact approved MusicXML bytes to the server-derived immutable object identity using create-once semantics. After the write, independently verify object size and SHA-256 and retain versioning/Object-Lock evidence.

A conflicting existing object fails closed. Failure must never delete an existing protected artifact.

### 3. published

Finalize the PostgreSQL publication record only after exact object re-verification. The record binds exact object identity/version, MusicXML SHA-256, publisher, approval record, tenant/resource, and publication identity.

Default visibility remains `private`. `PUBLISHED` does not mean `PUBLIC`.

The publication record is authoritative evidence of **which exact human-approved artifact was published**, but `authoritativeMusicalTruth=false` remains explicit: neither AI nor publication infrastructure claims universal musical correctness.

## Crash windows

### Crash after `prepared`, before object write

Exact replay may resume only after fresh precondition revalidation.

### Crash after object write, before finalization

The execution path must reopen and independently verify the exact immutable object. If bytes/hash/identity match, it may continue to finalization. If they differ, fail closed.

### Exact replay after `published`

Return the existing immutable publication record. Do not write a second object or publication record.

### Conflicting object

Do not overwrite and do not auto-delete. Preserve evidence and require failure resolution.

## Authority separation

Possession of publication storage/database credentials is not approval and is not enough to publish. ScoreMosaic RBAC and the Stage 8 human-approval/publication handoff chain both remain mandatory.

## Runtime locks

```text
publicationDatabasePreparedWriteActivated=false
publishedObjectWriteActivated=false
publicationFinalizationWriteActivated=false
publicationRouteActivated=false
externalPublicVisibilityActivated=false
realPublicationExecuted=false
```

## Safe next slice

After Stage 9-H merges, Stage 9-I may aggregate Stage 9-A through 9-H into a production-foundation eligibility report. That report must remain fail-closed and stop before real Hetzner provisioning, credential creation, DNS/TLS changes, or publication execution.
