# ScoreMosaic Stage 8-D — Authorized Read-Only Review Workspace

Status: **read-only projection foundation; no browser mutation or approval/publication activation**.

## Purpose

Stage 8-D creates the first Teacher Review workspace payload that a browser may eventually consume without receiving mutation authority. It projects one exact Stage 7 comparison report onto one exact Teacher Review musical-state snapshot.

The trust chain is:

```text
Stage 7 comparison report + SHA-256
  -> exact RevisionScope
  -> HMAC-sealed revision:read grant
  -> exact base Canonical SHA-256
  -> exact base or immutable revision snapshot
  -> independently revalidated report/comparison/difference hashes
  -> bounded deterministic projection page
  -> read-only focus metadata
```

## Authorization

Read-only is not public. Every projection requires a valid purpose-separated Stage 8 authorization grant with `revision:read` and exact binding to:

- tenant;
- job;
- reviewer;
- review report ID and SHA-256;
- base Canonical SHA-256;
- exact snapshot revision ID/SHA-256 when a revision snapshot is requested.

A revision snapshot is independently revalidated with the Stage 8-B revision-store validation boundary and its `resultingMusicalStateSha256` must equal the supplied Stage 8-C state hash.

A base snapshot is accepted only when the supplied state exactly equals a fresh deterministic materialization of the supplied immutable Canonical artifact. An edited but unpersisted state therefore cannot masquerade as the base snapshot.

## Stage 7 evidence revalidation

The Teacher Review service does not blindly trust a cross-service Python object. The projection boundary independently checks the closed Stage 7 comparison/report surface it consumes:

- report type/version and exact top-level keys;
- report ID derivation and report SHA-256;
- neutral/no-winner/no-auto-correction boundaries;
- comparison version/alignment/counts/result SHA-256;
- sorted unique candidate identities and Canonical SHA-256 bindings;
- closed difference category/field/location structures;
- candidate observation identity/source/Canonical consistency;
- actual disagreement between observations;
- deterministic difference ID derivation.

Malformed, excessive, tampered, cross-scope, or authority-widening input fails closed.

## Projection data minimization

The projection intentionally omits security-irrelevant or risky source details. In particular, browser-facing projection output does not contain:

- raw MusicXML;
- XML paths/source-event indices;
- artifact filesystem/object references;
- source artifact hashes;
- authorization signatures;
- allowed-action lists;
- credentials or signing material.

Each difference exposes only bounded observation values plus stable candidate/Canonical identities and focus metadata. UI consumers must treat every string/value as data, never HTML.

## Focus contract

For each Stage 7 difference, the projection exposes:

- ordinal comparison location;
- selected base-candidate stable part/measure/event IDs when present in the evidence;
- booleans showing whether those exact IDs still exist in the requested snapshot.

This supports a future read-only score focus/highlight interaction without converting ordinals or display coordinates into mutation authority. If a teacher revision removed an event, the evidence remains visible while `eventPresentInSnapshot=false` makes the divergence explicit.

## Pagination and determinism

Projection pages are explicit and bounded:

- maximum page size: 200 differences;
- total difference count is always returned;
- `hasMore` makes omission explicit rather than silently truncating evidence;
- identical trusted inputs produce an identical `projectionSha256`.

## Locked capabilities

Stage 8-D does **not** enable:

- HTTP read or write routes;
- public API exposure;
- browser mutation;
- score edit controls;
- corrected MusicXML generation;
- playback/cursor authority;
- teacher approval;
- publication;
- production durable-store activation.

The package flag `read-only-projection-foundation-enabled=true` means only that the server-side deterministic projection contract exists. `write-api-enabled`, `public-api-enabled`, `corrected-musicxml-materialization-enabled`, `approval-enabled`, `publication-enabled`, and `production-durable-store-enabled` remain false.

## Evidence gate

Required before merge:

- Stage 8-A authorization/revision regression remains green;
- Stage 8-B durable-store concurrency/restart/tamper regression remains green;
- Stage 8-C materialization/validation regression remains green;
- real Stage 7 comparison report -> Stage 8-D projection integration passes;
- ten-repeat projection determinism passes;
- report tamper/cross-tenant/missing-read-authority tests fail closed;
- unpersisted edited state cannot be projected as base;
- exact revision hash/state binding passes;
- raw source/XML/path authority is absent from projection output;
- JSON schema and diff checks pass.

## Next safe slice

After Stage 8-D merges, the next safe slice may bind this contract into the existing static UI shell as a **read-only** workspace with deterministic issue selection/focus and accessibility/keyboard behavior. Mutation controls remain absent until the separate Gate E/TR-8A browser/API security boundary is proved. Corrected MusicXML remains an isolated later derivative gate.
