from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RBAC = ROOT / "contracts" / "stage9-authentik-rbac-binding-v1.json"
DATABASE = ROOT / "contracts" / "stage9-postgresql-persistence-backup-v1.json"
STORAGE = ROOT / "contracts" / "stage9-object-storage-immutability-v1.json"
PUBLICATION = ROOT / "contracts" / "stage9-publication-persistence-protocol-v1.json"
DOC = ROOT / "docs" / "stage9h-publication-persistence-protocol.md"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class Stage9HPublicationPersistenceProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rbac = load(RBAC)
        cls.database = load(DATABASE)
        cls.storage = load(STORAGE)
        cls.publication = load(PUBLICATION)
        cls.document = DOC.read_text(encoding="utf-8")

    def test_contract_identity_and_dependencies(self) -> None:
        self.assertEqual(self.publication["version"], "scoremosaic-stage9-publication-persistence-protocol-v1")
        self.assertEqual(self.publication["stage"], "9-H")
        self.assertEqual(self.publication["rbacRef"], self.rbac["version"])
        self.assertEqual(self.publication["databaseRef"], self.database["version"])
        self.assertEqual(self.publication["storageRef"], self.storage["version"])
        self.assertEqual(self.publication["stage8HandoffSchema"], "teacher-review-publication-handoff-v1")

    def test_preconditions_require_fresh_stage8o_and_exact_publication_authorization(self) -> None:
        pre = self.publication["preconditions"]
        for field in (
            "freshStage8ORevalidationRequired",
            "suppliedVsRebuiltHandoffEqualityRequired",
            "exactCurrentRevisionRequired",
            "exactApprovedArtifactRequired",
            "exactPublisherPrincipalRequired",
            "exactTenantResourceOperationAuthorizationRequired",
        ):
            self.assertIs(pre[field], True, field)
        self.assertEqual(pre["publicationOperation"], "publication:execute")
        self.assertIs(pre["humanApprovalMayBeInferred"], False)

    def test_state_machine_is_linear_and_only_published_is_terminal_success(self) -> None:
        state = self.publication["stateMachine"]
        self.assertEqual(state["states"], ["prepared", "artifact-written", "published"])
        self.assertEqual(state["initialPersistentState"], "prepared")
        self.assertEqual(state["terminalState"], "published")
        self.assertIs(state["preparedCountsAsPublished"], False)
        self.assertIs(state["artifactWrittenCountsAsPublished"], False)
        self.assertIs(state["publishedStateMayReopen"], False)
        self.assertIs(state["stateAdvanceRequiresExactPriorState"], True)

    def test_prepared_record_is_create_once_and_idempotent(self) -> None:
        prepared = self.publication["preparedRecord"]
        self.assertIs(prepared["createOnceRequired"], True)
        self.assertIs(prepared["exactReplayIdempotent"], True)
        self.assertIs(prepared["differentRequestSamePublicationIdConflicts"], True)
        self.assertIs(prepared["containsNoRawCredentials"], True)
        self.assertEqual(prepared["visibility"], "private")

    def test_artifact_write_is_exact_verified_and_never_overwrites_conflict(self) -> None:
        artifact = self.publication["artifactWrite"]
        for field in (
            "serverDerivedObjectIdentityRequired",
            "createOnceRequired",
            "exactMusicXmlBytesRequired",
            "postWriteHashVerificationRequired",
            "postWriteSizeVerificationRequired",
            "versioningEvidenceRequired",
            "objectLockEvidenceRequired",
            "conflictingExistingBytesFailClosed",
        ):
            self.assertIs(artifact[field], True, field)
        self.assertIs(artifact["failureMayDeleteExistingProtectedArtifact"], False)

    def test_finalization_binds_exact_human_approved_artifact_but_not_universal_truth(self) -> None:
        final = self.publication["finalization"]
        for field in (
            "databaseRecordMustBindExactObjectIdentity",
            "databaseRecordMustBindExactObjectVersion",
            "databaseRecordMustBindExactMusicXmlSha256",
            "databaseRecordMustBindExactPublisher",
            "databaseRecordMustBindExactApprovalRecord",
        ):
            self.assertIs(final[field], True, field)
        self.assertEqual(final["defaultVisibility"], "private")
        self.assertIs(final["publishedImpliesPublic"], False)
        self.assertIs(final["authoritativeMusicalTruth"], False)

    def test_crash_recovery_is_reverify_not_overwrite(self) -> None:
        recovery = self.publication["crashRecovery"]
        self.assertIs(recovery["preparedWithoutObjectMayResume"], True)
        self.assertIs(recovery["objectWithoutPublishedFinalizationRequiresExactObjectReverification"], True)
        self.assertIs(recovery["conflictingObjectRequiresManualFailureResolution"], True)
        self.assertIs(recovery["publishedExactReplayReturnsExistingRecord"], True)
        self.assertIs(recovery["automaticOverwriteAllowed"], False)
        self.assertIs(recovery["automaticProtectedObjectDeletionAllowed"], False)

    def test_activation_locks_all_false(self) -> None:
        for name, value in self.publication["activationLocks"].items():
            self.assertIs(value, False, name)

    def test_document_preserves_external_execution_stop(self) -> None:
        for marker in (
            "No publication database write, object-storage write, route, public visibility change",
            "Only `published` is a completed publication",
            "`PUBLISHED` does not mean `PUBLIC`",
            "Do not overwrite and do not auto-delete",
            "stop before real Hetzner provisioning, credential creation, DNS/TLS changes, or publication execution",
        ):
            self.assertIn(marker, self.document)


if __name__ == "__main__":
    unittest.main()
