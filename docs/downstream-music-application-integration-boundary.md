# ScoreMosaic Downstream Music Application Integration Boundary

Status: **architecture-only future integration boundary; no live integration activated**  
Current architecture state contract: `contracts/architecture-current-state-v1.json`  
Boundary contract: `contracts/downstream-music-application-integration-v1.json`

## 1. Purpose

ScoreMosaic may later feed validated musical artifacts into sibling applications such as MusicXML-to-GuitarTab-Engine, playback/workstation tools, orchestration tools or export services. These integrations must remain downstream of ScoreMosaic's musical-truth and Teacher Review boundaries.

No downstream application may silently become an OMR engine, Canonical authority, Teacher Review authority, approval authority or publication authority.

## 2. Safe integration position

```text
PDF / image
  -> ScoreMosaic OMR
  -> Canonical Score
  -> Teacher Review
  -> deterministic validation
  -> corrected MusicXML
  -> explicit human approval
  -> approved revision/artifact identity
  -> DOWNSTREAM MUSIC APPLICATION BOUNDARY
       -> GuitarTab Engine
       -> playback/workstation
       -> orchestration
       -> other bounded derivatives
```

For non-production preview experiments, a validated Canonical/Teacher revision may be used when clearly labeled non-authoritative. Production-derived outputs require an exact approved teacher revision and exact corrected MusicXML hash.

## 3. Prohibited sources

Downstream production derivation must not consume:

- raw OMR engine output;
- unvalidated engine candidate MusicXML;
- browser-edited ad hoc XML;
- stale revision content presented as current;
- renderer-native state as musical truth.

## 4. Immutable lineage

Every downstream request/result must remain traceable to exact upstream identity.

Required bindings include:

```text
documentId
  -> canonicalScoreId
  -> teacherRevisionId
  -> correctedMusicXmlSha256
  -> integrationRequestId
  -> targetEngineVersion
  -> resultSha256
```

If the source TeacherScoreRevision changes, an older downstream result may remain historical evidence but must not remain current by implication.

## 5. UI/application boundary

The UI must never call a downstream music engine directly.

```text
UI
  -> typed application contract
  -> dedicated application adapter
  -> future authenticated transport
  -> downstream engine
```

Transport details remain adapter-owned. A visual redesign or navigation change must not require the browser to know engine hostnames, credentials or provider details.

## 6. MusicXML-to-GuitarTab-Engine

The intended role is:

```text
validated/approved MusicXML
  -> GuitarTab application contract
  -> GuitarTab adapter
  -> MusicXML-to-GuitarTab-Engine
  -> non-authoritative TAB/fingering candidates
  -> guitar-domain validation/evidence
```

GuitarTab Engine must preserve the source music and derive guitar realization evidence rather than rewriting ScoreMosaic's Canonical or TeacherScoreRevision state.

Required guitar context may include:

- tuning;
- fret domain;
- capo policy;
- instrument profile;
- playability constraints.

Expected evidence may include:

- string/fret assignment;
- alternative fingerings;
- position/playability evidence;
- abstention or `NO_SCORE`-style outcome where no safe realization should be asserted.

## 7. Future Guitar TAB workspace

UI Architecture Phase 1 does not implement Guitar TAB, but it deliberately leaves a safe extension point.

A later product workspace may contain:

```text
+--------------------------------------------------------------+
| Standard Notation                                            |
+--------------------------------------------------------------+
| Guitar TAB                                                   |
+-----------------------------+--------------------------------+
| Fingering Options           | Position / Playability Evidence|
+-----------------------------+--------------------------------+
```

This workspace can be added to navigation or document actions without changing Teacher Review's authority model.

## 8. Failure isolation

A GuitarTab/downstream integration failure must never:

- corrupt the ScoreMosaic document;
- mutate Canonical Score;
- create or overwrite TeacherScoreRevision;
- change approval state;
- publish anything;
- make a stale derived artifact current.

Failure produces bounded downstream status/evidence only.

## 9. Current locks

```text
guitarTabLiveIntegrationActivated=false
networkTransportActivated=false
productionCredentialsActivated=false
productionDerivedTabPublicationActivated=false
```

This document reserves a safe architectural seam only. It does not connect repositories or services.
