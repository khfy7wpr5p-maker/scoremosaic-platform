# SM-POLY-03 — Polyphonic Teacher-Gold Benchmark Harness

Status: **research/evaluation harness foundation**  
Production behavior change: **none**  
Teacher-gold corpus readiness at repository baseline: **NOT_READY**

## Purpose

SM-POLY-03 adds the deterministic harness needed to grow ScoreMosaic Polyphonic Teacher-Gold Benchmark v1 without inventing teacher verification or committing private score/gold assets to the public repository.

The package adds:

- `contracts/polyphonic-teacher-gold-registry-v1.schema.json`
- `evaluation/polyphonic-teacher-gold-v1/registry.json`
- `scripts/polyphonic_teacher_gold_harness.py`

It builds on the SM-POLY-02 fixture schema and taxonomy. The existing frozen `evaluation/fixed-v1` dataset remains unchanged and keeps its original regression role.

## Registry model

The public baseline registry is deliberately empty. This is a truthful state, not a missing synthetic claim.

Each future registry record contains only:

```text
fixtureId
metadataRef
metadataSha256
```

The referenced fixture metadata follows `scoremosaic-polyphonic-benchmark-fixture-v1`. Real private source images/PDFs, teacher-gold artifacts, private labels and personal information remain outside the public repository under the existing private-asset governance boundary.

Registry metadata references must be relative `fixtures/...` paths, SHA-256 pinned, unique and sorted by fixture identity. Traversal/absolute/backslash paths fail closed.

## Readiness gates

The harness distinguishes contract validity from corpus readiness.

```text
< 500 eligible verified fixtures
or missing required notation/feature/scan coverage
    -> NOT_READY

>= 500 eligible verified fixtures + complete required coverage
    -> MINIMUM_RESEARCH_BENCHMARK_READY

>= 1000 eligible verified fixtures + complete required coverage
    -> TARGET_RESEARCH_BENCHMARK_READY
```

`eligible verified` means both:

- teacher/review-panel verification status is `VERIFIED`; and
- dataset metadata explicitly says `evaluationAllowed=YES`.

`NO` and `REVIEW_REQUIRED` evaluation status do not count toward readiness.

Readiness never grants production authority or an accuracy claim. It only says the benchmark corpus is sufficiently populated for the next research evaluation stage.

## Coverage

For evaluation-eligible verified fixtures, the harness counts and requires non-zero coverage across every SM-POLY-02 label in:

- notation classes;
- notation features;
- scan conditions.

This prevents a nominal 500-example corpus from being declared ready if, for example, it contains no cross-staff, tuplets, phone photographs or damaged-score evidence.

## Teacher and training boundary

The following remain fixed:

```text
teacherGoldSeparateFromEngineOutputs = true
teacherCorrectionAutomaticallyTrainingData = false
teacherAuthority = true
productionDecisionAuthority = false
```

The harness may count fixtures whose `trainingAuthorization=SEPARATELY_AUTHORIZED`, but that count has no training side effect. Benchmark inclusion and training authorization are independent decisions.

## Determinism and integrity

The harness:

- validates closed registry and fixture metadata shapes without adding a third-party dependency;
- bounds JSON metadata size;
- verifies each fixture metadata SHA-256 before use;
- rejects duplicate fixture IDs and metadata refs;
- requires deterministic fixture ordering;
- derives deterministic coverage/readiness output;
- emits a canonical report with `reportSha256`.

Tampered/missing/unsafe metadata fails closed rather than being skipped.

## Explicit non-goals

SM-POLY-03 does not:

- create or fabricate 500 teacher-reviewed scores;
- copy private teacher-gold assets into GitHub;
- run Audiveris/HOMR/Clarity/ST-OMR;
- calculate per-engine accuracy metrics;
- rank engines;
- choose a winner;
- merge or repair MusicXML;
- modify Teacher Review revisions;
- authorize teacher corrections for training;
- enable production behavior.

SM-POLY-04 may consume a future populated, eligible registry to compute separate per-engine semantic metrics. Engine outputs must remain outside teacher-gold fixture records.
