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
| Candidate Safety Gate v1 | Implemented in this security slice | HOMR, Clarity, and Audiveris outputs are fail-closed validated before acceptance as safe candidates. |
| Safe Intake Gate runtime enforcement | Partially implemented | B.1 signature classification and B.2 declared MIME consistency exist; external PDF/image upload remains disabled. |
| Service-to-service authentication | Not started | Live engine dispatch remains blocked. |
| Durable job queue/state/recovery | Not started | Live orchestration remains blocked. |
| Production immutable object storage | Not started | Production persistence remains blocked. |
| External API auth/authz + rate/abuse controls | Not started | Public API exposure remains blocked. |
| Teacher Review API + RBAC + immutable revisions | Not started | Approval workflow remains a contract, not a production API. |
| Approval-to-publication barrier | Not started | Learner-facing publication remains blocked. |
| Base-image digest pinning + repository-owned security scans | Not started | Required before production readiness. |
| Backup/restore, monitoring, rollback | Not started | Required before production promotion. |

## Security-first sequence from this point

### Gate A — Candidate Safety Convergence

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

Goal: no untrusted PDF/image reaches an engine without a central fail-closed intake decision.

Requirements:

- signature/MIME verification;
- request byte limit;
- PDF page limit;
- decoded image/pixel limit;
- filename/path safety;
- explicit supported-format allowlist;
- malformed/truncated/oversized hostile fixtures;
- deterministic stable rejection categories.

Exit rule: Gateway upload remains disabled until these tests and runtime enforcement pass.

### Gate C — Internal Dispatch Security

Goal: enable private orchestration without creating an unauthenticated lateral-movement path.

Requirements:

- authenticated service-to-service requests;
- engine identity and endpoint allowlist;
- job/source/result identity binding;
- per-engine timeout/cancellation;
- bounded retry policy;
- safe diagnostic/error mapping.

Exit rule: `orchestrationMode` must remain disabled until Gate B and Gate C pass.

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
- safe upload session semantics;
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

## Architectural phase mapping

The original phase intent remains, but implementation has progressed through isolated foundations out of strict numerical order. The authoritative rule is now the security gate sequence above:

- Original Phase 0/1 concepts → repository/contracts/security foundations plus Gates A-B.
- Original Phase 2/3/6 engine work → current HOMR/Clarity/Audiveris private runtime foundations.
- Original Phase 4 → current Canonical/Ensemble foundations.
- Original Phase 5 → future Gate F.
- Original Phase 7 → future Gate G.

## Change-control rule

Each security or capability slice uses a dedicated branch and pull request. Direct feature work on `main` is prohibited by project policy. A new capability remains disabled until its protecting gate has fresh negative-test and CI evidence.
