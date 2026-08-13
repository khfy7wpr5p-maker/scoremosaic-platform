# ScoreMosaic Roadmap

Every capability is gated. Code presence alone does not authorize activation; the protecting security controls, negative tests, and CI evidence must pass first.

## Current secure-development status

| Area | Status | Security meaning |
|---|---|---|
| Repository/contracts foundation | Completed | Architecture, contracts, review concepts, isolated service layout exist. |
| GitHub Actions immutable action pins | Completed | Repository workflows use immutable action SHAs. |
| Private container/runtime isolation | Completed foundation | Engine services are non-root/private/read-only with restricted capabilities. |
| HOMR pinned runtime/model foundation | Completed foundation | Pinned runtime/model checks and private execution helper exist. |
| Clarity pinned source/model foundation | Completed foundation | Pinned source/model and controlled CPU/offline runtime exist. |
| Audiveris pinned runtime foundation | Completed foundation | Pinned package/runtime and private execution helper exist. |
| OMR Gateway health/orchestration contracts | Completed foundation | Gateway contracts exist; upload/execution remain disabled. |
| Candidate/artifact lifecycle v1 | Completed foundation | Candidate isolation and immutable lifecycle contracts exist; production persistence remains disabled. |
| Canonical Score / Ensemble comparator/report | Completed foundation | Deterministic normalization/comparison/report foundations exist. |
| Fixed evaluation foundations | Completed | Fixed evaluation datasets/contracts are present. |
| ST-OMR isolated development track | In progress | Synthetic/model-runtime contracts exist; production integration remains outside scope. |
| Candidate Safety Gate v1 | Implemented | HOMR, Clarity, and Audiveris outputs are fail-closed validated before acceptance as safe candidates. |
| Safe Intake Gate B | Completed foundation | B.1-B.6, the integrated fail-closed Safe Intake decision, hostile-input convergence coverage, and post-merge CI evidence are complete; external upload remains disabled. |
| Internal dispatch security | C.2-G + C-DIAG-1/2 foundations completed | C.1 and C.2-A-C.2-G contract foundations are on `main`, together with C-DIAG-1 bounded engine runtime diagnostic redaction and C-DIAG-2 bounded receiver/dispatch outward diagnostic mapping. Raw engine runtime/provider details and dispatch exception payloads do not cross the current safe surfaces; non-exact diagnostic strings are rejected. Live receiver routes, durable replay persistence, network dispatch, and orchestration activation remain disabled. |
| Durable job/artifact state and recovery | Completed contract/convergence foundation | Gate D.1-D.6 define fail-closed job state, idempotency, immutable artifact authority, provenance, restart-recovery decisions, and crash-window/partial-output convergence. No database/object-storage provider, queue/worker runtime, durable read/write adapter, or live recovery/orchestration authority is activated. |
| Production immutable object storage | Not started | Gate D storage authority contracts exist, but no production object-storage provider or storage-write runtime is selected or enabled. |
| External API authentication/authorization | In progress | Gate E.1 authentication, E.2 authorization, E.3A rate admission, E.3B request idempotency, E.3C admission composition, E.4A Safe Upload Session reservation, and E.4B Safe Intake Session Finalization foundations exist in the current Gate E sequence. E.4B accepts exact immutable document bytes only through the contract boundary, requires Gate B before atomic finalization evidence, and grants no HTTP upload, storage, or job authority. E.4C immutable source/job binding, provider/runtime wiring, edge abuse controls, and public routes remain blocked. |
| UI-0A visual/application-shell contract | Completed documentation foundation | Visual/application-shell direction exists only as documentation; it creates no frontend runtime or authority. |
| UI-0B static application shell | Completed isolated prototype | Repository-owned HTML/CSS prototype exists but remains disconnected, non-production, non-authoritative, and without backend/edit/playback runtime. GitHub-hosted executable CI coverage is tracked separately. |
| Teacher Review Score Editor TR-0A | Completed architecture contract | The future editor trust/authority and secure implementation sequence are documented; no Teacher Review API, writable editor, persistence, playback, approval, or publication runtime is activated. |
| Teacher Review API + RBAC + immutable revisions | Not started | Approval workflow remains a contract, not a production API. |
| Approval-to-publication barrier | Not started | Learner-facing publication remains blocked. |
| Base-image digest pinning + repository-owned security scans | Not started | Required before production readiness. |
| Backup/restore, monitoring, rollback | Not started | Required before production promotion. |

## Security-first sequence from this point

### Gate A — Candidate Safety Convergence

Status: completed foundation.

Goal: engine success must never bypass candidate validation.

Requirements:

- common Candidate Safety v1 policy;
- Audiveris MXL ZIP/member/container validation;
- HOMR MusicXML declaration/size/complexity validation;
- Clarity MusicXML complexity convergence;
- hostile MXL/XML negative regression tests;
- convergence check preventing policy drift across adapters;
- relevant service CI green.

Activation effect: none. Public upload/orchestration remains disabled.

### Gate B — Safe Intake Foundation

Status: completed foundation.

Goal: no untrusted PDF/image reaches a later processing boundary without one central fail-closed intake decision.

Completed slices:

- B.1 signature classification — completed.
- B.2 declared MIME/signature consistency — completed.
- B.3 observed request-byte budget — completed.
- B.4 strict PDF structure/page-budget inspection — completed with exact-pinned `pypdf==6.14.2` in a bounded helper subprocess; encrypted PDFs are rejected in v1.
- B.5 decoded image/pixel limit — completed for static JPEG/PNG with exact-pinned `Pillow==12.3.0`, a 12,000 px per-dimension ceiling, a 40,000,000 total-pixel ceiling, a 256 MiB helper address-space limit, and a 3-second timeout.
- B.6 original filename safety — completed; filename metadata is validated against fresh signature-derived format evidence and is never converted into a filesystem/storage path.
- Integrated Safe Intake decision — completed over the exact immutable payload, composing B.1-B.6 and returning bounded server-derived evidence only after every required check passes.
- Hostile-input convergence — completed as a dedicated integrated regression layer covering representative renamed/unsupported input, MIME mismatch, byte limits, filename attacks, malformed/encrypted PDF cases, page limits, malformed/animated image cases, dimension/pixel limits, and bounded inspector failures.

Requirements:

- signature/MIME verification;
- request byte limit;
- PDF page limit;
- decoded image/pixel limit;
- filename/path safety;
- explicit supported-format allowlist;
- malformed/truncated/oversized hostile fixtures;
- deterministic stable rejection categories.

Gate B completion has no activation effect by itself. The Gateway still has no external upload endpoint. E.4A reserves bounded session evidence and E.4B can consume exact immutable document bytes only inside the contract library, where it must run `decide_safe_intake()` before any finalization provider callback. E.4B still creates no storage write or job. E.4C remains required to bind accepted immutable source evidence to server-owned job/source identity. Production storage/runtime and production-readiness controls remain separately required.

### Gate C — Internal Dispatch Security

Goal: enable private orchestration without creating an unauthenticated lateral-movement path.

Completed slices:

- C.1 service-to-service authentication contract foundation — completed. Fixed Gateway/engine identities, explicit environment-scoped credential bindings, fail-closed resolver behavior, bounded opaque credential material, and negative regression evidence are on `main`. C.1 itself did not select or activate a network authentication mechanism and did not enable dispatch.
- C.2-A authenticated request envelope and receiver verification contract foundation — completed. Deterministic HMAC-SHA256 binds the C.1 caller/engine/audience/environment/credential-key relationship to the exact method, canonical path, timestamp, nonce, payload length, and payload SHA-256. Receiver verification independently validates the observed method/path, request freshness, signature, and replay-check ordering before acceptance. This slice does not register engine execution routes, wire live receiver handlers, persist replay state, provision production credentials, or enable network dispatch.
- C.2-B engine dispatch target allowlist contract foundation — completed. C.1 engine identity and C.2-A authenticated request metadata are bound to exact private test/staging engine origins and the fixed future `POST /internal/transcribe` target before signing. The allowlist is immutable, production has no authorized dispatch origin, malformed or cross-engine target shapes fail closed, and the reserved route is not registered by this slice. C.2-B does not send network requests, wire receiver handlers, provision production credentials, persist replay state, or enable orchestration.
- C.2-C dispatch job/source/run/result identity-binding foundation — completed. One verified orchestration plan/run/source/candidate/artifact lineage is bound to the authenticated dispatch payload, and returned result bytes are cryptographically bound back to that exact dispatch identity. It does not execute engines, persist state, or authorize a candidate as musically correct.
- C.2-D credential-generation, bounded rotation, and replay-reservation semantics foundation — completed. Current/previous generation identity, bounded grace semantics, exact generation selection, generation-bound proofs, and generation-scoped replay reservation identity/expiry are defined fail-closed. This foundation deliberately does not implement a durable replay store or provision/rotate real production credentials. Gate D now supplies the durable state/recovery contract foundation, while an operational replay/persistence provider remains separately disabled.
- C.2-E receiver verification adapter foundation — completed. C.2-B target evidence, C.2-C semantic identity, C.2-D generation proof, and C.2-A authenticated request/freshness/replay callback ordering converge into one immutable `VerifiedDispatchRequest`. No `/internal/transcribe` route is registered and no engine execution or network dispatch is activated.
- C.2-F dispatch timeout/cancellation decision foundation — completed. Receiver-owned monotonic evidence is evaluated against the immutable orchestration timeout/cancellation policy, terminal decisions cannot reopen, stale pre-timeout evidence cannot authorize a late result, and cancellation grace remains cleanup-only. No timers, process control, scheduler, persistence, or execution is activated.
- C.2-G bounded retry/attempt-budget foundation — completed. The existing orchestration v1 policy remains authoritative: one total execution attempt and zero retries. All terminal outcomes are non-retryable, attempt 2 or higher is rejected, and the decision layer cannot create a new run/candidate/artifact identity or start execution.
- C-DIAG-1 engine runtime diagnostic redaction — completed. HOMR, Clarity, and Audiveris runtime stdout/stderr and provider exception text are replaced by bounded stable markers or reason codes; failed readiness responses suppress untrusted runtime/version/model fields and fail closed. This slice does not register a receiver route, send a network request, enable orchestration, or add persistence.
- C-DIAG-2 receiver/dispatch diagnostic convergence — completed. Receiver-verification, dispatch-deadline, retry-budget, and unexpected dispatch exceptions map to a closed immutable outward diagnostic payload containing only version, stage, and reason. The mapper does not inspect exception text, trusted mappings require exact exception types, and diagnostic fields require exact `str` values so extensible subclasses cannot smuggle mutable or attacker-controlled representation state. No route, HTTP status mapping, network dispatch, engine execution, persistence, or orchestration activation is added.

Requirements:

- authenticated service-to-service requests;
- engine identity and endpoint allowlist;
- job/source/result identity binding;
- per-engine timeout/cancellation;
- bounded retry policy;
- safe diagnostic/error mapping.

C-DIAG-1 closes raw engine-runtime diagnostic leakage on the current probe, readiness, transcription-result, and raised-error surfaces. C-DIAG-2 closes the current receiver/dispatch outward diagnostic-mapping foundation for C.2-E/F/G without activating a receiver or transport. Live receiver route/network wiring and orchestration activation remain disabled. Gate D.1-D.6 now provide the durable state/recovery contract and crash-window convergence foundation; durable provider-backed replay/persistence and operational lifecycle activation remain separate disabled work.

Exit rule: `orchestrationMode` must remain disabled until the required intake and Gate C controls pass and activation prerequisites in the later gates are satisfied and separately approved.

### Gate D — Durable Job and Artifact State

Status: completed contract/convergence foundation.

Goal: make processing crash/restart safe before live workload activation.

Completed slices:

- D.1 durable job-state foundation — closed state vocabulary, valid transition graph, immutable snapshots, and terminal non-reopening behavior bound to the existing dispatch identity.
- D.2 idempotency/replay foundation — server-derived transition slots, exact replay without duplicate revisions, conflict rejection, and restore validation against the D.1 state graph.
- D.3 immutable artifact-storage authority foundation — server-derived normalized storage keys, immutable source/candidate bindings, exact SHA-256/size/media-type identity, replay-safe manifests, and fail-closed restore verification.
- D.4 durable provenance-record foundation — immutable bounded job/run/source/storage provenance records with deterministic hashes and append-only previous-record hash chaining, verified against authoritative lifecycle/storage evidence.
- D.5 restart-recovery decision foundation — exact restored D.1-D.4 evidence converges to pre-dispatch candidate, reconciliation-required, or terminal-preserved decisions without automatic retry/resume/execution authority.
- D.6 partial-output/crash-window convergence — cross-layer run/candidate/storage terminal consistency, partial sealed-output binding checks, and fail-closed pre-dispatch/in-flight crash-window regressions.

Requirements satisfied at the contract/convergence layer:

- durable job state machine;
- idempotency;
- immutable source/candidate storage authority;
- SHA-256/provenance record binding;
- retry/cancellation/restart-recovery decisions;
- partial-output and crash-window tests.

Activation effect: none. Gate D completion does **not** select or enable a database, S3/MinIO/filesystem object-store provider, durable replay adapter, queue/worker, process restart, storage writes, network dispatch, or orchestration. Those operational capabilities require separate reviewed activation work and evidence.

### Gate E — External API Security

Status: in progress.

Goal: expose only a controlled versioned platform boundary.

Completed foundations:

- E.1 external-principal authentication — provider-neutral, bounded, fail-closed verified identity evidence; internal service identities cannot become external principals; authentication grants no authorization or runtime capability.
- E.2 external authorization decision — deny-by-default exact `principalId + environment + operationId` authorization evidence from a server-owned policy; wildcard/implicit grants and direct allowed-decision construction are rejected; even an allowed decision grants no operation-execution, upload, job-creation, network-dispatch, or orchestration runtime authority.
- E.3A external rate-slot reservation — exact E.1 principal and matching allowed E.2 authorization evidence are required before one server-owned, operation-specific fixed-window rate slot can be atomically reserved through a provider-neutral callback seam. Principal/operation/window bucket identity is deterministic and remains stable across budget-only policy changes; malformed or mismatched receipts and provider failures fail closed. E.3A does not select a production rate-state backend, wire HTTP 429 behavior, accept uploads, create jobs, or grant operation-execution/network/orchestration authority.
- E.3B external request-idempotency admission — exact E.1 principal, matching allowed E.2 authorization, and matching allowed E.3A rate evidence are required before one principal/environment/operation-scoped idempotency slot can be atomically reserved, replayed, or rejected as a conflict. The client key is bounded input rather than authority, request SHA-256 is server-computed over the exact immutable request bytes, exact replay is distinguished from same-slot/different-payload conflict, and provider/receipt failures fail closed. E.3B does not select a durable idempotency backend, register a route, accept uploads, create jobs, or grant operation-execution/network/orchestration authority.
- E.3C external admission composition convergence — exact E.1/E.2 authority is composed with a fresh E.3A rate reservation and then E.3B idempotency for the same exact immutable request. The resulting binding is deterministic across exact replay, callback-visible reservation requests are defensively cloned, and principal/authorization/rate-policy authority is snapshotted and rechecked across callback seams so mutation fails closed. E.3C grants no upload, job, storage, execution, network-dispatch, or orchestration runtime authority.
- E.4A Safe Upload Session reservation — consumes only exact E.3C admission for the canonical `platform.safe_upload_session` operation, derives a server-owned deterministic session identity, carries server-owned TTL/byte/page/media-type budgets, and delegates one atomic reserve-or-replay decision through a provider-neutral callback seam. Unrelated admitted operations fail closed before the provider callback. Receipt and sealed decision evidence are also exact-operation bound. E.4A accepts no document payload, executes no Safe Intake decision, writes no storage, creates no job, and grants no upload/execution/network/orchestration authority.
- E.4B Safe Intake Session Finalization — consumes one exact still-active E.4A session and exact immutable document `bytes`, requires the canonical Safe Intake media-type tuple, executes the completed Gate B `decide_safe_intake()` boundary before any finalization provider callback, computes document SHA-256 server-side, and binds the resulting bounded Safe Intake evidence to a deterministic finalization identity. One provider-neutral atomic reserve/replay/conflict seam prevents silent same-session/different-document finalization. The provider receives no raw document bytes or original filename. E.4B creates no HTTP route, storage write, source/job identity, execution, network-dispatch, or orchestration authority. The normative boundary is documented in [`gate-e4b-safe-intake-session-finalization.md`](gate-e4b-safe-intake-session-finalization.md).

E.4A replay semantics require the future production reservation provider to atomically preserve the original immutable session record. On replay the provider must return the original creation time, expiry, budgets, and identity; it must never refresh TTL or widen budgets.

E.4B likewise requires a future stateful finalization provider to atomically preserve the original finalization record for one session. Exact replay must return the original finalization identity/evidence, while the same session with a different document identity must return a conflict. The contract validates exact receipt binding and time/evidence shape but does not itself persist provider state. These provider obligations do not create additional abstract E.4 gates.

Next bounded E.4 sequence:

- E.4C — Immutable Source / Job Binding: bind the E.4B-accepted exact source hash/evidence and E.4 session lineage to server-owned immutable source/job identity without bypassing Gate D authority.
- E.4 closure — convergence/regression across E.4A-E.4C. After that closure, the default direction is a minimum staging vertical slice rather than an open-ended E.4D/E.4E contract chain unless a concrete P1/P2 or required trust boundary proves otherwise.

Remaining requirements before Gate E can close or any public data plane can be activated:

- provider/runtime authentication wiring without weakening E.1;
- resource/user/tenant scope enforcement where an authoritative resource-ownership model actually exists;
- production/runtime rate-limit and idempotency adapters plus edge/anonymous abuse protection;
- a production upload-session reservation provider that preserves E.4A immutable replay semantics;
- a production Safe Intake finalization provider that preserves E.4B atomic exact-replay/conflict semantics;
- E.4C Immutable Source / Job Binding;
- privacy-safe logs/errors at the live API boundary;
- explicit versioned route wiring and negative authorization tests for each activated operation.

No public login, upload, job, review, or mutation route is activated by E.1-E.4B.

### Gate F — Teacher Review and Publication

Goal: ensure machine output can never become learner-facing truth without an explicit authorized human decision.

Requirements:

- Teacher Review API;
- RBAC;
- immutable corrections/revisions;
- complete audit evidence;
- approval bound to exact revision/hash;
- unresolved-warning/waiver rules;
- separate publication transition;
- negative unauthorized approval/publication tests.

### Gate G — Production Readiness

Goal: make the platform safely operable, recoverable, and reproducible.

Requirements:

- container base-image digest pinning;
- dependency/vulnerability/secret scanning;
- SBOM/provenance evidence;
- production secrets;
- monitoring/alerts;
- capacity/concurrency limits;
- encrypted backups and demonstrated restore;
- rollback/promotion procedure;
- staging soak and acceptance evidence.

Gate B.4 introduced the Gateway PDF parser dependency `pypdf==6.14.2`; Gate B.5 adds exact-pinned `Pillow==12.3.0` only for bounded JPEG/PNG inspection. Repository-owned vulnerability/dependency scanning, package-hash locking, SBOM/provenance, and base-image digest pinning remain Gate G work.

## Architectural phase mapping

The original phase intent remains, but implementation has progressed through isolated foundations out of strict numerical order. The authoritative rule is now the security gate sequence above:

- Original Phase 0/1 concepts → repository/contracts/security foundations plus completed Gates A-B foundations.
- Original Phase 2/3/6 engine work → current HOMR/Clarity/Audiveris private runtime foundations.
- Original Phase 4 → current Canonical/Ensemble foundations.
- Original Phase 5 → future Gate F.
- Original Phase 7 → future Gate G.

## Change-control rule

Each security or capability slice uses a dedicated branch and pull request. Direct feature work on `main` is prohibited by project policy. A new capability remains disabled until its protecting gate has fresh negative-test and CI evidence and the activation itself is separately approved.