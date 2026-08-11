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
                    Teacher Review API
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

## 3. Current activation state

The repository contains substantial runtime and comparison foundations, but the public data plane remains deliberately closed.

### Enabled foundations

- Private HOMR, Clarity-OMR, and Audiveris runtime adapters.
- Private OMR Gateway health and orchestration contracts.
- Safe Intake Gate B foundation: B.1 signature classification, B.2 MIME/signature binding, B.3 observed byte-budget enforcement, B.4 strict PDF structure/page-budget inspection, B.5 decoded static JPEG/PNG image/pixel enforcement, B.6 original filename safety, the integrated fail-closed intake decision, and hostile-input convergence coverage.
- Canonical Score and Ensemble comparison/report foundations.
- Immutable candidate/artifact lifecycle contracts.
- Candidate Safety v1 validation for HOMR, Clarity, and Audiveris outputs.
- ST-OMR development foundations isolated from the production candidate path.

### Deliberately disabled or not yet implemented

- External upload and a public upload endpoint.
- Live Gateway engine dispatch/orchestration.
- Production persistence.
- Public publication.
- Teacher Review production API.
- Authenticated service-to-service dispatch.
- Durable job queue/state/restart recovery.
- External API authentication/authorization and rate/abuse controls.

A disabled capability must not be interpreted as implemented merely because its protecting foundation or configuration limits already exist. Gate B completion does not authorize upload activation.

## 4. Service responsibilities

### omr-gateway

- Own the future external OMR job boundary.
- Require the integrated Safe Intake decision before any future external document can enter later processing.
- Derive PDF page evidence from exact bounded PDF bytes; do not trust caller-supplied page metadata.
- Keep PDF structural parsing in the bounded B.4 helper subprocess; current v1 rejects encrypted PDFs and does not render or extract document content.
- Derive JPEG/PNG dimensions and total pixel evidence from exact immutable bytes in the bounded B.5 helper; do not trust caller-supplied dimensions or permit animated image input.
- Validate original filename metadata through B.6 without converting it into a caller-controlled filesystem/storage path.
- Preserve server-owned job and artifact identity.
- Dispatch only to authenticated private engine endpoints once that capability is enabled.
- Apply explicit timeout, cancellation, retry, idempotency, and restart-recovery rules.
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
4. **Create durable job** — future persistence boundary; must support idempotency and restart recovery.
5. **Dispatch private engine runs** — only after service-to-service authentication is implemented.
6. **Preserve raw engine output** — raw artifacts remain distinct and immutable after sealing.
7. **Candidate Safety Gate v1** — validate MXL/ZIP and MusicXML before canonical/ensemble parsing.
8. **Canonicalize safe candidates** — retain provenance.
9. **Compare candidates** — disagreements remain evidence, not automatic corrections.
10. **Teacher review** — corrections create immutable revisions.
11. **Approval barrier** — teacher identity/revision hash/unresolved blocking issues are checked.
12. **Publication** — only the explicitly approved revision may become learner-facing output.

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
revisions/revision-0001.musicxml
approved/approved.musicxml
```

Raw output is never silently overwritten by a corrected revision. Sanitized/normalized derivatives must be separate logical artifacts with provenance back to the raw source.

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

- authentication and authorization;
- rate limiting and abuse controls;
- idempotency;
- cancellation and retry semantics;
- service-to-service authentication;
- the completed Safe Intake decision wired as a mandatory pre-processing boundary;
- durable job/artifact state;
- Candidate Safety v1 enforcement;
- safe error/logging behavior.

## 10. Deployment environments

- Development: GitHub Codespaces / local development
- Automated verification: GitHub Actions
- Integration environment: Coolify staging
- Production: blocked until explicit production-readiness acceptance gates pass

Engine containers remain private in all environments. Staging availability does not itself authorize public upload or production publication.

## 11. Non-goals of the current security slice

Gate B documentation convergence does **not** enable:

- public uploads or an upload endpoint;
- live Gateway dispatch;
- automatic candidate ranking/merging/correction;
- production storage;
- teacher approval APIs;
- learner-facing publication;
- ST-OMR production integration.
