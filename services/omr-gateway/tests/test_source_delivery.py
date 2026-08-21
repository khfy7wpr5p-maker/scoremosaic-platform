from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import secrets
import sys
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_gateway.config import EngineEndpoint
from scoremosaic_gateway.dispatch_identity import build_dispatch_identity
from scoremosaic_gateway.dispatch_input_capsule import build_dispatch_input_capsule
from scoremosaic_gateway.dispatch_target import APPROVED_ENGINE_ORIGINS
from scoremosaic_gateway.orchestration import build_orchestration_plan
from scoremosaic_gateway.service_auth import build_engine_auth_binding
from scoremosaic_gateway.source_delivery import (
    SOURCE_DELIVERY_HEADER_NAMES,
    SOURCE_DELIVERY_PATH,
    SourceDeliveryError,
    build_source_delivery_binding,
    build_source_delivery_request,
    resolve_source_delivery_credential,
)
from scoremosaic_gateway.trusted_plan_provisioning import (
    build_trusted_plan_provisioning_binding,
)


class SourceDeliveryContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = b"%PDF-1.4\n" + b"stage5a-source" * 64
        self.engine = "homr"
        self.endpoint = EngineEndpoint(
            self.engine,
            APPROVED_ENGINE_ORIGINS["staging"][self.engine],
        )
        self.plan = build_orchestration_plan(
            "job_stage5a12345678",
            source_artifact_ref="sources/job_stage5a12345678/source.pdf",
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
        self.binding = build_source_delivery_binding(self.endpoint)
        self.secret = secrets.token_bytes(32)
        self.credential = resolve_source_delivery_credential(
            self.binding,
            generation_id="gen-stage5a",
            resolver=lambda key, generation: (
                self.secret
                if key == self.binding.credential_key and generation == "gen-stage5a"
                else None
            ),
        )

    def test_builds_exact_bounded_non_executable_source_request(self) -> None:
        request = build_source_delivery_request(
            capsule=self.capsule,
            credential=self.credential,
            timestamp=1_800_500_000,
            nonce="11" * 16,
        )
        self.assertEqual(tuple(name for name, _ in request.headers), SOURCE_DELIVERY_HEADER_NAMES)
        self.assertEqual(request.body, self.source)
        self.assertEqual(request.source_sha256, sha256(self.source).hexdigest())
        self.assertEqual(request.source_size_bytes, len(self.source))
        self.assertEqual(request.dispatch_identity_sha256, self.identity.identity_sha256)
        self.assertEqual(self.binding.path, SOURCE_DELIVERY_PATH)
        self.assertFalse(request.network_delivery_allowed)
        self.assertFalse(request.engine_execution_allowed)
        self.assertFalse(request.result_persistence_allowed)
        self.assertFalse(request.retry_allowed)

    def test_source_credential_domain_is_separate_from_dispatch_and_provisioning(self) -> None:
        dispatch = build_engine_auth_binding(self.endpoint, "staging")
        provisioning = build_trusted_plan_provisioning_binding(
            self.endpoint,
            environment="staging",
        )
        self.assertNotEqual(self.binding.credential_key, dispatch.credential_key)
        self.assertNotEqual(self.binding.credential_key, provisioning.credential_key)
        self.assertIn("source-delivery", self.binding.credential_key)

    def test_arbitrary_or_cross_engine_origin_is_rejected(self) -> None:
        for endpoint in (
            EngineEndpoint("homr", "http://169.254.169.254:80"),
            EngineEndpoint("homr", APPROVED_ENGINE_ORIGINS["staging"]["clarity"]),
        ):
            with self.assertRaises(SourceDeliveryError):
                build_source_delivery_binding(endpoint)

    def test_resolver_exception_is_redacted(self) -> None:
        def resolver(_key: str, _generation: str):
            raise RuntimeError("SECRET_DO_NOT_LEAK /private/source")

        with self.assertRaises(SourceDeliveryError) as context:
            resolve_source_delivery_credential(
                self.binding,
                generation_id="gen-stage5a",
                resolver=resolver,
            )
        self.assertEqual(context.exception.category, "source_delivery_credential_unavailable")
        self.assertNotIn("SECRET_DO_NOT_LEAK", str(context.exception))

    def test_repr_and_safe_dict_hide_source_secret_nonce_and_signature(self) -> None:
        nonce = "22" * 16
        request = build_source_delivery_request(
            capsule=self.capsule,
            credential=self.credential,
            timestamp=1_800_500_000,
            nonce=nonce,
        )
        rendered = repr(self.credential) + repr(request) + repr(request.as_safe_dict())
        self.assertNotIn(self.secret.hex(), rendered)
        self.assertNotIn(self.source.decode("ascii"), rendered)
        self.assertNotIn(nonce, rendered)
        self.assertNotIn(request.signature, rendered)

    def test_invalid_nonce_and_cross_engine_capsule_fail_closed(self) -> None:
        with self.assertRaises(SourceDeliveryError):
            build_source_delivery_request(
                capsule=self.capsule,
                credential=self.credential,
                timestamp=1_800_500_000,
                nonce="bad",
            )

        clarity_endpoint = EngineEndpoint(
            "clarity",
            APPROVED_ENGINE_ORIGINS["staging"]["clarity"],
        )
        clarity_binding = build_source_delivery_binding(clarity_endpoint)
        clarity_credential = resolve_source_delivery_credential(
            clarity_binding,
            generation_id="gen-stage5a",
            resolver=lambda _key, _generation: secrets.token_bytes(32),
        )
        with self.assertRaises(SourceDeliveryError):
            build_source_delivery_request(
                capsule=self.capsule,
                credential=clarity_credential,
                timestamp=1_800_500_000,
                nonce="33" * 16,
            )


if __name__ == "__main__":
    unittest.main()
