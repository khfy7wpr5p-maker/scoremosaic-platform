from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "contracts" / "stage9-production-foundation-baseline-v1.json"
TOPOLOGY = ROOT / "contracts" / "stage9-resource-topology-v1.json"
STORAGE = ROOT / "contracts" / "stage9-object-storage-immutability-v1.json"
DOC = ROOT / "docs" / "stage9e-object-storage-immutability-contract.md"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class Stage9EObjectStorageImmutabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.baseline = load(BASELINE)
        cls.topology = load(TOPOLOGY)
        cls.storage = load(STORAGE)
        cls.document = DOC.read_text(encoding="utf-8")

    def test_contract_identity_and_parent_binding(self) -> None:
        self.assertEqual(self.storage["version"], "scoremosaic-stage9-object-storage-immutability-v1")
        self.assertEqual(self.storage["stage"], "9-E")
        self.assertEqual(self.storage["baselineRef"], self.baseline["version"])
        self.assertEqual(self.storage["topologyRef"], self.topology["version"])

    def test_provider_mapping_matches_approved_locations(self) -> None:
        provider = self.storage["provider"]
        approved = self.baseline["objectStorage"]
        self.assertEqual(provider["name"], "hetzner-object-storage")
        self.assertEqual(provider["primaryLocation"], approved["primaryLocation"])
        self.assertEqual(provider["secondaryBackupLocation"], approved["secondaryBackupLocation"])
        self.assertIs(provider["authenticatedTlsRequired"], True)
        self.assertIs(provider["publicBucketsAllowedByDefault"], False)
        self.assertIs(provider["nativeCrossLocationReplicationAssumed"], False)

    def test_source_and_candidate_are_create_once_and_hash_bound(self) -> None:
        classes = self.storage["artifactClasses"]
        source = classes["source"]
        candidate = classes["candidate"]
        self.assertIs(source["createOnceRequired"], True)
        self.assertIs(source["serverDerivedKeyRequired"], True)
        self.assertIs(source["sha256BindingRequired"], True)
        self.assertIs(source["callerControlledPathAllowed"], False)
        self.assertIs(candidate["createOnceRequired"], True)
        self.assertIs(candidate["sha256BindingRequired"], True)
        self.assertIs(candidate["overwriteDifferentBytesAllowed"], False)

    def test_published_artifacts_are_immutable_private_and_record_bound(self) -> None:
        published = self.storage["artifactClasses"]["published"]
        self.assertIs(published["versioningRequired"], True)
        self.assertIs(published["objectLockRequired"], True)
        self.assertIs(published["publicationRecordBindingRequired"], True)
        self.assertIs(published["sha256BindingRequired"], True)
        self.assertIs(published["mutableInPlace"], False)
        self.assertIs(published["publicByDefault"], False)

    def test_models_never_trust_mutable_latest_as_authority(self) -> None:
        model = self.storage["artifactClasses"]["model"]
        self.assertIs(model["sha256BindingRequired"], True)
        self.assertIs(model["versionIdentityRequired"], True)
        self.assertIs(model["mutableLatestAliasAuthoritative"], False)

    def test_backup_copy_is_one_way_verified_and_fail_closed(self) -> None:
        copy = self.storage["copyPolicy"]
        self.assertEqual(copy["direction"], "nbg1-primary-to-fsn1-secondary")
        self.assertIs(copy["scheduledIndependentCopyRequired"], True)
        self.assertIs(copy["copyMustVerifySourceHash"], True)
        self.assertIs(copy["copyMustVerifyDestinationHash"], True)
        self.assertIs(copy["copyMustVerifySize"], True)
        self.assertIs(copy["exactReplayMustBeIdempotent"], True)
        self.assertIs(copy["differentBytesMayOverwriteExistingBackupIdentity"], False)
        self.assertIs(copy["secondaryMayWriteBackToPrimary"], False)

    def test_browser_and_workers_do_not_gain_destructive_authority(self) -> None:
        access = self.storage["accessPolicy"]
        for field in (
            "browserMayReceiveS3Credentials",
            "callerMaySelectBucket",
            "callerMaySelectStorageRoot",
            "applicationMayDeletePublishedArtifact",
            "omrComputeMayDeleteSourceArtifact",
            "backupWorkerMayDeletePrimaryObjects",
        ):
            self.assertIs(access[field], False, field)
        self.assertIs(access["leastPrivilegeCredentialClassesRequired"], True)

    def test_retention_cannot_break_protected_lineage(self) -> None:
        retention = self.storage["retentionPolicy"]
        self.assertIs(retention["explicitPolicyRequiredBeforeActivation"], True)
        self.assertIs(retention["protectedPublicationMayBeDeletedByRoutineCleanup"], False)
        self.assertIs(retention["retentionMayBreakDatabaseArtifactBindings"], False)
        self.assertIs(retention["legalDeletionWorkflowDeferredToSeparateContract"], True)

    def test_activation_locks_all_remain_false(self) -> None:
        for name, value in self.storage["activationLocks"].items():
            self.assertIs(value, False, name)

    def test_document_preserves_non_activation_and_private_defaults(self) -> None:
        for marker in (
            "No Hetzner bucket, S3 credential, object, versioning flag, Object Lock setting",
            "does not assume native cross-location replication",
            "`PUBLISHED` remains separate from `PUBLIC`",
            "A mutable `latest` alias can never be treated as authoritative model identity",
            "must not create a real user, OIDC client, session, role assignment, or public login route",
        ):
            self.assertIn(marker, self.document)


if __name__ == "__main__":
    unittest.main()
