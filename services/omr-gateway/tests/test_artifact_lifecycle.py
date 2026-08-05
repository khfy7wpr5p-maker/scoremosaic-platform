from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_gateway.orchestration import build_orchestration_plan
from scoremosaic_gateway.artifact_lifecycle import (
    ARTIFACT_STATES,
    CANDIDATE_STATES,
    LIFECYCLE_CONTRACT_TYPE,
    LIFECYCLE_SCHEMA_VERSION,
    OUTPUT_ARTIFACT_KINDS,
    ArtifactLifecycleError,
    build_artifact_lifecycle,
    transition_artifact,
    transition_candidate,
    verify_artifact_lifecycle,
)


SOURCE_SHA = "a" * 64
OUTPUT_MEDIA_TYPES = {
    "raw_engine_result": "application/octet-stream",
    "musicxml": "application/vnd.recordare.musicxml+xml",
    "diagnostic": "application/json",
}


class CandidateArtifactLifecycleTests(unittest.TestCase):
    def _plan(self):
        return build_orchestration_plan(
            "job_lifecycle_12345678",
            source_artifact_ref="sources/job_lifecycle_12345678/input.pdf",
            source_sha256=SOURCE_SHA,
            source_size_bytes=4096,
            source_media_type="application/pdf",
            requested_engines=("clarity", "audiveris", "homr"),
        ).as_dict()

    def _sealed_first_candidate(self):
        plan = self._plan()
        lifecycle = build_artifact_lifecycle(plan)
        candidate = lifecycle.candidates[0]
        lifecycle = transition_candidate(
            lifecycle,
            candidate.candidate_id,
            "collecting",
        )
        for index, artifact in enumerate(candidate.artifacts, start=1):
            lifecycle = transition_artifact(
                lifecycle,
                artifact.artifact_id,
                "writing",
            )
            lifecycle = transition_artifact(
                lifecycle,
                artifact.artifact_id,
                "sealed",
                sha256=f"{index}" * 64,
                size_bytes=1000 + index,
                media_type=OUTPUT_MEDIA_TYPES[artifact.kind],
            )
        lifecycle = transition_candidate(
            lifecycle,
            candidate.candidate_id,
            "sealed",
        )
        return plan, lifecycle

    def test_initial_lifecycle_is_deterministic_and_plan_pinned(self) -> None:
        plan = self._plan()
        first = build_artifact_lifecycle(plan)
        second = build_artifact_lifecycle(plan)
        payload = first.as_dict()

        self.assertEqual(first.to_json(indent=None), second.to_json(indent=None))
        self.assertEqual(payload["schemaVersion"], LIFECYCLE_SCHEMA_VERSION)
        self.assertEqual(payload["contractType"], LIFECYCLE_CONTRACT_TYPE)
        self.assertEqual(payload["planRef"]["planId"], plan["planId"])
        self.assertEqual(payload["planRef"]["planSha256"], plan["planSha256"])
        self.assertEqual(payload["sequence"], 0)
        self.assertEqual(payload["events"], [])
        self.assertEqual(payload["sourceArtifact"]["state"], "sealed")
        self.assertTrue(payload["sourceArtifact"]["immutable"])
        verify_artifact_lifecycle(payload, plan)

    def test_candidates_preserve_engine_isolation_and_raw_results(self) -> None:
        payload = build_artifact_lifecycle(self._plan()).as_dict()
        namespaces = []
        artifact_ids = {payload["sourceArtifact"]["artifactId"]}
        artifact_refs = {payload["sourceArtifact"]["artifactRef"]}

        for candidate in payload["candidates"]:
            namespaces.append(candidate["candidateNamespace"])
            self.assertEqual(candidate["state"], "reserved")
            self.assertFalse(candidate["terminal"])
            self.assertEqual(
                tuple(item["kind"] for item in candidate["artifacts"]),
                OUTPUT_ARTIFACT_KINDS,
            )
            raw = candidate["artifacts"][0]
            self.assertEqual(raw["kind"], "raw_engine_result")
            self.assertTrue(raw["artifactRef"].endswith("/raw-engine-result"))
            for artifact in candidate["artifacts"]:
                self.assertEqual(artifact["candidateId"], candidate["candidateId"])
                self.assertEqual(artifact["engine"], candidate["engine"])
                self.assertTrue(
                    artifact["artifactRef"].startswith(
                        candidate["candidateNamespace"] + "/"
                    )
                )
                self.assertNotIn(artifact["artifactId"], artifact_ids)
                self.assertNotIn(artifact["artifactRef"], artifact_refs)
                artifact_ids.add(artifact["artifactId"])
                artifact_refs.add(artifact["artifactRef"])

        self.assertEqual(len(namespaces), len(set(namespaces)))

    def test_append_only_seal_flow_is_verified(self) -> None:
        plan, lifecycle = self._sealed_first_candidate()
        payload = lifecycle.as_dict()
        candidate = payload["candidates"][0]

        self.assertEqual(candidate["state"], "sealed")
        self.assertTrue(candidate["terminal"])
        self.assertTrue(all(a["state"] == "sealed" for a in candidate["artifacts"]))
        self.assertEqual(payload["sequence"], 8)
        self.assertEqual(len(payload["events"]), 8)
        self.assertEqual(
            payload["events"][0]["previousEventSha256"],
            "0" * 64,
        )
        for previous, current in zip(payload["events"], payload["events"][1:]):
            self.assertEqual(
                current["previousEventSha256"],
                previous["eventSha256"],
            )
        verify_artifact_lifecycle(payload, plan)

    def test_sealed_artifact_cannot_reopen_or_overwrite(self) -> None:
        _, lifecycle = self._sealed_first_candidate()
        artifact = lifecycle.candidates[0].artifacts[0]

        for next_state in ARTIFACT_STATES:
            with self.subTest(next_state=next_state):
                with self.assertRaises(ArtifactLifecycleError):
                    transition_artifact(
                        lifecycle,
                        artifact.artifact_id,
                        next_state,
                        reason_code=(
                            "overwrite_forbidden"
                            if next_state in {"rejected", "abandoned"}
                            else None
                        ),
                    )

    def test_source_artifact_transition_is_forbidden(self) -> None:
        lifecycle = build_artifact_lifecycle(self._plan())
        with self.assertRaises(ArtifactLifecycleError):
            transition_artifact(
                lifecycle,
                lifecycle.source_artifact.artifact_id,
                "writing",
            )

    def test_artifact_writing_requires_collecting_candidate(self) -> None:
        lifecycle = build_artifact_lifecycle(self._plan())
        artifact = lifecycle.candidates[0].artifacts[0]
        with self.assertRaises(ArtifactLifecycleError):
            transition_artifact(
                lifecycle,
                artifact.artifact_id,
                "writing",
            )

    def test_candidate_seal_requires_every_artifact_sealed(self) -> None:
        lifecycle = build_artifact_lifecycle(self._plan())
        candidate = lifecycle.candidates[0]
        lifecycle = transition_candidate(
            lifecycle,
            candidate.candidate_id,
            "collecting",
        )
        with self.assertRaises(ArtifactLifecycleError):
            transition_candidate(
                lifecycle,
                candidate.candidate_id,
                "sealed",
            )

    def test_terminal_failure_requires_explicit_artifact_closure(self) -> None:
        plan = self._plan()
        lifecycle = build_artifact_lifecycle(plan)
        candidate = lifecycle.candidates[0]

        with self.assertRaises(ArtifactLifecycleError):
            transition_candidate(
                lifecycle,
                candidate.candidate_id,
                "failed",
                reason_code="engine_failed",
            )

        for artifact in candidate.artifacts:
            lifecycle = transition_artifact(
                lifecycle,
                artifact.artifact_id,
                "abandoned",
                reason_code="engine_failed",
            )
        lifecycle = transition_candidate(
            lifecycle,
            candidate.candidate_id,
            "failed",
            reason_code="engine_failed",
        )
        payload = lifecycle.as_dict()
        self.assertEqual(payload["candidates"][0]["state"], "failed")
        self.assertTrue(payload["candidates"][0]["terminal"])
        verify_artifact_lifecycle(payload, plan)

    def test_invalid_content_metadata_and_reason_codes_are_rejected(self) -> None:
        lifecycle = build_artifact_lifecycle(self._plan())
        candidate = lifecycle.candidates[0]
        lifecycle = transition_candidate(
            lifecycle,
            candidate.candidate_id,
            "collecting",
        )
        artifact = candidate.artifacts[0]
        lifecycle = transition_artifact(
            lifecycle,
            artifact.artifact_id,
            "writing",
        )

        invalid_seals = [
            {"sha256": "A" * 64, "size_bytes": 10, "media_type": "application/octet-stream"},
            {"sha256": "b" * 64, "size_bytes": 0, "media_type": "application/octet-stream"},
            {"sha256": "b" * 64, "size_bytes": 10, "media_type": "application/json"},
            {"sha256": "b" * 64, "size_bytes": 10, "media_type": "application/octet-stream", "reason_code": "not_allowed"},
        ]
        for values in invalid_seals:
            with self.subTest(values=values):
                with self.assertRaises(ArtifactLifecycleError):
                    transition_artifact(
                        lifecycle,
                        artifact.artifact_id,
                        "sealed",
                        **values,
                    )

        with self.assertRaises(ArtifactLifecycleError):
            transition_artifact(
                lifecycle,
                candidate.artifacts[1].artifact_id,
                "abandoned",
                reason_code="Bad reason",
            )

    def test_verifier_rejects_tampering_and_extra_fields(self) -> None:
        plan, lifecycle = self._sealed_first_candidate()
        payload = lifecycle.as_dict()
        cases = []

        modified_event_hash = deepcopy(payload)
        modified_event_hash["events"][0]["eventSha256"] = "b" * 64
        cases.append(modified_event_hash)

        modified_content = deepcopy(payload)
        modified_content["candidates"][0]["artifacts"][0]["sha256"] = "c" * 64
        cases.append(modified_content)

        modified_boundary = deepcopy(payload)
        modified_boundary["boundaries"]["storageWritesEnabled"] = True
        cases.append(modified_boundary)

        modified_snapshot_hash = deepcopy(payload)
        modified_snapshot_hash["lifecycleSha256"] = "d" * 64
        cases.append(modified_snapshot_hash)

        extra_field = deepcopy(payload)
        extra_field["preferredEngine"] = "audiveris"
        cases.append(extra_field)

        for candidate in cases:
            with self.subTest(candidate=candidate):
                with self.assertRaises(ArtifactLifecycleError):
                    verify_artifact_lifecycle(candidate, plan)

    def test_modified_orchestration_plan_is_rejected(self) -> None:
        plan = self._plan()
        plan["boundaries"]["executionEnabled"] = True
        with self.assertRaises(ArtifactLifecycleError):
            build_artifact_lifecycle(plan)

    def test_serialized_mutation_does_not_change_future_ledgers(self) -> None:
        plan = self._plan()
        payload = build_artifact_lifecycle(plan).as_dict()
        payload["boundaries"]["storageWritesEnabled"] = True
        payload["policies"]["overwriteAllowed"] = True
        payload["candidates"][0]["artifacts"][0]["state"] = "sealed"

        fresh = build_artifact_lifecycle(plan).as_dict()
        self.assertFalse(fresh["boundaries"]["storageWritesEnabled"])
        self.assertFalse(fresh["policies"]["overwriteAllowed"])
        self.assertEqual(
            fresh["candidates"][0]["artifacts"][0]["state"],
            "reserved",
        )

    def test_state_sets_are_closed_and_terminal_states_do_not_reopen(self) -> None:
        self.assertEqual(
            CANDIDATE_STATES,
            ("reserved", "collecting", "sealed", "failed", "cancelled", "timed_out"),
        )
        self.assertEqual(
            ARTIFACT_STATES,
            ("reserved", "writing", "sealed", "rejected", "abandoned"),
        )
        _, lifecycle = self._sealed_first_candidate()
        candidate = lifecycle.candidates[0]
        for state in CANDIDATE_STATES:
            with self.subTest(state=state):
                with self.assertRaises(ArtifactLifecycleError):
                    transition_candidate(
                        lifecycle,
                        candidate.candidate_id,
                        state,
                        reason_code=(
                            "terminal_reopen"
                            if state in {"failed", "cancelled", "timed_out"}
                            else None
                        ),
                    )


class ArtifactLifecycleSchemaTests(unittest.TestCase):
    def test_schema_is_versioned_closed_and_neutral(self) -> None:
        schema_path = (
            SERVICE_ROOT.parents[1]
            / "contracts"
            / "candidate-artifact-lifecycle.schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        self.assertEqual(
            schema["$schema"],
            "https://json-schema.org/draft/2020-12/schema",
        )
        self.assertEqual(schema["properties"]["schemaVersion"]["const"], "1.0")
        self.assertEqual(
            schema["properties"]["contractType"]["const"],
            LIFECYCLE_CONTRACT_TYPE,
        )
        self.assertFalse(schema["additionalProperties"])
        self.assertNotIn("preferredEngine", schema["properties"])
        self.assertNotIn("winner", schema["properties"])
        self.assertNotIn("mergedMusicXml", schema["properties"])
        self.assertEqual(
            schema["$defs"]["candidate"]["properties"]["state"]["enum"],
            list(CANDIDATE_STATES),
        )
        self.assertEqual(
            schema["$defs"]["outputArtifact"]["properties"]["state"]["enum"],
            list(ARTIFACT_STATES),
        )


if __name__ == "__main__":
    unittest.main()
