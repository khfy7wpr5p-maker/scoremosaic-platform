from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
API = json.loads((ROOT / "contracts" / "teacher-review-api-v1.json").read_text(encoding="utf-8"))
REQUEST = json.loads((ROOT / "contracts" / "teacher-review-api-edit-intent-v1.schema.json").read_text(encoding="utf-8"))
RESPONSE = json.loads((ROOT / "contracts" / "teacher-review-api-revision-result-v1.schema.json").read_text(encoding="utf-8"))
INTERNAL_WRITE = json.loads((ROOT / "contracts" / "teacher-review-write-request-v1.schema.json").read_text(encoding="utf-8"))
COMMAND = json.loads((ROOT / "contracts" / "score-edit-command-v1.schema.json").read_text(encoding="utf-8"))
REVISION = json.loads((ROOT / "contracts" / "teacher-score-revision-v1.schema.json").read_text(encoding="utf-8"))
SECURITY = json.loads((ROOT / "contracts" / "live-ui-api-security-architecture-v1.json").read_text(encoding="utf-8"))
CURRENT = json.loads((ROOT / "contracts" / "architecture-current-state-v1.json").read_text(encoding="utf-8"))
DOC = (ROOT / "docs" / "teacher-review-api-contract-v1.md").read_text(encoding="utf-8")


class TeacherReviewApiContractV1Tests(unittest.TestCase):
    def test_contract_is_repository_only_unnumbered_and_not_stage12(self) -> None:
        self.assertEqual("scoremosaic-teacher-review-api-v1", API["version"])
        self.assertIs(API["stageNumberAssigned"], False)
        self.assertEqual("repository_only_api_contract_no_http_runtime_activation", API["scope"])
        self.assertIn("does not consume Stage 12", DOC)

    def test_stage8_internal_write_envelope_is_not_public_api_request(self) -> None:
        internal = API["stage8InternalContracts"]
        self.assertEqual("contracts/teacher-review-write-request-v1.schema.json", internal["internalWriteEnvelopeSchema"])
        self.assertEqual("Stage 8-G", internal["internalWriteBoundary"])
        self.assertIs(internal["internalWriteEnvelopeIsPublicApiRequest"], False)
        self.assertEqual("scoremosaic-teacher-review-write-request-v1", INTERNAL_WRITE["properties"]["schemaVersion"]["const"])
        self.assertIn("command", INTERNAL_WRITE["required"])

    def test_read_endpoints_preserve_security_baseline_and_add_revision_reads(self) -> None:
        endpoints = {entry["operation"]: entry for entry in API["readEndpoints"]}
        expected_security_reads = {
            entry["operation"]: (entry["method"], entry["pathTemplate"])
            for entry in SECURITY["apiTransport"]["initialReadEndpoints"]
        }
        for operation, expected in expected_security_reads.items():
            self.assertIn(operation, endpoints)
            self.assertEqual(expected, (endpoints[operation]["method"], endpoints[operation]["pathTemplate"]))
        self.assertEqual("GET", endpoints["revisions.list"]["method"])
        self.assertEqual("/api/v1/documents/{document_id}/revisions", endpoints["revisions.list"]["pathTemplate"])
        self.assertEqual("GET", endpoints["revision.read"]["method"])
        self.assertEqual("/api/v1/documents/{document_id}/revisions/{revision_id}", endpoints["revision.read"]["pathTemplate"])
        self.assertTrue(all(entry["mutation"] is False for entry in endpoints.values()))

    def test_only_one_revision_proposal_mutation_is_reserved_and_disabled(self) -> None:
        mutations = API["mutationEndpoints"]
        self.assertEqual(1, len(mutations))
        endpoint = mutations[0]
        self.assertEqual("revision.propose", endpoint["operation"])
        self.assertEqual("POST", endpoint["method"])
        self.assertEqual("/api/v1/documents/{document_id}/revision-proposals", endpoint["pathTemplate"])
        self.assertEqual("contracts/teacher-review-api-edit-intent-v1.schema.json", endpoint["requestSchema"])
        self.assertEqual("contracts/teacher-review-api-revision-result-v1.schema.json", endpoint["responseSchema"])
        self.assertIs(endpoint["idempotencyHeaderRequired"], True)
        self.assertIs(endpoint["csrfRequired"], True)
        self.assertIs(endpoint["exactOriginRequired"], True)
        self.assertIs(endpoint["runtimeActivated"], False)

    def test_public_api_operation_surface_is_least_privilege_subset_of_stage8(self) -> None:
        api_ops = API["initialBrowserOperationSurface"]
        stage8_ops = API["stage8ClosedServerOperationVocabulary"]
        self.assertEqual(["set_pitch", "set_effective_duration", "set_dots", "remove_event"], api_ops)
        self.assertTrue(set(api_ops).issubset(set(stage8_ops)))
        self.assertEqual(
            {
                "set_pitch",
                "set_effective_duration",
                "set_written_type",
                "set_dots",
                "set_staff_voice",
                "set_time_signature",
                "set_tab",
                "remove_event",
            },
            set(stage8_ops),
        )
        rules = API["operationRules"]
        self.assertIs(rules["apiMayExpandToAllStage8OperationsWithoutVersionedContractChange"], False)
        self.assertIs(rules["apiMayIntroduceOperationOutsideStage8Vocabulary"], False)
        for key in ("rawXmlAllowed", "jsonPatchAllowed", "arbitraryObjectPathAllowed", "rendererNativeMutationAllowed"):
            self.assertIs(rules[key], False, key)

    def test_public_request_schema_is_closed_and_omits_authority_fields(self) -> None:
        self.assertIs(REQUEST["additionalProperties"], False)
        self.assertEqual("scoremosaic-teacher-review-api-edit-intent-v1", REQUEST["properties"]["schemaVersion"]["const"])
        public_fields = set(REQUEST["properties"])
        self.assertEqual(set(API["browserRequestMayContain"]), public_fields)
        for forbidden in API["browserRequestMustNotContain"]:
            self.assertNotIn(forbidden, public_fields, forbidden)
        refs = REQUEST["$defs"]["operation"]["oneOf"]
        expected_refs = {
            "score-edit-command-v1.schema.json#/$defs/setPitch",
            "score-edit-command-v1.schema.json#/$defs/setEffectiveDuration",
            "score-edit-command-v1.schema.json#/$defs/setDots",
            "score-edit-command-v1.schema.json#/$defs/removeEvent",
        }
        self.assertEqual(expected_refs, {entry["$ref"] for entry in refs})

    def test_snapshot_schema_binds_base_or_exact_revision_shape(self) -> None:
        snapshot = REQUEST["$defs"]["snapshot"]
        self.assertEqual(["kind", "revisionId", "revisionSha256", "stateSha256"], snapshot["required"])
        self.assertEqual(["base", "revision"], snapshot["properties"]["kind"]["enum"])
        self.assertEqual(2, len(snapshot["allOf"]))
        rules = API["snapshotRules"]
        for key in (
            "baseRevisionKindAllowed",
            "baseKindRequiresNullRevisionId",
            "baseKindRequiresNullRevisionSha256",
            "revisionKindRequiresRevisionIdAndSha256",
            "stateSha256Required",
            "projectionSha256Required",
            "freshDurableHeadMustMatchRequestSnapshot",
        ):
            self.assertIs(rules[key], True, key)
        self.assertEqual("stale", rules["mismatchResult"])

    def test_server_resolution_order_preserves_authority_before_internal_write(self) -> None:
        order = API["serverResolutionOrder"]
        pos = {name: order.index(name) for name in order}
        self.assertLess(pos["authenticate_session"], pos["parse_and_validate_bounded_api_intent"])
        self.assertLess(pos["authorize_operation_and_document_scope"], pos["parse_and_validate_bounded_api_intent"])
        self.assertLess(pos["resolve_exact_current_document_revision_head"], pos["generate_server_command_identity"])
        self.assertLess(pos["resolve_current_staff_voice_onset_and_old_value_sha256"], pos["construct_and_validate_score_edit_command"])
        self.assertLess(pos["construct_and_validate_score_edit_command"], pos["construct_internal_teacher_review_write_request"])
        self.assertLess(pos["construct_internal_teacher_review_write_request"], pos["invoke_stage8g_authorized_write_boundary"])
        self.assertLess(pos["invoke_stage8g_authorized_write_boundary"], pos["map_safe_result_to_public_api_response"])

    def test_idempotency_never_authorizes_historical_replay(self) -> None:
        idem = API["idempotency"]
        self.assertEqual("Idempotency-Key", idem["header"])
        self.assertIs(idem["requiredForRevisionProposal"], True)
        self.assertIs(idem["clientKeyIsDomainIdentity"], False)
        self.assertIn("exact_parent_revision", idem["serverScopeMustInclude"])
        self.assertIn("request_digest", idem["serverScopeMustInclude"])
        self.assertIs(idem["exactReplayMayReturnExistingRevision"], True)
        self.assertIs(idem["sameKeyDifferentDigestRejected"], True)
        self.assertIs(idem["staleHistoricalParentReplayAllowed"], False)
        self.assertIs(idem["automaticBrowserMutationRetryAllowed"], False)
        self.assertIs(idem["ambiguousOutcomeRequiresReconciliation"], True)

    def test_public_revision_result_is_closed_and_cannot_grant_approval_or_publication(self) -> None:
        self.assertIs(RESPONSE["additionalProperties"], False)
        revision = RESPONSE["$defs"]["revision"]["properties"]
        self.assertEqual("draft", revision["status"]["const"])
        self.assertIs(revision["immutable"]["const"], True)
        self.assertIs(revision["approvalEligible"]["const"], False)
        self.assertIs(revision["publicationEligible"]["const"], False)
        authority = RESPONSE["$defs"]["authority"]["properties"]
        for field in authority.values():
            self.assertIs(field["const"], False)
        public = API["publicResponse"]
        for key in (
            "mayExposeInternalAuthorizationGrant",
            "mayExposeAuthorizationSignature",
            "mayExposeRawProviderError",
            "mayExposeInternalStack",
            "mayExposeRawMusicXml",
            "mayExposeServerFilesystemPath",
        ):
            self.assertIs(public[key], False, key)

    def test_http_semantics_preserve_cross_tenant_non_disclosure(self) -> None:
        semantics = API["httpSemantics"]
        self.assertEqual(401, semantics["unauthenticated"])
        self.assertEqual(403, semantics["unauthorized"])
        self.assertEqual(404, semantics["notVisibleOrUnknownResource"])
        self.assertEqual(409, semantics["staleOrIdempotencyConflict"])
        self.assertEqual(422, semantics["semanticallyRejectedEdit"])
        self.assertIs(semantics["errorBodiesMustUseStablePublicCodes"], True)
        self.assertIs(semantics["crossTenantExistenceDisclosureForbidden"], True)

    def test_approval_and_publication_are_explicitly_outside_this_api(self) -> None:
        boundary = API["approvalPublicationBoundary"]
        for key in (
            "approvalReadOrWriteEndpointsDefinedHere",
            "publicationReadOrWriteEndpointsDefinedHere",
            "revisionProposalMayApprove",
            "revisionProposalMayPublish",
            "revisionProposalMayPersistCorrectedMusicXmlToProduction",
        ):
            self.assertIs(boundary[key], False, key)
        self.assertIs(boundary["futureApprovalApiRequiresSeparateContract"], True)
        self.assertIs(boundary["futurePublicationApiRequiresSeparateContract"], True)
        self.assertEqual(False, REVISION["properties"]["approvalEligible"]["const"])
        self.assertEqual(False, REVISION["properties"]["publicationEligible"]["const"])

    def test_negative_coverage_includes_authority_stale_replay_and_side_effect_smuggling(self) -> None:
        required = {
            "browser_supplied_reviewer_id",
            "browser_supplied_authorization_decision",
            "browser_supplied_command_id",
            "browser_supplied_old_value_sha256",
            "unsupported_operation",
            "raw_xml_payload",
            "stale_projection_sha256",
            "stale_revision_id",
            "state_sha256_mismatch",
            "cross_tenant_document",
            "missing_idempotency_key",
            "same_idempotency_key_different_digest",
            "historical_parent_replay",
            "missing_csrf",
            "wrong_origin",
            "revision_proposal_attempt_to_approve",
            "revision_proposal_attempt_to_publish",
        }
        self.assertTrue(required.issubset(set(API["negativeCoverage"])))

    def test_activation_locks_are_all_false_and_current_state_registers_contract(self) -> None:
        for key, value in API["activationLocks"].items():
            self.assertIs(value, False, key)
        state = CURRENT["approvedWorkstreams"]["teacherReviewApiContract"]
        self.assertIs(state["stageNumberAssigned"], False)
        self.assertEqual("APPROVED_REPOSITORY_TEACHER_REVIEW_API_CONTRACT_BASELINE", state["status"])
        self.assertIs(state["repositoryApiContractReady"], True)
        for key in ("httpRoutesRegistered", "liveReadApiActivated", "liveWriteApiActivated", "productionPersistenceActivated"):
            self.assertIs(state[key], False, key)
        self.assertIs(CURRENT["teacherReview"]["repositoryApiContractReady"], True)
        self.assertIs(CURRENT["teacherReview"]["liveTeacherReviewApiActivated"], False)
        self.assertIs(CURRENT["browser"]["networkAllowed"], False)
        self.assertEqual("11-F", CURRENT["asOfStage"])


if __name__ == "__main__":
    unittest.main()
