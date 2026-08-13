# Security Boundaries

## 1. Trust model

All external documents, engine-produced MusicXML/MXL, filenames, metadata, model downloads, and remote-service responses are untrusted until the applicable validation boundary has passed.

A successful OMR process exit does not imply that its output is safe, structurally valid, musically correct, approved, or suitable for publication.

The platform therefore separates two mandatory data gates:

1. **Safe Intake Gate** — protects the platform from untrusted PDF/image input.
2. **Candidate Safety Gate v1** — protects canonicalization/comparison from untrusted OMR engine output.

## 2. External exposure

- Only a future versioned platform API may receive external traffic.
- HOMR, Clarity-OMR, Audiveris, and ST-OMR engine services remain on private container networks.
- Internal live dispatch must use authenticated service-to-service requests before it is enabled.
- Engine services must not receive browser-visible API keys.
- Development, staging, and production secrets must be separate.
- Current Gateway document upload and execution/orchestration remain disabled.
- Gate E.1 defines provider-neutral authenticated external-principal evidence, Gate E.2 defines deny-by-default authorization-decision evidence, Gate E.3A defines provider-neutral rate-admission evidence, Gate E.3B defines provider-neutral external request-idempotency admission evidence, Gate E.3C defines fail-closed fresh-rate/exact-request admission-composition evidence, and Gate E.4A defines bounded Safe Upload Session reservation evidence for the **exact canonical `platform.safe_upload_session` operation only**. None of these foundations registers a public route, accepts document bytes, executes an authorized operation, writes storage, creates a job, or enables network/orchestration behavior.

## 3. Safe Intake Gate

Before any external PDF/image job can be accepted for live processing, the Gateway data plane must enforce:

- file signature and MIME verification rather than extension-only trust;
- upload byte limits;
- PDF page-count limits;
- decoded image/pixel limits;
- safe supported format allowlists;
- server-owned job IDs and storage paths;
- filename/path normalization and traversal rejection;
- total job, per-page, CPU, memory, timeout, and output budgets;
- isolated non-root processing with restricted capabilities;
- no execution of embedded files, scripts, links, or external resources.

The Safe Intake Gate B foundation now implements B.1 signature classification, B.2 declared MIME/signature binding, B.3 observed byte-budget enforcement, B.4 strict PDF structure/page-budget inspection, B.5 decoded static JPEG/PNG image/pixel enforcement, B.6 original filename safety, one integrated fail-closed Safe Intake decision, and a dedicated hostile-input convergence regression layer.

B.4 derives page evidence from the exact PDF bytes in a bounded private helper subprocess using exact-pinned `pypdf==6.14.2` with `strict=True`. It rejects encrypted PDFs in v1, validates referenced page objects, and does not render pages, extract text/images/attachments, execute embedded content, follow external resources, or persist the inspected bytes. Immutable PDF `bytes` are forwarded without an additional parent-side payload copy. The Linux inspection worker applies a 256 MiB address-space limit before reading untrusted PDF bytes, and the current private Coolify staging Gateway container is budgeted at 512 MiB so parser growth remains isolated from the service-level memory ceiling.

B.5 derives image dimensions from exact immutable JPEG/PNG bytes using exact-pinned `Pillow==12.3.0` in a private helper subprocess. It rejects malformed/truncated inputs and animated/APNG inputs, enforces a 12,000 px ceiling on each dimension and a 40,000,000 total-pixel ceiling, applies a 256 MiB worker address-space limit and a 3-second wall timeout, and returns only bounded structural evidence. The Gateway configuration is fixed to the same 40,000,000-pixel security ceiling so deployment configuration cannot advertise a weaker or stronger policy than the enforced B.5 contract.

B.6 treats the original filename as metadata only. It rejects empty/overlong or whitespace-altered names, dot-path forms, drive prefixes, unsafe Windows filename characters, trailing dot/space forms, Unicode control/format/surrogate categories, Windows reserved device stems including the supported superscript aliases, and final extensions that disagree with a fresh B.1 signature classification. B.6 never converts caller filename metadata into a filesystem or storage path.

`decide_safe_intake()` accepts only the complete immutable `bytes` payload and composes the existing B.1-B.6 primitives over that same payload. It measures the byte budget first, verifies signature/MIME binding, validates the original filename against fresh signature evidence, routes PDF input only to the bounded PDF inspector, routes JPEG/PNG only to the bounded image inspector, verifies format evidence consistency, and returns only a frozen bounded decision record. Existing primitive rejection categories propagate unchanged. The decision does not persist bytes, derive a storage path, accept an HTTP upload, or dispatch work to an engine.

The hostile-input convergence layer exercises representative renamed/unsupported input, MIME mismatch, byte-budget rejection, traversal/control/device filename cases, malformed/missing-reference/encrypted PDFs, PDF page-budget rejection, malformed/truncated JPEG/PNG, animated/APNG rejection, dimension/pixel rejection, and bounded inspector timeout categories through the integrated decision boundary. The 256 MiB worker address-space limits are verified separately without allocating hostile-sized inputs.

Gate B completion is a security-foundation milestone, not an activation event. **External document upload remains disabled.** Gate D.1-D.6 durable state/recovery foundations and Gate E.1-E.4A external admission/session-reservation foundations exist, but E.4A accepts no document payload. E.4B must finalize the exact session-bound bytes through `decide_safe_intake()`, and E.4C must bind accepted immutable source/hash evidence to server-owned source/job identity. Production session/rate/idempotency providers, edge/anonymous abuse controls, resource scope where applicable, production storage/runtime activation, privacy-safe live API behavior, and production-readiness controls remain separately required.

E.4A replay handling has one explicit stateful-provider trust obligation. An exact replay must return the original stored session identity, creation time, expiry, and budgets; it must not refresh TTL or widen budgets. The contract checks exact receipt shape and binding, while the future atomic reservation provider is responsible for proving that replay evidence came from the original immutable stored session record. This obligation is not a separate capability Gate.

## 4. Candidate Safety Gate v1

Every engine candidate is treated as a fresh untrusted input before Canonical Score or Ensemble processing.

The shared policy is defined by `contracts/candidate-safety-policy-v1.json` and is currently applied to HOMR, Clarity, and Audiveris runtime outputs.

### MusicXML controls

- Bound artifact/XML byte size.
- Reject NUL bytes.
- Reject entity declarations.
- Permit only the explicitly recognized canonical MusicXML doctype form for sanitization before parse; reject other doctypes.
- Do not resolve external entities or perform external network resolution.
- Accept only expected MusicXML root forms.
- Bound XML depth, total element count, total attribute count, and attributes per element.
- Treat structural safety separately from musical plausibility.

### MXL controls

- Treat `.mxl` as an untrusted ZIP archive.
- Bound archive byte size, entry count, per-entry size, and total uncompressed size.
- Bound compression ratio.
- Reject encrypted entries.
- Reject ZIP symlink entries.
- Reject absolute paths, traversal paths, backslash paths, NUL-containing names, and duplicate members.
- Require `META-INF/container.xml`.
- Reject DTD/entity declarations in `container.xml`.
- Require exactly one declared MusicXML rootfile and verify that the declared member exists.

Raw engine output remains an audit artifact. Passing Candidate Safety v1 means only that the candidate is safe enough for the next controlled parsing stage; it does not mean the music is correct.

## 5. Storage and artifact controls

- Generate job IDs and artifact paths on the server.
- Keep original input and sealed raw engine outputs immutable.
- Store sanitization/normalization/correction results as derivatives or revisions rather than overwriting sealed raw artifacts.
- Calculate and retain SHA-256 hashes and provenance for source and result artifacts.
- Separate service writable areas; engines must not share unrestricted writable directories.
- Apply retention classes and cleanup only after checking review/protection status.
- Production backups must be encrypted and restore-tested.

Gate D.1-D.6 now provide the contract/convergence foundation for immutable artifact authority, storage-key derivation, SHA-256 content binding, provenance chaining, idempotency, restart decisions, and partial-output/crash-window recovery checks. These contracts perform no provider-backed storage operation by themselves.

Production immutable object storage, durable database/replay adapters, and provider-backed provenance persistence are **not enabled**.

## 6. Job execution controls

Before live orchestration is enabled:

- use explicit state transitions;
- apply per-engine timeouts and cancellation;
- limit retries and distinguish retryable from permanent failures;
- enforce idempotency or an equivalent duplicate-processing barrier;
- do not mark jobs complete until required artifacts are durably stored and verified;
- recover interrupted jobs into a defined state after restart;
- bind engine results to the correct job/source identity;
- require service-to-service authentication for engine dispatch.

Gate C and Gate D now define these controls at the contract/convergence layer: C.2-F/G fix timeout/cancellation and one-attempt/zero-retry semantics; D.1-D.6 define durable-state snapshots, idempotency/replay semantics, immutable storage authority, provenance records, restart-recovery decisions, and crash-window/partial-output convergence. In-flight `dispatching`/`running` recovery is reconciliation-only and does not authorize automatic resume/retry.

Current Gateway orchestration remains disabled because operational persistence/replay providers, real credential/network wiring, queue/worker/process control, storage writes, and explicit activation have **not** been authorized. Contract completion is not runtime activation.

## 7. Logging and privacy

Logs may include:

- job ID;
- engine name and pinned version;
- lifecycle state;
- duration/resource summary;
- stable bounded error category.

Logs must not include:

- PDF contents;
- complete MusicXML contents;
- bearer tokens or secrets;
- personal names inferred from filenames;
- unrestricted local paths.

External error responses must avoid stack traces, raw subprocess output, and internal infrastructure details.

Gate E.1 safe principal evidence excludes raw subject and credential material. Gate E.2 safe authorization evidence exposes only bounded principal/operation/decision information and does not disclose unrelated policy grants. Gate E.3A safe rate evidence excludes backend/provider diagnostics and does not grant execution authority. Gate E.3B safe idempotency evidence excludes the raw client key, request body, slot ID, request digest, subject, credentials, and provider details. Gate E.3C safe admission evidence excludes internal binding/request material and provider diagnostics while explicitly retaining all runtime authority flags as disabled. Gate E.4A safe session evidence exposes only bounded session identity/state/expiry/intake budgets and retains upload, storage-write, job, execution, network-dispatch and orchestration authority as disabled. Privacy-safe behavior for future live HTTP errors and request logs remains required before public API activation.

## 8. Dependency and model supply chain

- Pin application dependencies and upstream engine revisions.
- Record engine/model source revision and license.
- Verify model and downloaded engine artifacts with checksums.
- Never download mutable `latest` artifacts during a production request.
- Keep GitHub Actions references pinned to immutable commit SHAs.
- Add repository-owned vulnerability, dependency, and secret scanning before production readiness.
- Pin container base images by digest before production promotion.
- Generate/retain SBOM and provenance evidence for release artifacts when the production release process is introduced.

Gate B.4 introduced the Gateway's first PDF parser dependency and pins it exactly to `pypdf==6.14.2`. Gate B.5 adds exact-pinned `Pillow==12.3.0` only for bounded static JPEG/PNG inspection. Repository-owned dependency/vulnerability scanning, package-hash locking, SBOM/provenance, and base-image digest pinning remain Gate G production-readiness work; Gate B completion does not claim those controls are complete.

## 9. Teacher-review boundary

- Ensemble findings are evidence/recommendations, not final truth.
- Automatic candidate selection must never equal teacher approval.
- Only an authenticated and authorized reviewer may approve a revision.
- Every edit/approval must identify reviewer, revision, timestamp, reason/evidence, and unresolved warnings or waivers.
- Corrections create immutable revisions rather than changing raw candidate artifacts.
- Publication is a separate transition from approval.
- Learner-facing publication remains blocked while blocking issues are unresolved or no approved revision exists.

The production Teacher Review API/RBAC/publication barrier is not yet implemented. Gate E.2 does not define reviewer/admin roles and must not be treated as TR-8A RBAC authority.

## 10. Threat-test catalogue

Required negative coverage includes:

### Intake

- renamed non-PDF/non-image input;
- malformed/truncated PDF;
- malformed/truncated JPEG/PNG;
- oversized PDF/image;
- excessive page/pixel count;
- image dimension overflow and animated/APNG rejection;
- bounded failure when image inspection times out or exceeds its worker memory boundary;
- path traversal/control characters in filenames;
- unsupported/ambiguous container formats;
- encrypted PDF rejection while Safe Intake v1 does not support decryption;
- missing or malformed PDF page-object references;
- bounded failure when PDF structural inspection times out;
- bounded PDF inspection memory independent of parser/object-graph growth.

These intake categories are covered across the B.1-B.6 primitive suites and the integrated hostile-input convergence layer. The convergence layer verifies that the central decision preserves the stable fail-closed categories rather than replacing the lower-level safety evidence.

### Candidate output

- XML external/internal entity declarations;
- noncanonical doctypes;
- deeply nested XML;
- excessive element/attribute counts;
- oversized MusicXML;
- malformed MXL;
- ZIP traversal and symlink entries;
- excessive ZIP entry count/expanded size/compression ratio;
- encrypted/duplicate ZIP members;
- invalid/missing/multiple MXL rootfiles;
- HTML/JSON/other content returned in place of MusicXML.

### Runtime/job lifecycle

- engine timeout/crash/partial output;
- duplicate requests;
- cancellation races;
- restart during processing;
- result/job identity mismatch;
- unauthorized internal dispatch;
- unauthorized external operation requests;
- cross-operation attempts to use unrelated admitted authority for Safe Upload Session reservation;
- unauthorized review/approval/publication attempts.

Gate D.6 covers representative job/candidate/storage partial-output and crash-window convergence at the contract layer. E.1-E.4A cover external principal/authorization/rate/idempotency/composition/session-reservation confusion and fail-closed admission behavior without activating a public route. E.4A specifically rejects an unrelated valid E.3C operation before the session provider seam.

## 11. Security stop rules

The following capabilities remain blocked until their protecting controls and negative tests pass:

- **External upload** → Safe Intake Gate B is complete; Gate D.1-D.6 state/recovery foundations and Gate E.1-E.4A external security/session-reservation foundations exist. Upload remains blocked because E.4A accepts no document payload, E.4B Safe Intake Session Finalization and E.4C Immutable Source / Job Binding are incomplete, no public upload route is active, and provider-backed session/rate/idempotency/persistence/storage plus edge/anonymous-abuse and privacy controls remain incomplete.
- **Live Gateway dispatch** → Gate C internal-dispatch contracts and Gate D state/recovery contract/convergence foundations are present, but operational credentials/replay persistence, durable provider-backed state/storage, live receiver/network wiring, process/worker control, and explicit orchestration activation remain blocked.
- **Canonical/Ensemble consumption of engine output** → must pass Candidate Safety v1 first.
- **Teacher approval/publication** → blocked until Gate F/TR-8A RBAC, immutable revisions, audit evidence, and approval/publication barriers exist; generic E.2 authorization is not reviewer approval authority.
- **Production promotion** → blocked until supply-chain scanning/pinning, monitoring, backup/restore, rollback, and acceptance evidence exist.
