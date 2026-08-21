from __future__ import annotations

import json
from pathlib import Path
import secrets
import sys
import tempfile
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_gateway.config import EngineEndpoint
from scoremosaic_gateway.dispatch_identity import (
    build_dispatch_identity,
    build_dispatch_result_identity,
)
from scoremosaic_gateway.dispatch_target import APPROVED_ENGINE_ORIGINS
from scoremosaic_gateway.engine_result_ingestion import (
    EngineResultIngestionError,
    build_candidate_lifecycle_from_persistence,
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
<score-partwise version="4.0"><part-list/><part id="P1"><measure number="1"/></part></score-partwise>'''


class EngineResultIngestionHardeningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = build_orchestration_plan(
            "job_stage6hardening01",
            source_artifact_ref="sources/job_stage6hardening01/source.png",
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
        endpoint = EngineEndpoint(
            engine,
            APPROVED_ENGINE_ORIGINS["staging"][engine],
        )
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
                "modelVersion": "fixture-1",
                "status": "success",
                "warnings": [],
            },
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")

    def _candidate(self, engine: str, *, musicxml: bytes = MUSICXML):
        identity = build_dispatch_identity(self.plan, engine)
        frame = build_engine_result_frame(
            raw_engine_result=f"raw-{engine}".encode("ascii"),
            musicxml=musicxml,
            diagnostic=self._diagnostic(engine),
        )
        credential = self._credential(engine)
        result_identity = build_dispatch_result_identity(
            credential,
            identity,
            frame,
        )
        return ingest_authenticated_engine_result(
            credential=credential,
            expected_identity=identity,
            result_identity=result_identity,
            result_payload=frame,
        )

    def test_lifecycle_reauthenticates_actual_persisted_artifact_bytes(self) -> None:
        successes = []
        for engine in ENGINE_NAMES[:2]:
            candidate = self._candidate(engine)
            persist_normalized_candidate_once(
                provider=self.provider,
                orchestration_plan=self.plan,
                candidate=candidate,
            )
            successes.append(success_outcome(candidate))

        failed_engine = ENGINE_NAMES[2]
        outcomes = tuple(
            successes
            + [
                failure_outcome(
                    engine=failed_engine,
                    candidate_id=build_dispatch_identity(
                        self.plan,
                        failed_engine,
                    ).candidate_id,
                    reason_code="engine_unavailable",
                )
            ]
        )

        first_engine = ENGINE_NAMES[0]
        first_candidate_id = build_dispatch_identity(
            self.plan,
            first_engine,
        ).candidate_id
        musicxml_path = (
            self.provider._root
            / "artifacts"
            / "candidates"
            / self.plan["jobId"]
            / first_engine
            / first_candidate_id
            / "candidate.musicxml"
        )
        musicxml_path.chmod(0o600)
        musicxml_path.write_bytes(b"tampered-after-persistence")
        musicxml_path.chmod(0o400)

        with self.assertRaises(EngineResultIngestionError) as ctx:
            build_candidate_lifecycle_from_persistence(
                provider=self.provider,
                orchestration_plan=self.plan,
                outcomes=outcomes,
            )
        self.assertEqual(
            ctx.exception.category,
            "candidate_persistence_artifact_invalid",
        )

    def test_forbidden_xml_construct_after_first_megabyte_fails_as_unsafe(self) -> None:
        late_unsafe_xml = (
            b"<score-partwise><credit><credit-words>"
            + b"a" * (1024 * 1024 + 8192)
            + b"</credit-words></credit>"
            + b"<!DOCTYPE score-partwise>"
            + b"</score-partwise>"
        )
        with self.assertRaises(EngineResultIngestionError) as ctx:
            self._candidate("homr", musicxml=late_unsafe_xml)
        self.assertEqual(
            ctx.exception.category,
            "engine_result_musicxml_unsafe_xml",
        )


if __name__ == "__main__":
    unittest.main()
