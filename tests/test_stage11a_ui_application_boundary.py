from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / "contracts" / "stage11-ui-application-boundary-v1.json").read_text(encoding="utf-8"))
DOC = (ROOT / "docs" / "stage11a-ui-application-boundary.md").read_text(encoding="utf-8")
STAGE10 = json.loads((ROOT / "contracts" / "stage10-ui-experience-eligibility-v1.json").read_text(encoding="utf-8"))


class Stage11AUiApplicationBoundaryTests(unittest.TestCase):
    def test_parent_stage_allows_contract_design_only(self) -> None:
        boundary = STAGE10["stage11Boundary"]
        self.assertTrue(boundary["mayDesignTypedUiApplicationContracts"])
        self.assertTrue(boundary["mayDesignLocalAdapters"])
        self.assertFalse(boundary["mayActivateNetworkByDefault"])
        self.assertFalse(boundary["mayActivateServerWriteByDefault"])

    def test_contract_identity_and_request_vocabulary(self) -> None:
        self.assertEqual("scoremosaic-stage11-ui-application-boundary-v1", CONTRACT["version"])
        self.assertEqual("11-A", CONTRACT["stage"])
        self.assertEqual("CONTRACT_DESIGN_ONLY", CONTRACT["status"])
        self.assertEqual(
            ["review.read", "issues.read", "sourceEvidence.read", "validation.read", "editIntent.prepare"],
            CONTRACT["requestKinds"],
        )
        self.assertTrue(CONTRACT["security"]["unknownRequestKindRejected"])

    def test_transport_remains_local_only(self) -> None:
        transport = CONTRACT["transport"]
        self.assertFalse(transport["networkAllowed"])
        self.assertFalse(transport["productionApiAllowed"])
        self.assertTrue(transport["localAdapterAllowed"])
        self.assertFalse(transport["browserPersistenceAllowed"])

    def test_browser_and_local_adapter_are_non_authoritative(self) -> None:
        authority = CONTRACT["authority"]
        self.assertFalse(authority["browserAuthoritative"])
        self.assertFalse(authority["uiValidationAuthoritative"])
        self.assertFalse(authority["localAdapterAuthoritative"])
        self.assertTrue(authority["serverAuthorizationRequiredForMutation"])
        self.assertFalse(authority["uiMayCreateScoreEditCommand"])
        self.assertFalse(authority["uiMayCreateTeacherScoreRevision"])
        self.assertFalse(authority["uiMayApprove"])
        self.assertFalse(authority["uiMayPublish"])

    def test_response_envelope_is_bounded(self) -> None:
        envelope = CONTRACT["responseEnvelope"]
        self.assertEqual(
            ["schemaVersion", "requestId", "kind", "state", "data", "error"],
            envelope["requiredFields"],
        )
        self.assertEqual(["success", "empty", "rejected", "unavailable"], envelope["states"])
        self.assertTrue(envelope["successRequiresErrorNull"])
        self.assertTrue(envelope["nonSuccessMayNotImplyAuthority"])

    def test_identity_binding_is_exact_but_live_identity_is_deferred(self) -> None:
        identity = CONTRACT["identityFields"]
        self.assertTrue(identity["documentIdRequired"])
        self.assertTrue(identity["revisionRequired"])
        self.assertTrue(identity["requestIdRequired"])
        self.assertTrue(identity["tenantIdProductionMeaningDeferred"])
        self.assertTrue(identity["principalProductionMeaningDeferred"])

    def test_protected_material_and_live_artifact_reads_are_forbidden(self) -> None:
        security = CONTRACT["security"]
        self.assertTrue(security["credentialsForbidden"])
        self.assertTrue(security["tokensForbidden"])
        self.assertTrue(security["cookiesForbidden"])
        self.assertTrue(security["productionArtifactReadsForbidden"])

    def test_every_activation_lock_remains_false(self) -> None:
        for name, value in CONTRACT["activationLocks"].items():
            with self.subTest(lock=name):
                self.assertIs(value, False)

    def test_document_preserves_live_integration_boundary(self) -> None:
        for marker in (
            "Contract design only",
            "Unknown request kinds fail closed",
            "edit intent == ScoreEditCommand",
            "no network or production API",
            "Stage 11-B",
        ):
            self.assertIn(marker, DOC)


if __name__ == "__main__":
    unittest.main()
