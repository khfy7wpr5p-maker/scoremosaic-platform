import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import importlib

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))
_PACKAGE_BY_SERVICE = {
    "audiveris-service": "scoremosaic_audiveris",
    "homr-service": "scoremosaic_homr",
    "clarity-service": "scoremosaic_clarity",
}
receiver_authority = importlib.import_module(
    _PACKAGE_BY_SERVICE.get(SERVICE_ROOT.name, "invalid") + ".receiver_authority"
)
ENGINE_NAME = receiver_authority.ENGINE_NAME
EngineReceiverAuthority = receiver_authority.EngineReceiverAuthority
EngineReceiverAuthorityError = receiver_authority.EngineReceiverAuthorityError


def canonical(value):
    return json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("ascii")


def digest_id(prefix, *parts):
    digest = hashlib.sha256("\x1f".join(parts).encode()).hexdigest()
    return f"{prefix}_{digest[:24]}"


def plan_bytes(*, engines=("audiveris", "homr", "clarity"), job_id="job_12345678abcdef", source_ref="sources/input.png"):
    source_sha = "c" * 64
    source_id = digest_id("artifact", "1.0", job_id, source_ref, source_sha)
    runs = []
    for engine in engines:
        run_id = digest_id("run", "1.0", job_id, engine, source_sha)
        candidate_id = digest_id("candidate", "1.0", job_id, engine, run_id)
        namespace = f"candidates/{job_id}/{engine}/{candidate_id}"
        artifacts = [
            {
                "artifactId": digest_id("artifact", "1.0", candidate_id, kind),
                "kind": kind,
                "artifactRef": f"{namespace}/{kind}",
                "immutable": True,
                "sha256Required": True,
            }
            for kind in ("musicxml", "diagnostic")
        ]
        runs.append({
            "runId": run_id,
            "engine": engine,
            "operation": "transcribe",
            "transportProfile": "private-engine-adapter-v1",
            "endpointKey": engine,
            "inputArtifactId": source_id,
            "candidateId": candidate_id,
            "candidateNamespace": namespace,
            "timeoutSeconds": 3600,
            "attemptLimit": 1,
            "initialState": "planned",
            "expectedArtifacts": artifacts,
        })
    transitions = {
        "planned": ["queued", "cancelled"],
        "queued": ["dispatching", "cancelled", "timed_out"],
        "dispatching": ["running", "failed", "cancelled", "timed_out"],
        "running": ["completed", "failed", "cancelled", "timed_out"],
        "completed": [], "failed": [], "cancelled": [], "timed_out": [],
    }
    core = {
        "schemaVersion": "1.0",
        "contractType": "scoremosaic-gateway-orchestration-plan",
        "jobId": job_id,
        "sourceArtifact": {
            "artifactId": source_id,
            "artifactRef": source_ref,
            "sha256": source_sha,
            "sizeBytes": 123,
            "mediaType": "image/png",
            "immutable": True,
        },
        "requestedEngines": list(engines),
        "engineRuns": runs,
        "lifecyclePolicy": {
            "engineRunStates": list(transitions),
            "terminalEngineRunStates": ["completed", "failed", "cancelled", "timed_out"],
            "allowedEngineRunTransitions": transitions,
        },
        "timeoutPolicy": {
            "clock": "monotonic",
            "startsAt": "dispatch",
            "cancellationGraceSeconds": 30,
            "totalDeadlineSeconds": 3630,
            "timeoutIsTerminal": True,
            "retryAfterTimeout": False,
        },
        "artifactPolicy": {
            "sourceImmutable": True, "candidateIsolation": True, "hashRequired": True,
            "overwriteAllowed": False, "crossEngineWriteAllowed": False,
        },
        "boundaries": {
            "executionEnabled": False, "uploadEnabled": False, "persistenceEnabled": False,
            "networkDispatchEnabled": False, "engineRanking": False, "winnerSelection": False,
            "automaticMerge": False, "automaticCorrection": False, "teacherApproval": False,
            "publication": False,
        },
    }
    with_id = dict(core)
    with_id["planId"] = "plan_" + hashlib.sha256(canonical(core)).hexdigest()[:24]
    final = dict(with_id)
    final["planSha256"] = hashlib.sha256(canonical(with_id)).hexdigest()
    return canonical(final)


class ReceiverAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "authority"
        self.key = hashlib.sha256((ENGINE_NAME + "-test-key").encode()).digest()
        self.authority = EngineReceiverAuthority(root=self.root, integrity_key=self.key)

    def tearDown(self):
        self.temp.cleanup()

    def test_register_load_and_restart_are_deterministic_and_non_executable(self):
        raw = plan_bytes()
        written = self.authority.register_trusted_plan(job_id="job_12345678abcdef", canonical_plan_bytes=raw)
        replay = self.authority.register_trusted_plan(job_id="job_12345678abcdef", canonical_plan_bytes=raw)
        restarted = EngineReceiverAuthority(root=self.root, integrity_key=self.key)
        loaded = restarted.load_trusted_plan(job_id="job_12345678abcdef")
        self.assertEqual(written.persistence_state, "written")
        self.assertEqual(replay.persistence_state, "replay")
        self.assertEqual(loaded.persistence_state, "loaded")
        self.assertEqual(written.canonical_plan_sha256, replay.canonical_plan_sha256)
        self.assertEqual(written.canonical_plan_sha256, loaded.canonical_plan_sha256)
        self.assertEqual(loaded.canonical_plan_bytes, raw)
        self.assertFalse(loaded.network_dispatch_allowed)
        self.assertFalse(loaded.retry_allowed)
        self.assertFalse(loaded.job_state_mutation_allowed)
        self.assertFalse(loaded.engine_execution_allowed)
        self.assertNotIn(raw.decode(), repr(loaded))
        self.assertNotIn(self.key.hex(), repr(restarted))

    def test_cross_engine_plan_is_rejected(self):
        other = tuple(engine for engine in ("audiveris", "homr", "clarity") if engine != ENGINE_NAME)
        with self.assertRaises(EngineReceiverAuthorityError) as caught:
            self.authority.register_trusted_plan(job_id="job_12345678abcdef", canonical_plan_bytes=plan_bytes(engines=other))
        self.assertEqual(caught.exception.category, "receiver_authority_plan_invalid")

    def test_noncanonical_and_duplicate_json_are_rejected(self):
        raw = plan_bytes()
        parsed = json.loads(raw)
        noncanonical = json.dumps(parsed, indent=2).encode("ascii")
        with self.assertRaises(EngineReceiverAuthorityError):
            self.authority.register_trusted_plan(job_id="job_12345678abcdef", canonical_plan_bytes=noncanonical)
        duplicate = raw[:-1] + b',"jobId":"job_12345678abcdef"}'
        with self.assertRaises(EngineReceiverAuthorityError):
            self.authority.register_trusted_plan(job_id="job_12345678abcdef", canonical_plan_bytes=duplicate)

    def test_plan_digest_tamper_and_security_boundary_tamper_are_rejected(self):
        parsed = json.loads(plan_bytes())
        parsed["planSha256"] = "0" * 64
        with self.assertRaises(EngineReceiverAuthorityError):
            self.authority.register_trusted_plan(job_id="job_12345678abcdef", canonical_plan_bytes=canonical(parsed))
        parsed = json.loads(plan_bytes())
        parsed["boundaries"]["executionEnabled"] = True
        core = dict(parsed)
        core.pop("planSha256")
        core.pop("planId")
        parsed["planId"] = "plan_" + hashlib.sha256(canonical(core)).hexdigest()[:24]
        without_sha = dict(parsed)
        without_sha.pop("planSha256")
        parsed["planSha256"] = hashlib.sha256(canonical(without_sha)).hexdigest()
        with self.assertRaises(EngineReceiverAuthorityError):
            self.authority.register_trusted_plan(job_id="job_12345678abcdef", canonical_plan_bytes=canonical(parsed))

    def test_existing_plan_cannot_be_overwritten(self):
        raw = plan_bytes()
        self.authority.register_trusted_plan(job_id="job_12345678abcdef", canonical_plan_bytes=raw)
        different = plan_bytes(source_ref="sources/other.png")
        with self.assertRaises(EngineReceiverAuthorityError) as caught:
            self.authority.register_trusted_plan(job_id="job_12345678abcdef", canonical_plan_bytes=different)
        self.assertEqual(caught.exception.category, "receiver_authority_plan_conflict")
        self.assertEqual(self.authority.load_trusted_plan(job_id="job_12345678abcdef").canonical_plan_bytes, raw)

    def test_state_tamper_is_detected_after_restart(self):
        self.authority.register_trusted_plan(job_id="job_12345678abcdef", canonical_plan_bytes=plan_bytes())
        path = self.root / "trusted-plans" / "job_12345678abcdef.json"
        os.chmod(path, 0o600)
        data = bytearray(path.read_bytes())
        data[-10] = data[-10] ^ 1
        path.write_bytes(bytes(data))
        restarted = EngineReceiverAuthority(root=self.root, integrity_key=self.key)
        with self.assertRaises(EngineReceiverAuthorityError) as caught:
            restarted.load_trusted_plan(job_id="job_12345678abcdef")
        self.assertEqual(caught.exception.category, "receiver_authority_plan_not_found_or_invalid")

    def test_symlink_plan_path_is_never_followed(self):
        target = Path(self.temp.name) / "outside.json"
        target.write_text("outside", encoding="utf-8")
        path = self.root / "trusted-plans" / "job_12345678abcdef.json"
        path.symlink_to(target)
        with self.assertRaises(EngineReceiverAuthorityError) as caught:
            self.authority.register_trusted_plan(job_id="job_12345678abcdef", canonical_plan_bytes=plan_bytes())
        self.assertEqual(caught.exception.category, "receiver_authority_state_invalid")
        self.assertEqual(target.read_text(encoding="utf-8"), "outside")

    def test_root_symlink_is_rejected(self):
        actual = Path(self.temp.name) / "actual"
        actual.mkdir()
        linked = Path(self.temp.name) / "linked"
        linked.symlink_to(actual, target_is_directory=True)
        with self.assertRaises(EngineReceiverAuthorityError):
            EngineReceiverAuthority(root=linked, integrity_key=self.key)

    def test_replay_reservation_is_atomic_and_restart_safe(self):
        replay_key = hashlib.sha256(b"request-1").hexdigest()
        result = self.authority.reserve_replay(
            replay_key=replay_key,
            credential_generation_id="gen-1",
            request_timestamp=1000,
            replay_expires_at=1100,
        )
        self.assertFalse(result.retry_allowed)
        restarted = EngineReceiverAuthority(root=self.root, integrity_key=self.key)
        with self.assertRaises(EngineReceiverAuthorityError) as caught:
            restarted.reserve_replay(
                replay_key=replay_key,
                credential_generation_id="gen-1",
                request_timestamp=1000,
                replay_expires_at=1100,
            )
        self.assertEqual(caught.exception.category, "receiver_authority_replay_detected")

    def test_concurrent_exact_plan_registration_is_create_once(self):
        raw = plan_bytes()
        outcomes = []
        lock = threading.Lock()

        def attempt():
            try:
                result = self.authority.register_trusted_plan(
                    job_id="job_12345678abcdef", canonical_plan_bytes=raw
                )
                value = result.persistence_state
            except EngineReceiverAuthorityError as exc:
                value = exc.category
            with lock:
                outcomes.append(value)

        threads = [threading.Thread(target=attempt) for _ in range(12)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(outcomes.count("written"), 1)
        self.assertEqual(outcomes.count("replay"), 11)
        self.assertEqual(
            self.authority.load_trusted_plan(job_id="job_12345678abcdef").canonical_plan_bytes, raw
        )

    def test_replay_state_tamper_is_fail_closed_after_restart(self):
        replay_key = hashlib.sha256(b"tamper-request").hexdigest()
        self.authority.reserve_replay(
            replay_key=replay_key,
            credential_generation_id="gen-1",
            request_timestamp=3000,
            replay_expires_at=3100,
        )
        path = self.root / "replay-reservations" / f"{replay_key}.json"
        os.chmod(path, 0o600)
        data = bytearray(path.read_bytes())
        data[-10] ^= 1
        path.write_bytes(bytes(data))
        restarted = EngineReceiverAuthority(root=self.root, integrity_key=self.key)
        with self.assertRaises(EngineReceiverAuthorityError) as caught:
            restarted.reserve_replay(
                replay_key=replay_key,
                credential_generation_id="gen-1",
                request_timestamp=3000,
                replay_expires_at=3100,
            )
        self.assertEqual(caught.exception.category, "receiver_authority_state_invalid")

    def test_symlink_replay_path_is_never_followed(self):
        replay_key = hashlib.sha256(b"symlink-request").hexdigest()
        target = Path(self.temp.name) / "outside-replay.json"
        target.write_text("outside", encoding="utf-8")
        path = self.root / "replay-reservations" / f"{replay_key}.json"
        path.symlink_to(target)
        with self.assertRaises(EngineReceiverAuthorityError) as caught:
            self.authority.reserve_replay(
                replay_key=replay_key,
                credential_generation_id="gen-1",
                request_timestamp=4000,
                replay_expires_at=4100,
            )
        self.assertEqual(caught.exception.category, "receiver_authority_state_invalid")
        self.assertEqual(target.read_text(encoding="utf-8"), "outside")

    def test_oversized_plan_is_rejected_before_state_creation(self):
        raw = plan_bytes() + b" " * (65536 + 1)
        with self.assertRaises(EngineReceiverAuthorityError):
            self.authority.register_trusted_plan(
                job_id="job_12345678abcdef", canonical_plan_bytes=raw
            )
        self.assertFalse((self.root / "trusted-plans" / "job_12345678abcdef.json").exists())

    def test_concurrent_replay_reservation_accepts_exactly_one(self):
        replay_key = hashlib.sha256(b"concurrent-request").hexdigest()
        outcomes = []
        lock = threading.Lock()

        def attempt():
            try:
                self.authority.reserve_replay(
                    replay_key=replay_key,
                    credential_generation_id="gen-1",
                    request_timestamp=2000,
                    replay_expires_at=2100,
                )
                value = "accepted"
            except EngineReceiverAuthorityError as exc:
                value = exc.category
            with lock:
                outcomes.append(value)

        threads = [threading.Thread(target=attempt) for _ in range(12)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(outcomes.count("accepted"), 1)
        self.assertEqual(outcomes.count("receiver_authority_replay_detected"), 11)

    def test_gateway_orchestration_builder_is_byte_compatible(self):
        gateway_src = SERVICE_ROOT.parent / "omr-gateway" / "src"
        if not gateway_src.exists():
            self.skipTest("repository gateway source not present in isolated local test")
        sys.path.insert(0, str(gateway_src))
        try:
            from scoremosaic_gateway.orchestration import build_orchestration_plan

            gateway = build_orchestration_plan(
                "job_12345678abcdef",
                source_artifact_ref="sources/input.png",
                source_sha256="c" * 64,
                source_size_bytes=123,
                source_media_type="image/png",
            )
            gateway_bytes = canonical(gateway.as_dict())
            self.assertEqual(gateway_bytes, plan_bytes())
            stored = self.authority.register_trusted_plan(
                job_id="job_12345678abcdef", canonical_plan_bytes=gateway_bytes
            )
            self.assertEqual(stored.canonical_plan_bytes, gateway_bytes)
        finally:
            sys.path.remove(str(gateway_src))

    def test_path_traversal_and_replay_bounds_are_rejected(self):
        with self.assertRaises(EngineReceiverAuthorityError):
            self.authority.load_trusted_plan(job_id="../escape")
        with self.assertRaises(EngineReceiverAuthorityError):
            self.authority.reserve_replay(
                replay_key="../escape",
                credential_generation_id="gen-1",
                request_timestamp=0,
                replay_expires_at=1,
            )
        with self.assertRaises(EngineReceiverAuthorityError):
            self.authority.reserve_replay(
                replay_key="f" * 64,
                credential_generation_id="gen-1",
                request_timestamp=0,
                replay_expires_at=999999,
            )


if __name__ == "__main__":
    unittest.main()
