from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

import test_safe_upload_finalization as helpers
from scoremosaic_gateway.authenticated_request import (
    MAX_FUTURE_SKEW_SECONDS,
    MAX_REQUEST_AGE_SECONDS,
)
from scoremosaic_gateway.config import EngineEndpoint
from scoremosaic_gateway.controlled_staging_dispatch_intent import (
    persist_controlled_staging_dispatch_intent,
    recover_controlled_staging_dispatch_intent,
)
from scoremosaic_gateway.controlled_staging_job_lifecycle import (
    run_controlled_staging_job_lifecycle,
)
from scoremosaic_gateway.controlled_staging_queued_transition import (
    queue_controlled_staging_run,
    recover_controlled_staging_queued_run,
)
from scoremosaic_gateway.controlled_staging_signing_preflight import (
    ControlledStagingSigningPreflightError,
    ControlledStagingSigningPreflightResult,
    build_controlled_staging_signing_preflight,
)
from scoremosaic_gateway.controlled_staging_terminal_cancellation import (
    cancel_controlled_staging_queued_run,
)
from scoremosaic_gateway.credential_rotation import (
    build_rotation_set,
    resolve_engine_credential_generation,
)
from scoremosaic_gateway.dispatch_target import APPROVED_ENGINE_ORIGINS
from scoremosaic_gateway.minimum_staging_vertical_slice import (
    StagingUploadProvider,
    run_minimum_staging_vertical_slice,
)
from scoremosaic_gateway.service_auth import (
    MIN_CREDENTIAL_BYTES,
    build_engine_auth_binding,
)


class ControlledStagingSigningPreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = helpers.SafeUploadFinalizationContractTests(methodName="runTest")
        self.fixture.setUp()
        self.admission = self.fixture._admission()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.provider = StagingUploadProvider(
            self.root,
            state_integrity_key=b"S" * 32,
        )
        self.minimum_slice = run_minimum_staging_vertical_slice(
            admission=self.admission,
            session_policy=self.fixture.session_policy,
            payload=helpers.PNG_1X1,
            original_filename="scan.png",
            declared_media_type="image/png",
            observed_at_epoch_s=self.admission.evaluated_at_epoch_s,
            provider=self.provider,
        )
        run_controlled_staging_job_lifecycle(
            minimum_slice=self.minimum_slice,
            provider=self.provider,
        )
        self.endpoint = EngineEndpoint(
            "audiveris",
            APPROVED_ENGINE_ORIGINS["staging"]["audiveris"],
        )
        self.queued = queue_controlled_staging_run(
            minimum_slice=self.minimum_slice,
            provider=self.provider,
            engine="audiveris",
        )
        self.intent = persist_controlled_staging_dispatch_intent(
            minimum_slice=self.minimum_slice,
            provider=self.provider,
            endpoint=self.endpoint,
        )
        self.timestamp = 1_800_000_000
        self.now_seconds = self.timestamp
        self.nonce = "0123456789abcdef0123456789abcdef"
        self.secret = b"K" * MIN_CREDENTIAL_BYTES
        self.generation_id = "gen-2026-08-current"
        self.resolver_calls: list[tuple[str, str]] = []
        self.rotation = self._rotation(
            endpoint=self.endpoint,
            generation_id=self.generation_id,
            secret=self.secret,
        )
        self.resolver_calls_after_construction = len(self.resolver_calls)

    def _rotation(
        self,
        *,
        endpoint: EngineEndpoint,
        generation_id: str,
        secret: bytes,
    ):
        binding = build_engine_auth_binding(endpoint, "staging")

        def resolver(credential_key: str, observed_generation_id: str):
            self.resolver_calls.append((credential_key, observed_generation_id))
            self.assertEqual(credential_key, binding.credential_key)
            self.assertEqual(observed_generation_id, generation_id)
            return secret

        credential = resolve_engine_credential_generation(
            binding,
            generation_id,
            resolver,
        )
        return build_rotation_set(
            current=credential,
            previous=None,
            rotation_started_at=self.timestamp - 1,
            previous_valid_until=None,
        )

    def _preflight(self, **overrides):
        values = {
            "minimum_slice": self.minimum_slice,
            "provider": self.provider,
            "endpoint": self.endpoint,
            "rotation": self.rotation,
            "timestamp": self.timestamp,
            "nonce": self.nonce,
            "now_seconds": self.now_seconds,
        }
        values.update(overrides)
        return build_controlled_staging_signing_preflight(**values)

    def _snapshot(self):
        snapshot: dict[str, tuple[object, ...]] = {}
        for path in sorted(self.root.rglob("*")):
            relative = path.relative_to(self.root).as_posix()
            if path.is_symlink():
                snapshot[relative] = ("symlink", os.readlink(path))
            elif path.is_file():
                snapshot[relative] = ("file", path.read_bytes())
            elif path.is_dir():
                snapshot[relative] = ("dir",)
        return snapshot

    def _intent_path(self) -> Path:
        return (
            self.root
            / "state"
            / "dispatch_intents"
            / self.intent.job_id
            / f"{self.intent.run_id}.json"
        )

    def test_signs_exact_persisted_intent_without_export_or_state_mutation(self) -> None:
        before = self._snapshot()
        result = self._preflight()
        after = self._snapshot()

        self.assertEqual(after, before)
        self.assertEqual(
            len(self.resolver_calls),
            self.resolver_calls_after_construction,
        )
        self.assertEqual(result.job_id, self.intent.job_id)
        self.assertEqual(result.source_artifact_id, self.intent.source_artifact_id)
        self.assertEqual(result.engine, self.intent.engine)
        self.assertEqual(result.run_id, self.intent.run_id)
        self.assertEqual(
            result.dispatch_identity_sha256,
            self.intent.dispatch_identity_sha256,
        )
        self.assertEqual(result.credential_generation_id, self.generation_id)
        self.assertEqual(result.request_timestamp, self.timestamp)
        self.assertEqual(result.payload_bytes, self.intent.identity_payload_bytes)
        self.assertEqual(result.payload_sha256, self.intent.identity_payload_sha256)
        self.assertEqual(result.target_origin, self.intent.target_origin)
        self.assertEqual(result.target_method, self.intent.target_method)
        self.assertEqual(result.target_path, self.intent.target_path)
        self.assertEqual(result.state, "queued")
        self.assertEqual(result.revision, 1)
        self.assertTrue(result.signing_performed)

        for attribute in (
            "credential_resolution_allowed",
            "nonce_allocation_allowed",
            "timestamp_allocation_allowed",
            "signed_request_export_allowed",
            "signature_export_allowed",
            "persistence_allowed",
            "job_state_mutation_allowed",
            "queue_runtime_allowed",
            "worker_allowed",
            "network_dispatch_allowed",
            "dispatch_attempt_allowed",
            "orchestration_allowed",
            "engine_execution_allowed",
            "retry_allowed",
        ):
            self.assertIs(getattr(result, attribute), False)

        self.assertFalse(hasattr(result, "signature"))
        self.assertFalse(hasattr(result, "generation_signature"))
        self.assertFalse(hasattr(result, "credential_key"))
        self.assertFalse(hasattr(result, "nonce"))
        safe = result.as_safe_dict()
        self.assertNotIn("credentialKey", safe)
        self.assertNotIn("nonce", safe)
        self.assertNotIn(self.nonce, repr(safe))
        self.assertNotIn(self.secret.decode("ascii"), repr(safe))
        self.assertFalse(safe["signedRequestExportAllowed"])
        self.assertFalse(safe["signatureExportAllowed"])
        self.assertFalse(safe["networkDispatchAllowed"])

        queued = recover_controlled_staging_queued_run(
            minimum_slice=self.minimum_slice,
            provider=self.provider,
            engine="audiveris",
        )
        recovered_intent = recover_controlled_staging_dispatch_intent(
            minimum_slice=self.minimum_slice,
            provider=self.provider,
            endpoint=self.endpoint,
        )
        self.assertEqual((queued.state, queued.revision), ("queued", 1))
        self.assertEqual(recovered_intent.intent_sha256, self.intent.intent_sha256)

    def test_same_inputs_are_deterministic_ten_of_ten_and_read_only(self) -> None:
        before = self._snapshot()
        first = self._preflight()
        for attempt in range(10):
            with self.subTest(attempt=attempt + 1):
                observed = self._preflight()
                self.assertEqual(observed, first)
                self.assertEqual(self._snapshot(), before)
        self.assertEqual(
            len(self.resolver_calls),
            self.resolver_calls_after_construction,
        )

    def test_terminal_cancellation_blocks_before_credential_selection(self) -> None:
        cancel_controlled_staging_queued_run(
            minimum_slice=self.minimum_slice,
            provider=self.provider,
            engine="audiveris",
        )
        with patch(
            "scoremosaic_gateway.controlled_staging_signing_preflight.select_signing_credential",
            side_effect=AssertionError("credential touched"),
        ):
            with self.assertRaises(ControlledStagingSigningPreflightError) as raised:
                self._preflight()
        self.assertEqual(
            raised.exception.category,
            "staging_signing_preflight_superseded",
        )

    def test_missing_or_tampered_intent_blocks_before_credential_selection(self) -> None:
        path = self._intent_path()
        path.chmod(0o600)
        original = path.read_bytes()
        path.unlink()
        with patch(
            "scoremosaic_gateway.controlled_staging_signing_preflight.select_signing_credential",
            side_effect=AssertionError("credential touched"),
        ):
            with self.assertRaises(ControlledStagingSigningPreflightError) as raised:
                self._preflight()
        self.assertEqual(
            raised.exception.category,
            "staging_signing_preflight_intent_missing",
        )

        path.write_bytes(original)
        stored = json.loads(path.read_text(encoding="utf-8"))
        stored["dispatch_intent_integrity_mac"] = "0" * 64
        path.write_text(
            json.dumps(
                stored,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        with patch(
            "scoremosaic_gateway.controlled_staging_signing_preflight.select_signing_credential",
            side_effect=AssertionError("credential touched"),
        ):
            with self.assertRaises(ControlledStagingSigningPreflightError) as raised:
                self._preflight()
        self.assertEqual(
            raised.exception.category,
            "staging_signing_preflight_intent_invalid",
        )

    def test_modified_source_blocks_before_credential_selection(self) -> None:
        source_path = self.root / "objects" / self.minimum_slice.binding.source_storage_key
        source_path.chmod(0o600)
        source_path.write_bytes(b"X" * self.minimum_slice.binding.source_size_bytes)
        with patch(
            "scoremosaic_gateway.controlled_staging_signing_preflight.select_signing_credential",
            side_effect=AssertionError("credential touched"),
        ):
            with self.assertRaises(ControlledStagingSigningPreflightError) as raised:
                self._preflight()
        self.assertEqual(
            raised.exception.category,
            "staging_signing_preflight_source_invalid",
        )

    def test_wrong_target_and_cross_engine_rotation_fail_closed(self) -> None:
        wrong_endpoint = EngineEndpoint("audiveris", "http://attacker.invalid:9999")
        with patch(
            "scoremosaic_gateway.controlled_staging_signing_preflight.select_signing_credential",
            side_effect=AssertionError("credential touched"),
        ):
            with self.assertRaises(ControlledStagingSigningPreflightError) as raised:
                self._preflight(endpoint=wrong_endpoint)
        self.assertEqual(
            raised.exception.category,
            "staging_signing_preflight_intent_invalid",
        )

        homr_endpoint = EngineEndpoint(
            "homr",
            APPROVED_ENGINE_ORIGINS["staging"]["homr"],
        )
        homr_rotation = self._rotation(
            endpoint=homr_endpoint,
            generation_id="gen-2026-08-homr",
            secret=b"H" * MIN_CREDENTIAL_BYTES,
        )
        before = self._snapshot()
        with self.assertRaises(ControlledStagingSigningPreflightError) as raised:
            self._preflight(rotation=homr_rotation)
        self.assertEqual(
            raised.exception.category,
            "staging_signing_preflight_credential_binding_mismatch",
        )
        self.assertEqual(self._snapshot(), before)

    def test_timestamp_and_nonce_are_caller_supplied_and_fresh(self) -> None:
        cases = (
            (
                {
                    "timestamp": self.now_seconds + MAX_FUTURE_SKEW_SECONDS + 1,
                },
                "staging_signing_preflight_timestamp_in_future",
            ),
            (
                {
                    "timestamp": self.now_seconds - MAX_REQUEST_AGE_SECONDS - 1,
                },
                "staging_signing_preflight_timestamp_expired",
            ),
            (
                {"nonce": "ABCDEF0123456789ABCDEF0123456789"},
                "staging_signing_preflight_nonce_invalid",
            ),
            (
                {"nonce": "0" * 31},
                "staging_signing_preflight_nonce_invalid",
            ),
        )
        for overrides, category in cases:
            with self.subTest(category=category):
                before = self._snapshot()
                with self.assertRaises(ControlledStagingSigningPreflightError) as raised:
                    self._preflight(**overrides)
                self.assertEqual(raised.exception.category, category)
                self.assertEqual(self._snapshot(), before)
        self.assertEqual(
            len(self.resolver_calls),
            self.resolver_calls_after_construction,
        )

    def test_result_type_subclasses_fail_closed(self) -> None:
        result = self._preflight()

        class State(str):
            pass

        class RunId(str):
            pass

        class Timestamp(int):
            pass

        base = asdict(result)
        for field, invalid in (
            ("state", State("queued")),
            ("run_id", RunId(result.run_id)),
            ("request_timestamp", Timestamp(result.request_timestamp)),
        ):
            with self.subTest(field=field):
                kwargs = dict(base)
                kwargs[field] = invalid
                with self.assertRaises(ControlledStagingSigningPreflightError) as raised:
                    ControlledStagingSigningPreflightResult(**kwargs)
                self.assertEqual(
                    raised.exception.category,
                    "staging_signing_preflight_result_invalid",
                )


if __name__ == "__main__":
    unittest.main()
