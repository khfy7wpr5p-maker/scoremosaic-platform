from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ELIGIBILITY = ROOT / "contracts" / "stage9-production-foundation-eligibility-v1.json"
DOC = ROOT / "docs" / "stage9i-production-foundation-eligibility.md"
CONTRACT_PATHS = [
    ROOT / "contracts" / "stage9-production-foundation-baseline-v1.json",
    ROOT / "contracts" / "stage9-resource-topology-v1.json",
    ROOT / "contracts" / "stage9-service-identity-secrets-v1.json",
    ROOT / "contracts" / "stage9-postgresql-persistence-backup-v1.json",
    ROOT / "contracts" / "stage9-object-storage-immutability-v1.json",
    ROOT / "contracts" / "stage9-authentik-rbac-binding-v1.json",
    ROOT / "contracts" / "stage9-infisical-capability-eligibility-v1.json",
    ROOT / "contracts" / "stage9-publication-persistence-protocol-v1.json",
]


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class Stage9IProductionFoundationEligibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.eligibility = load(ELIGIBILITY)
        cls.contracts = [load(path) for path in CONTRACT_PATHS]
        cls.document = DOC.read_text(encoding="utf-8")

    def test_identity_and_all_stage9_contracts_are_bound(self) -> None:
        self.assertEqual(self.eligibility["version"], "scoremosaic-stage9-production-foundation-eligibility-v1")
        self.assertEqual(self.eligibility["stage"], "9-I")
        refs = self.eligibility["contractRefs"]
        self.assertEqual(refs, [contract["version"] for contract in self.contracts])

    def test_repository_preparation_is_complete_but_runtime_is_not_eligible(self) -> None:
        ready = self.eligibility["readiness"]
        self.assertIs(ready["repositoryProductionArchitectureBaselineComplete"], True)
        self.assertIs(ready["repositorySecurityContractsCompleteForStage9"], True)
        self.assertIs(ready["readyForExternalInfrastructureProvisioningHandoff"], True)
        self.assertIs(ready["productionRuntimeEligible"], False)
        self.assertIs(ready["publicTrafficEligible"], False)
        self.assertIs(ready["publicationExecutionEligible"], False)
        self.assertIs(ready["autonomousRepositoryOnlyStage9MayCrossProvisioningBoundary"], False)

    def test_external_blockers_cover_provider_compute_data_identity_and_operations(self) -> None:
        blockers = set(self.eligibility["externalBlockers"])
        required = {
            "concrete-hetzner-account-project-and-billing-authority",
            "st-omr-inference-benchmark-and-compute-sku-selection",
            "postgresql-rpo-rto-retention-and-isolated-restore-proof",
            "provider-versioning-object-lock-and-independent-copy-proof",
            "authentik-production-deployment-issuer-client-and-admin-protection",
            "infisical-current-deployment-license-capability-proof",
            "production-machine-identities-secret-bootstrap-rotation-and-revocation",
            "monitoring-incident-response-and-rollback-plan",
            "explicit-narrow-runtime-activation-scope",
        }
        self.assertTrue(required.issubset(blockers))

    def test_later_public_traffic_hardening_is_explicit(self) -> None:
        gates = set(self.eligibility["laterProductionTrafficGates"])
        self.assertTrue({
            "repository-owned-vulnerability-dependency-and-secret-scanning",
            "container-base-image-digest-pinning",
            "release-sbom-and-provenance-policy",
            "privacy-safe-production-logging-and-error-behavior",
            "load-capacity-and-failure-recovery-validation",
        }.issubset(gates))

    def test_external_inputs_are_not_pretended_present(self) -> None:
        inputs = self.eligibility["humanOrExternalInputsRequired"]
        for name, required in inputs.items():
            self.assertIs(required, True, name)

    def test_every_preserved_runtime_lock_is_false(self) -> None:
        for name, value in self.eligibility["preservedLocks"].items():
            self.assertIs(value, False, name)

    def test_parent_contract_runtime_locks_remain_false(self) -> None:
        for contract in self.contracts:
            locks = contract.get("activationLocks")
            if locks:
                for name, value in locks.items():
                    self.assertIs(value, False, f"{contract['version']}:{name}")

    def test_infisical_parent_still_not_eligible(self) -> None:
        infisical = next(contract for contract in self.contracts if contract["stage"] == "9-G")
        self.assertIs(infisical["eligibility"]["productionEligible"], False)

    def test_stop_boundary_blocks_paid_resources_credentials_and_publication(self) -> None:
        stop = self.eligibility["stopBoundary"]
        self.assertEqual(stop["name"], "external-production-provisioning-boundary")
        self.assertIs(stop["repositoryMayDescribeAndValidate"], True)
        self.assertIs(stop["repositoryMayInventProviderFacts"], False)
        self.assertIs(stop["repositoryMayProvisionPaidResourcesWithoutExternalAuthority"], False)
        self.assertIs(stop["repositoryMayGenerateOrExposeRealCredentialsWithoutExternalAuthority"], False)
        self.assertIs(stop["repositoryMayExecutePublicationWithoutRuntimeEligibility"], False)

    def test_document_explicitly_states_why_autonomous_repo_work_stops(self) -> None:
        for marker in (
            "production runtime eligibility remains false",
            "real external infrastructure provisioning",
            "Those facts cannot be safely invented by the repository.",
            "providerResourcesCreated=false",
            "Once the concrete external inputs are supplied",
        ):
            self.assertIn(marker, self.document)


if __name__ == "__main__":
    unittest.main()
