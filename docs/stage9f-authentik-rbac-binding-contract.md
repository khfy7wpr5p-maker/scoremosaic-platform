# Stage 9-F — Authentik Identity to ScoreMosaic RBAC Binding Contract

## Status

**Repository-only identity/authorization policy. No Authentik user, OIDC client, issuer configuration, production session, role assignment, login route, Teacher Review authorization, or publication authorization is activated by this stage.**

Authentik proves identity. ScoreMosaic decides resource authority.

## OIDC boundary

Production identity uses OIDC with exact issuer and audience validation, signature verification, authorization-code flow, PKCE, and state/nonce validation. IdP group or role claims are input evidence only; they do not directly grant ScoreMosaic musical or publication authority.

## Principal mapping

ScoreMosaic derives a server-owned principal identity from the exact external issuer + subject binding. Email address and display name are not authority keys because they are mutable/user-facing identifiers.

## RBAC/resource authorization

Every protected operation is deny-by-default and bound to one exact:

```text
principal + tenant + resource + operation
```

Wildcard tenant/resource grants and implicit cross-tenant access are forbidden.

The initial role vocabulary is:

- viewer;
- user;
- teacher;
- publisher;
- admin.

Roles do not replace resource grants. A teacher still needs authority for the exact tenant/resource/action.

## Approval and publication separation

Operations remain distinct:

```text
review:read
review:edit
review:approve
publication:execute
```

Approval does not imply publication. Publication does not manufacture approval. Admin status does not automatically publish an artifact.

## Session boundary

Production sessions require Secure + HttpOnly cookies, an explicit SameSite policy, state-changing-request CSRF protection, and session rotation after authentication. Raw provider tokens must not be stored in browser local/session storage.

## Audit

Authorization evidence records bounded principal, tenant, resource, operation, decision, and timestamp. Raw access tokens are never logged.

## Runtime locks

```text
authentikUserCreated=false
authentikOidcClientCreated=false
productionIssuerConfigured=false
productionSessionRuntimeActivated=false
productionRoleAssignmentsCreated=false
publicLoginRouteActivated=false
teacherReviewAuthorizationActivated=false
publicationAuthorizationActivated=false
```

## Safe next slice

After Stage 9-F merges, the next repository-only slice is Infisical production-capability eligibility. It may define the exact capabilities that must be verified for the chosen deployment/license, but must not install Infisical, create a machine identity, or provision a production secret.
