from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / "contracts" / "st-score-editor-core-integration-v1.json").read_text(encoding="utf-8"))
ARCHITECTURE = json.loads((ROOT / "contracts" / "architecture-current-state-v1.json").read_text(encoding="utf-8"))
BRIDGE = (ROOT / "prototypes" / "stage11-ui-application-contracts" / "score-editor-core-bridge.js").read_text(encoding="utf-8")
HOST = (ROOT / "prototypes" / "stage11-ui-application-contracts" / "score-editor-osmd-host.js").read_text(encoding="utf-8")
EDIT_INTENT = (ROOT / "prototypes" / "stage10-ui-application-experience" / "edit-intent.js").read_text(encoding="utf-8")
BUILDER = (ROOT / "scripts" / "build_web_preview.py").read_text(encoding="utf-8")

CORE_COMMIT = "b317abef915d1e16b37572221a38feb3e504450d"


class STScoreEditorCoreIntegrationV1Tests(unittest.TestCase):
    def test_contract_pins_exact_browser_bundle_and_renderer(self) -> None:
        self.assertEqual("scoremosaic-st-score-editor-core-integration-v1", CONTRACT["version"])
        self.assertEqual("E7-H", CONTRACT["stage"])
        self.assertIs(CONTRACT["repositoryIntegrationOnly"], True)
        self.assertIs(CONTRACT["productionActivation"], False)

        core = CONTRACT["core"]
        self.assertEqual("khfy7wpr5p-maker/st-score-editor-core", core["repository"])
        self.assertEqual(CORE_COMMIT, core["commit"])
        self.assertEqual("1.0.0", core["runtimeVersion"])
        self.assertEqual("ST_SCORE_EDITOR_CORE_BROWSER_BUNDLE", core["browserBundleContract"])
        self.assertEqual("STScoreEditorCoreRuntime", core["browserBundleGlobal"])
        self.assertIs(core["packagePrivate"], True)
        self.assertIs(core["remoteBrowserFetchAllowed"], False)
        self.assertIs(core["copiedCoreSourceAllowed"], False)
        self.assertIs(core["runtimeBundledInPublicPreview"], True)
        self.assertIs(core["artifactIntegrityVerifiedByBuilder"], True)

        renderer = CONTRACT["renderer"]
        self.assertEqual("osmd", renderer["family"])
        self.assertEqual("opensheetmusicdisplay", renderer["package"])
        self.assertEqual("2.1.1", renderer["version"])
        self.assertEqual("BSD-3-Clause", renderer["license"])
        self.assertIs(renderer["presentationOnly"], True)
        self.assertIs(renderer["localArtifactRequired"], True)
        self.assertIs(renderer["remoteCdnAllowed"], False)
        self.assertIs(renderer["runtimeBundledInPublicPreview"], True)
        self.assertIs(renderer["urlInputAllowedByHost"], False)
        self.assertIs(renderer["networkUseAllowed"], False)
        for key in ("coordinatesAuthoritative", "domIdsAuthoritative", "rendererObjectsAuthoritative", "svgHitTestingAuthoritative"):
            self.assertIs(renderer[key], False, key)

    def test_operation_mapping_is_closed_and_remove_event_fails_closed(self) -> None:
        mapping = CONTRACT["operationMapping"]
        self.assertEqual("SET_PITCH", mapping["set_pitch"])
        self.assertEqual("SET_DURATION", mapping["set_effective_duration"])
        self.assertEqual("SET_DOTS", mapping["set_dots"])
        self.assertIsNone(mapping["remove_event"])
        self.assertEqual(["remove_event"], CONTRACT["failClosedOperations"])
        self.assertIn("OPERATION_NOT_MAPPED", BRIDGE)
        self.assertNotIn("REPLACE_WITH_REST", BRIDGE)

    def test_browser_renderer_and_production_authority_remain_locked(self) -> None:
        authority = CONTRACT["authority"]
        for key in (
            "browserAuthoritative",
            "rendererAuthoritative",
            "networkAllowed",
            "persistenceAllowed",
            "serverRevisionAuthority",
            "approvalAuthority",
            "publicationAuthority",
            "liveApiActivated",
            "productionWriteActivated",
            "productionRendererActivated",
            "liveAiEditAuthority",
        ):
            self.assertIs(authority[key], False, key)

        state = ARCHITECTURE["approvedWorkstreams"]["stScoreEditorCoreIntegration"]
        self.assertEqual(CORE_COMMIT, state["coreCommit"])
        self.assertIs(state["browserBridgeReady"], True)
        self.assertIs(state["browserBundleReady"], True)
        self.assertIs(state["runtimeBundledInPreview"], True)
        self.assertIs(state["osmdFixturePreviewHostReady"], True)
        self.assertIs(state["osmdFixturePreviewPresentationActivated"], True)
        self.assertIs(state["osmdHostRuntimeActivated"], False)
        self.assertIs(state["productionRendererActivated"], False)
        self.assertIs(state["liveReadApiActivated"], False)
        self.assertIs(state["liveWriteApiActivated"], False)
        self.assertIs(state["productionPersistenceActivated"], False)

        teacher_review = ARCHITECTURE["teacherReview"]
        self.assertIs(teacher_review["stScoreEditorCoreRepositoryIntegrationReady"], True)
        self.assertIs(teacher_review["stScoreEditorCoreFixturePreviewRuntimeActivated"], True)
        self.assertIs(teacher_review["osmdFixturePreviewPresentationActivated"], True)
        self.assertIs(teacher_review["stScoreEditorCoreRuntimeActivated"], False)
        self.assertIs(teacher_review["productionScoreRendererActivated"], False)
        self.assertIs(teacher_review["liveTeacherReviewApiActivated"], False)
        self.assertIs(teacher_review["productionWriteActivated"], False)

    def test_bridge_is_fail_closed_and_pinned_to_new_core(self) -> None:
        self.assertIn("RUNTIME_UNAVAILABLE", BRIDGE)
        self.assertIn("RUNTIME_PROFILE_MISMATCH", BRIDGE)
        self.assertIn("SEMANTIC_TARGET_NOT_FOUND", BRIDGE)
        self.assertIn("entry.address.kind === 'note'", BRIDGE)
        self.assertIn("entry.address.eventId === issue.location.event", BRIDGE)
        self.assertIn(CORE_COMMIT, BRIDGE)
        self.assertIn("fixture-e7h-r", BRIDGE)
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

    def test_osmd_host_accepts_only_core_musicxml_and_never_renderer_coordinates(self) -> None:
        self.assertIn("bridge.getSessionSnapshot()", HOST)
        self.assertIn("snapshot.musicXml", HOST)
        self.assertIn("xml.includes('<score-partwise')", HOST)
        self.assertIn("/^https?:/i.test(xml)", HOST)
        self.assertIn("renderer.load(musicXml)", HOST)
        self.assertIn("renderer.render()", HOST)
        self.assertIn("fallback.hidden = true", HOST)
        self.assertIn("fallback.hidden = false", HOST)
        self.assertIn("coordinatesAuthoritative: false", HOST)
        self.assertIn("domIdsAuthoritative: false", HOST)
        self.assertIn("rendererObjectsAuthoritative: false", HOST)
        self.assertNotIn("elementFromPoint", HOST)
        self.assertNotIn("querySelector('svg", HOST)
        self.assertNotIn("getBoundingClientRect", HOST)
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
        ):
            self.assertNotIn(forbidden, HOST, forbidden)

    def test_structured_edit_rerenders_only_after_local_core_commit(self) -> None:
        self.assertIn("const coreBridge = window.ScoreMosaicScoreEditorCoreBridge", EDIT_INTENT)
        self.assertIn("const osmdHost = window.ScoreMosaicScoreEditorOsmdHost", EDIT_INTENT)
        self.assertIn("coreBridge?.available === true", EDIT_INTENT)
        self.assertIn("coreBridge.commitOperation", EDIT_INTENT)
        self.assertIn("osmdHost.renderCurrentSession()", EDIT_INTENT)
        self.assertIn("application.prepareEditIntent", EDIT_INTENT)
        self.assertIn("dots < 0 || dots > 8", EDIT_INTENT)
        self.assertIn("coreAvailable && dots > 3", EDIT_INTENT)

    def test_builder_requires_local_verified_core_and_osmd_artifacts(self) -> None:
        for marker in (
            "--core-bundle",
            "--core-manifest",
            "--osmd-bundle",
            "--osmd-package-json",
            "--osmd-license",
            "ST_SCORE_EDITOR_CORE_BROWSER_BUNDLE",
            "opensheetmusicdisplay-2.1.1.min.js",
            "OSMD-LICENSE.txt",
            "renderer-profile.js",
            "artifactSha256",
            "connect-src 'none'",
        ):
            self.assertIn(marker, BUILDER)
        self.assertNotIn("curl ", BUILDER)
        self.assertNotIn("wget ", BUILDER)


if __name__ == "__main__":
    unittest.main()
