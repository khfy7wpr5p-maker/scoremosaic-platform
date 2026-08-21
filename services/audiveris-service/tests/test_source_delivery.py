from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import secrets
import sys
import tempfile
import threading
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SERVICE_ROOT.parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "services" / "omr-gateway" / "src"))

from scoremosaic_gateway.config import EngineEndpoint
from scoremosaic_gateway.dispatch_identity import build_dispatch_identity
from scoremosaic_gateway.dispatch_input_capsule import build_dispatch_input_capsule
from scoremosaic_gateway.dispatch_target import APPROVED_ENGINE_ORIGINS
from scoremosaic_gateway.orchestration import build_orchestration_plan
from scoremosaic_gateway.source_delivery import (
    build_source_delivery_binding,
    build_source_delivery_request,
    resolve_source_delivery_credential,
)

if SERVICE_ROOT.name == "audiveris-service":
    from scoremosaic_audiveris.receiver_authority import EngineReceiverAuthority
    from scoremosaic_audiveris.source_delivery import (
        EngineSourceStore,
        SourceDeliveryReceiverError,
        SourceDeliveryRotation,
        accept_source_delivery,
        source_delivery_credential_key,
    )
    ENGINE = "audiveris"
elif SERVICE_ROOT.name == "homr-service":
    from scoremosaic_homr.receiver_authority import EngineReceiverAuthority
    from scoremosaic_homr.source_delivery import (
        EngineSourceStore,
        SourceDeliveryReceiverError,
        SourceDeliveryRotation,
        accept_source_delivery,
        source_delivery_credential_key,
    )
    ENGINE = "homr"
elif SERVICE_ROOT.name == "clarity-service":
    from scoremosaic_clarity.receiver_authority import EngineReceiverAuthority
    from scoremosaic_clarity.source_delivery import (
        EngineSourceStore,
        SourceDeliveryReceiverError,
        SourceDeliveryRotation,
        accept_source_delivery,
        source_delivery_credential_key,
    )
    ENGINE = "clarity"
else:
    raise RuntimeError("unexpected engine service root")


class EngineSourceDeliveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = 1_800_600_000
        self.source = b"%PDF-1.4\n" + b"stage5a-engine-source" * 128
        self.plan = build_orchestration_plan(
            "job_stage5aengine01",
            source_artifact_ref="sources/job_stage5aengine01/source.pdf",
            source_sha256=sha256(self.source).hexdigest(),
            source_size_bytes=len(self.source),
            source_media_type="application/pdf",
        ).as_dict()
        self.identity = build_dispatch_identity(self.plan, ENGINE)
        self.capsule = build_dispatch_input_capsule(
            self.plan,
            self.identity,
            [self.source],
        )
        self.authority = EngineReceiverAuthority(
            root=Path(self.temp.name) / "authority",
            integrity_key=secrets.token_bytes(32),
        )
        registered = self.authority.register_trusted_plan(
            job_id=self.identity.job_id,
            canonical_plan_bytes=self.capsule.canonical_plan_bytes,
        )
        self.assertEqual(registered.persistence_state, "written")
        self.store = EngineSourceStore(
            root=Path(self.temp.name) / "source-store",
            integrity_key=secrets.token_bytes(32),
        )
        self.secret = secrets.token_bytes(32)
        self.generation = "gen-stage5a-engine"
        endpoint = EngineEndpoint(
            ENGINE,
            APPROVED_ENGINE_ORIGINS["staging"][ENGINE],
        )
        binding = build_source_delivery_binding(endpoint)
        credential = resolve_source_delivery_credential(
            binding,
            generation_id=self.generation,
            resolver=lambda key, generation: (
                self.secret
                if key == binding.credential_key and generation == self.generation
                else None
            ),
        )
        self.request = build_source_delivery_request(
            capsule=self.capsule,
            credential=credential,
            timestamp=self.now,
            nonce="44" * 16,
        )
        self.rotation = SourceDeliveryRotation(
            current_generation_id=self.generation,
            current_activated_at=self.now - 1,
        )

    def resolver(self, key: str, generation: str):
        if key == source_delivery_credential_key() and generation == self.generation:
            return self.secret
        return None

    def accept(self, *, headers=None, body=None, now=None, resolver=None):
        return accept_source_delivery(
            authority=self.authority,
            store=self.store,
            rotation=self.rotation,
            headers=self.request.headers if headers is None else headers,
            body=self.request.body if body is None else body,
            now_seconds=self.now if now is None else now,
            credential_resolver=self.resolver if resolver is None else resolver,
        )

    def test_accepts_exact_source_create_once_and_replay_is_non_executable(self) -> None:
        first = self.accept()
        second = self.accept()
        self.assertEqual(first.persistence_state, "written")
        self.assertEqual(second.persistence_state, "replay")
        self.assertTrue(first.authenticated)
        self.assertTrue(first.trusted_plan_converged)
        self.assertTrue(first.source_persisted)
        self.assertFalse(first.engine_execution_allowed)
        self.assertFalse(first.retry_allowed)
        loaded = self.store.load(job_id=self.identity.job_id, run_id=self.identity.run_id)
        self.assertEqual(loaded.source_bytes, self.source)
        self.assertEqual(loaded.source_sha256, sha256(self.source).hexdigest())
        self.assertFalse(loaded.engine_execution_allowed)

    def test_semantic_plan_mismatch_fails_before_credential_resolution(self) -> None:
        observed = []

        def resolver(key: str, generation: str):
            observed.append((key, generation))
            return self.secret

        headers = list(self.request.headers)
        headers[3] = (headers[3][0], "job_stage5aother01")
        with self.assertRaises(SourceDeliveryReceiverError) as context:
            self.accept(headers=tuple(headers), resolver=resolver)
        self.assertIn(
            context.exception.category,
            {"source_delivery_plan_invalid", "source_delivery_plan_mismatch"},
        )
        self.assertEqual(observed, [])

    def test_tampered_signature_body_and_metadata_fail_closed(self) -> None:
        headers = list(self.request.headers)
        headers[-1] = (headers[-1][0], "0" * 64)
        with self.assertRaises(SourceDeliveryReceiverError) as context:
            self.accept(headers=tuple(headers))
        self.assertEqual(context.exception.category, "source_delivery_signature_invalid")

        tampered = bytearray(self.request.body)
        tampered[-1] ^= 1
        with self.assertRaises(SourceDeliveryReceiverError) as context:
            self.accept(body=bytes(tampered))
        self.assertEqual(context.exception.category, "source_delivery_body_invalid")

        headers = list(self.request.headers)
        headers[8] = (headers[8][0], "f" * 64)
        with self.assertRaises(SourceDeliveryReceiverError):
            self.accept(headers=tuple(headers))

    def test_duplicate_missing_and_unexpected_headers_fail_closed(self) -> None:
        with self.assertRaises(SourceDeliveryReceiverError):
            self.accept(headers=self.request.headers + (self.request.headers[0],))
        with self.assertRaises(SourceDeliveryReceiverError):
            self.accept(headers=self.request.headers[:-1])
        with self.assertRaises(SourceDeliveryReceiverError):
            self.accept(headers=self.request.headers + (("x-scoremosaic-extra", "x"),))

    def test_stale_request_and_unknown_generation_fail_closed(self) -> None:
        with self.assertRaises(SourceDeliveryReceiverError) as context:
            self.accept(now=self.now + 61)
        self.assertEqual(context.exception.category, "source_delivery_timestamp_invalid")

        bad_rotation = SourceDeliveryRotation(
            current_generation_id="different-generation",
            current_activated_at=self.now - 1,
        )
        with self.assertRaises(SourceDeliveryReceiverError) as context:
            accept_source_delivery(
                authority=self.authority,
                store=self.store,
                rotation=bad_rotation,
                headers=self.request.headers,
                body=self.request.body,
                now_seconds=self.now,
                credential_resolver=self.resolver,
            )
        self.assertEqual(context.exception.category, "source_delivery_generation_invalid")

    def test_previous_generation_is_bounded_by_grace(self) -> None:
        rotation = SourceDeliveryRotation(
            current_generation_id="gen-new",
            current_activated_at=self.now - 10,
            previous_generation_id=self.generation,
            previous_valid_until=self.now + 10,
        )
        accepted = accept_source_delivery(
            authority=self.authority,
            store=self.store,
            rotation=rotation,
            headers=self.request.headers,
            body=self.request.body,
            now_seconds=self.now,
            credential_resolver=self.resolver,
        )
        self.assertEqual(accepted.persistence_state, "written")
        with self.assertRaises(SourceDeliveryReceiverError):
            accept_source_delivery(
                authority=self.authority,
                store=EngineSourceStore(
                    root=Path(self.temp.name) / "source-store-expired",
                    integrity_key=secrets.token_bytes(32),
                ),
                rotation=rotation,
                headers=self.request.headers,
                body=self.request.body,
                now_seconds=self.now + 11,
                credential_resolver=self.resolver,
            )

    def test_concurrent_exact_source_has_one_written_winner(self) -> None:
        barrier = threading.Barrier(8)
        states: list[str] = []
        errors: list[str] = []
        lock = threading.Lock()

        def worker() -> None:
            try:
                barrier.wait()
                result = self.accept()
                with lock:
                    states.append(result.persistence_state)
            except Exception as exc:
                with lock:
                    errors.append(getattr(exc, "category", type(exc).__name__))

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(10)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(errors, [])
        self.assertEqual(states.count("written"), 1)
        self.assertEqual(states.count("replay"), 7)

    def test_store_detects_symlink_and_content_conflict(self) -> None:
        first = self.accept()
        self.assertEqual(first.persistence_state, "written")
        target = self.store._job_dir(self.identity.job_id, self.identity.run_id)
        source_path = target / "source.bin"
        source_path.unlink()
        source_path.symlink_to("/etc/passwd")
        with self.assertRaises(SourceDeliveryReceiverError):
            self.store.load(job_id=self.identity.job_id, run_id=self.identity.run_id)

    def test_safe_evidence_does_not_expose_secret_nonce_or_source(self) -> None:
        accepted = self.accept()
        rendered = repr(accepted.as_safe_dict()) + repr(
            self.store.load(job_id=self.identity.job_id, run_id=self.identity.run_id)
        )
        self.assertNotIn(self.secret.hex(), rendered)
        self.assertNotIn("44" * 16, rendered)
        self.assertNotIn(self.source.decode("ascii"), rendered)


if __name__ == "__main__":
    unittest.main()
