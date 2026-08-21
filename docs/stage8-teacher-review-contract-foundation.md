# Stage 8 — Teacher Review Contract Foundation

Status: **contract/hermetic foundation only; no writable or public runtime activated**.

## Goal

Stage 8 establishes the first safe mutation-domain contracts without exposing a mutation route. It reconciles the Teacher Review architecture ordering by putting authorization evidence and stale-target protection in the same non-network contract foundation as immutable revision identity.

The foundation contains three closed contracts:

1. `teacher-review-authorization-v1.schema.json`
2. `score-edit-command-v1.schema.json`
3. `teacher-score-revision-v1.schema.json`

## Trust and authority boundary

An OMR candidate, Canonical Score, Ensemble comparison, Review Report recommendation, renderer, playback adapter, or UI selection never gains mutation authority.

A draft revision proposal is valid only when all of the following bind exactly:

- authenticated/authorized reviewer decision identity;
- tenant/resource scope;
- job identity;
- Review Report identity and SHA-256;
- Canonical Score SHA-256;
- exact parent revision ID and SHA-256, or an explicit root state;
- closed `ScoreEditCommand` identity and SHA-256;
- stable musical location;
- old-value hash precondition identity (semantic comparison to the current musical state is deferred to revision materialization);
- resulting musical-state hash;
- validation-report hash;
- append-only audit-chain predecessor hash.

The repository implementation provides a purpose-separated HMAC-sealed authorization grant for hermetic contract verification. It is not a public bearer token and does not claim a production identity provider, session system, RBAC backend, TLS policy, or durable authorization store.

## Closed edit surface

The initial operation allowlist is intentionally narrow:

- `set_pitch`
- `set_effective_duration`
- `set_written_type`
- `set_dots`
- `set_staff_voice`
- `set_time_signature`
- `set_tab`
- `remove_event`

Arbitrary XML, JSON Patch, object paths, filesystem references, executable expressions, renderer-native mutation objects, arbitrary key/value extension fields, and unbounded operation payloads are rejected.

`insert_event`, ties, tuplets, chord-membership changes, beam/clef/slur/key-signature editing, corrected MusicXML generation, and automatic correction remain deferred until separately reviewed contracts exist.

## Stale-target and concurrency semantics

Every authorization decision and every edit command binds the exact parent revision ID/hash. A command created against an older parent fails closed once a newer revision becomes the current head.

This stage proves deterministic stale-parent rejection at the contract boundary. It does **not** claim production durable compare-and-swap semantics across processes or restarts. That requires the future durable Teacher Review persistence gate.

## Immutable revision semantics

`TeacherScoreRevision` is an immutable **draft** evidence record. Its deterministic revision SHA-256 binds the exact authorization, review report, Canonical base, parent revision, edit command, resulting musical-state hash, validation-report hash, counts, timestamp, and audit-chain predecessor.

The contract hard-codes:

- `status = draft`
- `immutable = true`
- `approvalEligible = false`
- `publicationEligible = false`

Undo/redo, when later implemented, must create additional revisions and audit events; no prior revision may be rewritten or deleted.

## Explicitly still locked

Stage 8 does not activate:

- public Teacher Review HTTP routes;
- writable UI;
- production authentication/session/RBAC provider;
- production durable revision storage;
- corrected MusicXML materialization;
- teacher approval;
- publication;
- winner selection, automatic merge, or automatic correction;
- engine or Ensemble authority over teacher truth.

## Verification expectations

Dedicated CI verifies closed schemas, deterministic hashes, purpose-separated authorization sealing, tamper rejection, exact-resource binding, operation bounds, arbitrary XML/path rejection, immutable records, stale-parent rejection, audit-chain binding, and activation-lock flags.
