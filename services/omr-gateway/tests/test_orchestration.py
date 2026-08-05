from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_gateway.orchestration import (
    ENGINE_NAMES,
    ORCHESTRATION_CONTRACT_TYPE,
    ORCHESTRATION_SCHEMA_VERSION,
    OrchestrationContractError,
    build_orchestration_plan,
    verify_orchestration_plan,
)


SOURCE_SHA = "a" * 64


class OrchestrationContractTests(unittest.TestCase):
    def _plan(self):
        return build_orchestration_plan(
            "job_contract_12345678",
            source_artifact_ref="sources/job_contract_12345678/input.pdf",
            source_sha256=SOURCE_SHA,
            source_size_bytes=4096,
            source_media_type="application/pdf",
            requested_engines=("clarity", "audiveris", "homr"),
            timeout_seconds_by_engine={"clarity": 5400, "audiveris": 3600},
            cancellation_grace_seconds=45,
        )

    def test_plan_is_deterministic_and_canonical(self) -> None:
        first = self._plan()
        second = self._plan()
        payload = first.as_dict()

        self.assertEqual(first.to_json(indent=None), second.to_json(indent=None))
        self.assertEqual(payload["schemaVersion"], ORCHESTRATION_SCHEMA_VERSION)
        self.assertEqual(payload["contractType"], ORCHESTRATION_CONTRACT_TYPE)
        self.assertEqual(payload["requestedEngines"], list(ENGINE_NAMES))
        self.assertEqual(
            [run["engine"] for run in payload["engineRuns"]],
            list(ENGINE_NAMES),
        )
        self.assertEqual(payload["timeoutPolicy"]["totalDeadlineSeconds"], 5445)
        self.assertEqual(len(payload["planSha256"]), 64)
        self.assertTrue(payload["planId"].startswith("plan_"))
        verify_orchestration_plan(payload)

    def test_candidate_namespaces_and_artifacts_are_isolated(self) -> None:
        payload = self._plan().as_dict()
        source_id = payload["sourceArtifact"]["artifactId"]
        namespaces = []
        artifact_refs = []

        for run in payload["engineRuns"]:
            self.assertEqual(run["inputArtifactId"], source_id)
            self.assertEqual(run["endpointKey"], run["engine"])
            self.assertNotIn("http", run["endpointKey"])
            self.assertEqual(run["attemptLimit"], 1)
            self.assertEqual(run["initialState"], "planned")
            namespaces.append(run["candidateNamespace"])
            for artifact in run["expectedArtifacts"]:
                self.assertTrue(
                    artifact["artifactRef"].startswith(
                        run["candidateNamespace"] + "/"
                    )
                )
                self.assertTrue(artifact["immutable"])
                self.assertTrue(artifact["sha256Required"])
                artifact_refs.append(artifact["artifactRef"])

        self.assertEqual(len(namespaces), len(set(namespaces)))
        self.assertEqual(len(artifact_refs), len(set(artifact_refs)))

    def test_boundaries_keep_execution_and_decisions_disabled(self) -> None:
        payload = self._plan().as_dict()
        self.assertEqual(
            payload["boundaries"],
            {
                "executionEnabled": False,
                "uploadEnabled": False,
                "persistenceEnabled": False,
                "networkDispatchEnabled": False,
                "engineRanking": False,
                "winnerSelection": False,
                "automaticMerge": False,
                "automaticCorrection": False,
                "teacherApproval": False,
                "publication": False,
            },
        )
        self.assertEqual(
            payload["artifactPolicy"],
            {
                "sourceImmutable": True,
                "candidateIsolation": True,
                "hashRequired": True,
                "overwriteAllowed": False,
                "crossEngineWriteAllowed": False,
            },
        )

    def test_lifecycle_and_timeout_policy_are_explicit(self) -> None:
        payload = self._plan().as_dict()
        transitions = payload["lifecyclePolicy"]["allowedEngineRunTransitions"]
        self.assertEqual(transitions["planned"], ["queued", "cancelled"])
        self.assertEqual(
            transitions["running"],
            ["completed", "failed", "cancelled", "timed_out"],
        )
        self.assertEqual(transitions["completed"], [])
        self.assertTrue(payload["timeoutPolicy"]["timeoutIsTerminal"])
        self.assertFalse(payload["timeoutPolicy"]["retryAfterTimeout"])
        self.assertEqual(payload["timeoutPolicy"]["clock"], "monotonic")

    def test_verifier_rejects_tampering_and_extra_fields(self) -> None:
        payload = self._plan().as_dict()
        cases = []

        modified_timeout = deepcopy(payload)
        modified_timeout["engineRuns"][0]["timeoutSeconds"] += 1
        cases.append(modified_timeout)

        modified_namespace = deepcopy(payload)
        modified_namespace["engineRuns"][0]["candidateNamespace"] = (
            modified_namespace["engineRuns"][1]["candidateNamespace"]
        )
        cases.append(modified_namespace)

        modified_boundary = deepcopy(payload)
        modified_boundary["boundaries"]["executionEnabled"] = True
        cases.append(modified_boundary)

        modified_hash = deepcopy(payload)
        modified_hash["planSha256"] = "b" * 64
        cases.append(modified_hash)

        extra_field = deepcopy(payload)
        extra_field["preferredEngine"] = "audiveris"
        cases.append(extra_field)

        for candidate in cases:
            with self.subTest(candidate=candidate):
                with self.assertRaises(OrchestrationContractError):
                    verify_orchestration_plan(candidate)

    def test_builder_rejects_unsafe_or_unsupported_inputs(self) -> None:
        base = {
            "job_id": "job_contract_12345678",
            "source_artifact_ref": "sources/job_contract_12345678/input.pdf",
            "source_sha256": SOURCE_SHA,
            "source_size_bytes": 4096,
            "source_media_type": "application/pdf",
        }
        invalid = [
            {"source_artifact_ref": "../secret.pdf"},
            {"source_artifact_ref": "/absolute/input.pdf"},
            {"source_media_type": "application/zip"},
            {"source_sha256": "A" * 64},
            {"source_size_bytes": 0},
            {"requested_engines": ("audiveris", "audiveris")},
            {"requested_engines": ("unknown",)},
            {"timeout_seconds_by_engine": {"clarity": 29}},
            {"timeout_seconds_by_engine": {"unknown": 100}},
            {"cancellation_grace_seconds": 301},
        ]
        for patch in invalid:
            values = dict(base)
            values.update(patch)
            with self.subTest(patch=patch):
                with self.assertRaises(OrchestrationContractError):
                    build_orchestration_plan(**values)

    def test_serialized_payload_mutation_does_not_change_future_plans(self) -> None:
        payload = self._plan().as_dict()
        payload["boundaries"]["executionEnabled"] = True
        payload["artifactPolicy"]["overwriteAllowed"] = True
        payload["lifecyclePolicy"]["allowedEngineRunTransitions"]["planned"].append(
            "running"
        )

        fresh = self._plan().as_dict()
        self.assertFalse(fresh["boundaries"]["executionEnabled"])
        self.assertFalse(fresh["artifactPolicy"]["overwriteAllowed"])
        self.assertEqual(
            fresh["lifecyclePolicy"]["allowedEngineRunTransitions"]["planned"],
            ["queued", "cancelled"],
        )

    def test_plan_generation_does_not_mutate_callers(self) -> None:
        engines = ["clarity", "audiveris"]
        timeouts = {"clarity": 4000}
        before_engines = list(engines)
        before_timeouts = dict(timeouts)

        build_orchestration_plan(
            "job_contract_12345678",
            source_artifact_ref="sources/job_contract_12345678/input.pdf",
            source_sha256=SOURCE_SHA,
            source_size_bytes=4096,
            source_media_type="application/pdf",
            requested_engines=engines,
            timeout_seconds_by_engine=timeouts,
        )

        self.assertEqual(engines, before_engines)
        self.assertEqual(timeouts, before_timeouts)


class SchemaTests(unittest.TestCase):
    def test_schema_is_versioned_closed_and_neutral(self) -> None:
        schema_path = (
            SERVICE_ROOT.parents[1]
            / "contracts"
            / "omr-orchestration-plan.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        self.assertEqual(
            schema["$schema"],
            "https://json-schema.org/draft/2020-12/schema",
        )
        self.assertEqual(schema["properties"]["schemaVersion"]["const"], "1.0")
        self.assertEqual(
            schema["properties"]["contractType"]["const"],
            ORCHESTRATION_CONTRACT_TYPE,
        )
        self.assertFalse(schema["additionalProperties"])
        self.assertNotIn("preferredEngine", schema["properties"])
        self.assertNotIn("winner", schema["properties"])
        self.assertNotIn("mergedMusicXml", schema["properties"])


if __name__ == "__main__":
    unittest.main()
