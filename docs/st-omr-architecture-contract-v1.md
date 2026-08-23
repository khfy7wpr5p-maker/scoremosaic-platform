# ST-OMR Architecture and Contract v1

Status: **isolated architecture/development track; not integrated into current Gateway/Stage 7 quorum**  
Current architecture state contract: `contracts/architecture-current-state-v1.json`

This phase is architecture-only. This document defines the ScoreMosaic-native ST-OMR architecture boundary. It does not activate an ST-OMR production service, Gateway key, Ensemble membership, public endpoint, training runtime, or production deployment.

## Purpose

ST-OMR is the planned ScoreMosaic-native OMR system. The intended design is modular: small specialist models produce bounded observations/evidence and deterministic musical composers/validators resolve musical structure wherever possible.

The architectural direction is:

```text
prepared immutable page set
  -> bounded visual specialists
       page/measure structure
       notehead/rest/accidental
       stem/beam/flag/dot/tuplet
       meter and other bounded specialists
  -> deterministic Duration/Meter/Pitch/Voice composition
  -> musical validation + abstention/uncertainty evidence
  -> immutable ST-OMR candidate artifacts
  -> Candidate Safety
  -> Canonical admission
```

ST-OMR must not become a monolithic model that directly emits authoritative musical truth.

## Current relationship to ScoreMosaic

The authoritative current Stage 7 v1 engine set remains:

```text
Audiveris
HOMR
Clarity
```

ST-OMR is not currently present in the Gateway engine enum, Stage 6 candidate runtime, or Stage 7 comparison quorum. The current Stage 7 rule requiring at least two Canonical candidates remains unchanged.

ST-OMR does not write Canonical Score directly, does not approve corrections, and does not publish.

## Long-term migration option

The project may later make ST-OMR the primary or sole production OMR, but that is a **migration target**, not current truth.

The safe migration sequence is:

```text
ST-OMR health-only service foundation
  -> ST-OMR SHADOW
  -> ST-OMR PRIMARY
  -> ST-OMR ONLY (optional, evidence-gated)
```

The **ST-OMR health-only service foundation** remains the next narrow runtime gate inherited from the original architecture contract. It may prove isolated health/readiness and service safety properties only. It must not load an AI model, process user files, join Gateway orchestration, enter Ensemble comparison, train from teacher corrections, expose a public endpoint, or grant production authority.

### Shadow gate

ST-OMR may first run without production decision authority. Required evidence includes exact model/data provenance, deterministic source/job/model binding, category-stratified evaluation and comparison against teacher-gold plus the current engine baseline.

### Primary gate

ST-OMR may become primary only after fixed benchmark and real-world shadow evidence proves no material regression across notation categories, scan quality, publisher/font variation, page complexity and document-level semantic correctness.

### Sole-OMR gate

Removing Audiveris/HOMR/Clarity from the production path requires a versioned Stage 7 migration contract. The old `>=2 independent Canonical candidates` rule must not be silently bypassed. The replacement safety model must explicitly define:

- specialist evidence boundaries;
- deterministic musical constraints;
- calibrated abstention/uncertainty;
- teacher-review correction rate thresholds;
- end-to-end MusicXML semantic correctness;
- measure/rhythm/meter/pitch/voice exactness;
- structural validity;
- adversarial/corrupt-input behavior;
- rollback to the previous validated ST-OMR release;
- model/dataset/release governance.

Multiple heads from one shared model must not be misrepresented as independent OMR engines. Correlated specialist evidence is different from independent engine quorum.

After a proved migration, Audiveris/HOMR/Clarity may remain offline benchmark/reference engines even if removed from production runtime.

## Input contract

ST-OMR receives only server-controlled prepared immutable page artifacts/references. It rejects raw external uploads, arbitrary URLs, caller credentials, caller-selected commands and direct caller-controlled storage paths.

The Gateway remains responsible for source validation, immutable source identity, bounded preparation, page ordering/orientation policy, artifact SHA-256/media type and job/run identity.

## Output and provenance contract

Every future ST-OMR run must preserve distinct immutable artifacts/evidence for:

1. raw specialist/model output;
2. deterministic composition/validation evidence;
3. MusicXML candidate;
4. bounded diagnostics;
5. uncertainty/abstention evidence when applicable.

Every release/run must bind exact engine version, model version, model checksum, training/evaluation provenance and source/job/run identity.

Confidence is advisory evidence, not winner authority.

## Model manifest

`contracts/st-omr-model-manifest-v1.schema.json` remains the release-provenance contract. A model manifest is evidence, not deployment authority.

Required release gates include:

1. model checksum verified;
2. training provenance verified;
3. dataset consent/licence verified;
4. fixed evaluation completed;
5. regression tests passed;
6. manual release approval recorded.

Automatic promotion is forbidden.

## Teacher-correction and training boundary

The live ScoreMosaic system does not train itself.

Teacher corrections may enter a future training corpus only through explicit permission, reviewed privacy handling, quality control, versioned immutable datasets, preserved frozen evaluation sets, regression testing and a new immutable model release.

A live correction never modifies a deployed model in place.

## Runtime security requirements

A future ST-OMR runtime must use:

- isolated service/container boundary;
- pinned dependencies and model checksum;
- non-root execution;
- read-only root filesystem where applicable;
- bounded temporary workspaces;
- outbound-network default deny;
- CPU/memory/disk/page/time limits;
- no public route;
- no caller-controlled executable options;
- no credential material inside model contracts.

## Current fixed locks

```text
stOmrIntegratedIntoGateway=false
stOmrInStage7Quorum=false
productionDeploymentEnabled=false
publicEndpointEnabled=false
liveTrainingEnabled=false
selfTrainingEnabled=false
automaticModelPromotionEnabled=false
automaticCorrectionEnabled=false
winnerSelectionAuthority=false
teacherApprovalEnabled=false
publicationEnabled=false
mayRemoveExistingProductionEnginesNow=false
```

## Acceptance principle

Training success alone is insufficient. ST-OMR promotion is based on end-to-end musical correctness, safety, provenance, abstention behavior and regression evidence, not only symbol-level F1.
