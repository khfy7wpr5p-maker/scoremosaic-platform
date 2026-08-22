# ScoreMosaic Stage 8-B — Durable Revision Store

Status: **controlled durable-provider foundation; no public/write API activation**.

## Purpose

Stage 8-B gives immutable `TeacherScoreRevision` records a durable append-only home before any writable Teacher Review surface is allowed. It does not make revisions authoritative musical truth and it does not activate approval or publication.

## Trust and authority boundary

The store accepts only a `TeacherScoreRevision` already produced by the Stage 8-A contract boundary and then independently revalidates its integrity, scope, parent identity, audit predecessor, deterministic revision hash and locked authority flags.

A persisted revision remains:

- `status=draft`;
- immutable;
- `approvalEligible=false`;
- `publicationEligible=false`.

Persistence never upgrades those flags.

## Durable model

The controlled provider uses a server-owned SQLite database at one fixed filename below an absolute private root. The root is restricted to mode `0700`; an existing database path must be a regular non-symlink file.

The database contains three security-relevant structures:

1. an HMAC-sealed exact resource scope;
2. append-only HMAC-sealed revision records with monotonic sequence numbers;
3. an HMAC-sealed current revision head.

Scope, record and head seals use purpose-separated HMAC domains.

## Atomic expected-parent rule

Every append executes inside `BEGIN IMMEDIATE` with `PRAGMA synchronous=FULL`. The current head is re-opened inside that transaction and must equal the caller's exact expected `(revisionId, revisionSha256)` pair.

For competing different revisions based on the same parent:

- exactly one transaction may advance the head;
- later transactions observe the advanced head and fail closed as stale;
- no automatic merge or conflict resolution occurs.

An exact replay of the same already-current revision is idempotent only when the persisted canonical record bytes also match. An older historical revision can never be replayed to rewind the head.

## Restart and crash window

The revision record insert and head movement are one SQLite transaction. Hermetic fault injection covers crashes:

- after record insert but before head update;
- after head update but before commit.

Both windows must roll back. Re-opening the provider after either injected crash must expose neither a partial head nor a partial history.

## Read-path re-verification

Restart/recovery never trusts database rows merely because SQLite returned them. The controlled provider revalidates:

- exact resource scope HMAC;
- current-head HMAC;
- revision-record HMAC and canonical bytes;
- revision identity/hash;
- parent chain;
- append-only audit predecessor chain;
- final head-to-history convergence.

Tampering therefore fails closed rather than being interpreted as a new authorized state.

## Explicit limits

This slice does **not** prove or activate:

- a production database service;
- public or internal HTTP mutation routes;
- external identity/session provider integration;
- multi-host distributed consensus;
- protection against an attacker who can restore an older, otherwise valid full database snapshot;
- corrected MusicXML materialization;
- teacher approval;
- publication.

Full-database rollback detection requires a separately reviewed monotonic/remote checkpoint or equivalent anti-rollback authority and is intentionally not claimed here.

## Evidence gate

Required before merge:

- Stage 8-A regression suite remains green;
- different-revision concurrency demonstrates one winner;
- stale-parent and cross-tenant attempts fail closed;
- exact replay is idempotent;
- both crash windows recover cleanly;
- HMAC tampering and wrong-key re-open fail closed;
- database symlink is rejected;
- architecture activation flags remain locked.
