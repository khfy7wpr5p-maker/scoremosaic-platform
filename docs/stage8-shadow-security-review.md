# Stage 8 Shadow Security Review Fixes

This note records security findings resolved before PR #119 is eligible to merge.

## SR-8-01 — exact tenant scope was not checked at verification call site

The sealed authorization body already included `tenantId`, but the first verifier API did not require a trusted `expected_tenant_id`. That left an avoidable cross-tenant replay seam if other resource identifiers ever overlapped across tenants.

Resolution:

- the public verifier now requires exact `expected_tenant_id`;
- cross-tenant mismatch fails closed as `AUTHZ_TENANT_MISMATCH`;
- a dedicated negative regression test covers replay across tenant scope.

## SR-8-02 — caller-constructible verified object could be mistaken for authority

A frozen Python dataclass is immutable but not unforgeable. The first internal design allowed a `VerifiedReviewAuthorization` object to be passed directly to the revision builder. A caller could construct such an object without proving it came from HMAC verification.

Resolution:

- the original implementation moved to private `_contracts.py` and is treated only as low-level mechanics;
- the supported public `contracts.py` facade does not expose `VerifiedReviewAuthorization` or `assert_authorized_command`;
- the public revision builder accepts the raw sealed grant plus the purpose-separated signing key and trusted expected scope;
- authorization is re-verified at the revision mutation boundary on every call;
- verifier output is explicitly marked `authoritativeCapability: false` and cannot be passed as mutation authority;
- a regression test verifies a forged/tampered grant cannot create a revision.

## Resulting public trust rule

No caller-created Python object is sufficient to obtain Teacher Review mutation authority. Draft revision creation requires re-verification of the sealed authorization grant against exact tenant, job, reviewer, Review Report, Canonical Score, and current parent revision identities.

This remains a hermetic contract foundation. It does not activate production identity/RBAC, public HTTP mutation, durable storage, approval, or publication.
