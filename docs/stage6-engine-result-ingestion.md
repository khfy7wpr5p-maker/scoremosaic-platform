# Stage 6 Engine Result Ingestion Boundary

Status: **Stage 6 integration contract**  
Scope: authenticated result bytes → immutable ScoreMosaic candidates  
Production/live result transport: **not authorized by this document**

## Purpose

Stage 6 converts engine-owned result evidence into bounded, authenticated, immutable ScoreMosaic candidates. It does not decide the authoritative musical score. HOMR, Clarity and Audiveris remain evidence producers.

The boundary is intentionally split from Stage 5:

`Stage 5: source + plan + identity -> authenticated one-shot execution`

`Stage 6: authenticated result identity + exact result bytes -> validated candidate evidence`

Result transport itself can later be HTTP, object storage, queue-backed or another provider-neutral implementation, but every transport must terminate at the same Stage 6 authentication and bounds checks.

## Existing security primitive reused

Stage 6 reuses the pre-existing `DispatchResultIdentity` contract rather than inventing a second result authentication scheme. The result identity binds:

- dispatch identity SHA-256;
- plan ID and plan SHA-256;
- job ID;
- immutable source artifact ID and source SHA-256;
- run ID;
- engine;
- candidate ID and namespace;
- expected MusicXML and diagnostic artifact IDs;
- exact result payload byte length and SHA-256;
- exact engine credential binding;
- HMAC signature.

Authentication is verified **before engine-result parsing**. A cross-job, cross-run, cross-engine, cross-source, cross-candidate or byte-tampered result therefore cannot reach parser or persistence authority.

## Deterministic result frame

Stage 6 defines `scoremosaic-engine-result-frame-v1` as an unambiguous binary frame:

- fixed 8-byte magic;
- unsigned 64-bit raw-result length;
- unsigned 64-bit MusicXML length;
- unsigned 64-bit diagnostic length;
- exact raw-result bytes;
- exact MusicXML bytes;
- exact diagnostic bytes;
- no trailing bytes.

Bounds:

- raw engine result: 64 MiB maximum;
- MusicXML: 64 MiB maximum;
- diagnostic JSON: 64 KiB maximum;
- total frame: the exact bounded sum only.

Integer lengths are checked before slicing. Truncation, trailing data, oversized fields and wrong framing fail closed.

## Engine adapter boundary

Three explicit adapters exist:

- `AudiverisResultAdapter`
- `HomrResultAdapter`
- `ClarityResultAdapter`

They share transport/frame mechanics but are exact-engine bound. Engine-specific SDK/model/library objects never enter the ScoreMosaic core candidate type. Cross-engine reuse fails before normalization.

Each adapter performs:

1. exact `DispatchResultIdentity` verification;
2. bounded frame validation;
3. bounded streaming MusicXML structural sanity validation;
4. strict diagnostic JSON parsing with duplicate-key, depth, collection and string bounds;
5. diagnostic normalization to deterministic canonical JSON;
6. creation of immutable `NormalizedEngineCandidate` evidence.

The normalized candidate preserves exact MusicXML bytes and exact raw-result bytes while canonicalizing only the controlled diagnostic evidence schema.

## XML safety boundary

Stage 6 MusicXML handling is a structural/safety admission layer, not final musical normalization. It rejects unsafe XML declarations such as DTD/entity material, malformed XML, pathological depth/element counts, excessive attributes/text and non-score roots.

Full musical/Canonical Score validation belongs to Stage 7 and remains stricter. Passing Stage 6 does **not** mean the MusicXML is musically authoritative or Canonical-ready.

## Diagnostic contract

Diagnostic input is UTF-8 JSON and may contain only:

- `engine` — exact adapter engine;
- `status` — exactly `success`;
- `engineVersion` — bounded optional version string;
- `modelVersion` — bounded optional version string;
- `warnings` — bounded list of bounded strings.

Unknown fields, duplicate keys, non-finite values, pathological nesting or engine mismatch fail closed. Error text from engine stdout/stderr is not accepted as an unbounded diagnostic channel.

## Candidate identity

`NormalizedEngineCandidate` binds:

- engine;
- job/run/plan identity;
- source identity;
- candidate identity/namespace;
- expected artifact identities;
- dispatch identity SHA-256;
- authenticated result payload SHA-256;
- raw-result SHA-256 + size;
- MusicXML SHA-256 + size;
- canonical diagnostic SHA-256 + size;
- bounded engine/model version evidence.

Its deterministic candidate SHA-256 is derived only from those normalized values. Raw payload bytes are excluded from `repr` and safe diagnostics.

## Immutable candidate persistence

Candidate persistence uses only server-derived paths below the controlled staging provider root. No caller path is accepted.

Artifacts are written create-once:

- raw engine result;
- exact MusicXML;
- canonical diagnostic JSON.

Exact existing bytes are an idempotent replay. Different existing bytes are a persistence conflict; overwrite is forbidden.

The candidate record is written after artifact content and is HMAC-sealed with the existing staging state-integrity key. It contains immutable identity/provenance metadata and artifact hashes/sizes/media types, never engine credentials or authentication signatures.

Crash recovery rule:

- exact artifacts present + candidate record missing: safe to complete the exact record publication;
- candidate record present and authentic: exact replay only;
- any differing artifact or record: fail closed;
- no automatic replacement or destructive cleanup.

This is intentionally compatible with content-addressed immutable storage migration later.

## Partial-success semantics

Engine failure is isolated per candidate. One engine failure does not invalidate another engine's already authenticated/persisted candidate.

For a normal three-engine ScoreMosaic plan:

| Result | Meaning | Comparator/Canonical convergence eligibility |
|---|---|---|
| 3/3 success | all candidates available | eligible |
| 2/3 success | degraded but independently comparable | eligible |
| 1/3 success | one candidate retained as evidence | not eligible |
| 0/3 success | no candidate available | not eligible |

The current minimum for Stage 7 comparison/convergence is **two authenticated candidates**. This does not mean two engines may silently vote an authoritative answer; Stage 7 Canonical and comparator rules still apply.

Allowed trusted engine-failure reason codes are bounded and normalized. Authentication failure is not converted into an ordinary engine failure record because an unauthenticated result must not gain durable candidate semantics.

## Deterministic lifecycle convergence

The existing append-only candidate/artifact lifecycle remains authoritative for lifecycle semantics. Stage 6 reconstructs it in canonical engine order from:

- immutable orchestration plan;
- bounded success/failure outcomes;
- HMAC-verified persisted candidate records.

Successful candidates follow:

`reserved -> collecting -> sealed`

with each artifact:

`reserved -> writing -> sealed`

Failed engines terminalize only their own artifacts/candidate with bounded reason codes. Terminal candidates do not reopen.

The same plan + same authenticated candidate records + same failure outcomes must produce the same lifecycle event order and lifecycle hash.

## Explicitly locked after Stage 6

Stage 6 does **not** authorize:

- engine output as authoritative score;
- winner selection;
- confidence-only musical decisions;
- automatic correction/merge;
- teacher approval/publication;
- production activation;
- arbitrary engine result destinations;
- unbounded error/result transport;
- live result network transport unless a later transport-specific security gate proves it.

Stage 7 owns Candidate Safety, Canonical normalization, Ensemble comparison, evidence aggregation and end-to-end convergence.