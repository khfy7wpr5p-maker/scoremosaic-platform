from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import secrets
import struct
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
    MAX_RAW_ENGINE_RESULT_BYTES,
    AudiverisResultAdapter,
    ClarityResultAdapter,
    EngineResultIngestionError,
    HomrResultAdapter,
    build_candidate_lifecycle_from_outcomes,
    build_engine_result_frame,
    failure_outcome,
    ingest_authenticated_engine_result,
    load_persisted_candidate_record,
    parse_engine_result_frame,
    persist_normalized_candidate_once,
    success_outcome,
    summarize_partial_success,
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
  <part id="P1"><measure number="1"><attributes><divisions>1</divisions><time><beats>4</beats><beat-type>4</beat-type></time><clef><sign>G</sign><line>2</line></clef></attributes><note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration><type>quarter</type></note></measure></part>
</score-partwise>'''


class EngineResultIngestionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.endpoints = {
            engine: EngineEndpoint(engine, origin)
            for engine, origin in APPROVED_ENGINE_ORIGINS["staging"].items()
        }
        self.plan = build_orchestration_plan(
            "job_stage6result01",
            source_artifact_ref="sources/job_stage6result01/source.png",
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
        binding = build_engine_auth_binding(self.endpoints[engine], "staging")
        return EngineCredential(
            binding=binding,
            _secret=(engine.encode("ascii") + b"K" * 64)[:MIN_CREDENTIAL_BYTES],
        )

    def _diagnostic(self, engine: str, *, noncanonical: bool = False) -> bytes:
        value = {
            "status": "success",
            "engine": engine,
            "warnings": [],
            "modelVersion": "fixture-model-1",
            "engineVersion": "fixture-engine-1",
        }
        if noncanonical:
            return json.dumps(value, indent=2).encode("utf-8")
        return json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")

    def _signed(
        self,
        engine: str,
        *,
        xml: bytes = MUSICXML,
        diagnostic: bytes | None = None,
        raw: bytes | None = None,
    ):
        identity = build_dispatch_identity(self.plan, engine)
        frame = build_engine_result_frame(
            raw_engine_result=(
                raw if raw is not None else f"raw-{engine}".encode("ascii")
            ),
            musicxml=xml,
            diagnostic=(
                diagnostic if diagnostic is not None else self._diagnostic(engine)
            ),
        )
        credential = self._credential(engine)
        result_identity = build_dispatch_result_identity(credential, identity, frame)
        return credential, identity, result_identity, frame

    def _candidate(self, engine: str, **kwargs):
        credential, identity, result_identity, frame = self._signed(engine, **kwargs)
        return ingest_authenticated_engine_result(
            credential=credential,
            expected_identity=identity,
            result_identity=result_identity,
            result_payload=frame,
        )

    def test_all_three_engine_adapters_are_bound_and_deterministic(self) -> None:
        adapters = {
            "audiveris": AudiverisResultAdapter(),
            "homr": HomrResultAdapter(),
            "clarity": ClarityResultAdapter(),
        }
        for engine in ENGINE_NAMES:
            with self.subTest(engine=engine):
                credential, identity, result_identity, frame = self._signed(
                    engine,
                    diagnostic=self._diagnostic(engine, noncanonical=True),
                )
                candidates = [
                    adapters[engine].normalize(
                        credential=credential,
                        expected_identity=identity,
                        result_identity=result_identity,
                        result_payload=frame,
                    )
                    for _ in range(10)
                ]
                first = candidates[0]
                self.assertEqual(first.engine, engine)
                self.assertTrue(first.as_safe_dict()["candidateOnly"])
                self.assertFalse(first.as_safe_dict()["authoritativeScore"])
                self.assertNotIn(MUSICXML.decode("utf-8"), repr(first))
                for item in candidates[1:]:
                    self.assertEqual(item.candidate_sha256, first.candidate_sha256)
                    self.assertEqual(item.musicxml_sha256, first.musicxml_sha256)
                    self.assertEqual(item.diagnostic, first.diagnostic)

    def test_cross_engine_result_is_rejected_before_parse(self) -> None:
        credential, homr_identity, _, _ = self._signed("homr")
        _, _, clarity_result, clarity_frame = self._signed("clarity")
        with self.assertRaises(EngineResultIngestionError) as ctx:
            ingest_authenticated_engine_result(
                credential=credential,
                expected_identity=homr_identity,
                result_identity=clarity_result,
                result_payload=clarity_frame,
            )
        self.assertEqual(ctx.exception.category, "engine_result_authentication_failed")

    def test_tampered_authenticated_bytes_fail_before_parser(self) -> None:
        credential, identity, result_identity, frame = self._signed("audiveris")
        tampered = frame[:-1] + bytes([frame[-1] ^ 1])
        with self.assertRaises(EngineResultIngestionError) as ctx:
            ingest_authenticated_engine_result(
                credential=credential,
                expected_identity=identity,
                result_identity=result_identity,
                result_payload=tampered,
            )
        self.assertEqual(ctx.exception.category, "engine_result_authentication_failed")

    def test_frame_rejects_truncation_trailing_data_and_oversized_claims(self) -> None:
        _, _, _, frame = self._signed("homr")
        with self.assertRaises(EngineResultIngestionError) as ctx:
            parse_engine_result_frame(frame[:-1])
        self.assertEqual(ctx.exception.category, "engine_result_frame_truncated")
        with self.assertRaises(EngineResultIngestionError) as ctx:
            parse_engine_result_frame(frame + b"x")
        self.assertEqual(ctx.exception.category, "engine_result_frame_trailing_data")
        oversized_header = struct.pack(
            ">8sQQQ",
            b"SMRES6V1",
            MAX_RAW_ENGINE_RESULT_BYTES + 1,
            1,
            1,
        ) + b"xy"
        with self.assertRaises(EngineResultIngestionError) as ctx:
            parse_engine_result_frame(oversized_header)
        self.assertEqual(ctx.exception.category, "engine_result_raw_oversized")

    def test_unsafe_xml_and_pathological_depth_fail_closed(self) -> None:
        unsafe = (
            b'<!DOCTYPE score-partwise [<!ENTITY x "x">]>'
            b'<score-partwise>&x;</score-partwise>'
        )
        credential, identity, result_identity, frame = self._signed(
            "clarity", xml=unsafe
        )
        with self.assertRaises(EngineResultIngestionError) as ctx:
            ingest_authenticated_engine_result(
                credential=credential,
                expected_identity=identity,
                result_identity=result_identity,
                result_payload=frame,
            )
        self.assertEqual(ctx.exception.category, "engine_result_musicxml_unsafe_xml")

        deep = (
            b"<score-partwise>"
            + b"<x>" * 260
            + b"</x>" * 260
            + b"</score-partwise>"
        )
        credential, identity, result_identity, frame = self._signed(
            "clarity", xml=deep
        )
        with self.assertRaises(EngineResultIngestionError) as ctx:
            ingest_authenticated_engine_result(
                credential=credential,
                expected_identity=identity,
                result_identity=result_identity,
                result_payload=frame,
            )
        self.assertEqual(ctx.exception.category, "engine_result_musicxml_complexity_exceeded")

    def test_duplicate_or_nonfinite_diagnostic_is_rejected(self) -> None:
        variants = (
            b'{"engine":"homr","engine":"homr","status":"success"}',
            b'{"engine":"homr","status":"success","modelVersion":NaN}',
        )
        for diagnostic in variants:
            with self.subTest(diagnostic=diagnostic):
                credential, identity, result_identity, frame = self._signed(
                    "homr", diagnostic=diagnostic
                )
                with self.assertRaises(EngineResultIngestionError):
                    ingest_authenticated_engine_result(
                        credential=credential,
                        expected_identity=identity,
                        result_identity=result_identity,
                        result_payload=frame,
                    )

    def test_candidate_persistence_is_create_once_exact_replay_and_no_overwrite(self) -> None:
        candidate = self._candidate("audiveris")
        first = persist_normalized_candidate_once(
            provider=self.provider,
            orchestration_plan=self.plan,
            candidate=candidate,
        )
        second = persist_normalized_candidate_once(
            provider=self.provider,
            orchestration_plan=self.plan,
            candidate=candidate,
        )
        self.assertEqual(first.persistence_state, "written")
        self.assertEqual(second.persistence_state, "replay")
        self.assertEqual(first.record_sha256, second.record_sha256)

        raw_path = (
            self.provider._root
            / "artifacts"
            / "candidates"
            / candidate.job_id
            / candidate.engine
            / candidate.candidate_id
            / "raw-engine-result.bin"
        )
        raw_path.chmod(0o600)
        raw_path.write_bytes(b"tampered")
        raw_path.chmod(0o400)
        with self.assertRaises(EngineResultIngestionError) as ctx:
            persist_normalized_candidate_once(
                provider=self.provider,
                orchestration_plan=self.plan,
                candidate=candidate,
            )
        self.assertEqual(ctx.exception.category, "candidate_persistence_conflict")

    def test_concurrent_candidate_persistence_has_one_writer_and_exact_replays(self) -> None:
        candidate = self._candidate("homr")

        def persist():
            return persist_normalized_candidate_once(
                provider=self.provider,
                orchestration_plan=self.plan,
                candidate=candidate,
            )

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(lambda _: persist(), range(8)))
        self.assertEqual(
            sum(item.persistence_state == "written" for item in results), 1
        )
        self.assertEqual(
            sum(item.persistence_state == "replay" for item in results), 7
        )
        self.assertEqual(len({item.record_sha256 for item in results}), 1)

    def test_partial_success_contract_is_deterministic_for_3_to_0_successes(self) -> None:
        candidates = {engine: self._candidate(engine) for engine in ENGINE_NAMES}
        for success_count in (3, 2, 1, 0):
            outcomes = []
            for index, engine in enumerate(ENGINE_NAMES):
                if index < success_count:
                    outcomes.append(success_outcome(candidates[engine]))
                else:
                    outcomes.append(
                        failure_outcome(
                            engine=engine,
                            candidate_id=build_dispatch_identity(
                                self.plan, engine
                            ).candidate_id,
                            reason_code="engine_timeout",
                        )
                    )
            first = summarize_partial_success(self.plan, tuple(outcomes))
            self.assertEqual(first.status, f"{success_count}_of_3_success")
            self.assertEqual(first.comparison_eligible, success_count >= 2)
            for _ in range(10):
                self.assertEqual(
                    summarize_partial_success(
                        self.plan, tuple(reversed(outcomes))
                    ).as_safe_dict(),
                    first.as_safe_dict(),
                )

    def test_failure_of_one_engine_does_not_invalidate_other_persisted_candidates(self) -> None:
        successful = {}
        outcomes = []
        for engine in ENGINE_NAMES[:2]:
            candidate = self._candidate(engine)
            persist_normalized_candidate_once(
                provider=self.provider,
                orchestration_plan=self.plan,
                candidate=candidate,
            )
            successful[engine] = load_persisted_candidate_record(
                provider=self.provider,
                orchestration_plan=self.plan,
                engine=engine,
            )
            outcomes.append(success_outcome(candidate))
        failed_engine = ENGINE_NAMES[2]
        outcomes.append(
            failure_outcome(
                engine=failed_engine,
                candidate_id=build_dispatch_identity(
                    self.plan, failed_engine
                ).candidate_id,
                reason_code="engine_crash",
            )
        )
        summary = summarize_partial_success(self.plan, tuple(outcomes))
        lifecycle = build_candidate_lifecycle_from_outcomes(
            self.plan,
            summary.outcomes,
            successful,
        )
        state_by_engine = {item.engine: item.state for item in lifecycle.candidates}
        self.assertEqual(state_by_engine[ENGINE_NAMES[0]], "sealed")
        self.assertEqual(state_by_engine[ENGINE_NAMES[1]], "sealed")
        self.assertEqual(state_by_engine[failed_engine], "failed")
        self.assertTrue(summary.comparison_eligible)
        # Two successful candidates: 2 * (candidate collect + 3*(write+seal) + seal)
        # One failed candidate: 3 artifact abandon events + candidate failed.
        self.assertEqual(len(lifecycle.events), 20)


if __name__ == "__main__":
    unittest.main()
