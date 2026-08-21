from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import secrets
import sys
import tempfile
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


class SourceDeliveryHardeningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = 1_800_600_100
        self.source = b"%PDF-1.4\n" + b"stage5a-hardening" * 64
        plan = build_orchestration_plan(
            "job_stage5aharden01",
            source_artifact_ref="sources/job_stage5aharden01/source.pdf",
            source_sha256=sha256(self.source).hexdigest(),
            source_size_bytes=len(self.source),
            source_media_type="application/pdf",
        ).as_dict()
        identity = build_dispatch_identity(plan, ENGINE)
        capsule = build_dispatch_input_capsule(plan, identity, [self.source])
        self.identity = identity
        self.authority = EngineReceiverAuthority(
            root=Path(self.temp.name) / "authority",
            integrity_key=secrets.token_bytes(32),
        )
        self.authority.register_trusted_plan(
            job_id=identity.job_id,
            canonical_plan_bytes=capsule.canonical_plan_bytes,
        )
        self.store = EngineSourceStore(
            root=Path(self.temp.name) / "store",
            integrity_key=secrets.token_bytes(32),
        )
        self.secret = secrets.token_bytes(32)
        self.generation = "gen-stage5a-harden"
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
            capsule=capsule,
            credential=credential,
            timestamp=self.now,
            nonce="55" * 16,
        )
        self.rotation = SourceDeliveryRotation(
            current_generation_id=self.generation,
            current_activated_at=self.now - 1,
        )

    def resolver(self, key: str, generation: str):
        if key == source_delivery_credential_key() and generation == self.generation:
            return self.secret
        return None

    def accept(self, *, rotation=None, now=None):
        return accept_source_delivery(
            authority=self.authority,
            store=self.store,
            rotation=self.rotation if rotation is None else rotation,
            headers=self.request.headers,
            body=self.request.body,
            now_seconds=self.now if now is None else now,
            credential_resolver=self.resolver,
        )

    def test_store_rejects_noncanonical_duplicate_key_metadata(self) -> None:
        accepted = self.accept()
        self.assertEqual(accepted.persistence_state, "written")
        target = self.store._job_dir(self.identity.job_id, self.identity.run_id)
        metadata_path = target / "metadata.json"
        raw = metadata_path.read_text(encoding="ascii")
        needle = f'"engine":"{ENGINE}"'
        self.assertIn(needle, raw)
        metadata_path.chmod(0o600)
        metadata_path.write_text(
            raw.replace(needle, f"{needle},{needle}", 1),
            encoding="ascii",
        )
        metadata_path.chmod(0o400)
        with self.assertRaises(SourceDeliveryReceiverError) as context:
            self.store.load(job_id=self.identity.job_id, run_id=self.identity.run_id)
        self.assertEqual(context.exception.category, "source_store_state_invalid")

    def test_current_generation_rejects_request_signed_before_activation(self) -> None:
        future_rotation = SourceDeliveryRotation(
            current_generation_id=self.generation,
            current_activated_at=self.now + 1,
        )
        with self.assertRaises(SourceDeliveryReceiverError) as context:
            self.accept(rotation=future_rotation, now=self.now + 1)
        self.assertEqual(
            context.exception.category,
            "source_delivery_generation_invalid",
        )


if __name__ == "__main__":
    unittest.main()
