from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "contracts" / "stage9-production-foundation-baseline-v1.json"
SECRETS = ROOT / "contracts" / "stage9-service-identity-secrets-v1.json"
ELIGIBILITY = ROOT / "contracts" / "stage9-infisical-capability-eligibility-v1.json"
DOC = ROOT / "docs" / "stage9g-infisical-capability-eligibility.md"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class Stage9GInfisicalCapabilityEligibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.baseline = load(BASELINE)
        cls.secrets = load(SECRETS)
        cls.eligibility = load(ELIGIBILITY)
        cls.document = DOC.read_text(encoding="utf-8")

    def test_contract_identity_and_parent_binding(self) -> None:
        self.assertEqual(self.eligibility["version"], "scoremosaic-stage9-infisical-capability-eligibility-v1")
        self.assertEqual(self.eligibility["stage"], "9-G")
        self.assertEqual(self.eligibility["baselineRef"], self.baseline["version"])
        self.assertEqual(self.eligibility["identitySecretsRef"], self.secrets["version"])

    def test_target_is_selected_but_not_production_eligible(self) -> None:
        target = self.eligibility["target"]
        self.assertEqual(target["product"], "infisical")
        self.assertIs(target["selectedAsArchitectureTarget"], True)
        self.assertIs(target["productionEligibilityGranted"], False)
        self.assertIs(target["paidCapabilitiesAssumed"], False)

    def test_required_capability_set_is_explicit(self) -> None:
        required = set(self.eligibility["requiredCapabilityEvidence"])
        self.assertTrue({
            "machine-identity-authentication",
            "least-privilege-secret-scoping",
            "development-staging-production-isolation",
            "credential-revocation",
            "bounded-audit-evidence",
            "backup-and-recovery",
        }.issubset(required))

    def test_live_docs_and_license_must_be_reverified(self) -> None:
        policy = self.eligibility["verificationPolicy"]
        self.assertIs(policy["currentDocumentationMustBeCheckedAtActivationTime"], True)
        self.assertIs(policy["selectedLicenseMustBeCheckedAtActivationTime"], True)
        self.assertIs(policy["requiredCapabilitiesMayNotBeInferredFromProductName"], True)
        self.assertIs(policy["missingCapabilityMayBeSilentlyWaived"], False)
        self.assertIs(policy["missingCapabilityRequiresAlternativeDesignOrProvider"], True)
        self.assertIs(policy["verificationEvidenceMustBeRetained"], True)

    def test_coolify_never_becomes_general_secret_store(self) -> None:
        bootstrap = self.eligibility["bootstrapBoundary"]
        self.assertIs(bootstrap["coolifyMayStoreMinimalBootstrapOnly"], True)
        self.assertIs(bootstrap["coolifyMayBecomeGeneralSecretStore"], False)
        self.assertIs(bootstrap["repositoryMayContainProductionSecretValues"], False)
        self.assertIs(bootstrap["browserMayReceiveMachineSecret"], False)

    def test_every_live_eligibility_field_is_false(self) -> None:
        for name, value in self.eligibility["eligibility"].items():
            self.assertIs(value, False, name)

    def test_activation_locks_all_false(self) -> None:
        for name, value in self.eligibility["activationLocks"].items():
            self.assertIs(value, False, name)

    def test_document_explicitly_refuses_invented_provider_proof(self) -> None:
        for marker in (
            "production eligibility is explicitly false",
            "does not infer production readiness from the product name",
            "A missing capability is not silently waived",
            "Stage 9-G defines the proof required; it does not invent that proof.",
            "must not execute a real publication or provider write",
        ):
            self.assertIn(marker, self.document)


if __name__ == "__main__":
    unittest.main()
