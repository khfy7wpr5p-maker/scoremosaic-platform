# Stage 7 Candidate Intelligence and Convergence

Status: **Stage 7 integration contract**  
Scope: deterministic candidate safety, Canonical admission, neutral comparison and bounded review evidence  
Production/live engine activation: **not implied by this contract**

## Purpose

Stage 7 connects the authenticated immutable candidate persistence completed in Stage 6 to the existing ScoreMosaic Canonical Score and Ensemble Comparator foundations without allowing engine or AI output to become authoritative score state.

The trust chain is:

`Stage 6 HMAC-sealed candidate record + immutable artifact bytes`

→ Gateway read-after-hash verification

→ `VerifiedCandidateHandoff`

→ independent Ensemble handoff verification

→ Canonical candidate admission

→ deterministic Canonical Score

→ neutral Ensemble comparison

→ deterministic comparison report + decomposed evidence

No winner, merged score, automatic correction, teacher approval, or publication authority is introduced.

## Gateway trust boundary

`candidate_convergence_handoff.py` may create a handoff only from Stage 6 persistence that passes all of the following again:

- exact orchestration plan / job / run / engine / candidate identity;
- HMAC-sealed Stage 6 candidate record verification;
- server-derived candidate artifact paths;
- no-follow bounded artifact reads;
- actual artifact byte size and SHA-256 verification;
- exact MusicXML artifact identity and artifact reference from the orchestration plan;
- exact candidate and source lineage;
- Stage 7 MusicXML size ceiling of 16 MiB, matching the Canonical normalizer boundary.

The handoff exposes no persistence key, state-integrity key, credential, HMAC, signature, caller-controlled path, or storage mutation authority.

`to_ensemble_payload()` is an **in-memory integration payload**, not a network credential. Any future Gateway → Ensemble network transport requires a purpose-separated authenticated transport contract. Private networking alone will not make the payload trusted.

## Handoff integrity

The handoff includes deterministic identity/content metadata and exact MusicXML bytes. `handoffSha256` is derived from canonical metadata including:

- job / plan / source identity;
- engine / run / candidate identity;
- Stage 6 candidate hash;
- persistence-record hash;
- MusicXML artifact identity/ref/hash/size;
- bounded engine/model version metadata;
- explicit candidate-only / non-authoritative boundaries.

The document itself is represented by exact size + SHA-256 in the handoff digest. The Ensemble side recomputes both the document SHA-256 and `handoffSha256`; it does not trust a Gateway Python class.

## Candidate Safety

Stage 7 intentionally composes rather than duplicates existing safety layers:

1. Stage 6 authenticates result lineage before parsing.
2. Stage 6 applies bounded framing, XML structural safety and diagnostic normalization.
3. Stage 6 durable persistence re-verifies actual artifact bytes against sealed metadata.
4. Stage 7 Gateway handoff re-opens that durable evidence and rechecks content identity.
5. Stage 7 Ensemble independently verifies the handoff bytes/hash/identity.
6. Canonical normalization applies musical/structural bounds for parts, measures, events, durations, pitches, staffs, tuplets, TAB positions and supported MusicXML semantics.

Current Stage 6 candidates do **not** carry image bounding boxes/localization coordinates. Therefore Stage 7 must not invent coordinate confidence or localization evidence. `localizationReliability.available=false` and `bboxEvidenceAvailable=false` remain explicit. A future bbox/localization channel must define bounded page dimensions, finite coordinate ranges, source-page binding and deterministic normalization before this field can become available.

## Canonical Score

Canonical normalization remains the existing deterministic `scoremosaic_ensemble.musicxml` implementation. Stage 7 does not weaken its rules.

For the same exact candidate bytes, source identity and contract version:

- normalization output is deterministic;
- Canonical Score serialization is deterministic;
- `canonicalSha256` is deterministic.

Canonical scores remain candidate interpretations. Stage 7 does not select one as authoritative solely because of engine confidence or majority agreement.

## Ensemble Comparator

Comparison remains neutral and read-only. It exposes agreement/disagreement with per-candidate provenance for categories including:

- measure structure;
- event timing;
- pitch;
- duration;
- rest;
- chord;
- voice/staff;
- tie/dot/tuplet;
- TAB position.

A Canonical rejection of one engine candidate is isolated. Comparison is produced only when at least two candidates pass Canonical admission. If fewer than two survive, Stage 7 returns `insufficient_canonical_candidates` and no comparison report.

## Confidence and evidence

Stage 7 deliberately has no opaque aggregate confidence score.

Evidence is separated into:

- `engineAgreement` — accepted/rejected count and comparison difference count;
- `visualConfidence` — unavailable until a validated visual-evidence contract exists;
- `structuralConsistency` — structural difference count;
- `musicalConsistency` — musical difference count and category counts;
- `sourceQuality` — unavailable until a validated source-quality contract exists;
- `localizationReliability` — unavailable for bbox evidence; Canonical XML provenance is reported separately.

Unavailable evidence is explicit and cannot silently become zero confidence or authoritative evidence.

## Determinism

The Stage 7 result hash is computed from canonical JSON over safe handoff metadata, Canonical admission evidence, neutral comparison report, decomposed evidence and locked decision boundaries.

Input order is normalized by canonical engine order. Reversing equivalent handoff input order must therefore produce the same Stage 7 result and hash.

Wall clock, filesystem ordering, random values, temporary paths and runtime diagnostics are excluded from the result hash.

## Partial success

Stage 6 owns engine execution partial-success semantics:

- 3/3 success → Stage 7 eligible;
- 2/3 success → Stage 7 eligible;
- 1/3 success → fail closed before comparison;
- 0/3 success → fail closed before comparison.

Stage 7 can further reduce the admitted set if Canonical safety rejects a successful Stage 6 candidate. A 2/3 Stage 6 success can therefore become non-comparable when one of those two candidates fails Canonical admission.

No engine failure invalidates an already authenticated candidate from another engine.

## Bounded result evidence

Stage 7 reuses the existing bounded Comparator and Comparison Report contracts. The report preserves deterministic hashes and disabled decision boundaries. No raw source image, credential, signature, HMAC, raw engine diagnostic stream or filesystem path is included in the safe Stage 7 result.

## Hermetic vertical-slice level

The Stage 7 CI integration path is intentionally hermetic. It exercises real repository contracts and deterministic fixture bytes through:

`orchestration identity`

→ authenticated result identity

→ Stage 6 result ingestion

→ immutable candidate persistence

→ Stage 7 verified handoff

→ Canonical admission

→ Ensemble comparison/report.

Stage 5 separately proves immutable source intake, durable job lifecycle, atomic queued→dispatching arbitration, authenticated dispatch/source delivery and one-shot execution boundaries. The Stage 7 test suite composes those frozen contracts at repository integration level; it does **not** claim that HOMR, Clarity or Audiveris production binaries/models were executed live.

Live runtime/network status must always be reported separately from contract/integration status.

## Recovery and rollback

Stage 7 is read-only with respect to Stage 5/6 durable lifecycle state. It cannot reopen terminal state, retry execution or overwrite candidate artifacts.

A missing, tampered or conflicting Stage 6 artifact causes handoff failure. A malformed/tampered handoff causes Ensemble rejection before Canonical normalization.

Older code that does not understand Stage 6 immutable candidate records may read neither Stage 7 handoff authority nor comparison readiness from them; it must not rewrite those records.

## Locked features

Still locked after this integration contract:

- live production engine activation where external runtime/model infrastructure is unavailable;
- unauthenticated Gateway → Ensemble network transport;
- bbox/localization confidence without a validated localization contract;
- engine ranking;
- winner selection;
- automatic merge/correction;
- authoritative score publication;
- Teacher Review mutation/approval APIs;
- public UI mutation APIs.

These locks are intentional and are part of the Stage 7 security boundary, not missing implicit permissions.
