from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "contracts" / "stage9-production-foundation-baseline-v1.json"
SECRETS = ROOT / "contracts" / "stage9-service-identity-secrets-v1.json"
DATABASE = ROOT / "contracts" / "stage9-postgresql-persistence-backup-v1.json"
DOC = ROOT / "docs" / "stage9d-postgresql-persistence-backup-contract.md"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class Stage9DPostgresqlPersistenceBackupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.baseline = load(BASELINE)
        cls.secrets = load(SECRETS)
        cls.database = load(DATABASE)
        cls.document = DOC.read_text(encoding="utf-8")

    def test_contract_identity_and_parent_binding(self) -> None:
        self.assertEqual(self.database["version"], "scoremosaic-stage9-postgresql-persistence-backup-v1")
        self.assertEqual(self.database["stage"], "9-D")
        self.assertEqual(self.database["baselineRef"], self.baseline["version"])
        self.assertEqual(self.database["identityPolicyRef"], self.secrets["version"])

    def test_postgresql18_private_durability_boundary(self) -> None:
        db = self.database["database"]
        self.assertEqual(db["engine"], "postgresql")
        self.assertEqual(db["majorVersion"], 18)
        self.assertIs(db["currentSupportedMinorRequiredAtDeployment"], True)
        self.assertIs(db["privateHostRequired"], True)
        self.assertIs(db["separateFromOmrComputeRequired"], True)
        self.assertIs(db["publicListenerAllowed"], False)
        self.assertIs(db["fsyncMayBeDisabled"], False)
        self.assertIs(db["fullPageWritesMayBeDisabled"], False)
        self.assertIs(db["authoritativeTransactionsMayUseAsyncDurability"], False)

    def test_large_artifact_bytes_stay_out_of_database(self) -> None:
        placement = self.database["dataPlacement"]
        self.assertIs(placement["relationalMetadataInDatabase"], True)
        for field in (
            "sourceDocumentBytesInDatabase",
            "candidateArtifactBytesInDatabase",
            "publishedMusicXmlBytesInDatabase",
        ):
            self.assertIs(placement[field], False, field)
        self.assertIs(placement["artifactContentAddressedByHashAndStorageRef"], True)

    def test_database_roles_are_distinct_and_non_admin(self) -> None:
        roles = self.database["roles"]
        role_values = [
            roles["applicationRole"],
            roles["publicationRole"],
            roles["backupRole"],
            roles["authentikRole"],
        ]
        self.assertEqual(len(role_values), len(set(role_values)))
        self.assertIs(roles["ordinaryServicesMayUseDatabaseAdmin"], False)
        self.assertIs(roles["rolesMustBeDistinct"], True)

    def test_integrity_never_allows_stale_overwrite_or_silent_repair(self) -> None:
        integrity = self.database["integrity"]
        self.assertIs(integrity["immutableApprovalAndPublicationLineageRequired"], True)
        self.assertIs(integrity["artifactSha256BindingRequired"], True)
        self.assertIs(integrity["revisionParentBindingRequired"], True)
        self.assertIs(integrity["auditPredecessorBindingRequired"], True)
        self.assertIs(integrity["silentRepairAllowed"], False)
        self.assertIs(integrity["staleWriteMayOverwriteCurrentHead"], False)

    def test_backup_is_off_host_private_encrypted_and_restore_driven(self) -> None:
        backup = self.database["backupPolicy"]
        self.assertIs(backup["backupMustLeavePrimaryHost"], True)
        self.assertIs(backup["s3CompatibleTargetRequired"], True)
        self.assertIs(backup["backupTargetMustNotBePublic"], True)
        self.assertIs(backup["logicalBackupRequired"], True)
        self.assertIs(backup["pointInTimeRecoveryOrEquivalentRequiredBeforeGa"], True)
        self.assertIs(backup["backupEncryptionRequired"], True)
        self.assertIs(backup["retentionPolicyMustBeExplicitBeforeActivation"], True)
        self.assertIs(backup["rpoRtoMustBeExplicitBeforeActivation"], True)
        self.assertIs(backup["backupSuccessAloneCountsAsRecoveryProof"], False)

    def test_restore_drill_cannot_target_production(self) -> None:
        restore = self.database["restorePolicy"]
        self.assertIs(restore["isolatedRestoreDrillRequiredBeforeProduction"], True)
        self.assertIs(restore["restoreMustUseFreshTarget"], True)
        self.assertIs(restore["restoredSchemaValidationRequired"], True)
        self.assertIs(restore["restoredLineageValidationRequired"], True)
        self.assertIs(restore["restoredArtifactReferenceValidationRequired"], True)
        self.assertIs(restore["restoreMustNotOverwriteProductionDuringTest"], True)

    def test_destructive_migration_is_separately_gated(self) -> None:
        migration = self.database["migrationPolicy"]
        self.assertIs(migration["schemaMigrationsMustBeVersioned"], True)
        self.assertIs(migration["destructiveMigrationRequiresSeparateApproval"], True)
        self.assertIs(migration["destructiveMigrationRequiresFreshBackupAndRestoreEvidence"], True)
        self.assertIs(migration["automaticProductionMigrationFromUnreviewedBranch"], False)

    def test_runtime_locks_all_remain_false(self) -> None:
        for name, value in self.database["activationLocks"].items():
            self.assertIs(value, False, name)

    def test_document_does_not_invent_rpo_or_activate_database(self) -> None:
        for marker in (
            "No PostgreSQL server, production database, role, connection string",
            "does not invent RPO/RTO numbers",
            "A successful backup command is **not** recovery proof",
            "must never run a production schema migration automatically",
            "must not create a bucket, S3 key, object, or scheduled copy job",
        ):
            self.assertIn(marker, self.document)


if __name__ == "__main__":
    unittest.main()
