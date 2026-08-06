from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENGINE_SCHEMA_PATH = ROOT / "contracts" / "st-omr-engine-contract-v1.schema.json"
MODEL_SCHEMA_PATH = ROOT / "contracts" / "st-omr-model-manifest-v1.schema.json"
DOC_PATH = ROOT / "docs" / "st-omr-architecture-contract-v1.md"

EXPECTED_PROFILES = (
    "single_staff",
    "piano_multistaff",
    "chamber_music",
    "orchestra_score",
    "orchestra_part",
    "guitar_tab",
    "choir_lyrics",
    "percussion",
)

DISABLED_ENGINE_BOUNDARIES = (
    "serviceImplementationEnabled",
    "gatewayIntegrationEnabled",
    "ensembleIntegrationEnabled",
    "publicEndpointEnabled",
    "uploadEnabled",
    "networkDispatchEnabled",
    "persistentStorageEnabled",
    "automaticMergeEnabled",
    "automaticCorrectionEnabled",
    "engineRankingEnabled",
    "winnerSelectionEnabled",
    "teacherApprovalEnabled",
    "publicationEnabled",
    "liveTrainingEnabled",
    "selfTrainingEnabled",
    "productionDeploymentEnabled",
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class STOmrArchitectureContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine_schema = load_json(ENGINE_SCHEMA_PATH)
        cls.model_schema = load_json(MODEL_SCHEMA_PATH)
        cls.document = DOC_PATH.read_text(encoding="utf-8")

    def test_contract_files_exist_and_parse(self) -> None:
        for path in (ENGINE_SCHEMA_PATH, MODEL_SCHEMA_PATH, DOC_PATH):
            self.assertTrue(path.is_file(), path)
            self.assertFalse(path.is_symlink(), path)

    def test_schemas_are_closed_and_versioned(self) -> None:
        for schema in (self.engine_schema, self.model_schema):
            self.assertEqual(
                schema["$schema"],
                "https://json-schema.org/draft/2020-12/schema",
            )
            self.assertIs(schema["additionalProperties"], False)

        self.assertEqual(
            self.engine_schema["properties"]["schemaVersion"]["const"],
            "1.0",
        )
        self.assertEqual(
            self.engine_schema["properties"]["contractType"]["const"],
            "scoremosaic.st-omr-engine-contract",
        )
        self.assertEqual(
            self.model_schema["properties"]["schemaVersion"]["const"],
            "1.0",
        )
        self.assertEqual(
            self.model_schema["properties"]["manifestType"]["const"],
            "scoremosaic.st-omr-model-manifest",
        )

    def test_engine_is_candidate_only_and_isolated(self) -> None:
        service = self.engine_schema["properties"]["service"]["properties"]
        self.assertEqual(service["serviceName"]["const"], "st-omr-service")
        self.assertEqual(service["role"]["const"], "candidate_omr_engine")
        self.assertIs(service["candidateOnly"]["const"], True)
        self.assertIs(service["finalTruthAuthority"]["const"], False)
        self.assertIs(service["embeddedInGateway"]["const"], False)
        self.assertIs(service["embeddedInEnsemble"]["const"], False)
        self.assertIs(service["deploymentIsolationRequired"]["const"], True)

    def test_input_boundary_is_prepared_and_private(self) -> None:
        input_policy = self.engine_schema["properties"]["input"]["properties"]
        self.assertIs(input_policy["preparedInputOnly"]["const"], True)
        self.assertIs(input_policy["acceptsRawExternalUpload"]["const"], False)
        self.assertIs(input_policy["acceptsArbitraryUrl"]["const"], False)
        self.assertIs(input_policy["acceptsCallerCredentials"]["const"], False)
        self.assertIs(input_policy["gatewayOwnsPdfDecoding"]["const"], True)
        self.assertEqual(
            [item["const"] for item in input_policy["acceptedPageMediaTypes"]["prefixItems"]],
            ["image/jpeg", "image/png"],
        )

    def test_output_artifacts_remain_separate(self) -> None:
        output = self.engine_schema["properties"]["output"]["properties"]
        self.assertEqual(
            [item["const"] for item in output["artifactKinds"]["prefixItems"]],
            [
                "raw_engine_output",
                "musicxml",
                "diagnostics",
                "confidence_evidence",
            ],
        )
        self.assertIs(output["writesCanonicalScoreDirectly"]["const"], False)
        self.assertEqual(output["normalizationOwner"]["const"], "ensemble-service")
        self.assertIs(output["rawArtifactsRemainSeparate"]["const"], True)
        self.assertIs(output["overwriteForbidden"]["const"], True)
        self.assertIs(output["crossEngineWriteForbidden"]["const"], True)

    def test_all_long_term_profiles_are_named(self) -> None:
        profiles = self.engine_schema["$defs"]["profile"]["properties"]["name"]["enum"]
        self.assertEqual(tuple(profiles), EXPECTED_PROFILES)
        self.assertEqual(len(set(profiles)), len(EXPECTED_PROFILES))

    def test_model_manifest_requires_provenance_and_release_gates(self) -> None:
        required = set(self.model_schema["required"])
        self.assertTrue(
            {
                "model",
                "runtimeCompatibility",
                "provenance",
                "evaluationEvidence",
                "promotionGates",
                "boundaries",
                "manifestSha256",
            }.issubset(required)
        )
        promotion = self.model_schema["properties"]["promotionGates"]["properties"]
        self.assertIs(promotion["automaticPromotion"]["const"], False)
        self.assertIn("manualApprovalRecorded", promotion)
        self.assertIn("regressionTestsPassed", promotion)

    def test_training_and_release_boundaries_are_closed(self) -> None:
        engine_boundaries = self.engine_schema["$defs"]["boundaries"]["properties"]
        self.assertIs(engine_boundaries["architectureOnly"]["const"], True)
        for key in DISABLED_ENGINE_BOUNDARIES:
            self.assertIs(engine_boundaries[key]["const"], False, key)

        model_boundaries = self.model_schema["properties"]["boundaries"]["properties"]
        self.assertIs(model_boundaries["deployableFromThisManifestAlone"]["const"], False)
        self.assertIs(model_boundaries["liveTraining"]["const"], False)
        self.assertIs(model_boundaries["selfTraining"]["const"], False)
        self.assertIs(model_boundaries["teacherCorrectionIngestion"]["const"], False)
        self.assertIs(model_boundaries["generalAccuracyClaim"]["const"], False)

    def test_runtime_boundary_is_guarded_and_gateway_integration_absent(
        self,
    ) -> None:
        validator = (
            ROOT
            / "services"
            / "st-omr-service"
            / "tools"
            / "validate_safety_boundary.py"
        )
        self.assertTrue(validator.is_file(), validator)
        self.assertFalse(validator.is_symlink(), validator)

        orchestration = (
            ROOT / "contracts" / "omr-orchestration-plan.schema.json"
        ).read_text(encoding="utf-8")
        self.assertNotIn('"st-omr"', orchestration)
        compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
        self.assertNotIn("st-omr-service:", compose)

    def test_document_preserves_the_next_gate(self) -> None:
        self.assertIn("This phase is architecture-only.", self.document)
        self.assertIn("live ScoreMosaic system does not train itself", self.document)
        self.assertIn("ST-OMR health-only service foundation", self.document)


if __name__ == "__main__":
    unittest.main()
