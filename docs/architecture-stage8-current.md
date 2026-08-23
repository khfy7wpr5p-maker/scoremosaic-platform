# ScoreMosaic Stage 8 Current Architecture

Status: **Stage 8-A through Stage 8-O merged; synchronized through Stage 11-F**  
Current architecture state contract: `contracts/architecture-current-state-v1.json`

Stage 8 completed the repository-only Teacher Review and publication-preparation chain. Its stop boundary applies specifically to the **external production publication effect**. It does not prohibit later repository-only architecture, UI, or contract work; Stage 9-11 were subsequently completed without crossing that external effect.

## Current Stage 8 trust chain

```text
Stage 7 immutable read-only evidence
  -> Review Report + exact Canonical SHA-256
  -> HMAC-sealed reviewer/tenant/resource authorization
  -> closed bounded ScoreEditCommand
  -> exact parent + stable musical location
  -> old-value SHA-256 precondition
  -> deterministic Canonical-derived review musical state
  -> deterministic post-edit validation evidence
  -> immutable draft TeacherScoreRevision
  -> controlled durable exact-parent append
  -> authorization-first read-only review projection
  -> disconnected read-only browser review
  -> exact revision/state corrected-MusicXML derivative
  -> generated-XML safety + Canonical semantic round-trip
  -> server-authorized non-network write boundary foundation
  -> disconnected local BrowserEditIntent
  -> exact-current rational review timeline
  -> non-executing presentation transport state
  -> exact-current approval-candidate evidence
  -> exact human-approval handoff
  -> [HUMAN DECISION]
  -> explicit-human immutable approval record foundation
  -> fresh publication-handoff eligibility evidence
  -> exact publisher-bound non-executing PublicationHandoffRequest
  -> state=awaiting_external_publication_execution
  -> [EXTERNAL PRODUCTION SIDE-EFFECT BOUNDARY]
  -> [LOCKED] production persistence/write
  -> [LOCKED] actual publication execution
  -> [LOCKED] published-artifact record
```

Engine/AI evidence never becomes authoritative musical truth. Teacher work remains an immutable lineage separate from source artifacts, engine candidates, Stage 7 Canonical artifacts and Ensemble evidence.

## Stage 8-A through 8-C

Merged foundations include purpose-separated reviewer authorization, closed typed edit commands, immutable draft revisions, append-only audit lineage, exact-parent durable storage, deterministic Canonical-derived review state, old-value/location preconditions and visible validation with no silent repair.

## Stage 8-D through 8-H

- **8-D:** authorization-first read-only review projection; no HTTP route.
- **8-E:** disconnected fail-closed browser review workspace; no mutation/approval/publication/playback authority.
- **8-F:** corrected MusicXML derivative with structural safety and Canonical semantic round-trip; production persistence locked.
- **8-G:** server-authorized in-process write-boundary foundation; `write-api-enabled=false`, `public-api-enabled=false`.
- **8-H:** disconnected typed BrowserEditIntent; no server authority.

## Stage 8-I through 8-O

- **8-I:** exact-current rational timeline; no audio/network/runtime authority.
- **8-J:** non-executing transport presentation state; audio and mutation authority false.
- **8-K:** approval-eligibility evidence with exact durable head, independently rebuilt corrected MusicXML, structural safety, semantic round-trip equality and zero blocking/unresolved issues.
- **8-L:** exact human-approval handoff with `state=awaiting_human_decision`; human authority boundary.
- **8-M:** explicit-human immutable approval-record foundation; no inferred/default approval.
- **8-N:** publication-eligibility evidence; `productionPublicationEligible=false` remains fixed.
- **8-O:** publisher-bound non-executing handoff; `canExecutePublication=false`, `canWriteExternal=false`, `canPersistProduction=false`, `publicationGranted=false`.

## External publication-effect boundary

Stage 8-O is the final repository-only preparation layer before an actual external publication effect. The following still require concrete external facts/authority:

- production identity/session provider and RBAC source;
- exact publisher identity/destination;
- production durable/object-store provider;
- authenticated transport and provider credentials;
- explicit external execution authority;
- published-artifact/audit persistence semantics against the real provider.

No later repository stage may reinterpret Stage 8-O as permission to publish.

## Later repository-only work completed safely

After Stage 8, the project continued only on boundaries that did not execute the publication effect:

- **Stage 9-A through 9-I:** production architecture/contracts; real provisioning deferred.
- **Stage 10-A through 10-F:** disconnected repository UI experience.
- **Stage 11-A through 11-F:** typed local UI/application contracts, state model and disconnected integration.

These later stages do not activate production publication, production persistence, public API traffic, auth runtime, server write, or playback.

## Still locked / not proved

- actual production publication execution;
- production publication persistence and published-artifact record;
- production identity/session/RBAC wiring;
- live Teacher Review/public HTTP routes;
- production DB/object-store deployment;
- corrected MusicXML production persistence/transport;
- browser writable production editor activation;
- real-time audio/MIDI/SoundFont playback;
- production traffic.

See `docs/architecture-stage9-11-current.md` for the later current boundary.
