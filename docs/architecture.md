# ScoreMosaic Architecture

## 1. Purpose

ScoreMosaic receives an untrusted score document, preserves the source, runs isolated OMR engines, validates every engine-produced candidate as untrusted data, normalizes safe musical content, compares candidates, and produces structured evidence for teacher review.

ScoreMosaic is an OMR and review-support platform. It is not the learner-facing playback, narration, or lesson application.

## 2. Secure target architecture

```text
External application
        |
        | versioned authenticated HTTPS API
        v
+---------------------------+
| Safe Intake Gate          |
| - signature / MIME        |
| - bytes / pages / pixels  |
| - filename / path safety  |
+---------------------------+
        |
        v
Immutable source artifact
SHA-256 + provenance
        |
        v
OMR Gateway / job orchestration
        |
        +-------------------+-------------------+
        |                   |                   |
        v                   v                   v
  homr-service       clarity-service     audiveris-service
        |                   |                   |
        +-------------------+-------------------+
                            |
                            v
+------------------------------------------------+
| Candidate Safety Gate v1                       |
| MXL ZIP safety + XML declarations + budgets    |
+------------------------------------------------+
                            |
                            v
                    Canonical Score
                            |
                            v
                   Ensemble Comparator
                            |
                            v
                  Review report/evidence
                            |
                            v
              Teacher Review Score Editor
                            |
                            v
              Immutable TeacherScoreRevision
                            |
                            v
          Musical + structural validation
                            |
                            v
              Corrected MusicXML derivative
                            |
                            v
              MusicXML safety validation
                            |
                            v
              Canonical re-normalization
                            |
                            v
        Revision/semantic consistency check
                            |
                            v
                   Approval barrier
                            |
                            v
                  Published MusicXML
```

The Safe Intake Gate protects the platform from untrusted external documents. The Candidate Safety Gate protects the platform from untrusted **engine output**. These are separate trust boundaries and neither may be skipped.

Gate B.4 adds one implementation boundary inside Safe Intake: exact PDF bytes are passed to a bounded private helper subprocess using exact-pinned `pypdf==6.14.2` with `strict=True` to derive structural/page evidence. The helper does not render pages, extract text/images/attachments, follow links, execute embedded content, persist bytes, or enable external upload. Encrypted PDFs are rejected in Safe Intake v1.

Gate B.5 likewise leaves the target architecture unchanged. Exact immutable JPEG/PNG bytes are inspected in a bounded private helper using exact-pinned `Pillow==12.3.0`; only static JPEG/PNG is accepted, dimensions are server-derived, each dimension is capped at 12,000 px, total pixels are capped at 40,000,000, and the helper is bounded by a 256 MiB address-space limit and a 3-second timeout. The helper persists nothing and does not enable upload or orchestration.

Gate B.6 validates original filename metadata without deriving caller-controlled filesystem paths. The integrated `decide_safe_intake()` boundary then composes B.1-B.6 over one exact immutable payload and returns only bounded server-derived evidence after all required checks pass. The hostile-input convergence suite verifies representative fail-closed categories through that integrated decision. None of these Gate B slices enables HTTP upload, storage, or engine dispatch.

Gate C.1 and Gate C.2-A through C.2-G contract foundations are present on `main`. Together they define service identity/environment credential binding, authenticated request envelopes, exact test/staging target allowlisting, job/source/run/result identity binding, credential-generation/rotation and replay-reservation semantics, receiver verification convergence, deterministic timeout/cancellation decisions, and the orchestration v1 one-attempt/zero-retry budget. C-DIAG-1 is also present: HOMR, Clarity, and Audiveris runtime stdout/stderr and provider exception text are replaced by bounded stable markers or reason codes, and failed readiness responses suppress untrusted runtime/version/model fields. C-DIAG-2 is present as the bounded outward diagnostic convergence for C.2-E/F/G: receiver-verification, dispatch-deadline, retry-budget, and unexpected dispatch exceptions map to a closed immutable version/stage/reason payload without inspecting exception text, trusted mappings require exact exception types, and diagnostic fields require exact `str` values. Production has no authorized dispatch origin. The reserved future `POST /internal/transcribe` target is not registered and no live engine receiver route or network dispatch is enabled.

Gate D.1-D.6 are present as the durable job/artifact state and recovery **contract/convergence foundation**. They define closed durable job state, server-derived idempotency slots, immutable storage authority and content identity, append-only provenance evidence, restart-recovery decisions, and cross-layer partial-output/crash-window convergence. These contracts do not select or operate a database/object-store provider, durable replay adapter, queue/worker, process restart mechanism, storage writer, or live orchestration runtime.

Gate E.1 and Gate E.2 provide the first external API security foundations without activating the external API. E.1 produces bounded authenticated external-principal evidence through a provider-neutral verifier seam. E.2 evaluates deny-by-default exact principal/environment/operation grants from a server-owned policy. Authentication and authorization remain distinct, and E.2 authorization evidence carries no operation-execution, upload, job-creation, network-dispatch, or orchestration authority. Provider/runtime wiring, resource/tenant scope where an authoritative ownership model exists, rate/abuse protection, safe upload sessions, request/idempotency binding, and live privacy-safe API behavior remain later Gate E work.

The Teacher Review Score Editor architecture is defined by [`teacher-review-score-editor-architecture-contract.md`](teacher-review-score-editor-architecture-contract.md). That contract refines the future Gate F boundary without changing the Gate C -> D -> E -> F -> G security order. It does not activate a Teacher Review API, editor, storage, playback, approval, or publication capability.

UI-0A is a documentation-only visual/application-shell foundation. UI-0B is an isolated repository-owned static HTML/CSS prototype built on that visual contract; it remains disconnected and non-production, with no backend, rendering authority, editor writes, playback runtime, authentication, approval, or publication capability. Neither UI foundation changes the Teacher Review or security-gate authority model.

## 3. Current activation state

The repository contains substantial runtime and comparison foundations, but the public data plane remains deliberately closed.

### Enabled foundations

- Private HOMR, Clarity-OMR, and Audiveris runtime adapters.
- Private OMR Gateway health and orchestration contracts.
- Safe Intake Gate B foundation: B.1 signature classification, B.2 MIME/signature binding, B.3 observed byte-budget enforcement, B.4 strict PDF structure/page-budget inspection, B.5 decoded static JPEG/PNG image/pixel enforcement, B.6 original filename safety, the integrated fail-closed intake decision, and hostile-input convergence coverage.
- Gate C.1 service identity/environment-scoped credential foundation.
- Gate C.2-A deterministic HMAC-SHA256 authenticated request-envelope and receiver-verification foundation.
- Gate C.2-B immutable exact test/staging engine-origin plus method/path dispatch-target allowlist foundation; production remains fail-closed and live dispatch remains disabled.
- Gate C.2-C exact dispatch job/source/run/candidate/artifact/result identity-binding foundation.
- Gate C.2-D credential-generation, bounded rotation, and persistence-neutral replay-reservation semantics foundation; no durable replay store is activated.
- Gate C.2-E fail-closed receiver verification adapter foundation producing immutable verified dispatch evidence without registering a live route.
- Gate C.2-F deterministic timeout/cancellation decision foundation with fresh result-arrival evaluation and terminal non-reopening behavior; no timers/process control are activated.
- Gate C.2-G bounded retry/attempt-budget foundation preserving one total v1 attempt and zero retries; it cannot create or start another run.
- C-DIAG-1 bounded engine runtime diagnostic redaction across HOMR, Clarity, and Audiveris probe, readiness, transcription-result, and raised-error surfaces; no runtime output or provider exception text becomes dispatch authority.
- C-DIAG-2 bounded receiver/dispatch outward diagnostic mapping for C.2-E/F/G failures; the payload is closed to version/stage/reason, exception text is not inspected, and non-exact string fields fail closed.
- Gate D.1-D.6 durable job/artifact state, idempotency, immutable storage-authority, provenance, restart-recovery, and partial-output/crash-window contract/convergence foundations; no provider-backed persistence/runtime activation is implied.
- Gate E.1 provider-neutral external-principal authentication foundation; no provider SDK or public auth route is activated.
- Gate E.2 deny-by-default external authorization-decision foundation; even an allowed decision grants no operation-execution authority.
- Canonical Score and Ensemble comparison/report foundations.
- Immutable candidate/artifact lifecycle contracts.
- Candidate Safety v1 validation for HOMR, Clarity, and Audiveris outputs.
- Teacher Review Score Editor TR-0A architecture contract foundation; no runtime capability is activated by the document.
- UI-0A documentation-only visual/application-shell foundation.
- UI-0B isolated static application-shell prototype; disconnected, non-production, and non-authoritative.
- ST-OMR development foundations isolated from the production candidate path.

### Deliberately disabled or not yet implemented

- External upload and a public upload endpoint/session.
- Live authenticated Gateway engine dispatch/orchestration and receiver route wiring.
- Provider-backed durable replay/job/artifact/provenance persistence and storage writes.
- Production immutable object storage.
- Queue/worker/process restart runtime and automatic recovery execution.
- External authentication-provider/runtime wiring and versioned public API routes.
- Resource/user/tenant scope enforcement where applicable.
- External API rate/abuse controls, safe upload-session semantics, and request/idempotency wiring.
- Public publication.
- Teacher Review production API and writable editor runtime.
- Production approval/publication runtime.

A disabled capability must not be interpreted as implemented merely because its protecting foundation or configuration limits already exist. Gate B completion does not authorize upload activation, Gate C contract foundations do not authorize live dispatch, Gate D contract/convergence completion does not authorize provider-backed persistence or recovery execution, E.1/E.2 do not authorize a public API, UI-0B does not constitute a working Teacher Review editor, and TR-0A does not authorize Teacher Review runtime activation.

## 4. Service responsibilities

### omr-gateway

- Own the future external OMR job boundary.
- Require the integrated Safe Intake decision before any future external document can enter later processing.
- Derive PDF page evidence from exact bounded PDF bytes; do not trust caller-supplied page metadata.
- Keep PDF structural parsing in the bounded B.4 helper subprocess; current v1 rejects encrypted PDFs and does not render or extract document content.
- Derive JPEG/PNG dimensions and total pixel evidence from exact immutable bytes in the bounded B.5 helper; do not trust caller-supplied dimensions or permit animated image input.
- Validate original filename metadata through B.6 without converting it into a caller-controlled filesystem/storage path.
- Preserve server-owned job and artifact identity.
- Dispatch only to authenticated, allowlisted private engine endpoints after the completed C-DIAG-1/C-DIAG-2 and Gate D contract/convergence foundations are paired with separately reviewed operational credentials, replay/persistence, receiver/network wiring, and explicit activation.
- Apply explicit timeout, cancellation, retry, idempotency, and restart-recovery rules without widening the current v1 one-attempt/zero-retry contract by implication.
- Require exact Gate E authentication and authorization evidence before any future external operation is wired, while keeping authorization evidence separate from operation execution authority.
- Never bypass Candidate Safety v1 when accepting engine results.

### homr-service

- Run one pinned HOMR runtime in an isolated CPU-oriented environment.
- Accept only server-staged safe paths and fixed command options.
- Verify pinned model artifacts.
- Treat generated MusicXML as untrusted and enforce Candidate Safety v1 before returning it as an accepted candidate.
- Never approve or publish a score.

### clarity-service

- Run one pinned Clarity source/model combination in an isolated CPU environment.
- Keep model/network behavior controlled and offline during normal runtime.
- Sanitize only an allowed canonical MusicXML doctype before parsing.
- Enforce Candidate Safety v1 size and structural-complexity budgets.
- Never approve or publish a score.

### audiveris-service

- Run the pinned Audiveris runtime in an isolated non-root container.
- Accept only fixed server-controlled command options and safe workspace paths.
- Treat every produced `.mxl` archive as untrusted.
- Enforce Candidate Safety v1 ZIP/member/container/XML limits before the artifact can cross the candidate boundary.
- Preserve `.omr` project artifacts separately when present.

### ensemble-service

- Consume only candidates that have passed the applicable safety boundary.
- Preserve engine identity, version, timing, errors, hashes, and artifact references.
- Normalize safe MusicXML into the Canonical Score model.
- Compare measure, pitch, rhythm, rest, chord, voice, staff, and TAB evidence.
- Produce deterministic review evidence with provenance.
- Never silently overwrite, merge, approve, or publish an engine result.

### ST-OMR

ST-OMR remains an isolated development track. Its current synthetic/model-runtime contracts do not authorize user input, Gateway integration, MusicXML publication, or production dispatch. Before ST-OMR can join the candidate path it must satisfy the same intake/output trust boundaries and integration gates as other engines.

## 5. Data flow and trust transitions

1. **Receive external document** — still disabled in the current runtime; no upload endpoint exists.
2. **Safe Intake Gate** — the completed Gate B foundation applies B.1 signature classification, B.2 MIME/signature binding, B.3 observed byte-budget enforcement, B.4 strict PDF structure/page inspection, B.5 static JPEG/PNG dimension/pixel inspection, B.6 filename safety, and one integrated fail-closed decision over the exact immutable bytes. Hostile-input convergence validates the central boundary.
3. **Seal immutable source** — assign server-owned identity and SHA-256/provenance.
4. **Create durable job/state evidence** — Gate D.1-D.6 define the fail-closed state/idempotency/storage-authority/provenance/restart/crash-window contract. Actual provider-backed persistence, queue/worker behavior, and durable writes remain disabled until separately reviewed and activated.
5. **Dispatch private engine runs** — C.1/C.2-A-C.2-G contract foundations define identity, authenticated-request, target, rotation/replay semantics, receiver verification, timeout/cancellation, and one-attempt/zero-retry policy evidence. C-DIAG-1 prevents raw engine runtime output/provider exception text from crossing current safe surfaces, while C-DIAG-2 bounds outward receiver/dispatch diagnostics for C.2-E/F/G failures. Live receiver routes/network dispatch remain disabled pending operational credentials/replay persistence, receiver wiring, and explicit activation.
6. **Preserve raw engine output** — raw artifacts remain distinct and immutable after sealing.
7. **Candidate Safety Gate v1** — validate MXL/ZIP and MusicXML before canonical/ensemble parsing.
8. **Canonicalize safe candidates** — retain provenance.
9. **Compare candidates** — disagreements remain evidence, not automatic corrections.
10. **Teacher review** — the future authorized Teacher Review Score Editor consumes source/candidate/canonical/report evidence and emits new immutable `TeacherScoreRevision` artifacts; it never mutates upstream artifacts. UI-0A/UI-0B provide only visual/static prototype evidence and do not implement this runtime.
11. **Revision validation and corrected MusicXML derivation** — materialize only from an exact immutable teacher revision, re-run structural/security checks, and verify canonical/revision consistency before approval eligibility.
12. **Approval barrier** — bind approval to exact revision/artifact hashes, reviewer identity, and blocking-issue/waiver state.
13. **Publication** — only the explicitly eligible approved artifact may become learner-facing output.

The detailed Teacher Review authority, adapter boundaries, immutable revision direction, and secure implementation sequence are defined in [`teacher-review-score-editor-architecture-contract.md`](teacher-review-score-editor-architecture-contract.md). The product-level review behavior remains documented in [`teacher-review-workflow.md`](teacher-review-workflow.md).

## 6. Candidate Safety v1

`contracts/candidate-safety-policy-v1.json` is the common engine-output safety policy for HOMR, Clarity, and Audiveris.

The policy requires, among other controls:

- bounded artifact and XML size;
- bounded XML depth, element count, and attribute count;
- rejection of entity declarations and unsafe doctypes;
- expected MusicXML root types only;
- `.mxl` entry-count and total-expanded-size limits;
- compression-ratio limits;
- rejection of encrypted entries, symlinks, duplicate members, absolute paths, and traversal paths;
- a valid `META-INF/container.xml` with exactly one declared rootfile.

Candidate validation is a **security gate**, not a musical-correctness judgment. A candidate that passes can still be musically wrong and must continue through canonical comparison and teacher review.

## 7. Artifact policy

Artifacts remain distinct by trust stage and purpose:

```text
source/original.pdf
engines/homr/raw.musicxml
engines/clarity/raw.musicxml
engines/audiveris/raw.mxl
engines/audiveris/project.omr
canonical/<candidate-id>.json
ensemble/review-report.json
revisions/teacher-revision-0001
revisions/teacher-revision-0002
corrected/<revision-id>.musicxml
approved/approved.musicxml
```

Raw output is never silently overwritten by a corrected revision. Sanitized/normalized derivatives must be separate logical artifacts with provenance back to the raw source. Gate D now defines immutable storage-authority and provenance contracts for the OMR job/candidate layer, but the concrete provider-backed durable storage layout remains unactivated; these paths are architectural examples, not an active persistence layout.

## 8. Job lifecycle

Public lifecycle vocabulary remains:

```text
received
validated
queued
processing
candidates_ready
needs_review
under_review
corrected
approved
rejected
published
failed
expired
```

Implementation may introduce internal substates, but public transitions must remain explicit and auditable. No state may imply durable success before required artifacts are durably stored and verified.

## 9. Integration boundary

External applications integrate through a versioned API and never access engine containers, local storage paths, or model files directly.

Before external or staging upload exposure, the integration boundary must demonstrate:

- E.1-compatible provider/runtime authentication and E.2-compatible deny-by-default authorization for every activated operation;
- resource/user/tenant scope enforcement where an authoritative ownership model exists;
- rate limiting and abuse controls;
- external request/idempotency binding;
- cancellation and retry semantics;
- approved live receiver/dispatch wiring on top of the completed C.1/C.2-A-C.2-G and C-DIAG-1/C-DIAG-2 foundations;
- operational provider-backed durable replay/job/artifact/provenance state and restart behavior consistent with the completed Gate D.1-D.6 contract/convergence foundation;
- the completed Safe Intake decision wired as a mandatory pre-processing boundary;
- safe upload-session semantics;
- Candidate Safety v1 enforcement;
- privacy-safe external error/logging behavior.

A live writable Teacher Review surface additionally requires Gate D operational durable state, Gate E external/API security, and the TR-8A reviewer RBAC/audit authorization foundation before TR-4 may be activated. Generic E.2 authorization does not replace reviewer RBAC. This dependency is normative in the TR-0A architecture contract.

## 10. Deployment environments

- Development: GitHub Codespaces / local development
- Automated verification: GitHub Actions
- Integration environment: Coolify staging
- Production: blocked until explicit production-readiness acceptance gates pass

Engine containers remain private in all environments. Staging availability does not itself authorize public upload or production publication.

## 11. Non-goals of the current architecture foundations

The current architecture and documentation foundations do **not** enable:

- public uploads or an upload endpoint;
- live Gateway dispatch;
- automatic candidate ranking/merging/correction;
- production storage;
- Teacher Review API or writable editor runtime;
- playback/cursor runtime;
- teacher approval endpoints;
- learner-facing publication;
- ST-OMR production integration.
