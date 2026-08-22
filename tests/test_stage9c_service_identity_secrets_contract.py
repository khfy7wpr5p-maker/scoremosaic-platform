from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = ROOT / "contracts" / "stage9-production-foundation-baseline-v1.json"
TOPOLOGY_PATH = ROOT / "contracts" / "stage9-resource-topology-v1.json"
SECRETS_PATH = ROOT / "contracts" / "stage9-service-identity-secrets-v1.json"
DOC_PATH = ROOT / "docs" / "stage9c-service-identity-secrets-contract.md"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class Stage9CServiceIdentitySecretsContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.baseline = load_json(BASELINE_PATH)
        cls.topology = load_json(TOPOLOGY_PATH)
        cls.policy = load_json(SECRETS_PATH)
        cls.document = DOC_PATH.read_text(encoding="utf-8")

    def test_identity_and_parent_contracts_are_exact(self) -> None:
        self.assertEqual(
            self.policy["version"], "scoremosaic-stage9-service-identity-secrets-v1"
        )
        self.assertEqual(self.policy["stage"], "9-C")
        self.assertEqual(self.policy["baselineRef"], self.baseline["version"])
        self.assertEqual(self.policy["topologyRef"], self.topology["version"])
        self.assertEqual(
            self.policy["status"],
            "REPOSITORY_ONLY_IDENTITY_AND_SECRET_POLICY_WITH_RUNTIME_LOCKS",
        )

    def test_infisical_selection_preserves_capability_gate(self) -> None:
        manager = self.policy["secretManager"]
        self.assertEqual(manager["target"], "infisical")
        self.assertIs(manager["selfHostedTarget"], True)
        self.assertEqual(manager["coolifyRole"], "minimal-bootstrap-only")
        self.assertIs(manager["paidCapabilitiesAssumed"], False)
        self.assertIs(manager["licensingCapabilityGateRequired"], True)

    def test_environment_isolation_is_fail_closed(self) -> None:
        env = self.policy["environmentPolicy"]
        self.assertEqual(
            set(env["environments"]), {"development", "staging", "production"}
        )
        self.assertIs(env["crossEnvironmentReadAllowed"], False)
        self.assertIs(env["crossEnvironmentWriteAllowed"], False)
        self.assertIs(env["productionSecretsUsableInCi"], False)
        self.assertIs(env["productionSecretsUsableInDevelopment"], False)
        self.assertIs(env["sharedProductionMachineIdentityAllowed"], False)

    def test_rotation_is_generation_bound_and_never_unbounded(self) -> None:
        rotation = self.policy["rotationPolicy"]
        self.assertIs(rotation["generationIdentityRequired"], True)
        self.assertIs(rotation["boundedCurrentAndPreviousOverlapAllowed"], True)
        self.assertIs(rotation["unboundedGracePeriodAllowed"], False)
        self.assertIs(rotation["revokedGenerationMayAuthenticate"], False)
        self.assertIs(rotation["rotationMayWidenSecretScope"], False)
        self.assertIs(rotation["rotationEvidenceRequiredBeforePromotion"], True)

    def test_service_identities_are_unique_and_least_privilege(self) -> None:
        identities = self.policy["serviceIdentities"]
        names = [item["service"] for item in identities]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(
            set(names),
            {
                "scoremosaic-application",
                "gateway-orchestrator",
                "omr-compute",
                "publication-service",
                "backup-worker",
                "authentik-identity",
                "infisical-secrets",
                "coolify-control-plane",
            },
        )
        for item in identities:
            allowed = set(item["secretClasses"])
            forbidden = set(item["forbiddenSecretClasses"])
            self.assertTrue(allowed)
            self.assertTrue(forbidden)
            self.assertTrue(allowed.isdisjoint(forbidden), item["service"])

    def test_high_privilege_secret_classes_are_not_given_to_application_services(self) -> None:
        identities = {item["service"]: item for item in self.policy["serviceIdentities"]}
        for service in (
            "scoremosaic-application",
            "gateway-orchestrator",
            "omr-compute",
            "publication-service",
            "backup-worker",
            "authentik-identity",
        ):
            forbidden = set(identities[service]["forbiddenSecretClasses"])
            self.assertIn("provider-account-admin", forbidden)
            self.assertIn("database-admin", forbidden)

    def test_omr_identity_is_engine_specific_not_cross_engine(self) -> None:
        identities = {item["service"]: item for item in self.policy["serviceIdentities"]}
        omr = identities["omr-compute"]
        self.assertIn("engine-specific-receiver-identity", omr["secretClasses"])
        self.assertIn("engine-specific-result-return", omr["secretClasses"])
        self.assertIn("other-engine-identity", omr["forbiddenSecretClasses"])

    def test_publication_secret_does_not_equal_publication_authority(self) -> None:
        auth = self.policy["authorizationPolicy"]
        self.assertIs(auth["authenticationIdentityMayImplyMusicalAuthorization"], False)
        self.assertIs(auth["machineIdentityMayImplyTenantAuthorization"], False)
        self.assertIs(auth["secretPossessionAloneMayGrantPublicationAuthority"], False)
        self.assertIs(auth["purposeSeparatedCredentialRequired"], True)
        self.assertIs(auth["wildcardSecretScopeAllowed"], False)
        self.assertIs(auth["leastPrivilegeRequired"], True)

    def test_bootstrap_material_cannot_escape_to_repo_browser_or_logs(self) -> None:
        bootstrap = self.policy["bootstrapPolicy"]
        self.assertIs(bootstrap["repositoryMayContainSecretValues"], False)
        self.assertIs(bootstrap["browserMayReceiveMachineSecrets"], False)
        self.assertIs(bootstrap["logsMayContainSecretValues"], False)
        self.assertIs(bootstrap["coolifyMayActAsGeneralProductionSecretStore"], False)
        self.assertIs(bootstrap["bootstrapMaterialMustBeMinimal"], True)
        self.assertIs(bootstrap["bootstrapMaterialMustBeRotatable"], True)

    def test_contract_contains_classes_only_not_secret_value_fields(self) -> None:
        raw = SECRETS_PATH.read_text(encoding="utf-8").lower()
        forbidden_field_markers = (
            '"secretvalue"',
            '"password"',
            '"privatekey"',
            '"accesstoken"',
            '"bearertoken"',
            '"clientsecretvalue"',
        )
        for marker in forbidden_field_markers:
            self.assertNotIn(marker, raw)

    def test_every_real_credential_activation_remains_false(self) -> None:
        locks = self.policy["activationLocks"]
        self.assertGreaterEqual(len(locks), 12)
        for name, enabled in locks.items():
            self.assertIs(enabled, False, name)

    def test_document_preserves_non_activation_and_revocation_boundaries(self) -> None:
        markers = (
            "No real service identity, secret, token, key, password",
            "one shared production machine identity",
            "A revoked generation must never regain authority",
            "production secret activation stops rather than silently weakening this contract",
            "must not create a database server or production credentials",
        )
        for marker in markers:
            self.assertIn(marker, self.document)


if __name__ == "__main__":
    unittest.main()
