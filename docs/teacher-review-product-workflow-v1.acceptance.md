# Teacher Review Product Workflow v1 — Acceptance

Acceptance target for this slice:

- Teacher Review remains the primary review workspace.
- Score View stays presentation-only and renderer coordinates stay non-authoritative.
- Structured Edit remains bounded to the existing local editor-core bridge.
- A selected issue can be marked reviewed only in browser memory.
- Local validation is disabled while any blocking issue is unresolved.
- Approval preparation is disabled until local validation passes.
- The final production `Approve score` control is visible but disabled.
- No network, persistence, authentication, RBAC, server revision, approval authority, publication authority, or production activation is introduced.

A green CI result proves only repository/browser fixture behavior and authority-boundary regression checks. It does not prove production readiness.
