from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_gateway.authenticated_request import MAX_REQUEST_AGE_SECONDS
from scoremosaic_gateway.config import EngineEndpoint
from scoremosaic_gateway.controlled_staging_replay_reservation import (
    ControlledStagingReplayReservationError,
    ControlledStagingReplayReservationResult,
    REPLAY_RETENTION_MODE,
    build_controlled_staging_generation_replay_checker,
    reserve_controlled_staging_generation_replay,
)
from scoremosaic_gateway.credential_rotation import (
    MAX_REPLAY_RESERVATION_SECONDS,
    build_rotation_set,
    resolve_engine_credential_generation,
    sign_rotation_authenticated_request,
)
from scoremosaic_gateway.dispatch_identity import (
    build_dispatch_identity,
    dispatch_identity_payload,
)
from scoremosaic_gateway.dispatch_target import build_engine_dispatch_target
from scoremosaic_gateway.minimum_staging_vertical_slice import StagingUploadProvider
from scoremosaic_gateway.orchestration import build_orchestration_plan
from scoremosaic_gateway.receiver_verification import (
    ReceiverVerificationError,
    verify_receiver_dispatch_request,
)
from scoremosaic_gateway.service_auth import (
    MIN_CREDENTIAL_BYTES,
    build_engine_auth_binding,
)


class ControlledStagingReplayReservationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.provider = StagingUploadProvider(
            self.root,
            state_integrity_key=b"P" * 32,
        )
        self.endpoint = EngineEndpoint("homr", "http://homr-foundation:8080")
        self.binding = build_engine_auth_binding(self.endpoint, "staging")
        self.generation = "gen-2026-08-replay"
        self.nonce = "abcdef0123456789abcdef0123456789"
        self.timestamp = 1_800_200_000

    def reserve(self, **overrides):
        values = {
            "provider": self.provider,
            "binding": self.binding,
            "generation_id": self.generation,
            "nonce": self.nonce,
            "request_timestamp": self.timestamp,
        }
        values.update(overrides)
        return reserve_controlled_staging_generation_replay(**values)

    def reservation_path(self, key: str) -> Path:
        return (
            self.root
            / "state"
            / "replay_reservations"
            / key[:2]
            / f"{key}.json"
        )

    def replay_files(self):
        base = self.root / "state" / "replay_reservations"
        if not base.exists():
            return []
        return sorted(base.rglob("*.json"))

    def test_first_reservation_is_create_once_and_persists_no_raw_replay_inputs(self) -> None:
        result = self.reserve()
        self.assertTrue(result.accepted)
        self.assertFalse(result.replay_detected)
        self.assertEqual(result.persistence_state, "written")
        self.assertEqual(result.retention_mode, REPLAY_RETENTION_MODE)
        self.assertEqual(
            result.expires_at,
            self.timestamp + MAX_REPLAY_RESERVATION_SECONDS,
        )

        path = self.reservation_path(result.reservation_key)
        self.assertTrue(path.is_file())
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        self.assertNotIn(self.nonce, text)
        self.assertNotIn(self.generation, text)
        self.assertNotIn(self.binding.credential_key, text)
        self.assertIn(result.reservation_key, text)
        stored = json.loads(text)
        self.assertIn("replay_reservation_integrity_mac", stored)
        self.assertEqual(stored["retention_mode"], REPLAY_RETENTION_MODE)
        self.assertFalse(stored["boundaries"]["automaticCleanupAllowed"])
        self.assertFalse(stored["boundaries"]["nonceReuseAllowed"])

        safe = result.as_safe_dict()
        self.assertFalse(safe["automaticCleanupAllowed"])
        self.assertFalse(safe["nonceReuseAllowed"])
        self.assertFalse(safe["networkDispatchAllowed"])
        self.assertFalse(safe["engineExecutionAllowed"])

    def test_duplicate_is_permanent_replay_tombstone_and_bytes_never_change(self) -> None:
        first = self.reserve()
        path = self.reservation_path(first.reservation_key)
        original = path.read_bytes()

        for attempt in range(10):
            with self.subTest(attempt=attempt + 1):
                replay = self.reserve()
                self.assertFalse(replay.accepted)
                self.assertTrue(replay.replay_detected)
                self.assertEqual(replay.persistence_state, "existing")
                self.assertEqual(replay.reservation_key, first.reservation_key)
                self.assertEqual(replay.expires_at, first.expires_at)
                self.assertEqual(path.read_bytes(), original)

    def test_atomic_concurrency_has_exactly_one_winner(self) -> None:
        def attempt(_):
            return self.reserve()

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(attempt, range(16)))

        accepted = [result for result in results if result.accepted]
        replays = [result for result in results if result.replay_detected]
        self.assertEqual(len(accepted), 1)
        self.assertEqual(len(replays), 15)
        self.assertEqual(
            {result.reservation_key for result in results},
            {accepted[0].reservation_key},
        )
        self.assertEqual(len(self.replay_files()), 1)

    def test_generation_scope_produces_distinct_create_once_keys(self) -> None:
        first = self.reserve()
        second = self.reserve(generation_id="gen-2026-08-replay-next")
        self.assertTrue(first.accepted)
        self.assertTrue(second.accepted)
        self.assertNotEqual(first.reservation_key, second.reservation_key)
        self.assertEqual(len(self.replay_files()), 2)

    def test_invalid_timestamp_and_environment_fail_before_persistence(self) -> None:
        with self.assertRaises(ControlledStagingReplayReservationError) as raised:
            self.reserve(request_timestamp=-1)
        self.assertEqual(
            raised.exception.category,
            "staging_replay_timestamp_invalid",
        )
        self.assertEqual(self.replay_files(), [])

        test_binding = build_engine_auth_binding(self.endpoint, "test")
        with self.assertRaises(ControlledStagingReplayReservationError) as raised:
            self.reserve(binding=test_binding)
        self.assertEqual(raised.exception.category, "staging_replay_binding_invalid")
        self.assertEqual(self.replay_files(), [])

    def test_tamper_and_symlink_fail_closed_instead_of_becoming_replay(self) -> None:
        first = self.reserve()
        path = self.reservation_path(first.reservation_key)
        stored = json.loads(path.read_text(encoding="utf-8"))
        stored["replay_reservation_integrity_mac"] = "0" * 64
        path.chmod(0o600)
        path.write_text(
            json.dumps(
                stored,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        with self.assertRaises(ControlledStagingReplayReservationError) as raised:
            self.reserve()
        self.assertEqual(raised.exception.category, "staging_replay_state_invalid")

        path.unlink()
        outside = self.root / "outside-replay.json"
        outside.write_text("{}", encoding="utf-8")
        os.symlink(outside, path)
        with self.assertRaises(ControlledStagingReplayReservationError) as raised:
            self.reserve()
        self.assertEqual(raised.exception.category, "staging_replay_state_invalid")

    def _signed_receiver_fixture(self, *, job_id: str, source_sha: str):
        secret = b"V" * MIN_CREDENTIAL_BYTES
        generation_credential = resolve_engine_credential_generation(
            self.binding,
            self.generation,
            lambda credential_key, generation_id: (
                secret
                if credential_key == self.binding.credential_key
                and generation_id == self.generation
                else None
            ),
        )
        rotation = build_rotation_set(
            current=generation_credential,
            previous=None,
            rotation_started_at=self.timestamp,
            previous_valid_until=None,
        )
        plan = build_orchestration_plan(
            job_id,
            source_artifact_ref=f"sources/{job_id}/source.pdf",
            source_sha256=source_sha,
            source_size_bytes=4096,
            source_media_type="application/pdf",
        ).as_dict()
        target = build_engine_dispatch_target(self.binding, self.endpoint)
        identity = build_dispatch_identity(plan, "homr")
        payload = dispatch_identity_payload(identity)
        request = sign_rotation_authenticated_request(
            rotation,
            method=target.method,
            path=target.path,
            timestamp=self.timestamp,
            nonce=self.nonce,
            payload=payload,
            now_seconds=self.timestamp,
        )
        checker = build_controlled_staging_generation_replay_checker(
            provider=self.provider,
        )
        return rotation, plan, target, identity, payload, request, checker

    def test_receiver_accepts_first_signed_request_and_rejects_exact_replay(self) -> None:
        rotation, plan, target, identity, payload, request, checker = (
            self._signed_receiver_fixture(
                job_id="job_c2edurablereplay01",
                source_sha="7" * 64,
            )
        )

        verified = verify_receiver_dispatch_request(
            plan,
            target,
            rotation,
            request,
            observed_method="POST",
            observed_path="/internal/transcribe",
            payload=payload,
            now_seconds=self.timestamp,
            replay_checker=checker,
        )
        self.assertEqual(verified.dispatch_identity, identity)
        self.assertEqual(len(self.replay_files()), 1)

        with self.assertRaises(ReceiverVerificationError) as raised:
            verify_receiver_dispatch_request(
                plan,
                target,
                rotation,
                request,
                observed_method="POST",
                observed_path="/internal/transcribe",
                payload=payload,
                now_seconds=self.timestamp,
                replay_checker=checker,
            )
        self.assertEqual(raised.exception.category, "replay_detected")
        self.assertEqual(len(self.replay_files()), 1)

    def test_invalid_or_expired_receiver_request_never_consumes_reservation(self) -> None:
        rotation, plan, target, identity, payload, request, checker = (
            self._signed_receiver_fixture(
                job_id="job_c2edurablereplay02",
                source_sha="8" * 64,
            )
        )
        tampered = replace(request, generation_signature="0" * 64)
        with self.assertRaises(ReceiverVerificationError) as raised:
            verify_receiver_dispatch_request(
                plan,
                target,
                rotation,
                tampered,
                observed_method="POST",
                observed_path="/internal/transcribe",
                payload=payload,
                now_seconds=self.timestamp,
                replay_checker=checker,
            )
        self.assertEqual(
            raised.exception.category,
            "generation_request_signature_invalid",
        )
        self.assertEqual(self.replay_files(), [])

        with self.assertRaises(ReceiverVerificationError) as raised:
            verify_receiver_dispatch_request(
                plan,
                target,
                rotation,
                request,
                observed_method="POST",
                observed_path="/internal/transcribe",
                payload=payload,
                now_seconds=self.timestamp + MAX_REQUEST_AGE_SECONDS + 1,
                replay_checker=checker,
            )
        self.assertEqual(raised.exception.category, "timestamp_expired")
        self.assertEqual(self.replay_files(), [])

    def test_result_type_subclasses_fail_closed(self) -> None:
        first = self.reserve()

        class Key(str):
            pass

        class Expires(int):
            pass

        class Accepted(int):
            pass

        base = {
            "reservation_key": first.reservation_key,
            "expires_at": first.expires_at,
            "accepted": True,
            "replay_detected": False,
            "persistence_state": "written",
            "retention_mode": REPLAY_RETENTION_MODE,
        }
        for field, invalid in (
            ("reservation_key", Key(first.reservation_key)),
            ("expires_at", Expires(first.expires_at)),
            ("accepted", Accepted(1)),
        ):
            with self.subTest(field=field):
                kwargs = dict(base)
                kwargs[field] = invalid
                with self.assertRaises(ControlledStagingReplayReservationError) as raised:
                    ControlledStagingReplayReservationResult(**kwargs)
                self.assertEqual(
                    raised.exception.category,
                    "staging_replay_result_invalid",
                )


if __name__ == "__main__":
    unittest.main()
