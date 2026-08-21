from __future__ import annotations

import json
from pathlib import Path
import secrets
import sys
import tempfile
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_gateway.candidate_convergence_handoff import (
    CandidateConvergenceHandoffError,
    load_verified_candidate_handoff,
    load_verified_candidate_handoffs,
)
from scoremosaic_gateway.config import EngineEndpoint
from scoremosaic_gateway.dispatch_identity import (
    build_dispatch_identity,
    build_dispatch_result_identity,
)
from scoremosaic_gateway.dispatch_target import APPROVED_ENGINE_ORIGINS
from scoremosaic_gateway.engine_result_ingestion import (
    build_engine_result_frame,
    failure_outcome,
    ingest_authenticated_engine_result,
    persist_normalized_candidate_once,
    success_outcome,
)
from scoremosaic_gateway.minimum_staging_vertical_slice import StagingUploadProvider
from scoremosaic_gateway.orchestration import ENGINE_NAMES, build_orchestration_plan
from scoremosaic_gateway.service_auth import (
    EngineCredential,
    MIN_CREDENTIAL_BYTES,
    build_engine_auth_binding,
)

MUSICXML = b'''<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0">
 <part-list><score-part id="P1"><part-name>Music</part-name></score-part></part-list>
 <part id="P1"><measure number="1"><attributes><divisions>1</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes><note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><type>whole</type></note></measure></part>
</score-partwise>'''


class CandidateConvergenceHandoffTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = build_orchestration_plan(
            "job_stage7handoff01",
            source_artifact_ref="sources/job_stage7handoff01/source.png",
            source_sha256="1" * 64,
            source_size_bytes=128,
            source_media_type="image/png",
            requested_engines=ENGINE_NAMES,
        ).as_dict()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.provider = StagingUploadProvider(
            Path(self.temp.name),
            state_integrity_key=secrets.token_bytes(32),
        )

    def _credential(self, engine: str) -> EngineCredential:
        endpoint = EngineEndpoint(engine, APPROVED_ENGINE_ORIGINS["staging"][engine])
        return EngineCredential(
            binding=build_engine_auth_binding(endpoint, "staging"),
            _secret=(engine.encode("ascii") + b"K" * 64)[:MIN_CREDENTIAL_BYTES],
        )

    @staticmethod
    def _diagnostic(engine: str) -> bytes:
        return json.dumps(
            {
                "engine": engine,
                "engineVersion": "fixture-1",
                "modelVersion": "fixture-model-1",
                "status": "success",
                "warnings": [],
            },
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")

    def _candidate(self, engine: str):
        identity = build_dispatch_identity(self.plan, engine)
        frame = build_engine_result_frame(
            raw_engine_result=f"raw-{engine}".encode("ascii"),
            musicxml=MUSICXML,
            diagnostic=self._diagnostic(engine),
        )
        credential = self._credential(engine)
        result_identity = build_dispatch_result_identity(credential, identity, frame)
        candidate = ingest_authenticated_engine_result(
            credential=credential,
            expected_identity=identity,
            result_identity=result_identity,
            result_payload=frame,
        )
        persist_normalized_candidate_once(
            provider=self.provider,
            orchestration_plan=self.plan,
            candidate=candidate,
        )
        return candidate

    def test_handoff_is_deterministic_and_redacted(self) -> None:
        candidate = self._candidate("audiveris")
        values = [
            load_verified_candidate_handoff(
                provider=self.provider,
                orchestration_plan=self.plan,
                engine="audiveris",
            )
            for _ in range(10)
        ]
        first = values[0]
        self.assertEqual(first.candidate_sha256, candidate.candidate_sha256)
        self.assertEqual(first.document, MUSICXML)
        self.assertNotIn(MUSICXML.decode("utf-8"), repr(first))
        self.assertFalse(first.as_safe_dict()["transportAuthorizationGranted"])
        self.assertNotIn("document", first.as_safe_dict())
        for item in values[1:]:
            self.assertEqual(item.handoff_sha256, first.handoff_sha256)
            self.assertEqual(item.as_safe_dict(), first.as_safe_dict())

    def test_two_successes_are_loaded_and_failure_is_isolated(self) -> None:
        candidates = [self._candidate(engine) for engine in ENGINE_NAMES[:2]]
        failed = ENGINE_NAMES[2]
        outcomes = (
            success_outcome(candidates[0]),
            success_outcome(candidates[1]),
            failure_outcome(
                engine=failed,
                candidate_id=build_dispatch_identity(self.plan, failed).candidate_id,
                reason_code="engine_unavailable",
            ),
        )
        handoffs = load_verified_candidate_handoffs(
            provider=self.provider,
            orchestration_plan=self.plan,
            outcomes=outcomes,
        )
        self.assertEqual(tuple(item.engine for item in handoffs), ENGINE_NAMES[:2])
        self.assertEqual(len({item.handoff_sha256 for item in handoffs}), 2)

    def test_insufficient_successes_fail_closed(self) -> None:
        candidate = self._candidate(ENGINE_NAMES[0])
        outcomes = [success_outcome(candidate)]
        for engine in ENGINE_NAMES[1:]:
            outcomes.append(
                failure_outcome(
                    engine=engine,
                    candidate_id=build_dispatch_identity(self.plan, engine).candidate_id,
                    reason_code="engine_timeout",
                )
            )
        with self.assertRaises(CandidateConvergenceHandoffError) as ctx:
            load_verified_candidate_handoffs(
                provider=self.provider,
                orchestration_plan=self.plan,
                outcomes=tuple(outcomes),
            )
        self.assertEqual(ctx.exception.category, "stage7_handoff_insufficient_candidates")

    def test_tampered_persisted_musicxml_cannot_cross_handoff(self) -> None:
        candidate = self._candidate("homr")
        path = (
            self.provider._root
            / "artifacts"
            / "candidates"
            / candidate.job_id
            / candidate.engine
            / candidate.candidate_id
            / "candidate.musicxml"
        )
        path.chmod(0o600)
        path.write_bytes(b"tampered")
        path.chmod(0o400)
        with self.assertRaises(CandidateConvergenceHandoffError) as ctx:
            load_verified_candidate_handoff(
                provider=self.provider,
                orchestration_plan=self.plan,
                engine="homr",
            )
        self.assertEqual(ctx.exception.category, "stage7_handoff_persistence_invalid")


if __name__ == "__main__":
    unittest.main()
