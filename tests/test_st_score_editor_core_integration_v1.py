from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / "contracts" / "st-score-editor-core-integration-v1.json").read_text(encoding="utf-8"))
ARCHITECTURE = json.loads((ROOT / "contracts" / "architecture-current-state-v1.json").read_text(encoding="utf-8"))
BRIDGE = (ROOT / "prototypes" / "stage11-ui-application-contracts" / "score-editor-core-bridge.js").read_text(encoding="utf-8")
EDIT_INTENT = (ROOT / "prototypes" / "stage10-ui-application-experience" / "edit-intent.js").read_text(encoding="utf-8")
BUILDER = (ROOT / "scripts" / "build_web_preview.py").read_text(encoding="utf-8")

CORE_COMMIT = "70c884fcc0f4c51f3baecf0bf057c78e1ca87f9b"


class STScoreEditorCoreIntegrationV1Tests(unittest.TestCase):
    def test_contract_pins_exact_non_production_core_runtime(self) -> None:
        self.assertEqual("scoremosaic-st-score-editor-core-integration-v1", CONTRACT["version"])
        self.assertIs(CONTRACT["repositoryIntegrationOnly"], True)
        self.assertIs(CONTRACT["productionActivation"], False)
        core = CONTRACT["core"]
        self.assertEqual("khfy7wpr5p-maker/st-score-editor-core", core["repository"])
        self.assertEqual(CORE_COMMIT, core["commit"])
        self.assertEqual("1.0.0", core["runtimeVersion"])
        self.assertIs(core["packagePrivate"], True)
        self.assertIs(core["hostInjected"], True)
        self.assertIs(core["remoteBrowserFetchAllowed"], False)
        self.assertIs(core["copiedCoreSourceAllowed"], False)
        self.assertIs(core["runtimeBundledInPublicPreview"], False)

    def test_operation_mapping_is_closed_and_remove_event_fails_closed(self) -> None:
        mapping = CONTRACT["operationMapping"]
        self.assertEqual("SET_PITCH", mapping["set_pitch"])
        self.assertEqual("SET_DURATION", mapping["set_effective_duration"])
        self.assertEqual("SET_DOTS", mapping["set_dots"])
        self.assertIsNone(mapping["remove_event"])
        self.assertEqual(["remove_event"], CONTRACT["failClosedOperations"])
        self.assertIn("OPERATION_NOT_MAPPED", BRIDGE)
        self.assertNotIn("REPLACE_WITH_REST", BRIDGE)

    def test_browser_and_production_authority_remain_locked(self) -> None:
        authority = CONTRACT["authority"]
        for key in (
            "browserAuthoritative",
            "networkAllowed",
            "persistenceAllowed",
            "serverRevisionAuthority",
            "approvalAuthority",
            "publicationAuthority",
            "liveApiActivated",
            "productionWriteActivated",
        ):
            self.assertIs(authority[key], False, key)

        state = ARCHITECTURE["approvedWorkstreams"]["stScoreEditorCoreIntegration"]
        self.assertEqual(CORE_COMMIT, state["coreCommit"])
        self.assertIs(state["browserBridgeReady"], True)
        self.assertIs(state["runtimeBundledInPreview"], False)
        self.assertIs(state["osmdHostRuntimeActivated"], False)
        self.assertIs(state["liveReadApiActivated"], False)
        self.assertIs(state["liveWriteApiActivated"], False)
        self.assertIs(state["productionPersistenceActivated"], False)

        teacher_review = ARCHITECTURE["teacherReview"]
        self.assertIs(teacher_review["stScoreEditorCoreRepositoryIntegrationReady"], True)
        self.assertIs(teacher_review["stScoreEditorCoreRuntimeActivated"], False)
        self.assertIs(teacher_review["liveTeacherReviewApiActivated"], False)
        self.assertIs(teacher_review["productionWriteActivated"], False)

    def test_bridge_is_fail_closed_and_has_no_network_or_persistence_capability(self) -> None:
        self.assertIn("RUNTIME_UNAVAILABLE", BRIDGE)
        self.assertIn("RUNTIME_PROFILE_MISMATCH", BRIDGE)
        self.assertIn("SEMANTIC_TARGET_NOT_FOUND", BRIDGE)
        self.assertIn("entry.address.kind === 'note'", BRIDGE)
        self.assertIn("entry.address.eventId === issue.location.event", BRIDGE)
        self.assertIn(CORE_COMMIT, BRIDGE)
        for forbidden in (
            "fetch(",
            "XMLHttpRequest",
            "WebSocket",
            "EventSource",
            "navigator.sendBeacon",
            "localStorage",
            "sessionStorage",
            "indexedDB",
            "document.cookie",
            "http://",
            "https://",
        ):
            self.assertNotIn(forbidden, BRIDGE, forbidden)

    def test_structured_edit_uses_core_only_when_exact_safe_bridge_is_available(self) -> None:
        self.assertIn("const coreBridge = window.ScoreMosaicScoreEditorCoreBridge", EDIT_INTENT)
        self.assertIn("coreBridge?.available === true", EDIT_INTENT)
        self.assertIn("coreBridge.serverRevisionAuthority === false", EDIT_INTENT)
        self.assertIn("coreBridge.approvalAuthority === false", EDIT_INTENT)
        self.assertIn("coreBridge.publicationAuthority === false", EDIT_INTENT)
        self.assertIn("coreBridge.commitOperation", EDIT_INTENT)
        self.assertIn("application.prepareEditIntent", EDIT_INTENT)
        self.assertIn("dots < 0 || dots > 8", EDIT_INTENT)
        self.assertIn("coreAvailable && dots > 3", EDIT_INTENT)

    def test_public_fixture_preview_copies_bridge_but_not_core_runtime(self) -> None:
        self.assertIn('"score-editor-core-bridge.js"', BUILDER)
        self.assertIn("core runtime is intentionally not bundled", BUILDER)
        self.assertNotIn("st-score-editor-core/dist", BUILDER)
        self.assertNotIn("opensheetmusicdisplay", BUILDER)


if __name__ == "__main__":
    unittest.main()
