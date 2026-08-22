from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = ROOT / "contracts" / "stage9-production-foundation-baseline-v1.json"
DOC_PATH = ROOT / "docs" / "stage9a-production-foundation-baseline.md"
STAGE8O_SCHEMA_PATH = ROOT / "contracts" / "teacher-review-publication-handoff-v1.schema.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class Stage9AProductionFoundationBaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.baseline = load_json(BASELINE_PATH)
        cls.document = DOC_PATH.read_text(encoding="utf-8")
        cls.stage8o = load_json(STAGE8O_SCHEMA_PATH)

    def test_files_exist_are_regular_and_parse(self) -> None:
        for path in (BASELINE_PATH, DOC_PATH, STAGE8O_SCHEMA_PATH):
            self.assertTrue(path.is_file(), path)
            self.assertFalse(path.is_symlink(), path)

    def test_baseline_identity_is_exact(self) -> None:
        self.assertEqual(
            self.baseline["version"],
            "scoremosaic-stage9-production-foundation-baseline-v1",
        )
        self.assertEqual(self.baseline["stage"], "9-A")
        self.assertEqual(
            self.baseline["status"],
            "APPROVED_REPOSITORY_BASELINE_WITH_RUNTIME_LOCKS",
        )

    def test_hosting_choice_is_bounded_and_compute_is_deferred(self) -> None:
        hosting = self.baseline["hosting"]
        self.assertEqual(hosting["provider"], "hetzner")
        self.assertEqual(hosting["country"], "DE")
        self.assertEqual(hosting["primaryLocation"], "nbg1")
        self.assertEqual(hosting["deploymentController"], "coolify")
        self.assertEqual(
            hosting["computeSkuSelection"],
            "deferred_until_st_omr_inference_benchmark",
        )

    def test_database_is_postgresql18_private_and_restore_oriented(self) -> None:
        database = self.baseline["database"]
        self.assertEqual(database["engine"], "postgresql")
        self.assertEqual(database["majorVersion"], 18)
        self.assertIs(database["currentSupportedMinorRequired"], True)
        self.assertIs(database["separatePrivateHostRequired"], True)
        self.assertIs(database["publicInternetExposure"], False)
        self.assertIs(database["externalS3CompatibleBackupRequired"], True)

    def test_object_storage_does_not_invent_native_replication(self) -> None:
        storage = self.baseline["objectStorage"]
        self.assertEqual(storage["provider"], "hetzner-object-storage")
        self.assertEqual(storage["primaryLocation"], "nbg1")
        self.assertEqual(storage["secondaryBackupLocation"], "fsn1")
        self.assertIs(storage["s3Compatible"], True)
        self.assertIs(storage["versioningRequired"], True)
        self.assertIs(storage["objectLockRequiredForPublishedArtifacts"], True)
        self.assertIs(storage["nativeCrossLocationReplicationAssumed"], False)
        self.assertIs(storage["scheduledIndependentCopyRequired"], True)

    def test_identity_proves_identity_but_not_musical_authority(self) -> None:
        identity = self.baseline["identity"]
        self.assertEqual(identity["provider"], "authentik")
        self.assertEqual(identity["deployment"], "self-hosted")
        self.assertIs(identity["oidcRequired"], True)
        self.assertEqual(identity["resourceAuthorizationOwner"], "scoremosaic")
        self.assertIs(identity["identityProviderMayGrantMusicalAuthorityDirectly"], False)

    def test_secrets_baseline_assumes_no_paid_capability(self) -> None:
        secrets = self.baseline["secrets"]
        self.assertEqual(secrets["targetManager"], "infisical")
        self.assertEqual(secrets["coolifyRole"], "bootstrap-secrets-only")
        self.assertIs(secrets["environmentIsolationRequired"], True)
        self.assertIs(secrets["paidCapabilitiesAssumed"], False)
        self.assertIs(secrets["licensingAndCapabilityGateRequiredBeforeProduction"], True)
        self.assertIs(secrets["applicationSecretsMayBeCommittedToRepository"], False)

    def test_publication_is_internal_immutable_and_private_by_default(self) -> None:
        publication = self.baseline["publication"]
        self.assertEqual(publication["destination"], "scoremosaic-internal-publication")
        self.assertEqual(publication["recordStore"], "postgresql")
        self.assertEqual(publication["artifactStore"], "hetzner-object-storage")
        self.assertEqual(publication["defaultVisibility"], "private")
        self.assertIs(publication["immutableArtifactRequired"], True)
        self.assertIs(publication["objectLockRequired"], True)
        self.assertIs(publication["approvalAndPublicationPermissionsSeparated"], True)
        self.assertIs(publication["publishedImpliesPublicVisibility"], False)

    def test_every_runtime_activation_lock_remains_false(self) -> None:
        locks = self.baseline["activationLocks"]
        self.assertGreaterEqual(len(locks), 10)
        for name, enabled in locks.items():
            self.assertIs(enabled, False, name)

    def test_stage8o_external_side_effect_boundary_is_unchanged(self) -> None:
        properties = self.stage8o["properties"]
        authorization = properties["authorization"]["properties"]
        capabilities = properties["capabilities"]["properties"]
        state = properties["state"]["properties"]

        self.assertIs(authorization["productionPublicationAuthority"]["const"], False)
        self.assertEqual(
            state["status"]["const"],
            "awaiting_external_publication_execution",
        )
        self.assertIs(capabilities["canExecutePublication"]["const"], False)
        self.assertIs(capabilities["canWriteExternal"]["const"], False)
        self.assertIs(capabilities["canPersistProduction"]["const"], False)
        self.assertIs(capabilities["publicationGranted"]["const"], False)
        self.assertIs(capabilities["authoritativeMusicalTruth"]["const"], False)

    def test_document_explicitly_forbids_implicit_activation(self) -> None:
        required_markers = (
            "No production resource, credential, route, provider write",
            "Stage 8-O remains the authoritative external side-effect boundary",
            "PUBLISHED` does not mean `PUBLIC",
            "must never be committed to the repository",
            "A passing architecture baseline is not permission to create infrastructure",
        )
        for marker in required_markers:
            self.assertIn(marker, self.document)


if __name__ == "__main__":
    unittest.main()
