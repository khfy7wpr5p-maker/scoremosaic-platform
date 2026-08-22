from __future__ import annotations

import json
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ELIGIBILITY = ROOT / "contracts" / "stage10-ui-experience-eligibility-v1.json"
PARENT = ROOT / "contracts" / "stage10-ui-application-experience-v1.json"
STAGE9 = ROOT / "contracts" / "stage9-production-foundation-eligibility-v1.json"
DOC = ROOT / "docs" / "stage10f-ui-experience-eligibility.md"
PROTOTYPE = ROOT / "prototypes" / "stage10-ui-application-experience"
HTML_PATH = PROTOTYPE / "index.html"
JS_PATHS = [PROTOTYPE / "fixture.js", PROTOTYPE / "app.js", PROTOTYPE / "edit-intent.js"]


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class ResourceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.urls: list[str] = []
        self.csp = ""

    def handle_starttag(self, tag: str, attrs) -> None:
        data = dict(attrs)
        if tag == "meta" and data.get("http-equiv") == "Content-Security-Policy":
            self.csp = data.get("content", "")
        for key in ("src", "href", "action"):
            value = data.get(key)
            if value:
                self.urls.append(value)


class Stage10FUiExperienceEligibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.eligibility = load(ELIGIBILITY)
        cls.parent = load(PARENT)
        cls.stage9 = load(STAGE9)
        cls.document = DOC.read_text(encoding="utf-8")
        cls.html = HTML_PATH.read_text(encoding="utf-8")
        cls.javascript = "\n".join(path.read_text(encoding="utf-8") for path in JS_PATHS)
        cls.parser = ResourceParser()
        cls.parser.feed(cls.html)

    def test_contract_identity_and_parent_binding(self) -> None:
        self.assertEqual(self.eligibility["version"], "scoremosaic-stage10-ui-experience-eligibility-v1")
        self.assertEqual(self.eligibility["stage"], "10-F")
        self.assertEqual(self.eligibility["parentContract"], self.parent["version"])
        self.assertEqual(self.eligibility["scope"], "repository-only-ui-application-experience")

    def test_repository_scope_is_complete_but_live_capabilities_are_not_eligible(self) -> None:
        readiness = self.eligibility["readiness"]
        for field in (
            "stage10RepositoryScopeComplete",
            "integratedProductShellComplete",
            "deterministicFixtureReviewComplete",
            "disconnectedEditIntentUxComplete",
            "accessibilityResponsiveBaselineComplete",
            "readyForStage11UiApplicationContractDesign",
        ):
            self.assertIs(readiness[field], True, field)
        for field in (
            "apiIntegrationEligible",
            "productionFrontendEligible",
            "realUploadEligible",
            "authRuntimeEligible",
            "sessionRuntimeEligible",
            "rbacRuntimeEligible",
            "teacherReviewServerWriteEligible",
            "scoreEditCommandCreationEligible",
            "teacherScoreRevisionCreationEligible",
            "approvalExecutionEligible",
            "publicationExecutionEligible",
            "playbackEligible",
            "productionInfrastructureEligible",
        ):
            self.assertIs(readiness[field], False, field)

    def test_browser_fixture_renderer_and_local_intent_never_gain_authority(self) -> None:
        for name, value in self.eligibility["authority"].items():
            self.assertIs(value, False, name)

    def test_security_preservation_is_fail_closed_and_stage9_stays_deferred(self) -> None:
        security = self.eligibility["securityPreservation"]
        for field in (
            "networkRequestsAllowed",
            "browserPersistenceAllowed",
            "externalAssetsAllowed",
            "dynamicHtmlInjectionAllowed",
            "dynamicCodeEvaluationAllowed",
            "productionArtifactAccessAllowed",
            "productionCredentialAccessAllowed",
        ):
            self.assertIs(security[field], False, field)
        self.assertIs(security["stage9ExternalProvisioningStillDeferred"], True)
        self.assertIs(self.stage9["readiness"]["productionRuntimeEligible"], False)
        self.assertIs(self.stage9["readiness"]["publicTrafficEligible"], False)
        self.assertIs(self.stage9["readiness"]["publicationExecutionEligible"], False)

    def test_parent_and_exit_activation_locks_remain_false(self) -> None:
        for contract in (self.parent, self.eligibility):
            for name, value in contract["activationLocks"].items():
                self.assertIs(value, False, f"{contract['version']}:{name}")

    def test_stage11_is_contract_design_only_by_default(self) -> None:
        boundary = self.eligibility["stage11Boundary"]
        self.assertIs(boundary["mayDesignTypedUiApplicationContracts"], True)
        self.assertIs(boundary["mayDesignLocalAdapters"], True)
        for field in (
            "mayActivateNetworkByDefault",
            "mayActivateProductionInfrastructureByDefault",
            "mayCreateProductionCredentialsByDefault",
            "mayActivateServerWriteByDefault",
        ):
            self.assertIs(boundary[field], False, field)
        self.assertIs(boundary["separateSecurityGateRequiredForAnyLiveIntegration"], True)

    def test_accessibility_evidence_is_present_without_certification_overclaim(self) -> None:
        accessibility = self.eligibility["accessibilityEvidence"]
        for field in (
            "keyboardNavigationPresent",
            "visibleFocusPresent",
            "programmaticLabelsPresent",
            "textualSeverityPresent",
            "liveStatusPresent",
            "touchTargetBaselinePresent",
            "reducedMotionPresent",
            "increasedContrastPresent",
            "forcedColorsPresent",
            "responsiveScoreViewPriorityPresent",
        ):
            self.assertIs(accessibility[field], True, field)
        self.assertIs(accessibility["runtimeCertificationClaimed"], False)

    def test_prototype_csp_and_resources_remain_disconnected(self) -> None:
        for directive in (
            "default-src 'none'",
            "connect-src 'none'",
            "object-src 'none'",
            "frame-src 'none'",
            "base-uri 'none'",
            "form-action 'none'",
        ):
            self.assertIn(directive, self.parser.csp)
        for url in self.parser.urls:
            self.assertFalse(re.match(r"^(?:https?:)?//", url), url)

    def test_all_stage10_javascript_remains_free_of_live_integration_apis(self) -> None:
        banned_patterns = {
            "fetch": r"\bfetch\s*\(",
            "xhr": r"XMLHttpRequest",
            "websocket": r"WebSocket",
            "eventsource": r"EventSource",
            "localStorage": r"localStorage",
            "sessionStorage": r"sessionStorage",
            "indexedDB": r"indexedDB",
            "cookie": r"document\.cookie",
            "serviceWorker": r"navigator\.serviceWorker",
            "clipboard": r"navigator\.clipboard",
            "dynamicHtml": r"innerHTML|insertAdjacentHTML",
            "eval": r"\beval\s*\(",
            "Function": r"new\s+Function",
            "windowLocation": r"\bwindow\.location\b",
            "documentLocation": r"\bdocument\.location\b",
        }
        for name, pattern in banned_patterns.items():
            self.assertIsNone(re.search(pattern, self.javascript), name)

    def test_document_marks_stage10_complete_without_production_overclaim(self) -> None:
        for marker in (
            "Stage 10 repository-only UI/Application Experience scope is complete",
            "productionFrontendEligible=false",
            "Stage 9 external provisioning remains deferred",
            "Stage 11 may now design typed UI↔application contracts",
            "Live integration / production activation ❌",
        ):
            self.assertIn(marker, self.document)


if __name__ == "__main__":
    unittest.main()
