# Security Boundaries

Current architecture state contract: `contracts/architecture-current-state-v1.json`

## 1. Trust model

All external documents, engine-produced MusicXML/MXL, filenames, metadata, model/model-download material and remote-service responses are untrusted until the applicable validation boundary passes.

A successful OMR process exit does not imply that output is safe, structurally valid, musically correct, approved or publishable.

Two independent mandatory data gates remain central:

1. **Safe Intake Gate** — protects the platform from untrusted PDF/image input.
2. **Candidate Safety Gate v1** — protects Canonical/Ensemble processing from untrusted engine output.

AI/OMR output is evidence, not authoritative musical truth.

## 2. External exposure

- Public production API/upload traffic is not activated.
- Audiveris, HOMR and Clarity remain private candidate-engine services.
- ST-OMR is not currently integrated into Gateway/Stage 7.
- Controlled-staging authenticated private dispatch/execution exists through Stage 5.
- Controlled staging must not be described as public or production orchestration.
- Real production service credentials, provider resources, DNS/TLS and production public traffic remain locked. The verified fixture-only GitHub Pages preview is the sole current public exception and has no API or production authority.
- Engine services must never receive browser-visible API keys or caller-controlled executable options.

## 3. Safe Intake Gate

Before an external PDF/image can enter later processing, the platform requires central fail-closed intake evidence for:

- signature and MIME verification;
- request byte limits;
- PDF page limits;
- decoded image/pixel limits;
- safe supported-format allowlists;
- server-owned job IDs and paths;
- filename/path safety;
- bounded CPU/memory/time/output behavior;
- isolated non-root processing;
- no execution/following of embedded files, scripts, links or external resources.

Current B.1-B.6 controls include strict PDF structural/page inspection and static JPEG/PNG inspection. Existing limits remain part of the Safe Intake v1 contract, including bounded parser workers and explicit image/pixel ceilings. Encrypted PDFs remain rejected in Safe Intake v1.

Safe Intake completion does not grant public upload authority.

## 4. Candidate Safety Gate v1

Every candidate is treated as fresh untrusted input before Canonical admission.

### MusicXML controls

- bounded artifact/XML byte size;
- NUL rejection;
- entity declaration rejection;
- only explicitly accepted canonical MusicXML doctype handling;
- no external entity/network resolution;
- expected root forms only;
- bounded XML depth/element/attribute counts;
- structural safety separated from musical correctness.

### MXL controls

- treat MXL as an untrusted ZIP;
- bound archive size, entry count, expanded size and compression ratio;
- reject encrypted/symlink/traversal/absolute/backslash/NUL/duplicate entries;
- require `META-INF/container.xml`;
- reject DTD/entity declarations in container metadata;
- require one declared root MusicXML file and verify it exists.

Passing Candidate Safety means only safe-enough structured input for the next controlled stage.

## 5. Controlled execution and candidate persistence

Stage 5 and Stage 6 are active only at controlled-staging/integration level.

Required invariants:

- exact authenticated dispatch identity;
- fixed allowlisted private destinations;
- fixed method/path;
- bounded timeout/cancellation;
- one-attempt/zero-retry v1 policy;
- no silent re-execution after ambiguous remote execution;
- exact source/job/run/result identity binding;
- bounded engine-specific result parsing;
- create-once immutable candidate artifacts;
- HMAC-sealed persistence records;
- artifact-byte revalidation on replay;
- reconciliation-only recovery for ambiguous execution.

Production/public orchestration is not activated by this staging evidence.

## 6. Canonical and Ensemble boundary

Stage 7 requires at least two Canonical candidates before comparison.

- Canonical admission is deterministic and fail closed.
- Comparator/report are neutral and read-only.
- Engine confidence cannot grant winner authority.
- Missing evidence is reported as unavailable rather than invented.
- Candidate order normalization must remain deterministic.

Any future ST-OMR-only design requires a versioned migration instead of silently bypassing Stage 7 independence/quorum assumptions.

## 7. Teacher Review boundary

Stage 8 repository foundations enforce:

- reviewer/resource authorization before mutation;
- closed ScoreEditCommand vocabulary;
- exact-current parent and old-value preconditions;
- immutable TeacherScoreRevision lineage;
- deterministic validation with no silent repair;
- corrected MusicXML as a derivative, not an overwrite;
- explicit human approval bound to exact revision/artifact;
- publication eligibility separate from approval;
- publisher-bound non-executing handoff before any external effect.

The external publication effect remains locked.

## 8. Browser/UI boundary

Stage 10/11 are disconnected repository/local-integration layers. `UI Architecture Phase 1` is an approved unnumbered product-design workstream above those layers; it does not activate transport or authority.

Current browser rules:

- `connect-src 'none'`;
- repository-local scripts only;
- no browser persistence;
- no production artifact reads;
- no credentials;
- no dynamic HTML/code execution;
- no service worker;
- no server write;
- no approval/publication/playback authority.

Typed local reads and `editIntent.prepare` are non-authoritative. A local edit intent is not a ScoreEditCommand.

UI Phase 1 may define navigation, Dashboard/Documents/New Document flows, Score Viewer interactions, Structured Edit UX, revision/validation presentation, approval/publication presentation and a Design System. These visual/product decisions must not reinterpret a displayed state as server authority.

Any future live UI integration requires a separate gate for authentication/session, tenant/resource authorization, exact API scope, CSRF/origin/CSP, exact-current revision checks, old-value preconditions, idempotency/failure/retry, privacy-safe errors/logs, audit and rollback.

## 9. Downstream music-application boundary

A downstream music application is a derivative consumer, not an upstream score authority.

Required invariants:

- production derivation does not consume raw OMR candidates or raw engine output;
- exact Canonical/Teacher revision and corrected MusicXML identity remain bound;
- production-derived output requires an approved TeacherScoreRevision unless a future versioned contract explicitly changes that rule;
- downstream results cannot mutate Canonical Score or TeacherScoreRevision;
- downstream results cannot approve or publish;
- browser code cannot call downstream engines directly;
- stale source revision invalidates currentness of older downstream results;
- downstream failure cannot corrupt or roll back ScoreMosaic state.

The reserved MusicXML-to-GuitarTab-Engine seam remains architecture-only. Any future live integration requires dedicated service authentication, bounded transport, idempotency/failure handling, exact source lineage, engine/model version provenance, and rollback/disable evidence.

## 10. Storage and artifact controls

- source paths and artifact identities are server-derived;
- source documents and raw engine results are immutable;
- candidate/revision/publication/downstream derivatives are new artifacts, never overwrites;
- SHA-256 and provenance remain bound to stored content;
- conflicting create-once writes fail closed;
- service writable areas remain separated;
- restore must revalidate content identity and lineage.

Stage 9 documents production PostgreSQL/object-storage architecture but does not activate those providers.

## 11. Production infrastructure boundary

Stage 9 repository contracts document the planned Hetzner/Coolify, PostgreSQL 18, object-storage, Authentik and Infisical boundaries.

The following remain false:

```text
providerResourcesCreated=false
productionCredentialsProvisioned=false
productionNetworkActivated=false
productionDatabaseActivated=false
productionObjectStorageActivated=false
productionIdentityActivated=false
productionSecretsActivated=false
publicApiActivated=false
publicTrafficActivated=false
publicationExecutionActivated=false
```

Real provider configuration and billing authority are outside repository-only development.

## 12. Logging and privacy

Logs may expose bounded operational identifiers such as job ID, engine identity/version, lifecycle state, duration/resource summary and stable error category.

Logs/external errors must not expose:

- source document contents;
- full MusicXML;
- credentials/tokens;
- raw subprocess output;
- provider exception text;
- unrestricted local paths;
- sensitive filename-derived personal information.

## 13. Supply chain

Required principles:

- pin dependencies and engine/model revisions;
- verify model/runtime artifacts with checksums;
- never fetch mutable `latest` during production requests;
- pin GitHub Actions to immutable SHAs;
- add repository-owned vulnerability/dependency/secret scanning before production readiness;
- pin production container base images by digest;
- retain SBOM/provenance for production releases.

## 14. ST-OMR migration boundary

ST-OMR may become primary or sole production OMR only after explicit migration evidence.

Required gates include:

- immutable model/dataset provenance;
- teacher-gold and untouched-final evaluation;
- notation-category and scan-quality stratification;
- document-level semantic correctness;
- deterministic musical validation;
- calibrated abstention/uncertainty;
- adversarial input tests;
- no-regression evidence against current baseline;
- rollback and retained prior validated model.

Training success or a high symbol F1 alone does not authorize production promotion or removal of existing engines.

## 15. Threat-test catalogue

Required negative coverage includes at minimum:

### Intake
- renamed/unsupported input;
- malformed/truncated/oversized PDF or image;
- page/pixel/dimension overflow;
- encrypted PDF;
- path/control/device filename attacks;
- bounded parser timeout/memory failures.

### Candidate output
- XML entity/doctype attacks;
- oversized/deep/high-count XML;
- malformed MXL/ZIP traversal/symlink/encryption/duplicate members;
- missing/multiple invalid rootfiles;
- non-MusicXML content substitution.

### Runtime/lifecycle
- timeout/crash/partial output;
- duplicate request/replay;
- cancellation races;
- restart during execution;
- result/job/source mismatch;
- unauthorized dispatch;
- stale or cross-resource Teacher Review mutation;
- stale approval/publication artifacts;
- browser authority escalation;
- ST-OMR model/version/provenance substitution;
- direct-browser downstream-engine call attempt;
- raw-OMR-to-GuitarTab production bypass attempt;
- stale TeacherRevision used as current downstream source;
- downstream result attempting Canonical/TeacherRevision mutation.

## 16. Stop rule

Repository-only work may continue only while production/live activation remains false. Stop before paid resource creation, real credentials, DNS/TLS changes, new public traffic beyond the authorized fixture-only Pages preview, production writes, destructive provider operations, actual publication execution, or live downstream music-service activation unless a separate explicit operational gate authorizes that action.
