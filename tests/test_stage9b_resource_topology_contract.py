from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = ROOT / "contracts" / "stage9-production-foundation-baseline-v1.json"
TOPOLOGY_PATH = ROOT / "contracts" / "stage9-resource-topology-v1.json"
DOC_PATH = ROOT / "docs" / "stage9b-resource-topology-contract.md"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class Stage9BResourceTopologyContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.baseline = load_json(BASELINE_PATH)
        cls.topology = load_json(TOPOLOGY_PATH)
        cls.document = DOC_PATH.read_text(encoding="utf-8")

    def test_contract_identity_and_baseline_binding(self) -> None:
        self.assertEqual(
            self.topology["version"], "scoremosaic-stage9-resource-topology-v1"
        )
        self.assertEqual(self.topology["stage"], "9-B")
        self.assertEqual(
            self.topology["baselineRef"], self.baseline["version"]
        )
        self.assertEqual(
            self.topology["status"],
            "REPOSITORY_ONLY_TOPOLOGY_WITH_RUNTIME_LOCKS",
        )

    def test_provider_mapping_matches_stage9a_without_real_resources(self) -> None:
        provider = self.topology["providerMapping"]
        baseline_hosting = self.baseline["hosting"]
        self.assertEqual(provider["provider"], baseline_hosting["provider"])
        self.assertEqual(
            provider["primaryLocation"], baseline_hosting["primaryLocation"]
        )
        self.assertEqual(
            provider["deploymentController"],
            baseline_hosting["deploymentController"],
        )
        self.assertIs(provider["realResourceIdsAssigned"], False)
        self.assertIs(provider["realAddressesAssigned"], False)
        self.assertIs(provider["realDnsNamesAssigned"], False)

    def test_required_trust_zones_are_closed_and_unique(self) -> None:
        zones = self.topology["trustZones"]
        self.assertEqual(len(zones), len(set(zones)))
        self.assertEqual(
            set(zones),
            {
                "public-edge",
                "application-private",
                "identity-controlled",
                "data-private",
                "security-private",
                "compute-private",
                "provider-object-storage",
            },
        )

    def test_only_edge_is_normal_user_facing_application_ingress(self) -> None:
        roles = {item["role"]: item for item in self.topology["resourceRoles"]}
        self.assertIs(roles["scoremosaic-edge"]["userFacingApplicationEndpoint"], True)
        self.assertEqual(
            roles["scoremosaic-edge"]["allowedPublicIngress"], ["https-443"]
        )
        self.assertIs(roles["scoremosaic-edge"]["mayHoldProviderCredentials"], False)
        self.assertIs(roles["scoremosaic-application"]["directPublicIngress"], False)
        self.assertIs(roles["postgresql-primary"]["directPublicIngress"], False)
        self.assertIs(roles["omr-compute"]["directPublicIngress"], False)
        self.assertIs(
            roles["infisical-secrets"]["directPublicApplicationIngress"], False
        )

    def test_identity_does_not_gain_musical_authority(self) -> None:
        roles = {item["role"]: item for item in self.topology["resourceRoles"]}
        identity = roles["authentik-identity"]
        self.assertIs(identity["userLoginMayBePublishedThroughEdge"], True)
        self.assertIs(identity["adminInterfacePublicByDefault"], False)
        self.assertIs(
            identity["mayGrantScoremosaicMusicalAuthorityDirectly"], False
        )

    def test_private_network_never_counts_as_authentication(self) -> None:
        policy = self.topology["networkPolicy"]
        self.assertIs(policy["defaultDenyBetweenTrustZones"], True)
        self.assertIs(policy["privateNetworkAloneCountsAsAuthentication"], False)
        self.assertIs(policy["serviceToServiceAuthenticationRequired"], True)
        self.assertIs(policy["tlsRequiredForProviderApiTraffic"], True)

    def test_browser_cannot_reach_privileged_backends_or_receive_credentials(self) -> None:
        policy = self.topology["networkPolicy"]
        for field in (
            "browserMayReachDatabaseDirectly",
            "browserMayReachSecretsManagerDirectly",
            "browserMayReachOmrComputeDirectly",
            "browserMayReceiveProviderCredentials",
            "databaseMayExposePublicListener",
            "omrComputeMayExposePublicListener",
            "secretManagerMayExposePublicApplicationListener",
            "objectStorageBucketsPublicByDefault",
        ):
            self.assertIs(policy[field], False, field)

    def test_storage_locations_match_stage9a_and_no_native_replication_is_invented(self) -> None:
        roles = {item["role"]: item for item in self.topology["resourceRoles"]}
        storage = self.baseline["objectStorage"]
        self.assertEqual(
            roles["object-storage-primary"]["location"],
            storage["primaryLocation"],
        )
        self.assertEqual(
            roles["object-storage-secondary-backup"]["location"],
            storage["secondaryBackupLocation"],
        )
        self.assertIs(
            roles["object-storage-secondary-backup"]["nativeReplicationAssumed"],
            False,
        )

    def test_compute_sku_remains_deferred(self) -> None:
        roles = {item["role"]: item for item in self.topology["resourceRoles"]}
        self.assertEqual(
            roles["omr-compute"]["computeSku"],
            self.baseline["hosting"]["computeSkuSelection"],
        )

    def test_planned_edges_are_descriptive_not_activation_authority(self) -> None:
        edges = self.topology["plannedEdges"]
        self.assertIn("internet -> scoremosaic-edge:https-443", edges)
        self.assertIn(
            "gateway-orchestrator -> omr-compute:purpose-separated-authenticated-dispatch",
            edges,
        )
        self.assertIn(
            "backup-worker -> object-storage-secondary-backup:authenticated-s3-write",
            edges,
        )

    def test_all_runtime_activation_locks_remain_false(self) -> None:
        locks = self.topology["activationLocks"]
        self.assertGreaterEqual(len(locks), 12)
        for name, enabled in locks.items():
            self.assertIs(enabled, False, name)

    def test_document_preserves_non_activation_boundary(self) -> None:
        markers = (
            "No Hetzner network, VM, firewall, DNS record, TLS certificate",
            "A service being on a private network is never enough to authenticate it",
            "browser must never connect directly to PostgreSQL, Infisical, or OMR workers",
            "These strings describe the maximum intended topology",
            "must contain no real credential material",
        )
        for marker in markers:
            self.assertIn(marker, self.document)


if __name__ == "__main__":
    unittest.main()
