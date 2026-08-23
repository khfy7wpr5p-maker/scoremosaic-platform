from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / "contracts" / "live-ui-api-security-architecture-v1.json").read_text(encoding="utf-8"))
CURRENT = json.loads((ROOT / "contracts" / "architecture-current-state-v1.json").read_text(encoding="utf-8"))
STAGE11 = json.loads((ROOT / "contracts" / "stage11-ui-application-eligibility-v1.json").read_text(encoding="utf-8"))
DOC = (ROOT / "docs" / "live-ui-api-security-architecture-v1.md").read_text(encoding="utf-8")


class LiveUiApiSecurityArchitectureV1Tests(unittest.TestCase):
    def test_identity_and_scope_are_repository_only_and_unnumbered(self) -> None:
        self.assertEqual("scoremosaic-live-ui-api-security-architecture-v1", CONTRACT["version"])
        self.assertIs(CONTRACT["stageNumberAssigned"], False)
        self.assertEqual("repository_only_security_architecture_no_runtime_activation", CONTRACT["scope"])
        self.assertIn("does not consume Stage 12", DOC)

    def test_browser_and_client_claims_never_become_authority(self) -> None:
        principles = CONTRACT["principles"]
        self.assertIs(principles["browserIsNotAuthority"], True)
        self.assertIs(principles["serverAuthorizesEveryProtectedRequest"], True)
        self.assertIs(principles["clientClaimsAreNotAuthorization"], True)
        authz = CONTRACT["authorization"]
        self.assertIs(authz["principalResolvedServerSide"], True)
        self.assertIs(authz["tenantMembershipResolvedServerSide"], True)
        self.assertIs(authz["resourceAuthorizationResolvedServerSide"], True)
        self.assertIs(authz["idpRoleClaimAloneSufficientForResourceAccess"], False)
        self.assertIs(authz["hiddenOrDisabledUiActionCountsAsAuthorization"], False)

    def test_provider_tokens_remain_out_of_browser_application_storage(self) -> None:
        identity = CONTRACT["identityAndSession"]
        self.assertEqual("Authentik", identity["targetIdentityProvider"])
        self.assertEqual("authorization_code_with_pkce", identity["flow"])
        self.assertIs(identity["browserReceivesProviderAccessToken"], False)
        self.assertIs(identity["browserReceivesProviderRefreshToken"], False)
        self.assertIs(identity["browserStoresSessionInLocalStorage"], False)
        self.assertIs(identity["browserStoresSessionInSessionStorage"], False)
        cookie = identity["sessionCookie"]
        self.assertEqual("__Host-scoremosaic_session", cookie["name"])
        for key in ("httpOnly", "secure", "boundedIdleExpiryRequired", "boundedAbsoluteExpiryRequired", "rotationAfterAuthenticationRequired", "serverSideInvalidationOnLogoutRequired"):
            self.assertIs(cookie[key], True, key)
        self.assertEqual("Lax", cookie["sameSite"])
        self.assertEqual("/", cookie["path"])
        self.assertIs(cookie["domainAttributeAllowed"], False)

    def test_stage11_read_vocabulary_maps_to_exact_versioned_get_endpoints(self) -> None:
        transport = CONTRACT["apiTransport"]
        self.assertEqual("/api/v1", transport["basePath"])
        endpoints = {entry["operation"]: entry for entry in transport["initialReadEndpoints"]}
        self.assertEqual({"review.read", "issues.read", "sourceEvidence.read", "validation.read"}, set(endpoints))
        expected = {
            "review.read": "/api/v1/documents/{document_id}/revisions/{revision_id}/review",
            "issues.read": "/api/v1/documents/{document_id}/revisions/{revision_id}/issues",
            "sourceEvidence.read": "/api/v1/documents/{document_id}/revisions/{revision_id}/source-evidence",
            "validation.read": "/api/v1/documents/{document_id}/revisions/{revision_id}/validation",
        }
        for operation, path in expected.items():
            self.assertEqual("GET", endpoints[operation]["method"])
            self.assertEqual(path, endpoints[operation]["pathTemplate"])
        self.assertIs(transport["localEditIntentPrepareIsServerEndpoint"], False)
        self.assertIs(transport["mutationEndpointCatalogRequiresTeacherReviewApiContract"], True)

    def test_csrf_origin_cors_and_csp_fail_closed(self) -> None:
        boundary = CONTRACT["csrfOriginCors"]
        self.assertEqual(["POST", "PUT", "PATCH", "DELETE"], boundary["stateChangingMethods"])
        self.assertIs(boundary["sessionBoundCsrfTokenRequiredForStateChange"], True)
        self.assertIs(boundary["exactAllowedOriginCheckRequiredForStateChange"], True)
        self.assertIs(boundary["missingOrInvalidCsrfFailsClosed"], True)
        self.assertIs(boundary["wildcardCorsWithCredentialsAllowed"], False)
        self.assertIs(boundary["credentialedCrossOriginApiAllowedByDefault"], False)
        csp = CONTRACT["contentSecurityPolicy"]
        self.assertEqual("'none'", csp["currentDisconnectedConnectSrc"])
        self.assertEqual("'self'", csp["futureLiveApiConnectSrcMaximumBaseline"])
        self.assertIs(csp["futureConnectSrcMayActivateBeforeRuntimeGate"], False)
        self.assertIs(csp["unsafeEvalAllowed"], False)

    def test_score_mutation_requires_exact_server_side_guards(self) -> None:
        mutation = CONTRACT["mutationSafety"]
        for key in (
            "scoreMutationRequiresAuthenticatedPrincipal",
            "scoreMutationRequiresAuthorizedResource",
            "scoreMutationRequiresExactCurrentParentRevision",
            "scoreMutationRequiresStableTargetIdentity",
            "scoreMutationRequiresOldValuePrecondition",
            "scoreMutationRequiresClosedOperationVocabulary",
            "serverMustCreateOrValidateCommandIdentity",
        ):
            self.assertIs(mutation[key], True, key)
        self.assertIs(mutation["browserLocalIntentIsScoreEditCommand"], False)
        self.assertIs(mutation["validationPassMayAutoApprove"], False)
        self.assertIs(mutation["approvalMayAutoPublish"], False)

    def test_idempotency_does_not_become_domain_identity_or_silent_retry(self) -> None:
        idem = CONTRACT["idempotencyAndRetry"]
        self.assertIs(idem["mutationIdempotencyRequired"], True)
        self.assertIs(idem["idempotencyKeyIsOpaqueRetryTokenNotDomainIdentity"], True)
        self.assertIn("exact_parent_revision", idem["idempotencyScopeIncludes"])
        self.assertIn("request_digest", idem["idempotencyScopeIncludes"])
        self.assertIs(idem["sameKeySameDigestReturnsSameCommittedOutcome"], True)
        self.assertIs(idem["sameKeyDifferentDigestRejected"], True)
        self.assertIs(idem["browserAutomaticMutationRetryAllowed"], False)
        self.assertIs(idem["ambiguousMutationOutcomeRequiresReconciliation"], True)

    def test_errors_audit_and_rate_limits_do_not_leak_or_grant_authority(self) -> None:
        error = CONTRACT["errorModel"]
        for key in ("rawExceptionTextExposed", "credentialsOrTokensExposed", "sourceDocumentContentExposed", "fullMusicXmlExposed", "unrestrictedLocalPathExposed"):
            self.assertIs(error[key], False, key)
        audit = CONTRACT["audit"]
        self.assertIs(audit["appendOnlyEvidenceRequired"], True)
        self.assertIs(audit["rawSessionTokenLogged"], False)
        self.assertIs(audit["rawCsrfTokenLogged"], False)
        self.assertIs(audit["rawIdempotencyKeyLogged"], False)
        rate = CONTRACT["rateLimitAndAbuse"]
        self.assertIs(rate["serverSideRateLimitsRequired"], True)
        self.assertIs(rate["rateLimitMayGrantAuthorization"], False)
        self.assertIs(rate["mutationRateLimitFailureMayTriggerAutomaticReplay"], False)

    def test_required_negative_security_catalogue_covers_material_boundaries(self) -> None:
        required = {
            "missing_session",
            "forged_session",
            "cross_tenant_document_access",
            "browser_supplied_role_escalation",
            "missing_csrf",
            "wrong_origin",
            "stale_revision_mutation",
            "old_value_precondition_mismatch",
            "duplicate_idempotency_key_different_payload",
            "ambiguous_write_retry_attempt",
            "direct_browser_omr_engine_call",
            "direct_browser_downstream_engine_call",
        }
        self.assertTrue(required.issubset(set(CONTRACT["negativeSecurityCoverage"])))

    def test_runtime_prerequisites_are_explicit_but_not_claimed_complete(self) -> None:
        prereq = CONTRACT["runtimePrerequisites"]
        for key, value in prereq.items():
            self.assertIs(value, True, key)
        for key, value in CONTRACT["activationLocks"].items():
            self.assertIs(value, False, key)

    def test_current_state_registers_security_baseline_without_live_activation(self) -> None:
        state = CURRENT["approvedWorkstreams"]["liveUiApiSecurityDesign"]
        self.assertIs(state["stageNumberAssigned"], False)
        self.assertEqual("APPROVED_REPOSITORY_LIVE_UI_API_SECURITY_ARCHITECTURE_BASELINE", state["status"])
        self.assertEqual("contracts/live-ui-api-security-architecture-v1.json", state["contract"])
        self.assertIs(state["repositorySecurityArchitectureReady"], True)
        for key in ("runtimeActivated", "liveNetworkActivated", "authRuntimeActivated", "serverWriteActivated"):
            self.assertIs(state[key], False, key)
        self.assertEqual("11-F", CURRENT["asOfStage"])

    def test_stage11_live_eligibility_and_browser_network_remain_locked(self) -> None:
        readiness = STAGE11["readiness"]
        for key in (
            "liveApiIntegrationEligible",
            "productionFrontendEligible",
            "authRuntimeEligible",
            "sessionRuntimeEligible",
            "rbacRuntimeEligible",
            "teacherReviewServerWriteEligible",
            "scoreEditCommandCreationEligible",
            "teacherScoreRevisionCreationEligible",
        ):
            self.assertIs(readiness[key], False, key)
        self.assertIs(CURRENT["browser"]["networkAllowed"], False)
        self.assertIs(CURRENT["browser"]["serverWriteAllowed"], False)


if __name__ == "__main__":
    unittest.main()
