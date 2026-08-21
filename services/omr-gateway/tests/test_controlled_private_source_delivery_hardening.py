from __future__ import annotations
from hashlib import sha256
import os
from pathlib import Path
import secrets
import tempfile
import unittest

from scoremosaic_gateway.config import EngineEndpoint
from scoremosaic_gateway.controlled_private_network_dispatch import (
    CONTROLLED_PRIVATE_NETWORK_DISPATCH_VERSION,
    ControlledPrivateNetworkDispatchResult,
)
from scoremosaic_gateway.controlled_private_source_delivery import (
    ControlledPrivateSourceDeliveryError,
    deliver_controlled_private_source_once,
)
from scoremosaic_gateway.dispatch_identity import build_dispatch_identity
from scoremosaic_gateway.dispatch_input_capsule import build_dispatch_input_capsule
from scoremosaic_gateway.dispatch_target import APPROVED_ENGINE_ORIGINS
from scoremosaic_gateway.minimum_staging_vertical_slice import StagingUploadProvider
from scoremosaic_gateway.orchestration import build_orchestration_plan
from scoremosaic_gateway.source_delivery import build_source_delivery_binding


class ControlledPrivateSourceDeliveryHardeningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = 1_800_700_000
        self.engine = "audiveris"
        self.endpoint = EngineEndpoint(
            self.engine,
            APPROVED_ENGINE_ORIGINS["staging"][self.engine],
        )
        self.source = b"%PDF-1.4\n" + b"stage5a2-hardening" * 64
        self.plan = build_orchestration_plan(
            "job_stage5a2hardening01",
            source_artifact_ref="sources/job_stage5a2hardening01/source.pdf",
            source_sha256=sha256(self.source).hexdigest(),
            source_size_bytes=len(self.source),
            source_media_type="application/pdf",
        ).as_dict()
        self.identity = build_dispatch_identity(self.plan, self.engine)
        self.capsule = build_dispatch_input_capsule(
            self.plan,
            self.identity,
            [self.source],
        )
        self.dispatch_result = ControlledPrivateNetworkDispatchResult(
            version=CONTROLLED_PRIVATE_NETWORK_DISPATCH_VERSION,
            job_id=self.identity.job_id,
            engine=self.engine,
            run_id=self.identity.run_id,
            dispatch_identity_sha256=self.identity.identity_sha256,
            target_origin=self.endpoint.base_url,
            dispatching_revision=2,
            provisioning_http_status=201,
            dispatch_http_status=202,
            provisioning_attempt_count=1,
            dispatch_attempt_count=1,
            reconciliation_required_on_restart=True,
        )
        self.generation = "gen-stage5a2-hardening"
        self.secret = secrets.token_bytes(32)
        self.binding = build_source_delivery_binding(self.endpoint)

    def resolver(self, key: str, generation: str):
        if key == self.binding.credential_key and generation == self.generation:
            return self.secret
        return None

    def _provider(self, name: str) -> StagingUploadProvider:
        return StagingUploadProvider(
            Path(self.temp.name) / name,
            state_integrity_key=secrets.token_bytes(32),
        )

    def _create_ambiguous_claim(self, provider: StagingUploadProvider, nonce: str) -> Path:
        calls: list[int] = []

        def failing_transport(*_args):
            calls.append(1)
            raise OSError("transport detail must not escape")

        with self.assertRaises(ControlledPrivateSourceDeliveryError) as context:
            deliver_controlled_private_source_once(
                provider=provider,
                endpoint=self.endpoint,
                capsule=self.capsule,
                dispatch_result=self.dispatch_result,
                generation_id=self.generation,
                credential_resolver=self.resolver,
                now_seconds=self.now,
                nonce=nonce,
                transport=failing_transport,
            )
        self.assertEqual(context.exception.category, "staging_source_transport_failed")
        self.assertEqual(len(calls), 1)
        claims = list((provider._root / "state" / "source_delivery_claims").rglob("*.json"))
        self.assertEqual(len(claims), 1)
        return claims[0]

    def test_tampered_durable_claim_fails_closed_with_zero_restart_network(self) -> None:
        provider = self._provider("tamper")
        claim = self._create_ambiguous_claim(provider, "aa" * 16)
        claim.chmod(0o600)
        claim.write_bytes(claim.read_bytes() + b" ")
        restart_calls: list[int] = []

        with self.assertRaises(ControlledPrivateSourceDeliveryError) as context:
            deliver_controlled_private_source_once(
                provider=provider,
                endpoint=self.endpoint,
                capsule=self.capsule,
                dispatch_result=self.dispatch_result,
                generation_id=self.generation,
                credential_resolver=self.resolver,
                now_seconds=self.now,
                nonce="aa" * 16,
                transport=lambda *_args: restart_calls.append(1),
            )
        self.assertEqual(context.exception.category, "staging_source_state_invalid")
        self.assertEqual(restart_calls, [])

    def test_symlinked_durable_claim_is_never_followed_and_restart_sends_zero(self) -> None:
        provider = self._provider("symlink")
        claim = self._create_ambiguous_claim(provider, "bb" * 16)
        outside = Path(self.temp.name) / "outside-claim.json"
        outside.write_text("outside", encoding="utf-8")
        claim.unlink()
        os.symlink(outside, claim)
        restart_calls: list[int] = []

        with self.assertRaises(ControlledPrivateSourceDeliveryError) as context:
            deliver_controlled_private_source_once(
                provider=provider,
                endpoint=self.endpoint,
                capsule=self.capsule,
                dispatch_result=self.dispatch_result,
                generation_id=self.generation,
                credential_resolver=self.resolver,
                now_seconds=self.now,
                nonce="bb" * 16,
                transport=lambda *_args: restart_calls.append(1),
            )
        self.assertEqual(context.exception.category, "staging_source_state_invalid")
        self.assertEqual(restart_calls, [])
        self.assertEqual(outside.read_text(encoding="utf-8"), "outside")

    def test_safe_failures_and_results_do_not_render_source_or_secret(self) -> None:
        provider = self._provider("redaction")
        with self.assertRaises(ControlledPrivateSourceDeliveryError) as context:
            deliver_controlled_private_source_once(
                provider=provider,
                endpoint=self.endpoint,
                capsule=self.capsule,
                dispatch_result=self.dispatch_result,
                generation_id=self.generation,
                credential_resolver=self.resolver,
                now_seconds=self.now,
                nonce="cc" * 16,
                transport=lambda *_args: (_ for _ in ()).throw(
                    RuntimeError(self.secret.hex() + self.source.hex())
                ),
            )
        rendered = str(context.exception)
        self.assertEqual(rendered, "staging_source_transport_failed")
        self.assertNotIn(self.secret.hex(), rendered)
        self.assertNotIn(self.source.hex(), rendered)


if __name__ == "__main__":
    unittest.main()
