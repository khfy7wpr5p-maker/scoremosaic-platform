# ScoreMosaic ↔ ST-Orchestration Integration Boundary

Status: **DISCONNECTED COMPATIBILITY READY / LIVE INTEGRATION DISABLED**

Counterpart repository: `khfy7wpr5p-maker/ST-Orchestration`

Pinned counterpart main commit: `6c7f74fdbf13dd3acc2e0daa93cab7037d6a0a90`

ScoreMosaic contract: `contracts/st-orchestration-integration-v1.json`

ST-Orchestration contract: `contracts/H7_SCOREMOSAIC_INTEGRATION_V0.json`

## 1. Safe position

ST-Orchestration is a downstream music application. It does not become part of OMR, Canonical authority, Teacher Review authority, approval authority or publication authority.

```text
PDF / image
  -> ScoreMosaic OMR
  -> Canonical Score
  -> Teacher Review
  -> deterministic validation
  -> corrected MusicXML
  -> explicit human approval when production derivation is requested
  -> exact revision / corrected MusicXML identity
  -> typed orchestration application contract
  -> dedicated ScoreMosaic orchestration adapter
  -> future transport — disabled
  -> ST-Orchestration bounded capability
  -> deterministic validation
  -> non-authoritative proposal / alternatives / abstention
  -> ScoreMosaic Teacher Review
```

The browser never calls ST-Orchestration directly.

## 2. Current capability is deliberately narrow

The exact promoted ST-Orchestration model is:

- id: `o5c-ossq-anonymous-context-v0`
- model fingerprint: `15cd94722a0ba2724ceea6f450f16a87ef455fa8bc21d4b619f0bda6d880ca14`
- H4 result fingerprint: `462f492ace58ecf0c4d1125966057c869177cad99367f1364d89c17710081225`
- frozen abstention threshold: `0.55`

It is currently promoted only for bounded research/evaluation.

The only integration capability admitted by v1 is:

`string-seat-ranking-v0`

This is **not** a general piano-to-orchestra or full-score orchestration model.

Requests for full-score orchestration, piano-to-orchestra, full symphonic orchestration, automatic arrangement, source-music rewriting or automatic publication must fail closed.

## 3. Source lineage

Every request must bind exact upstream musical identity:

```text
integration_request_id
document_id
canonical_score_id
teacher_revision_id
corrected_musicxml_sha256
source_state
capability
```

Allowed source states are `validated-preview` and `approved`.

A validated preview remains non-authoritative. A future production-derived request requires the exact approved teacher revision and exact corrected MusicXML hash.

Forbidden sources include raw OMR candidates, raw engine output, browser-edited ad hoc XML and stale revisions.

## 4. Result boundary

A future result must bind to the exact request and source hash and carry exact model identity, frozen threshold, alternatives/abstention, deterministic validation evidence and a result SHA-256.

A result is downstream evidence, not ScoreMosaic musical truth.

A proposal that fails deterministic validation must not survive as a proposal.

## 5. Authority separation

ST-Orchestration may not:

- mutate Canonical Score;
- create or overwrite TeacherScoreRevision;
- approve a revision;
- publish a revision;
- mark a stale result current;
- automatically train from teacher/user corrections.

If a teacher chooses an orchestration proposal later, ScoreMosaic must convert that choice into its own explicit edit/revision workflow under ScoreMosaic authority.

## 6. Failure isolation

A transport/model/validation failure must not alter ScoreMosaic state. It may produce only bounded downstream status/evidence.

## 7. Current activation locks

```text
disconnectedCompatibilityHarnessReady = true
adapterRuntimeActivated = false
runtimeModelCallActivated = false
networkTransportActivated = false
productionCredentialsActivated = false
productionInferenceActivated = false
canonicalMutationActivated = false
teacherRevisionMutationActivated = false
approvalActivated = false
publicationActivated = false
stOmrIntegrationActivated = false
postH4RetuningAuthorized = false
h4RerunAuthorized = false
automaticLearningActivated = false
```

## 8. Next gate

H7-B establishes only disconnected compatibility evidence.

The next explicit human gate is **H7-C — non-authoritative local/preview adapter activation**.

Authenticated staging transport and production inference remain separate later gates.
