from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

import test_safe_upload_finalization as helpers
from scoremosaic_gateway.app import route_request
from scoremosaic_gateway.config import load_config
from scoremosaic_gateway.controlled_staging_job_lifecycle import (
    run_controlled_staging_job_lifecycle,
)
from scoremosaic_gateway.controlled_staging_queued_transition import (
    queue_controlled_staging_run,
)
from scoremosaic_gateway.controlled_staging_trusted_plan_store import (
    ControlledStagingTrustedPlanStoreError,
    ControlledStagingTrustedPlanStoreResult,
    ControlledStagingTrustedReceiverPlanResolver,
    _load_verified_record,
    _plan_path,
    _seal_record,
    persist_controlled_staging_trusted_receiver_plan,
)
from scoremosaic_gateway.dispatch_identity import (
    build_dispatch_identity,
    dispatch_identity_payload,
)
from scoremosaic_gateway.minimum_staging_vertical_slice import (
    StagingUploadProvider,
    run_minimum_staging_vertical_slice,
)
from scoremosaic_gateway.orchestration import ENGINE_NAMES, build_orchestration_plan
from scoremosaic_gateway.trusted_receiver_plan_lookup import (
    TrustedReceiverPlanLookupError,
    parse_receiver_plan_lookup_hint,
    resolve_trusted_receiver_plan,
)


class _StrSubclass(str):
    pass


class ControlledStagingTrustedPlanStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = helpers.SafeUploadFinalizationContractTests(methodName="runTest")
        self.fixture.setUp()
        self.admission = self.fixture._admission()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.key = b"T" * 32
        self.provider = StagingUploadProvider(
            self.root,
            state_integrity_key=self.key,
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
        self.binding = self.minimum_slice.binding
        self.plan = build_orchestration_plan(
            self.binding.job_id,
            source_artifact_ref=self.binding.source_artifact_ref,
            source_sha256=self.binding.document_sha256,
            source_size_bytes=self.binding.source_size_bytes,
            source_media_type=self.binding.source_media_type,
            requested_engines=ENGINE_NAMES,
        ).as_dict()
        self.engine = "homr"
        self.identity = build_dispatch_identity(self.plan, self.engine)
        self.payload = dispatch_identity_payload(self.identity)

    def _run_lifecycle(self) -> None:
        run_controlled_staging_job_lifecycle(
            minimum_slice=self.minimum_slice,
            provider=self.provider,
        )

    def _persist(self, *, provider=None):
        return persist_controlled_staging_trusted_receiver_plan(
            minimum_slice=self.minimum_slice,
            provider=self.provider if provider is None else provider,
        )

    def _path(self) -> Path:
        return _plan_path(self.provider, job_id=self.binding.job_id)

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

    def test_persists_exact_full_plan_create_once_without_runtime_authority(self) -> None:
        self._run_lifecycle()
        result = self._persist()
        self.assertEqual(result.persistence_state, "written")
        self.assertEqual(result.job_id, self.binding.job_id)
        self.assertEqual(result.source_artifact_id, self.binding.source_artifact_id)
        self.assertEqual(result.orchestration_plan_id, self.binding.orchestration_plan_id)
        self.assertEqual(
            result.orchestration_plan_sha256,
            self.binding.orchestration_plan_sha256,
        )
        record = _load_verified_record(self.provider, job_id=self.binding.job_id)
        self.assertEqual(record["plan"], self.plan)
        self.assertEqual(record["job_id"], self.binding.job_id)
        self.assertEqual(record["source_sha256"], self.binding.document_sha256)
        self.assertEqual(record["orchestration_plan_id"], self.plan["planId"])
        self.assertEqual(
            record["orchestration_plan_sha256"],
            self.plan["planSha256"],
        )
        for attribute in (
            "job_state_mutation_allowed",
            "credential_resolution_allowed",
            "replay_reservation_allowed",
            "queue_runtime_allowed",
            "worker_allowed",
            "network_dispatch_allowed",
            "orchestration_allowed",
            "engine_execution_allowed",
        ):
            self.assertIs(getattr(result, attribute), False)

    def test_exact_replay_is_byte_identical_ten_of_ten_across_provider_restart(self) -> None:
        self._run_lifecycle()
        first = self._persist()
        path = self._path()
        expected_bytes = path.read_bytes()
        for attempt in range(10):
            with self.subTest(attempt=attempt + 1):
                restarted = StagingUploadProvider(
                    self.root,
                    state_integrity_key=self.key,
                )
                observed = self._persist(provider=restarted)
                self.assertEqual(observed.persistence_state, "replay")
                self.assertEqual(observed.job_id, first.job_id)
                self.assertEqual(observed.canonical_plan_sha256, first.canonical_plan_sha256)
                self.assertEqual(path.read_bytes(), expected_bytes)

    def test_requires_exact_existing_lifecycle_before_plan_persistence(self) -> None:
        with self.assertRaises(ControlledStagingTrustedPlanStoreError) as context:
            self._persist()
        self.assertEqual(
            context.exception.category,
            "staging_trusted_plan_lifecycle_invalid",
        )
        self.assertFalse(self._path().exists())

    def test_existing_transition_supersedes_new_plan_persistence(self) -> None:
        self._run_lifecycle()
        queue_controlled_staging_run(
            minimum_slice=self.minimum_slice,
            provider=self.provider,
            engine="homr",
        )
        with self.assertRaises(ControlledStagingTrustedPlanStoreError) as context:
            self._persist()
        self.assertEqual(context.exception.category, "staging_trusted_plan_superseded")
        self.assertFalse(self._path().exists())

    def test_plan_persistence_before_queue_does_not_block_later_queue_transition(self) -> None:
        self._run_lifecycle()
        self._persist()
        queued = queue_controlled_staging_run(
            minimum_slice=self.minimum_slice,
            provider=self.provider,
            engine="homr",
        )
        self.assertEqual((queued.state, queued.revision), ("queued", 1))
        record = _load_verified_record(self.provider, job_id=self.binding.job_id)
        self.assertEqual(record["plan"], self.plan)

    def test_source_substitution_fails_before_plan_publication(self) -> None:
        self._run_lifecycle()
        source_path = self.provider._source_path(self.binding)
        source_path.chmod(0o600)
        source_path.write_bytes(b"tampered")
        with self.assertRaises(ControlledStagingTrustedPlanStoreError) as context:
            self._persist()
        self.assertEqual(context.exception.category, "staging_trusted_plan_lifecycle_invalid")
        self.assertFalse(self._path().exists())

    def test_hmac_tamper_fails_closed_on_replay_and_lookup(self) -> None:
        self._run_lifecycle()
        self._persist()
        path = self._path()
        sealed = json.loads(path.read_text("ascii"))
        sealed["orchestration_plan_sha256"] = "0" * 64
        path.chmod(0o600)
        path.write_text(json.dumps(sealed, sort_keys=True, separators=(",", ":")), "ascii")

        with self.assertRaises(ControlledStagingTrustedPlanStoreError):
            self._persist()
        resolver = ControlledStagingTrustedReceiverPlanResolver(self.provider)
        hint = parse_receiver_plan_lookup_hint(self.payload)
        with self.assertRaises(ControlledStagingTrustedPlanStoreError) as context:
            resolver(hint)
        self.assertEqual(
            context.exception.category,
            "staging_trusted_plan_lookup_unavailable",
        )

    def test_valid_mac_but_semantically_invalid_plan_still_fails_closed(self) -> None:
        self._run_lifecycle()
        self._persist()
        path = self._path()
        record = _load_verified_record(self.provider, job_id=self.binding.job_id)
        record["plan"]["boundaries"]["networkDispatchEnabled"] = True
        sealed = _seal_record(self.provider, record)
        path.chmod(0o600)
        path.write_text(json.dumps(sealed, sort_keys=True, separators=(",", ":")), "ascii")
        resolver = ControlledStagingTrustedReceiverPlanResolver(self.provider)
        with self.assertRaises(ControlledStagingTrustedPlanStoreError):
            resolver(parse_receiver_plan_lookup_hint(self.payload))

    def test_symlink_plan_record_fails_closed(self) -> None:
        self._run_lifecycle()
        self._persist()
        path = self._path()
        outside = self.root / "outside-plan.json"
        outside.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(outside)
        resolver = ControlledStagingTrustedReceiverPlanResolver(self.provider)
        with self.assertRaises(ControlledStagingTrustedPlanStoreError):
            resolver(parse_receiver_plan_lookup_hint(self.payload))

    def test_resolver_is_read_only_and_composes_with_trusted_lookup(self) -> None:
        self._run_lifecycle()
        self._persist()
        resolver = ControlledStagingTrustedReceiverPlanResolver(self.provider)
        before = self._snapshot()
        resolution = resolve_trusted_receiver_plan(
            payload=self.payload,
            expected_engine=self.engine,
            resolver=resolver,
        )
        after = self._snapshot()
        self.assertEqual(after, before)
        self.assertEqual(resolution.plan_mapping(), self.plan)
        self.assertEqual(resolution.job_id, self.binding.job_id)
        self.assertEqual(resolution.run_id, self.identity.run_id)
        self.assertEqual(resolution.engine, self.engine)
        self.assertTrue(resolution.trusted_plan_resolved)
        self.assertFalse(resolution.receiver_authentication_passed)
        self.assertFalse(resolution.network_dispatch_allowed)
        self.assertFalse(resolution.engine_execution_allowed)

    def test_untrusted_wrong_job_hint_cannot_escape_store_or_become_authority(self) -> None:
        self._run_lifecycle()
        self._persist()
        parsed = json.loads(self.payload.decode("ascii"))
        parsed["jobId"] = "job_" + "0" * 32
        tampered = json.dumps(
            parsed,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
        resolver = ControlledStagingTrustedReceiverPlanResolver(self.provider)
        with self.assertRaises(TrustedReceiverPlanLookupError) as context:
            resolve_trusted_receiver_plan(
                payload=tampered,
                expected_engine=self.engine,
                resolver=resolver,
            )
        self.assertEqual(context.exception.category, "trusted_receiver_plan_unavailable")

    def test_wrong_integrity_key_restart_cannot_resolve_existing_plan(self) -> None:
        self._run_lifecycle()
        self._persist()
        wrong = StagingUploadProvider(
            self.root,
            state_integrity_key=b"W" * 32,
        )
        resolver = ControlledStagingTrustedReceiverPlanResolver(wrong)
        with self.assertRaises(TrustedReceiverPlanLookupError) as context:
            resolve_trusted_receiver_plan(
                payload=self.payload,
                expected_engine=self.engine,
                resolver=resolver,
            )
        self.assertEqual(context.exception.category, "trusted_receiver_plan_unavailable")

    def test_resolver_repr_and_authority_flags_expose_no_provider_secret(self) -> None:
        resolver = ControlledStagingTrustedReceiverPlanResolver(self.provider)
        rendered = repr(resolver)
        self.assertNotIn(str(self.root), rendered)
        self.assertNotIn(self.key.decode("ascii"), rendered)
        for attribute in (
            "persistence_allowed",
            "job_state_mutation_allowed",
            "credential_resolution_allowed",
            "replay_reservation_allowed",
            "network_dispatch_allowed",
            "engine_execution_allowed",
        ):
            self.assertIs(getattr(resolver, attribute), False)

    def test_result_requires_exact_types(self) -> None:
        self._run_lifecycle()
        result = self._persist()
        self.assertIs(type(result), ControlledStagingTrustedPlanStoreResult)
        with self.assertRaises(ControlledStagingTrustedPlanStoreError):
            replace(result, job_id=_StrSubclass(result.job_id))
        with self.assertRaises(ControlledStagingTrustedPlanStoreError):
            replace(
                result,
                orchestration_plan_sha256=_StrSubclass(
                    result.orchestration_plan_sha256
                ),
            )

    def test_persisted_record_contains_no_transport_or_credential_proof(self) -> None:
        self._run_lifecycle()
        self._persist()
        rendered = self._path().read_text("ascii")
        for forbidden in (
            "credential_generation_id",
            "credential_key",
            "request_nonce",
            "generation_signature",
            "request_signature",
            "authorization",
        ):
            self.assertNotIn(forbidden, rendered)

    def test_internal_transcribe_http_route_remains_disabled(self) -> None:
        response = route_request("POST", "/internal/transcribe", load_config({}))
        self.assertEqual(response.status, 405)
        self.assertEqual(response.allow, "GET")
        self.assertEqual(response.payload, {"error": "method_not_allowed"})


if __name__ == "__main__":
    unittest.main()
