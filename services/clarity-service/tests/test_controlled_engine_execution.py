from __future__ import annotations

from hashlib import sha256
import importlib
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
import threading
import time
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SERVICE_ROOT.parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "services" / "omr-gateway" / "src"))

from scoremosaic_gateway.dispatch_identity import build_dispatch_identity
from scoremosaic_gateway.orchestration import build_orchestration_plan

_PACKAGE_BY_SERVICE = {
    "audiveris-service": "scoremosaic_audiveris",
    "homr-service": "scoremosaic_homr",
    "clarity-service": "scoremosaic_clarity",
}
PACKAGE = _PACKAGE_BY_SERVICE[SERVICE_ROOT.name]
config_module = importlib.import_module(PACKAGE + ".config")
controller = importlib.import_module(PACKAGE + ".controlled_engine_execution")
dispatch_acceptance = importlib.import_module(PACKAGE + ".dispatch_acceptance")
capability = importlib.import_module(PACKAGE + ".engine_execution_capability")
receiver_authority = importlib.import_module(PACKAGE + ".receiver_authority")
runtime = importlib.import_module(PACKAGE + ".runtime")
source_delivery = importlib.import_module(PACKAGE + ".source_delivery")

ENGINE = receiver_authority.ENGINE_NAME
EngineReceiverAuthority = receiver_authority.EngineReceiverAuthority
EngineDispatchAcceptanceStore = dispatch_acceptance.EngineDispatchAcceptanceStore
EngineSourceStore = source_delivery.EngineSourceStore
EngineExecutionClaimStore = controller.EngineExecutionClaimStore
ControlledEngineExecutionError = controller.ControlledEngineExecutionError
execute_controlled_engine_once = controller.execute_controlled_engine_once
evaluate_engine_execution_eligibility = capability.evaluate_engine_execution_eligibility
TranscriptionResult = runtime.TranscriptionResult
RuntimeExecutionError = runtime.RuntimeExecutionError

SUPPORTED = {
    "audiveris": ("application/pdf", "image/jpeg", "image/png"),
    "homr": ("image/jpeg", "image/png"),
    "clarity": ("application/pdf",),
}
ALL_MEDIA = {"application/pdf", "image/jpeg", "image/png"}


def canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")


def source_bytes(media_type: str, marker: str) -> bytes:
    if media_type == "application/pdf":
        return b"%PDF-1.4\n" + marker.encode("ascii") * 8
    if media_type == "image/png":
        return b"\x89PNG\r\n\x1a\n" + marker.encode("ascii") * 8
    return b"\xff\xd8\xff\xe0" + marker.encode("ascii") * 8 + b"\xff\xd9"


class ControlledEngineExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.authority = EngineReceiverAuthority(
            root=self.root / "authority",
            integrity_key=secrets.token_bytes(32),
        )
        self.acceptance = EngineDispatchAcceptanceStore(
            root=self.root / "dispatch",
            integrity_key=secrets.token_bytes(32),
        )
        self.source_store = EngineSourceStore(
            root=self.root / "source-store",
            integrity_key=secrets.token_bytes(32),
        )
        self.claim_store = EngineExecutionClaimStore(
            root=self.root / "execution-state",
            integrity_key=secrets.token_bytes(32),
        )
        self.sequence = 0
        self.transcriber_calls = 0
        self.call_lock = threading.Lock()

    def config(self, *, request_timeout: int = 60):
        workspace = self.root / "workspace"
        if ENGINE == "audiveris":
            values = {
                "SCOREMOSAIC_AUDIVERIS_WORKSPACE_ROOT": str(workspace),
                "SCOREMOSAIC_AUDIVERIS_REQUEST_TIMEOUT_SECONDS": str(request_timeout),
            }
        elif ENGINE == "homr":
            values = {
                "SCOREMOSAIC_HOMR_WORKSPACE_ROOT": str(workspace),
                "SCOREMOSAIC_HOMR_REQUEST_TIMEOUT_SECONDS": str(request_timeout),
            }
        else:
            values = {
                "SCOREMOSAIC_CLARITY_WORKSPACE_ROOT": str(workspace),
                "SCOREMOSAIC_CLARITY_REQUEST_TIMEOUT_SECONDS": str(request_timeout),
            }
        return config_module.load_config(values)

    def prepare(self, media_type: str, *, timeout_seconds: int = 3600):
        self.sequence += 1
        job_id = f"job_stage5b2exec{self.sequence:02d}"
        body = source_bytes(media_type, f"m{self.sequence:02d}")
        digest = sha256(body).hexdigest()
        plan = build_orchestration_plan(
            job_id,
            source_artifact_ref=f"sources/{job_id}/source.bin",
            source_sha256=digest,
            source_size_bytes=len(body),
            source_media_type=media_type,
            timeout_seconds_by_engine={ENGINE: timeout_seconds},
        ).as_dict()
        identity = build_dispatch_identity(plan, ENGINE)
        self.authority.register_trusted_plan(
            job_id=job_id,
            canonical_plan_bytes=canonical(plan),
        )
        self.acceptance.publish(
            job_id=identity.job_id,
            run_id=identity.run_id,
            dispatch_identity_sha256=identity.identity_sha256,
        )
        self.source_store.publish(
            job_id=identity.job_id,
            run_id=identity.run_id,
            dispatch_identity_sha256=identity.identity_sha256,
            source_artifact_id=identity.source_artifact_id,
            source_bytes=body,
            source_sha256=digest,
            source_media_type=media_type,
        )
        return body, identity

    def exact_result(self, output: Path):
        if ENGINE == "audiveris":
            return TranscriptionResult(
                return_code=0,
                musicxml_artifacts=(output,),
                omr_artifacts=(),
                diagnostic="",
                candidate_handoffs=(),
            )
        return TranscriptionResult(
            return_code=0,
            musicxml_artifacts=(output,),
            diagnostic="",
            candidate_handoffs=(),
        )

    def success_transcriber(self, input_path: Path, output_dir: Path, _config):
        with self.call_lock:
            self.transcriber_calls += 1
        self.assertTrue(input_path.is_file())
        self.assertEqual(input_path.parent, output_dir)
        output = output_dir / "candidate.musicxml"
        output.write_bytes(b"<score-partwise version='4.0'></score-partwise>")
        return self.exact_result(output)

    def execute(self, identity, *, transcriber=None, config=None):
        kwargs = {
            "authority": self.authority,
            "dispatch_acceptance_store": self.acceptance,
            "source_store": self.source_store,
            "claim_store": self.claim_store,
            "config": self.config() if config is None else config,
            "job_id": identity.job_id,
            "run_id": identity.run_id,
            "dispatch_identity_sha256": identity.identity_sha256,
        }
        if transcriber is not None:
            kwargs["transcriber"] = transcriber
        return execute_controlled_engine_once(**kwargs)

    def claim_path(self, identity) -> Path:
        return (
            self.root
            / "execution-state"
            / "execution-claims"
            / f"{identity.job_id}.{identity.run_id}.json"
        )

    def test_exact_supported_source_executes_once_and_returns_only_safe_handoff(self) -> None:
        body, identity = self.prepare(SUPPORTED[ENGINE][0])
        result = self.execute(identity, transcriber=self.success_transcriber)
        self.assertEqual(self.transcriber_calls, 1)
        self.assertTrue(result.engine_execution_performed)
        self.assertFalse(result.automatic_retry_allowed)
        self.assertFalse(result.restart_reexecution_allowed)
        self.assertFalse(result.result_return_allowed)
        self.assertFalse(result.result_persistence_allowed)
        self.assertFalse(result.gateway_state_mutation_allowed)
        self.assertTrue(result.reconciliation_required_on_restart)
        self.assertEqual(result.execution_attempt_count, 1)
        self.assertEqual(len(result.artifacts), 1)
        safe = result.as_safe_dict()
        self.assertEqual(safe["outputCount"], 1)
        self.assertNotIn("path", json.dumps(safe).lower())
        self.assertNotIn(body.hex(), repr(result))
        self.assertNotIn(str(self.root), repr(result))
        with self.assertRaises(ControlledEngineExecutionError) as caught:
            self.execute(identity, transcriber=self.success_transcriber)
        self.assertEqual(caught.exception.category, "engine_execution_reconciliation_required")
        self.assertEqual(self.transcriber_calls, 1)

    def test_runtime_failure_consumes_claim_and_restart_never_reexecutes(self) -> None:
        _body, identity = self.prepare(SUPPORTED[ENGINE][0])
        def failing(_input, _output, _config):
            with self.call_lock:
                self.transcriber_calls += 1
            raise RuntimeExecutionError("sensitive runtime detail")
        with self.assertRaises(ControlledEngineExecutionError) as caught:
            self.execute(identity, transcriber=failing)
        self.assertEqual(caught.exception.category, "engine_execution_runtime_failed")
        self.assertNotIn("sensitive", str(caught.exception))
        with self.assertRaises(ControlledEngineExecutionError) as restarted:
            self.execute(identity, transcriber=failing)
        self.assertEqual(restarted.exception.category, "engine_execution_reconciliation_required")
        self.assertEqual(self.transcriber_calls, 1)

    def test_concurrent_callers_have_exactly_one_process_winner(self) -> None:
        _body, identity = self.prepare(SUPPORTED[ENGINE][0])
        def slow(input_path, output_dir, config):
            with self.call_lock:
                self.transcriber_calls += 1
            time.sleep(0.05)
            output = output_dir / "candidate.musicxml"
            output.write_bytes(b"<score-partwise></score-partwise>")
            return self.exact_result(output)
        barrier = threading.Barrier(8)
        outcomes: list[str] = []
        lock = threading.Lock()
        def worker():
            barrier.wait()
            try:
                self.execute(identity, transcriber=slow)
                value = "success"
            except ControlledEngineExecutionError as exc:
                value = exc.category
            with lock:
                outcomes.append(value)
        threads = [threading.Thread(target=worker) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(5)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(outcomes.count("success"), 1)
        self.assertEqual(
            outcomes.count("engine_execution_reconciliation_required"),
            7,
        )
        self.assertEqual(self.transcriber_calls, 1)

    def test_unsupported_media_fails_before_claim_or_process(self) -> None:
        unsupported = sorted(ALL_MEDIA - set(SUPPORTED[ENGINE]))
        if not unsupported:
            self.skipTest("Audiveris supports every admitted source media type")
        _body, identity = self.prepare(unsupported[0])
        with self.assertRaises(ControlledEngineExecutionError) as caught:
            self.execute(identity, transcriber=self.success_transcriber)
        self.assertEqual(caught.exception.category, "engine_execution_media_type_unsupported")
        self.assertEqual(self.transcriber_calls, 0)
        self.assertFalse(self.claim_path(identity).exists())

    def test_runtime_timeout_cannot_exceed_trusted_plan_timeout(self) -> None:
        _body, identity = self.prepare(SUPPORTED[ENGINE][0], timeout_seconds=30)
        with self.assertRaises(ControlledEngineExecutionError) as caught:
            self.execute(
                identity,
                transcriber=self.success_transcriber,
                config=self.config(request_timeout=60),
            )
        self.assertEqual(caught.exception.category, "engine_execution_timeout_policy_invalid")
        self.assertEqual(self.transcriber_calls, 0)
        self.assertFalse(self.claim_path(identity).exists())

    def test_symlinked_execution_workspace_fails_after_claim_and_restart_is_zero_process(self) -> None:
        _body, identity = self.prepare(SUPPORTED[ENGINE][0])
        workspace = self.root / "workspace"
        workspace.mkdir()
        outside = self.root / "outside"
        outside.mkdir()
        os.symlink(outside, workspace / "stage5-executions")
        with self.assertRaises(ControlledEngineExecutionError) as caught:
            self.execute(identity, transcriber=self.success_transcriber)
        self.assertEqual(caught.exception.category, "engine_execution_workspace_invalid")
        self.assertTrue(self.claim_path(identity).is_file())
        self.assertEqual(self.transcriber_calls, 0)
        with self.assertRaises(ControlledEngineExecutionError) as restarted:
            self.execute(identity, transcriber=self.success_transcriber)
        self.assertEqual(restarted.exception.category, "engine_execution_reconciliation_required")
        self.assertEqual(self.transcriber_calls, 0)
        self.assertEqual(list(outside.iterdir()), [])

    def test_tampered_or_symlinked_claim_is_fail_closed_without_process(self) -> None:
        _body, identity = self.prepare(SUPPORTED[ENGINE][0])
        eligibility = evaluate_engine_execution_eligibility(
            authority=self.authority,
            dispatch_acceptance_store=self.acceptance,
            source_store=self.source_store,
            job_id=identity.job_id,
            run_id=identity.run_id,
            dispatch_identity_sha256=identity.identity_sha256,
        )
        self.claim_store.reserve(eligibility)
        path = self.claim_path(identity)
        path.chmod(0o600)
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaises(ControlledEngineExecutionError) as caught:
            self.execute(identity, transcriber=self.success_transcriber)
        self.assertEqual(caught.exception.category, "engine_execution_claim_state_invalid")
        self.assertEqual(self.transcriber_calls, 0)

        path.unlink()
        outside = self.root / "outside-claim"
        outside.write_text("do not read", encoding="utf-8")
        os.symlink(outside, path)
        with self.assertRaises(ControlledEngineExecutionError) as symlinked:
            self.execute(identity, transcriber=self.success_transcriber)
        self.assertEqual(symlinked.exception.category, "engine_execution_claim_state_invalid")
        self.assertEqual(self.transcriber_calls, 0)

    def test_runtime_output_cannot_escape_execution_workspace(self) -> None:
        _body, identity = self.prepare(SUPPORTED[ENGINE][0])
        outside = self.root / "outside-result.musicxml"
        def escaping(_input, _output, _config):
            with self.call_lock:
                self.transcriber_calls += 1
            outside.write_bytes(b"<score-partwise></score-partwise>")
            return self.exact_result(outside)
        with self.assertRaises(ControlledEngineExecutionError) as caught:
            self.execute(identity, transcriber=escaping)
        self.assertEqual(caught.exception.category, "engine_execution_output_invalid")
        self.assertEqual(self.transcriber_calls, 1)
        with self.assertRaises(ControlledEngineExecutionError) as restarted:
            self.execute(identity, transcriber=escaping)
        self.assertEqual(restarted.exception.category, "engine_execution_reconciliation_required")
        self.assertEqual(self.transcriber_calls, 1)


if __name__ == "__main__":
    unittest.main()
