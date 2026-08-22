from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "contracts" / "stage9-production-foundation-baseline-v1.json"
TOPOLOGY = ROOT / "contracts" / "stage9-resource-topology-v1.json"
RBAC = ROOT / "contracts" / "stage9-authentik-rbac-binding-v1.json"
DOC = ROOT / "docs" / "stage9f-authentik-rbac-binding-contract.md"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class Stage9FAuthentikRbacBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.baseline = load(BASELINE)
        cls.topology = load(TOPOLOGY)
        cls.rbac = load(RBAC)
        cls.document = DOC.read_text(encoding="utf-8")

    def test_identity_and_parent_binding(self) -> None:
        self.assertEqual(self.rbac["version"], "scoremosaic-stage9-authentik-rbac-binding-v1")
        self.assertEqual(self.rbac["stage"], "9-F")
        self.assertEqual(self.rbac["baselineRef"], self.baseline["version"])
        self.assertEqual(self.rbac["topologyRef"], self.topology["version"])

    def test_oidc_is_strict_and_idp_claims_are_not_authority(self) -> None:
        oidc = self.rbac["identityProvider"]
        self.assertEqual(oidc["provider"], "authentik")
        self.assertEqual(oidc["protocol"], "oidc")
        for field in (
            "exactIssuerRequired",
            "exactAudienceRequired",
            "signatureVerificationRequired",
            "authorizationCodeFlowRequired",
            "pkceRequired",
            "stateAndNonceValidationRequired",
        ):
            self.assertIs(oidc[field], True, field)
        self.assertIs(oidc["idpGroupOrRoleClaimMayGrantScoremosaicAuthorityDirectly"], False)

    def test_principal_mapping_avoids_mutable_user_fields(self) -> None:
        mapping = self.rbac["principalMapping"]
        self.assertIs(mapping["serverOwnedPrincipalIdRequired"], True)
        self.assertIs(mapping["externalSubjectBoundToIssuerRequired"], True)
        self.assertIs(mapping["emailMayBeUsedAsAuthorityKey"], False)
        self.assertIs(mapping["displayNameMayBeUsedAsAuthorityKey"], False)
        self.assertIs(mapping["principalMappingMustBeDeterministic"], True)

    def test_rbac_is_exact_deny_by_default_and_tenant_safe(self) -> None:
        auth = self.rbac["authorizationBinding"]
        for field in (
            "exactPrincipalRequired",
            "exactTenantRequired",
            "exactResourceRequired",
            "exactOperationRequired",
            "denyByDefault",
        ):
            self.assertIs(auth[field], True, field)
        self.assertIs(auth["wildcardTenantGrantAllowed"], False)
        self.assertIs(auth["wildcardResourceGrantAllowed"], False)
        self.assertIs(auth["implicitCrossTenantAccessAllowed"], False)
        self.assertIs(auth["authenticatedMeansAuthorized"], False)

    def test_approval_and_publication_are_separate(self) -> None:
        ops = self.rbac["operationSeparation"]
        self.assertNotEqual(ops["approve"], ops["publish"])
        self.assertIs(ops["approveImpliesPublish"], False)
        self.assertIs(ops["publishImpliesApprove"], False)
        self.assertIs(ops["adminRoleAutomaticallyPublishes"], False)

    def test_session_policy_keeps_provider_tokens_out_of_browser_storage(self) -> None:
        session = self.rbac["sessionPolicy"]
        self.assertIs(session["secureCookieRequired"], True)
        self.assertIs(session["httpOnlyCookieRequired"], True)
        self.assertIs(session["sameSitePolicyRequired"], True)
        self.assertIs(session["csrfProtectionRequiredForStateChangingRequests"], True)
        self.assertIs(session["sessionRotationAfterAuthenticationRequired"], True)
        self.assertIs(session["rawProviderTokenMayBeStoredInBrowserStorage"], False)

    def test_audit_never_logs_raw_access_token(self) -> None:
        audit = self.rbac["auditPolicy"]
        for field in (
            "principalIdRequired",
            "tenantIdRequired",
            "resourceIdRequired",
            "operationIdRequired",
            "authorizationDecisionRequired",
            "timestampRequired",
        ):
            self.assertIs(audit[field], True, field)
        self.assertIs(audit["rawAccessTokenMayBeLogged"], False)

    def test_activation_locks_all_false(self) -> None:
        for name, value in self.rbac["activationLocks"].items():
            self.assertIs(value, False, name)

    def test_document_preserves_identity_vs_authority_boundary(self) -> None:
        for marker in (
            "Authentik proves identity. ScoreMosaic decides resource authority.",
            "principal + tenant + resource + operation",
            "Approval does not imply publication",
            "Raw provider tokens must not be stored in browser local/session storage",
            "must not install Infisical, create a machine identity, or provision a production secret",
        ):
            self.assertIn(marker, self.document)


if __name__ == "__main__":
    unittest.main()
