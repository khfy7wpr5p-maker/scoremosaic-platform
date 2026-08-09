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
- Current Gateway upload and execution/orchestration remain disabled.

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

Current runtime foundations implement B.1 signature classification, B.2 declared MIME/signature binding, B.3 observed byte-budget enforcement, and B.4 strict PDF structure/page-budget inspection. B.4 derives page evidence from the exact PDF bytes in a bounded private helper subprocess using exact-pinned `pypdf==6.14.2` with `strict=True`. It rejects encrypted PDFs in v1 and does not render pages, extract text/images/attachments, execute embedded content, follow external resources, or persist the inspected bytes.

B.5 decoded image/pixel enforcement, B.6 filename/path enforcement, hostile-input convergence, and the integrated Safe Intake decision remain incomplete. Configuration alone is not an implemented intake gate. **External upload must remain disabled until the complete runtime enforcement and hostile-input regression set pass.**

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

Production immutable object storage and durable provenance persistence are not yet enabled.

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

Current Gateway orchestration remains disabled while these controls are incomplete.

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

## 8. Dependency and model supply chain

- Pin application dependencies and upstream engine revisions.
- Record engine/model source revision and license.
- Verify model and downloaded engine artifacts with checksums.
- Never download mutable `latest` artifacts during a production request.
- Keep GitHub Actions references pinned to immutable commit SHAs.
- Add repository-owned vulnerability, dependency, and secret scanning before production readiness.
- Pin container base images by digest before production promotion.
- Generate/retain SBOM and provenance evidence for release artifacts when the production release process is introduced.

Gate B.4 introduces the Gateway's first PDF parser dependency and pins it exactly to `pypdf==6.14.2`. Repository-owned dependency/vulnerability scanning, package-hash locking, SBOM/provenance, and base-image digest pinning remain Gate G production-readiness work; B.4 does not claim those controls are complete.

## 9. Teacher-review boundary

- Ensemble findings are evidence/recommendations, not final truth.
- Automatic candidate selection must never equal teacher approval.
- Only an authenticated and authorized reviewer may approve a revision.
- Every edit/approval must identify reviewer, revision, timestamp, reason/evidence, and unresolved warnings or waivers.
- Corrections create immutable revisions rather than changing raw candidate artifacts.
- Publication is a separate transition from approval.
- Learner-facing publication remains blocked while blocking issues are unresolved or no approved revision exists.

The production Teacher Review API/RBAC/publication barrier is not yet implemented.

## 10. Threat-test catalogue

Required negative coverage includes:

### Intake

- renamed non-PDF/non-image input;
- malformed/truncated PDF;
- oversized PDF/image;
- excessive page/pixel count;
- path traversal/control characters in filenames;
- unsupported/ambiguous container formats;
- encrypted PDF rejection while Safe Intake v1 does not support decryption;
- bounded failure when PDF structural inspection times out.

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
- unauthorized review/approval/publication attempts.

## 11. Security stop rules

The following capabilities remain blocked until their protecting controls and negative tests pass:

- **External upload** → blocked until the complete Safe Intake Gate runtime enforcement exists; B.1-B.4 alone are not sufficient.
- **Live Gateway dispatch** → blocked until intake enforcement, service-to-service authentication, durable job state, and candidate handling are demonstrated.
- **Canonical/Ensemble consumption of engine output** → must pass Candidate Safety v1 first.
- **Teacher approval/publication** → blocked until RBAC, immutable revisions, audit evidence, and approval/publication barriers exist.
- **Production promotion** → blocked until supply-chain scanning/pinning, monitoring, backup/restore, rollback, and acceptance evidence exist.

Security controls must be implemented before the capability they protect is activated.
