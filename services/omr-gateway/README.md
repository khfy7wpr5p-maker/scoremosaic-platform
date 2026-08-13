# OMR Gateway Foundation

## Current status

This service remains a private, health-only foundation for the shared ScoreMosaic OMR Gateway. It centralizes the configured internal addresses for Audiveris, HOMR, and Clarity, but it does not accept files, create jobs through HTTP, call an OMR conversion endpoint, persist artifacts, or produce MusicXML.

Phase 11 added a **versioned orchestration-plan contract library** without enabling orchestration. Phase 12 added a **versioned candidate and artifact lifecycle contract library** without enabling runtime mutation or storage. Both libraries are deterministic and perform no file, network, queue, database, or storage operation.

Safe Intake Gate B is a completed foundation without enabling upload. B.1 signature classification, B.2 declared MIME/signature binding, B.3 observed byte-budget enforcement, B.4 strict PDF structure/page-budget inspection, B.5 decoded static JPEG/PNG image/pixel enforcement, B.6 original filename safety, the integrated fail-closed Safe Intake decision, and hostile-input convergence coverage are present on `main` with post-merge CI evidence.

Gate C.1 service-to-service authentication contract foundation is present on `main`. It defines fixed Gateway/engine identities, explicit environment-scoped credential bindings, fail-closed credential resolution, bounded opaque credential material, and negative regression evidence.

Gate C.2-A authenticated request envelope and receiver verification contract foundation is also present on `main`. It selects deterministic HMAC-SHA256 over the existing C.1 engine/environment credential, binds the caller/engine/audience/environment relationship to the exact method, canonical path, timestamp, nonce, payload length, and payload SHA-256, and defines fail-closed receiver verification including receiver-observed target matching and replay-check ordering.

Gate C.2-B through C.2-G contract foundations are present on `main`: exact test/staging target allowlisting, job/source/run/candidate/artifact/result identity binding, credential-generation and bounded rotation semantics, generation-scoped replay-reservation identity/expiry, receiver verification convergence, deterministic timeout/cancellation decisions, and the orchestration v1 one-attempt/zero-retry budget. C-DIAG-1 is also present across HOMR, Clarity, and Audiveris: raw runtime stdout/stderr and provider exception text are replaced by bounded stable markers or reason codes, and failed readiness surfaces suppress untrusted runtime/version/model fields. C-DIAG-2 is present for the C.2-E/F/G failure boundary: receiver-verification, dispatch-deadline, retry-budget, and unexpected dispatch exceptions map to a closed immutable version/stage/reason payload without inspecting exception text; trusted mappings require exact exception types and payload fields require exact `str` values. `production` deliberately has no authorized dispatch origin. The reserved future `POST /internal/transcribe` route is not registered, no network request is sent, and orchestration remains disabled.

Gate D.1-D.6 are now complete as a **durable job/artifact state and recovery contract/convergence foundation**. The Gateway library contains fail-closed durable run-state snapshots, server-derived idempotency/replay slots, immutable artifact-storage authority manifests, bounded provenance records/hash chaining, restart-recovery decisions, and partial-output/crash-window convergence. This foundation does not select or operate a database, S3/MinIO/filesystem storage provider, durable replay adapter, queue/worker, process-restart mechanism, or live storage/orchestration runtime.

Gate E is in progress. E.1 defines provider-neutral authenticated external-principal evidence without a provider SDK or HTTP auth route. E.2 defines deny-by-default exact principal/environment/operation authorization decisions from a server-owned policy. E.3A defines provider-neutral authenticated-operation rate-slot reservation evidence. E.3B defines provider-neutral external request-idempotency admission evidence bound to the exact E.1 principal, matching allowed E.2 authorization, matching allowed E.3A rate evidence, bounded client key, and server-computed digest of the exact immutable request bytes. E.3C composes those exact authorities by evaluating E.3A freshly and then E.3B for the same request, derives one deterministic admission binding, uses defensive callback request copies, and detects callback authority mutation fail-closed. All of this remains contract/admission evidence rather than operation-execution authority: upload, job creation, persistence, network dispatch, and orchestration remain false. Public route wiring, provider/runtime auth, resource/tenant scope where applicable, production rate/idempotency adapters that preserve E.3C semantics, edge/anonymous abuse controls, safe upload sessions, and privacy-safe live API behavior remain disabled/unimplemented.

Implemented now:

- Python 3.12 standard-library HTTP service
- exact-pinned `pypdf==6.14.2` used only by the private B.4 PDF inspection helper
- exact-pinned `Pillow==12.3.0` used only by the private B.5 JPEG/PNG inspection helper
- `GET /health` returning process health and disabled capabilities
- `GET /ready` returning HTTP 503 while orchestration remains disabled
- bounded readiness probes for the three private engine `/ready` endpoints
- isolated probe results so one unavailable engine does not hide the others
- declared future PDF, JPEG (`.jpg`/`.jpeg`), and PNG input capability
- Safe Intake B.1 bounded signature classification
- Safe Intake B.2 declared MIME/signature consistency
- Safe Intake B.3 observed byte-budget enforcement
- Safe Intake B.4 strict PDF structural/page-count inspection in a bounded helper subprocess
- Safe Intake B.5 immutable static JPEG/PNG inspection with server-derived dimensions, a 12,000 px per-dimension ceiling, a 40,000,000 total-pixel ceiling, animation rejection, a 256 MiB helper address-space limit, and a 3-second timeout
- Safe Intake B.6 original filename metadata safety bound to fresh signature-derived format evidence
- integrated `decide_safe_intake()` composition over one exact immutable payload
- dedicated hostile-input convergence coverage through the integrated decision boundary
- Gate C.1 fail-closed service identity, environment-scoped credential binding, and credential-resolution contract
- Gate C.2-A deterministic HMAC-SHA256 authenticated request envelope plus fail-closed receiver-verification contract
- Gate C.2-B immutable exact test/staging engine-origin allowlist plus fixed future `POST /internal/transcribe` dispatch-target binding; production dispatch remains unconfigured/fail-closed
- Gate C.2-C immutable job/source/run/candidate/artifact dispatch identity plus authenticated result-byte identity binding
- Gate C.2-D explicit credential-generation identity, bounded current/previous rotation semantics, generation-bound request/result proofs, and persistence-neutral replay-reservation identity/expiry
- Gate C.2-E immutable receiver verification adapter convergence over C.2-A/B/C/D without route registration or engine execution
- Gate C.2-F deterministic receiver-owned monotonic timeout/cancellation/result-acceptance decisions; terminal states cannot reopen and cancellation grace is cleanup-only
- Gate C.2-G bounded retry/attempt-budget decision foundation preserving orchestration v1 `attemptLimit = 1`, `retryAfterTimeout = false`, and zero retry attempts
- C-DIAG-1 bounded HOMR, Clarity, and Audiveris runtime diagnostic redaction across probe, readiness, transcription-result, and raised-error surfaces
- C-DIAG-2 bounded outward receiver/dispatch diagnostic mapping for C.2-E/F/G failures, with exact exception-type and exact-string enforcement and no exception text inspection
- Gate D.1 closed durable run-state contract bound to exact dispatch identity
- Gate D.2 server-derived idempotency/replay ledger contract with exact-replay and conflict semantics
- Gate D.3 immutable artifact-storage authority contract with server-derived keys and exact sealed-content identity
- Gate D.4 bounded append-only provenance-record/hash-chain contract verified against authoritative lifecycle/storage evidence
- Gate D.5 restart-recovery decision contract: pre-dispatch candidate, reconciliation-required, or terminal-preserved; no automatic resume/retry
- Gate D.6 partial-output/crash-window convergence across run, candidate, sealed artifact, and storage-manifest evidence
- Gate E.1 provider-neutral external-principal authentication contract with bounded/redacted safe evidence and no authorization authority
- Gate E.2 deny-by-default external authorization-decision contract with exact principal/environment/operation grants and no runtime operation authority
- Gate E.3A provider-neutral rate-slot reservation contract with deterministic server-owned operation/window bucket identity and no production rate backend or HTTP 429 wiring
- Gate E.3B provider-neutral request-idempotency admission contract with exact replay/conflict semantics and no durable idempotency backend or live request wiring
- Gate E.3C fail-closed external admission composition contract with fresh E.3A evaluation, exact E.3B request binding, defensive provider-request clones, and authority-mutation convergence; no live route or runtime operation authority
- immutable in-memory job and engine-run record model aligned with the existing OMR job contract
- versioned `1.0` orchestration-plan JSON Schema
- deterministic orchestration plan, run, candidate, and artifact identifiers
- explicit engine-run lifecycle transitions and bounded timeout policy
- versioned `1.0` candidate/artifact lifecycle JSON Schema
- immutable source, raw-result, MusicXML, and diagnostic artifact relationships
- append-only lifecycle events with a SHA-256 hash chain
- deterministic lifecycle, event, candidate, and artifact verification
- independent candidate namespaces for Audiveris, HOMR, and Clarity
- non-root, read-only container foundation
- no public port or direct browser route

B.4 derives page evidence from the exact bounded PDF bytes rather than caller-supplied page metadata. The helper uses `pypdf` with `strict=True`, rejects encrypted PDFs in Safe Intake v1, validates referenced page objects, has a bounded inspection timeout, suppresses raw parser diagnostics, and returns only a bounded stable result. Immutable `bytes` are forwarded to the helper without creating a second parent-side payload copy. On the Linux container boundary the worker applies a 256 MiB address-space limit before reading untrusted PDF bytes, while the private Coolify staging Gateway container is budgeted at 512 MiB. It does not render pages, extract text/images/attachments, follow links, execute embedded content, persist input bytes, or enable upload.

B.5 derives image evidence from exact immutable JPEG/PNG bytes. The helper rejects malformed/truncated content, rejects animated/APNG input, validates the decoded format against the signature-derived format, enforces a 12,000 px per-dimension and 40,000,000 total-pixel ceiling, fully decodes only inside the bounded subprocess, and returns only stable structural evidence. The worker has a 256 MiB address-space limit and a 3-second wall timeout. The Gateway `SCOREMOSAIC_GATEWAY_MAX_IMAGE_PIXELS` setting is fixed to `40000000` so deployment configuration cannot drift from the enforced B.5 policy.

B.6 validates the caller-supplied original filename as metadata only. It rejects invalid or overlong names, unsafe path forms, control/format/surrogate Unicode categories, Windows reserved device aliases, and final extensions that disagree with fresh B.1 signature evidence. The primitive never turns the filename into a filesystem or storage path.

`decide_safe_intake()` accepts only a complete immutable `bytes` payload, measures the byte budget before downstream inspection, verifies signature/MIME consistency, applies B.6 to the same bytes, dispatches only the verified PDF or JPEG/PNG format to the corresponding bounded inspector, and returns a frozen record containing only bounded server-derived evidence. Existing primitive error categories propagate unchanged. It does not persist bytes, derive storage paths, create jobs, accept HTTP uploads, or dispatch engines.

The hostile-input convergence layer verifies representative renamed/unsupported content, MIME mismatch, byte-budget rejection, traversal/control/device filename cases, malformed/missing-reference/encrypted PDF cases, PDF page-budget rejection, malformed/truncated JPEG/PNG, animated/APNG rejection, dimension/pixel limits, and bounded inspector timeout categories through the integrated decision boundary. The 256 MiB PDF and image worker address-space limits are verified separately without allocating hostile-sized inputs.

## Current endpoints

```text
GET /health -> 200; gateway process is running
GET /ready  -> 503; orchestration and upload are disabled
```

All other paths return 404. Non-GET methods return 405. In particular, `/internal/jobs`, an upload endpoint, an orchestration endpoint, external auth/authz/rate/idempotency/admission endpoints, and an artifact lifecycle endpoint do not exist in this foundation. The reserved engine target `/internal/transcribe` remains a contract value only and is not registered by the Gateway or engine services.

The health payload declares:

```json
{
  "gateway": "running",
  "capabilities": {
    "acceptedInputFormats": [
      "application/pdf",
      "image/jpeg",
      "image/png"
    ],
    "uploadEnabled": false,
    "orchestrationEnabled": false,
    "orchestrationMode": "disabled",
    "candidateIsolation": true
  },
  "engines": {
    "audiveris": "not_ready",
    "homr": "not_ready",
    "clarity": "not_ready"
  }
}
```

The liveness endpoint does not contact sibling services. The readiness endpoint performs bounded private probes and still returns 503 because orchestration is fixed to disabled.

## Orchestration contract v1 boundary

`build_orchestration_plan()` creates an immutable deterministic plan only. Its serialized shape is governed by:

```text
contracts/omr-orchestration-plan.schema.json
```

The contract defines:

- one immutable source artifact and SHA-256
- one to three canonical engine runs
- symbolic endpoint keys rather than user-supplied URLs
- one isolated candidate namespace per engine
- expected immutable MusicXML and diagnostic artifact slots
- per-engine timeout values from 30 to 7200 seconds
- monotonic timeout accounting beginning at dispatch
- a bounded cancellation grace period
- terminal timeout behavior with no automatic retry
- explicit engine-run state transitions
- deterministic `planId` and `planSha256`
- exact verification that rejects modified identifiers, relationships, hashes, policies, extra fields, ranking, or execution flags

The contract does **not** dispatch the plan. `transportProfile` is only a future adapter label. `endpointKey` is one of `audiveris`, `homr`, or `clarity`; it is not a URL, hostname, path, token, or credential.

See `docs/gateway-orchestration-contract-v1.md` for the complete architectural boundary.

## Candidate and artifact lifecycle v1 boundary

`build_artifact_lifecycle()` accepts a verified orchestration-plan payload and creates a deterministic initial lifecycle only. Its serialized shape is governed by:

```text
contracts/candidate-artifact-lifecycle.schema.json
```

Each engine candidate receives three isolated output artifact records in fixed order:

```text
raw_engine_result
musicxml
diagnostic
```

The raw engine result is preserved as a separate opaque artifact. It is never treated as automatically correct and is not merged into another engine's result.

Candidate states:

```text
reserved -> collecting -> sealed
reserved/collecting -> failed | cancelled | timed_out
```

Artifact states:

```text
reserved -> writing -> sealed
reserved/writing -> rejected | abandoned
```

Terminal candidate and artifact states cannot be reopened. The source artifact is sealed at lifecycle creation and cannot transition. A candidate can be sealed only when all of its artifacts are sealed. A failed, cancelled, or timed-out candidate requires every artifact to be terminal first.

`transition_candidate()` and `transition_artifact()` return new immutable lifecycle objects. Every transition appends one deterministic event. Events use contiguous sequence numbers, `previousEventSha256`, and `eventSha256` to form an append-only chain.

A sealed output artifact requires:

- lowercase SHA-256
- positive bounded byte size
- exact kind-specific media type

`verify_artifact_lifecycle()` rebuilds the initial lifecycle from the pinned orchestration plan, replays all events, verifies the event chain, and requires an exact final payload match. It rejects changed content hashes, state records, relationships, policies, boundaries, lifecycle hashes, events, or extra fields.

Fixed lifecycle policies include:

```json
{
  "appendOnlyEvents": true,
  "sourceImmutable": true,
  "rawEngineResultPreserved": true,
  "hashRequiredBeforeSeal": true,
  "overwriteAllowed": false,
  "crossEngineWriteAllowed": false,
  "terminalStateReopenAllowed": false,
  "candidateSealRequiresAllArtifactsSealed": true
}
```

See `docs/candidate-artifact-lifecycle-v1.md` for the complete state and security boundary.

## Disabled execution and decision boundaries

```json
{
  "executionEnabled": false,
  "uploadEnabled": false,
  "networkDispatchEnabled": false,
  "queueEnabled": false,
  "persistenceEnabled": false,
  "storageWritesEnabled": false,
  "runtimeMutationEnabled": false,
  "engineRanking": false,
  "winnerSelection": false,
  "automaticMerge": false,
  "automaticCorrection": false,
  "teacherApproval": false,
  "publication": false
}
```

An allowed E.2 authorization decision, an allowed E.3A rate decision, a reserved/replay E.3B idempotency decision, or an E.3C exact-request admission binding is contract evidence only. Their safe evidence keeps `operationExecutionAllowed`, `uploadAllowed`, `jobCreationAllowed`, `networkDispatchAllowed`, and `orchestrationAllowed` false. Therefore this section remains authoritative for runtime capability activation.

## Existing job model boundary

`build_job_record()` creates an immutable in-memory planning record only. It validates the existing `job_...` identifier format and creates one unique engine run and candidate namespace per requested engine.

It does not:

- accept or read a user file through HTTP
- create a queue entry
- start an engine
- write a database record
- create storage paths on disk
- merge or rank candidate results
- approve or publish output

The candidate separation is intentionally explicit:

```text
candidates/{jobId}/{engine}/{candidateId}
```

No engine is allowed to overwrite another engine's candidate.

## Configuration

| Variable | Default | Boundary |
|---|---:|---|
| `SCOREMOSAIC_GATEWAY_HOST` | `127.0.0.1` | loopback or wildcard bind address only |
| `SCOREMOSAIC_GATEWAY_PORT` | `8090` | 1024-65535 |
| `SCOREMOSAIC_GATEWAY_LOG_LEVEL` | `INFO` | DEBUG, INFO, WARNING, ERROR, CRITICAL |
| `SCOREMOSAIC_GATEWAY_ORCHESTRATION_MODE` | `disabled` | must remain disabled |
| `SCOREMOSAIC_GATEWAY_PROBE_TIMEOUT_SECONDS` | `1` | 1-10 seconds per engine |
| `SCOREMOSAIC_GATEWAY_MAX_REQUEST_BYTES` | `20971520` | B.3 policy input; configuration 1 KiB-100 MiB; HTTP upload still disabled |
| `SCOREMOSAIC_GATEWAY_MAX_PAGES` | `40` | B.4 policy input; configuration 1-200; HTTP upload still disabled |
| `SCOREMOSAIC_GATEWAY_MAX_IMAGE_PIXELS` | `40000000` | B.5 fixed security ceiling; values other than 40,000,000 are rejected |
| `SCOREMOSAIC_GATEWAY_WORKSPACE_ROOT` | `/tmp/scoremosaic-gateway` | absolute path only |
| `SCOREMOSAIC_GATEWAY_AUDIVERIS_BASE_URL` | `http://audiveris-foundation:8082` | administrator-controlled HTTP(S) base URL without credentials/path/query |
| `SCOREMOSAIC_GATEWAY_HOMR_BASE_URL` | `http://homr-foundation:8080` | same boundary |
| `SCOREMOSAIC_GATEWAY_CLARITY_BASE_URL` | `http://clarity-foundation:8081` | same boundary |

The engine addresses are deployment configuration, never orchestration-plan, lifecycle, or user input. Gate C.2-B separately constrains authenticated future dispatch targets to the immutable exact test/staging allowlist before signing; deployment configuration alone does not authorize a target. Readiness probes read at most 64 KiB from each response and use a strict timeout.

No E.1 authentication provider, E.2 authorization policy runtime, E.3A rate-state adapter, E.3B idempotency backend, or E.3C live request wiring is loaded from these deployment variables yet. Provider/runtime and policy/adapter wiring remain later reviewed Gate E work rather than implicit configuration authority.

## Dependency boundary

Gate B.4 introduced the Gateway PDF parser dependency `pypdf==6.14.2`; Gate B.5 adds exact-pinned `Pillow==12.3.0` only for bounded static JPEG/PNG inspection. Both inspection helpers are subprocess-isolated with 256 MiB address-space limits inside the current 512 MiB private staging Gateway container. Repository-owned vulnerability/dependency scanning, package-hash locking, SBOM/provenance, and base-image digest pinning remain Gate G production-readiness work.

## Local checks

From the repository root:

```bash
python -m pip install pypdf==6.14.2 Pillow==12.3.0
python -m compileall -q services/omr-gateway/src
python -m unittest discover -s services/omr-gateway/tests -v
```

Docker validation is performed in GitHub Actions and later in Coolify staging.

## Required gates before real orchestration, storage, and external API activation

Gate B Safe Intake, Gate C dispatch-security contracts, Gate D.1-D.6 durable state/recovery contract/convergence foundations, and Gate E.1-E.3C external API security foundations do not activate an upload or execution surface. Before real orchestration, storage, or external upload is enabled, the platform still requires:

- separately approved live receiver/dispatch wiring on top of the completed C.1/C.2-A-C.2-G and C-DIAG-1/C-DIAG-2 foundations, with operational credential-generation/rotation and durable replay implementation consistent with those contracts
- provider-backed durable replay/job/run/candidate/artifact/provenance persistence and immutable storage writes consistent with Gate D.1-D.6; no concrete database/S3/MinIO/filesystem provider is currently active
- concrete engine adapter request/response contracts and controlled execution wiring
- queue/cancellation/cleanup/process-recovery behavior consistent with Gate D recovery decisions and the existing v1 one-attempt/zero-retry policy; in-flight ambiguous work must not automatically resume
- content-addressed immutable source and candidate artifact storage plus retention, cleanup, backup/recovery rules
- safe MusicXML validation through Candidate Safety v1
- E.1-compatible real authentication-provider/runtime wiring without exposing credentials or raw subjects
- E.2-compatible deny-by-default authorization wired independently for each activated operation, plus resource/user/tenant scope enforcement where an authoritative ownership model exists
- E.3A-compatible production/runtime rate limiting plus edge/anonymous abuse protection
- production/runtime request-idempotency persistence that preserves E.3C fresh-rate, exact-request replay/conflict composition semantics, with privacy-safe external error/log handling
- a safe upload-session path that must pass `decide_safe_intake()` before later processing
- real engine adapters with pinned versions
- no automatic teacher approval or publication; reviewer RBAC remains Gate F/TR-8A rather than E.2

## Explicit non-goals

- public API or domain
- real upload or conversion
- live network dispatch or orchestration execution
- database, queue, or persistent storage runtime
- runtime artifact mutation or overwrite
- automatic Ensemble comparison invocation
- engine ranking, preferred candidate, or winner selection
- automatic MusicXML merge or correction
- user editor, teacher approval, or note tracking
- ST-OMR implementation or integration