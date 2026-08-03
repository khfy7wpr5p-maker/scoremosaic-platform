# Security Boundaries

## 1. Trust model

All uploaded PDFs, engine-produced MusicXML, filenames, metadata, model downloads, and remote-service responses are untrusted until validated.

A successful OMR conversion does not imply that the output is safe, structurally valid, musically correct, or suitable for publication.

## 2. External exposure

- Only the versioned platform API may receive external traffic.
- HOMR, Clarity-OMR, and future Audiveris services remain on a private container network.
- Internal services require authenticated service-to-service requests.
- Engine services must not receive browser-visible API keys.
- Development, staging, and production secrets must be separate.

## 3. PDF intake controls

Before a job is accepted:

- Verify the PDF signature and reject extension-only validation.
- Enforce upload-size and page-count limits.
- Sanitize the displayed filename and generate server-owned storage paths.
- Reject path traversal, control characters, and ambiguous archive formats.
- Apply total job, per-page, memory, CPU, and output-size limits.
- Process files in isolated, non-root containers with restricted capabilities.
- Do not execute embedded files, scripts, links, or external resources.

## 4. MusicXML and XML controls

Every candidate must pass a dedicated security gate before parsing:

- Disable DTD processing.
- Disable external entities and external network resolution.
- Reject entity expansion and oversized node/text structures.
- Enforce maximum document size, depth, element count, and attribute count.
- Accept only expected MusicXML root forms and supported encodings.
- Parse with a maintained XML parser rather than regular expressions.
- Validate structural rules separately from musical plausibility.
- Treat `.mxl` archives as untrusted ZIP files with entry-count, expanded-size, path, and compression-ratio limits.

Raw engine output is preserved for audit but must never be rendered or parsed by an unsafe path.

## 5. Storage and artifact controls

- Generate job IDs and artifact paths on the server.
- Keep original input and raw engine outputs immutable.
- Store revisions as new artifacts.
- Calculate and store SHA-256 hashes for input and result artifacts.
- Separate service volumes; engines must not share a writable directory.
- Apply retention classes and cleanup only after checking review and protection status.
- Backups must be encrypted and restore-tested.

## 6. Job execution controls

- Use explicit state transitions.
- Apply per-engine timeouts and cancellation.
- Limit retries and distinguish retryable from permanent errors.
- Prevent duplicate processing with idempotency keys or equivalent controls.
- Do not mark a job completed until required artifacts are durably stored.
- On restart, interrupted jobs must enter a defined recovery state rather than being assumed successful.

## 7. Logging and privacy

Logs may include:

- job ID
- engine name and pinned version
- lifecycle state
- duration and resource summary
- stable error category

Logs must not include:

- PDF contents
- complete MusicXML contents
- bearer tokens or secrets
- personal names inferred from filenames
- unrestricted local paths

Error responses must avoid stack traces and internal infrastructure details.

## 8. Dependency and model supply chain

- Pin application dependencies and upstream engine revisions.
- Record the license and source revision of every engine.
- Pin model revisions and verify checksums before use.
- Do not download mutable `latest` artifacts during a production request.
- Run vulnerability and secret scanning in CI.
- Review base-image updates deliberately rather than silently.

## 9. Teacher-review boundary

- Ensemble findings are recommendations, not final truth.
- Automatic candidate selection must not equal teacher approval.
- Only an authenticated, authorized reviewer can approve a revision.
- Every edit and approval must be attributable and timestamped.
- Learner-facing publication remains blocked while unresolved blocking issues exist.

## 10. Initial threat-test catalogue

Phase 1 must include tests for:

- renamed non-PDF input
- malformed and truncated PDF
- oversized PDF and excessive page count
- path traversal in filenames and archive entries
- XML external entities
- entity expansion
- deeply nested XML
- oversized MusicXML
- malformed `.mxl` and ZIP bomb characteristics
- HTML or JSON returned in place of MusicXML
- engine timeout, crash, and partial output
- duplicate requests
- cancellation races
- restart during processing
- unauthorized review and approval attempts

## 11. Security stop rule

No real OMR engine, public endpoint, or Coolify deployment should be added until the applicable validation, isolation, authentication, and failure tests for that phase are defined.
