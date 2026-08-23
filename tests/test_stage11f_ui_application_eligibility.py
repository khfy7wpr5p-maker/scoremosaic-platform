from __future__ import annotations

import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / "contracts" / "stage11-ui-application-eligibility-v1.json").read_text(encoding="utf-8"))
BOUNDARY = json.loads((ROOT / "contracts" / "stage11-ui-application-boundary-v1.json").read_text(encoding="utf-8"))
STAGE10 = json.loads((ROOT / "contracts" / "stage10-ui-experience-eligibility-v1.json").read_text(encoding="utf-8"))
STAGE9 = json.loads((ROOT / "contracts" / "stage9-production-foundation-eligibility-v1.json").read_text(encoding="utf-8"))
DOC = (ROOT / "docs" / "stage11f-ui-application-eligibility.md").read_text(encoding="utf-8")
HTML = (ROOT / "prototypes" / "stage10-ui-application-experience" / "index.html").read_text(encoding="utf-8")
JS_FILES = list((ROOT / "prototypes" / "stage11-ui-application-contracts").glob("*.js")) + [
    ROOT / "prototypes" / "stage10-ui-application-experience" / "app.js",
    ROOT / "prototypes" / "stage10-ui-application-experience" / "edit-intent.js",
]
JS = "\n".join(path.read_text(encoding="utf-8") for path in JS_FILES)


class Stage11FUiApplicationEligibilityTests(unittest.TestCase):
    def test_identity_parent_and_repository_completion(self) -> None:
        self.assertEqual("scoremosaic-stage11-ui-application-eligibility-v1", CONTRACT["version"])
        self.assertEqual("11-F", CONTRACT["stage"])
        self.assertEqual("scoremosaic-stage11-ui-application-boundary-v1", CONTRACT["parentContract"])
        readiness = CONTRACT["readiness"]
        for key in (
            "stage11RepositoryScopeComplete",
            "typedBoundaryComplete",
            "typedReadContractsComplete",
            "typedEditIntentContractsComplete",
            "applicationStateModelComplete",
            "localUiApplicationIntegrationComplete",
            "readyForLaterLiveIntegrationSecurityDesign",
        ):
            self.assertIs(readiness[key], True)

    def test_live_and_production_readiness_remains_false(self) -> None:
        readiness = CONTRACT["readiness"]
        for key, value in readiness.items():
            if key in {
                "stage11RepositoryScopeComplete",
                "typedBoundaryComplete",
                "typedReadContractsComplete",
                "typedEditIntentContractsComplete",
                "applicationStateModelComplete",
                "localUiApplicationIntegrationComplete",
                "readyForLaterLiveIntegrationSecurityDesign",
            }:
                continue
            with self.subTest(readiness=key):
                self.assertIs(value, False)

    def test_every_stage11_activation_lock_is_false(self) -> None:
        for key, value in CONTRACT["activationLocks"].items():
            with self.subTest(lock=key):
                self.assertIs(value, False)

    def test_every_local_component_remains_non_authoritative(self) -> None:
        for key, value in CONTRACT["authority"].items():
            with self.subTest(authority=key):
                self.assertIs(value, False)

    def test_security_preservation_is_fail_closed(self) -> None:
        security = CONTRACT["securityPreservation"]
        for key in (
            "networkRequestsAllowed",
            "browserPersistenceAllowed",
            "externalAssetsAllowed",
            "dynamicHtmlInjectionAllowed",
            "dynamicCodeEvaluationAllowed",
            "productionArtifactAccessAllowed",
            "productionCredentialAccessAllowed",
            "serverAuthorizationManufactureAllowed",
            "oldValuePreconditionManufactureAllowed",
            "commandIdentityManufactureAllowed",
        ):
            self.assertIs(security[key], False)
        self.assertIs(security["stage9ExternalProvisioningStillDeferred"], True)

    def test_future_live_integration_requires_separate_security_gate(self) -> None:
        gate = CONTRACT["liveIntegrationBoundary"]
        for key in (
            "separateSecurityGateRequired",
            "mustDefineAuthenticatedPrincipal",
            "mustDefineTenantAndResourceAuthorization",
            "mustDefineOriginCsrfAndCspPolicy",
            "mustDefineExactApiTransport",
            "mustDefineFailureAndRetrySemantics",
            "mustDefineAuditEvidence",
            "mustDefineRollbackBoundary",
        ):
            self.assertIs(gate[key], True)
        for key in (
            "mayActivateLiveNetworkingByDefault",
            "mayActivateProductionCredentialsByDefault",
            "mayActivateServerWriteByDefault",
            "mayActivateProductionInfrastructureByDefault",
        ):
            self.assertIs(gate[key], False)

    def test_parent_stage10_and_stage9_runtime_locks_remain_false(self) -> None:
        self.assertTrue(STAGE10["activationLocks"])
        for key, value in STAGE10["activationLocks"].items():
            with self.subTest(stage10_lock=key):
                self.assertIs(value, False)
        for key, value in STAGE9["runtimeActivationLocks"].items():
            with self.subTest(stage9_lock=key):
                self.assertIs(value, False)

    def test_stage11_boundary_still_forbids_live_transport(self) -> None:
        self.assertFalse(BOUNDARY["transport"]["networkAllowed"])
        self.assertFalse(BOUNDARY["transport"]["productionApiAllowed"])
        self.assertTrue(BOUNDARY["transport"]["localAdapterAllowed"])
        self.assertFalse(BOUNDARY["transport"]["browserPersistenceAllowed"])

    def test_browser_csp_still_blocks_connections(self) -> None:
        self.assertIn("connect-src 'none'", HTML)
        self.assertIn("form-action 'none'", HTML)
        self.assertIn("object-src 'none'", HTML)
        self.assertIn("frame-src 'none'", HTML)

    def test_stage11_and_ui_javascript_contains_no_live_integration_apis(self) -> None:
        banned = {
            "fetch": r"\bfetch\s*\(",
            "xhr": r"XMLHttpRequest",
            "websocket": r"WebSocket",
            "eventsource": r"EventSource",
            "sendBeacon": r"sendBeacon",
            "localStorage": r"localStorage",
            "sessionStorage": r"sessionStorage",
            "indexedDB": r"indexedDB",
            "cookie": r"document\.cookie",
            "serviceWorker": r"serviceWorker",
            "clipboard": r"navigator\.clipboard",
            "navigation": r"\b(?:window|document)\.location\b",
            "innerHTML": r"innerHTML",
            "insertAdjacentHTML": r"insertAdjacentHTML",
            "eval": r"\beval\s*\(",
            "Function": r"new\s+Function",
        }
        for name, pattern in banned.items():
            with self.subTest(api=name):
                self.assertIsNone(re.search(pattern, JS))

    def test_document_closes_stage11_without_production_overclaim(self) -> None:
        for marker in (
            "Stage 11 repository-only typed UI↔application scope is complete",
            "Live API integration and every production side effect remain locked",
            "ready for later live-integration security design",
            "Stage 9 remains deferred",
        ):
            self.assertIn(marker.lower(), DOC.lower())


if __name__ == "__main__":
    unittest.main()
