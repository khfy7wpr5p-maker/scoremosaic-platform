from __future__ import annotations

from hashlib import sha256
import importlib
import json
from pathlib import Path
import secrets
import sys
import tempfile
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
capability = importlib.import_module(PACKAGE + ".engine_execution_capability")
dispatch_acceptance = importlib.import_module(PACKAGE + ".dispatch_acceptance")
receiver_authority = importlib.import_module(PACKAGE + ".receiver_authority")
source_delivery = importlib.import_module(PACKAGE + ".source_delivery")

ENGINE = receiver_authority.ENGINE_NAME
EngineReceiverAuthority = receiver_authority.EngineReceiverAuthority
EngineDispatchAcceptanceStore = dispatch_acceptance.EngineDispatchAcceptanceStore
EngineSourceStore = source_delivery.EngineSourceStore
EngineExecutionCapabilityError = capability.EngineExecutionCapabilityError
ENGINE_EXECUTION_MEDIA_TYPES = capability.ENGINE_EXECUTION_MEDIA_TYPES
evaluate_engine_execution_eligibility = capability.evaluate_engine_execution_eligibility

EXPECTED = {
    "audiveris": frozenset({"application/pdf", "image/jpeg", "image/png"}),
    "homr": frozenset({"image/jpeg", "image/png"}),
    "clarity": frozenset({"application/pdf"}),
}
SUFFIX = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
}


def canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")


class EngineExecutionCapabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.authority = EngineReceiverAuthority(
            root=root / "authority",
            integrity_key=secrets.token_bytes(32),
        )
        self.acceptance = EngineDispatchAcceptanceStore(
            root=root / "dispatch",
            integrity_key=secrets.token_bytes(32),
        )
        self.source_store = EngineSourceStore(
            root=root / "source",
            integrity_key=secrets.token_bytes(32),
        )
        self.sequence = 0

    def prepare(self, media_type: str):
        self.sequence += 1
        job_id = f"job_stage5b1cap{self.sequence:02d}"
        source = (f"stage5b1-{ENGINE}-{media_type}-{self.sequence}").encode("ascii")
        source_sha = sha256(source).hexdigest()
        plan = build_orchestration_plan(
            job_id,
            source_artifact_ref=f"sources/{job_id}/source.bin",
            source_sha256=source_sha,
            source_size_bytes=len(source),
            source_media_type=media_type,
        ).as_dict()
        identity = build_dispatch_identity(plan, ENGINE)
        self.authority.register_trusted_plan(
            job_id=job_id,
            canonical_plan_bytes=canonical(plan),
        )
        return job_id, source, plan, identity

    def persist_dispatch_and_source(self, *, source: bytes, identity) -> None:
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
            source_bytes=source,
            source_sha256=sha256(source).hexdigest(),
            source_media_type=identity.source_media_type,
        )

    def test_capability_table_is_exact_and_immutable(self) -> None:
        self.assertEqual(ENGINE_EXECUTION_MEDIA_TYPES[ENGINE], EXPECTED[ENGINE])
        with self.assertRaises(TypeError):
            ENGINE_EXECUTION_MEDIA_TYPES[ENGINE] = frozenset()  # type: ignore[index]

    def test_each_supported_media_type_converges_without_execution_authority(self) -> None:
        for media_type in sorted(EXPECTED[ENGINE]):
            with self.subTest(media_type=media_type):
                job_id, source, _plan, identity = self.prepare(media_type)
                self.persist_dispatch_and_source(source=source, identity=identity)
                result = evaluate_engine_execution_eligibility(
                    authority=self.authority,
                    dispatch_acceptance_store=self.acceptance,
                    source_store=self.source_store,
                    job_id=job_id,
                    run_id=identity.run_id,
                    dispatch_identity_sha256=identity.identity_sha256,
                )
                self.assertTrue(result.execution_eligible)
                self.assertEqual(result.runtime_input_suffix, SUFFIX[media_type])
                self.assertFalse(result.engine_execution_allowed)
                self.assertFalse(result.source_conversion_allowed)
                self.assertFalse(result.automatic_retry_allowed)
                self.assertFalse(result.result_persistence_allowed)
                self.assertFalse(result.gateway_state_mutation_allowed)
                safe = result.as_safe_dict()
                self.assertNotIn("sourceBytes", safe)
                self.assertNotIn(source.decode("ascii"), repr(result))
                self.assertEqual(safe["candidateId"], identity.candidate_id)

    def test_dispatch_acceptance_is_required_before_source_lookup(self) -> None:
        job_id, source, _plan, identity = self.prepare(next(iter(EXPECTED[ENGINE])))
        self.source_store.publish(
            job_id=identity.job_id,
            run_id=identity.run_id,
            dispatch_identity_sha256=identity.identity_sha256,
            source_artifact_id=identity.source_artifact_id,
            source_bytes=source,
            source_sha256=sha256(source).hexdigest(),
            source_media_type=identity.source_media_type,
        )
        with self.assertRaises(EngineExecutionCapabilityError) as caught:
            evaluate_engine_execution_eligibility(
                authority=self.authority,
                dispatch_acceptance_store=self.acceptance,
                source_store=self.source_store,
                job_id=job_id,
                run_id=identity.run_id,
                dispatch_identity_sha256=identity.identity_sha256,
            )
        self.assertEqual(caught.exception.category, "engine_execution_dispatch_not_accepted")

    def test_missing_source_is_fail_closed_after_dispatch(self) -> None:
        job_id, _source, _plan, identity = self.prepare(next(iter(EXPECTED[ENGINE])))
        self.acceptance.publish(
            job_id=identity.job_id,
            run_id=identity.run_id,
            dispatch_identity_sha256=identity.identity_sha256,
        )
        with self.assertRaises(EngineExecutionCapabilityError) as caught:
            evaluate_engine_execution_eligibility(
                authority=self.authority,
                dispatch_acceptance_store=self.acceptance,
                source_store=self.source_store,
                job_id=job_id,
                run_id=identity.run_id,
                dispatch_identity_sha256=identity.identity_sha256,
            )
        self.assertEqual(caught.exception.category, "engine_execution_source_unavailable")

    def test_runtime_media_mismatch_is_explicitly_fail_closed(self) -> None:
        unsupported = (
            {"application/pdf", "image/jpeg", "image/png"} - set(EXPECTED[ENGINE])
        )
        if not unsupported:
            self.skipTest("engine supports every admitted source media type")
        media_type = sorted(unsupported)[0]
        job_id, source, _plan, identity = self.prepare(media_type)
        self.persist_dispatch_and_source(source=source, identity=identity)
        with self.assertRaises(EngineExecutionCapabilityError) as caught:
            evaluate_engine_execution_eligibility(
                authority=self.authority,
                dispatch_acceptance_store=self.acceptance,
                source_store=self.source_store,
                job_id=job_id,
                run_id=identity.run_id,
                dispatch_identity_sha256=identity.identity_sha256,
            )
        self.assertEqual(
            caught.exception.category,
            "engine_execution_media_type_unsupported",
        )

    def test_wrong_run_or_dispatch_identity_never_converges(self) -> None:
        job_id, source, _plan, identity = self.prepare(next(iter(EXPECTED[ENGINE])))
        self.persist_dispatch_and_source(source=source, identity=identity)
        with self.assertRaises(EngineExecutionCapabilityError):
            evaluate_engine_execution_eligibility(
                authority=self.authority,
                dispatch_acceptance_store=self.acceptance,
                source_store=self.source_store,
                job_id=job_id,
                run_id="run_" + "0" * 24,
                dispatch_identity_sha256=identity.identity_sha256,
            )
        with self.assertRaises(EngineExecutionCapabilityError):
            evaluate_engine_execution_eligibility(
                authority=self.authority,
                dispatch_acceptance_store=self.acceptance,
                source_store=self.source_store,
                job_id=job_id,
                run_id=identity.run_id,
                dispatch_identity_sha256="0" * 64,
            )


if __name__ == "__main__":
    unittest.main()
