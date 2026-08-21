from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import secrets
import sys
import tempfile
import unittest

TEST_FILE = Path(__file__).resolve()
ENSEMBLE_ROOT = TEST_FILE.parents[1]
REPO_ROOT = TEST_FILE.parents[3]
sys.path.insert(0, str(ENSEMBLE_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "services" / "omr-gateway" / "src"))

from scoremosaic_ensemble.convergence import (
    CandidateConvergenceError,
    converge_verified_candidates,
)
from scoremosaic_gateway.candidate_convergence_handoff import (
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

VALID_MUSICXML = b'''<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0">
 <part-list><score-part id="P1"><part-name>Music</part-name></score-part></part-list>
 <part id="P1"><measure number="1"><attributes><divisions>1</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes><note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><type>whole</type></note></measure></part>
</score-partwise>'''

CANONICAL_INVALID_MUSICXML = b'''<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0">
 <part-list><score-part id="P1"><part-name>Music</part-name></score-part></part-list>
 <part id="P1"><measure number="1"><note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><type>whole</type></note></measure></part>
</score-partwise>'''


class Stage7ConvergenceIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = build_orchestration_plan(
            "job_stage7integration01",
            source_artifact_ref="sources/job_stage7integration01/source.png",
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

    def _persist(self, engine: str, document: bytes = VALID_MUSICXML):
        identity = build_dispatch_identity(self.plan, engine)
        frame = build_engine_result_frame(
            raw_engine_result=f"raw-{engine}".encode("ascii"),
            musicxml=document,
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

    def _two_success_handoffs(
        self,
        *,
        second_document: bytes = VALID_MUSICXML,
    ):
        first = self._persist(ENGINE_NAMES[0], VALID_MUSICXML)
        second = self._persist(ENGINE_NAMES[1], second_document)
        failed_engine = ENGINE_NAMES[2]
        outcomes = (
            success_outcome(first),
            success_outcome(second),
            failure_outcome(
                engine=failed_engine,
                candidate_id=build_dispatch_identity(
                    self.plan,
                    failed_engine,
                ).candidate_id,
                reason_code="engine_unavailable",
            ),
        )
        return load_verified_candidate_handoffs(
            provider=self.provider,
            orchestration_plan=self.plan,
            outcomes=outcomes,
        )

    def test_two_persisted_candidates_converge_deterministically(self) -> None:
        handoffs = self._two_success_handoffs()
        payloads = tuple(item.to_ensemble_payload() for item in handoffs)
        first = converge_verified_candidates(payloads)

        self.assertEqual(first.status, "comparison_ready")
        self.assertEqual(first.admission.accepted_candidate_count, 2)
        self.assertEqual(first.admission.rejected_candidate_count, 0)
        self.assertIsNotNone(first.admission.comparison)
        self.assertTrue(first.admission.comparison.identical)
        self.assertIsNotNone(first.comparison_report)
        safe = first.as_safe_dict()
        self.assertEqual(safe["evidence"]["engineAgreement"]["status"], "full_agreement")
        self.assertIsNone(safe["evidence"]["aggregateConfidenceScore"])
        self.assertFalse(safe["evidence"]["visualConfidence"]["available"])
        self.assertFalse(safe["evidence"]["sourceQuality"]["available"])
        self.assertFalse(safe["evidence"]["localizationReliability"]["bboxEvidenceAvailable"])
        self.assertFalse(safe["boundaries"]["authoritativeScore"])
        self.assertFalse(safe["boundaries"]["winnerSelection"])

        for _ in range(10):
            repeated = converge_verified_candidates(tuple(reversed(payloads)))
            self.assertEqual(repeated.result_sha256, first.result_sha256)
            self.assertEqual(repeated.as_safe_dict(), first.as_safe_dict())

    def test_canonical_rejection_is_isolated_and_comparison_fails_closed(self) -> None:
        handoffs = self._two_success_handoffs(
            second_document=CANONICAL_INVALID_MUSICXML,
        )
        result = converge_verified_candidates(
            tuple(item.to_ensemble_payload() for item in handoffs)
        )
        self.assertEqual(result.status, "insufficient_canonical_candidates")
        self.assertEqual(result.admission.accepted_candidate_count, 1)
        self.assertEqual(result.admission.rejected_candidate_count, 1)
        self.assertIsNone(result.admission.comparison)
        self.assertIsNone(result.comparison_report)
        self.assertTrue(result.admission.as_dict()["failClosed"])

    def test_tampered_handoff_document_is_rejected_before_canonical_parse(self) -> None:
        payloads = [item.to_ensemble_payload() for item in self._two_success_handoffs()]
        payloads[0] = dict(payloads[0])
        payloads[0]["document"] = payloads[0]["document"] + b" "
        with self.assertRaises(CandidateConvergenceError) as ctx:
            converge_verified_candidates(payloads)
        self.assertEqual(ctx.exception.category, "stage7_handoff_integrity_invalid")

    def test_cross_source_handoffs_are_rejected_even_with_valid_internal_hashes(self) -> None:
        handoffs = list(self._two_success_handoffs())
        handoffs[1] = replace(handoffs[1], source_sha256="2" * 64)
        payloads = tuple(item.to_ensemble_payload() for item in handoffs)
        with self.assertRaises(CandidateConvergenceError) as ctx:
            converge_verified_candidates(payloads)
        self.assertEqual(ctx.exception.category, "stage7_convergence_source_binding_mismatch")


if __name__ == "__main__":
    unittest.main()
