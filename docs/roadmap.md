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
| Internal dispatch security | C.2-G contract foundations completed | C.1 and C.2-A-C.2-G contract foundations are on `main`: authenticated request binding, exact target allowlisting, job/source/run/result identity binding, credential-generation/rotation and replay-reservation semantics, receiver verification, timeout/cancellation decisions, and the v1 one-attempt/zero-retry budget. Live receiver routes, durable replay persistence, safe diagnostic/error convergence, network dispatch, and orchestration activation remain incomplete. |
| UI-0A visual/application-shell contract | Completed documentation foundation | Visual/application-shell direction exists only as documentation; it creates no frontend runtime or authority. |
| UI-0B static application shell | Completed isolated prototype | Repository-owned HTML/CSS prototype exists but remains disconnected, non-production, non-authoritative, and without backend/edit/playback runtime. GitHub-hosted executable CI coverage is tracked separately. |
| Teacher Review Score Editor TR-0A | Completed architecture contract | The future editor trust/authority and secure implementation sequence are documented; no Teacher Review API, writable editor, persistence, playback, approval, or publication runtime is activated. |
| Durable job queue/state/recovery | Not started | Live orchestration remains blocked. |
| Production immutable object storage | Not started | Production persistence remains blocked. |
| External API auth/authz + rate/abuse controls | Not started | Public API exposure remains blocked. |
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

Gate B completion has no activation effect by itself. The Gateway still has no external upload endpoint, and upload remains disabled until later job/storage, external API authentication/authorization, rate/abuse, and production-readiness controls are implemented and explicitly approved.

### Gate C — Internal Dispatch Security

Goal: enable private orchestration without creating an unauthenticated lateral-movement path.

Completed slices:

- C.1 service-to-service authentication contract foundation — completed. Fixed Gateway/engine identities, explicit environment-scoped credential bindings, fail-closed resolver behavior, bounded opaque credential material, and negative regression evidence are on `main`. C.1 itself did not select or activate a network authentication mechanism and did not enable dispatch.
- C.2-A authenticated request envelope and receiver verification contract foundation — completed. Deterministic HMAC-SHA256 binds the C.1 caller/engine/audience/environment/credential-key relationship to the exact method, canonical path, timestamp, nonce, payload length, and payload SHA-256. Receiver verification independently validates the observed method/path, request freshness, signature, and replay-check ordering before acceptance. This slice does not register engine execution routes, wire live receiver handlers, persist replay state, provision production credentials, or enable network dispatch.
- C.2-B engine dispatch target allowlist contract foundation — completed. C.1 engine identity and C.2-A authenticated request metadata are bound to exact private test/staging engine origins and the fixed future `POST /internal/transcribe` target before signing. The allowlist is immutable, production has no authorized dispatch origin, malformed or cross-engine target shapes fail closed, and the reserved route is not registered by this slice. C.2-B does not send network requests, wire receiver handlers, provision production credentials, persist replay state, or enable orchestration.
- C.2-C dispatch job/source/run/result identity-binding foundation — completed. One verified orchestration plan/run/source/candidate/artifact lineage is bound to the authenticated dispatch payload, and returned result bytes are cryptographically bound back to that exact dispatch identity. It does not execute engines, persist state, or authorize a candidate as musically correct.
- C.2-D credential-generation, bounded rotation, and replay-reservation semantics foundation — completed. Current/previous generation identity, bounded grace semantics, exact generation selection, generation-bound proofs, and generation-scoped replay reservation identity/expiry are defined fail-closed. This foundation deliberately does not implement a durable replay store or provision/rotate real production credentials; durable persistence remains Gate D work.
- C.2-E receiver verification adapter foundation — completed. C.2-B target evidence, C.2-C semantic identity, C.2-D generation proof, and C.2-A authenticated request/freshness/replay callback ordering converge into one immutable `VerifiedDispatchRequest`. No `/internal/transcribe` route is registered and no engine execution or network dispatch is activated.
- C.2-F dispatch timeout/cancellation decision foundation — completed. Receiver-owned monotonic evidence is evaluated against the immutable orchestration timeout/cancellation policy, terminal decisions cannot reopen, stale pre-timeout evidence cannot authorize a late result, and cancellation grace remains cleanup-only. No timers, process control, scheduler, persistence, or execution is activated.
- C.2-G bounded retry/attempt-budget foundation — completed. The existing orchestration v1 policy remains authoritative: one total execution attempt and zero retries. All terminal outcomes are non-retryable, attempt 2 or higher is rejected, and the decision layer cannot create a new run/candidate/artifact identity or start execution.

Requirements:

- authenticated service-to-service requests;
- engine identity and endpoint allowlist;
- job/source/result identity binding;
- per-engine timeout/cancellation;
- bounded retry policy;
- safe diagnostic/error mapping.

Remaining Gate C foundation work is safe diagnostic/error convergence. Live receiver route/network wiring and orchestration activation remain disabled. Durable replay persistence, durable job/artifact state, restart recovery, and operational lifecycle authority remain Gate D responsibilities rather than being implied by the completed C.2-D semantics foundation.

Exit rule: `orchestrationMode` must remain disabled until the required intake and Gate C controls pass and activation prerequisites in the later gates are satisfied and separately approved.

### Gate D — Durable Job and Artifact State

Goal: make processing crash/restart safe before live workload activation.

Requirements:

- durable job state machine;
- idempotency;
- immutable source/candidate storage;
- SHA-256/provenance persistence;
- retry/cancellation/restart recovery;
- partial-output and crash-window tests.

### Gate E — External API Security

Goal: expose only a controlled versioned platform boundary.

Requirements:

- authentication and authorization;
- tenant/user scope enforcement where applicable;
- rate limiting and abuse protection;
- safe upload session semantics wired through the completed Safe Intake decision;
- request/idempotency binding;
- privacy-safe logs/errors.

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