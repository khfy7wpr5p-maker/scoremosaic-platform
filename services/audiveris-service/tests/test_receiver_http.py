from __future__ import annotations

from hashlib import sha256
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
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
from scoremosaic_gateway.controlled_staging_dispatch_wire import (
    serialize_controlled_staging_dispatch_wire,
)
from scoremosaic_gateway.credential_rotation import (
    build_rotation_set,
    resolve_engine_credential_generation,
    sign_rotation_authenticated_request,
)
from scoremosaic_gateway.dispatch_identity import (
    build_dispatch_identity,
    dispatch_identity_payload,
)
from scoremosaic_gateway.dispatch_input_capsule import build_dispatch_input_capsule
from scoremosaic_gateway.dispatch_target import (
    APPROVED_ENGINE_ORIGINS,
    build_engine_dispatch_target,
)
from scoremosaic_gateway.orchestration import build_orchestration_plan
from scoremosaic_gateway.service_auth import build_engine_auth_binding
from scoremosaic_gateway.trusted_plan_provisioning import (
    TRUSTED_PLAN_PROVISIONING_PATH,
    build_trusted_plan_provisioning_binding,
    build_trusted_plan_provisioning_request,
    resolve_trusted_plan_provisioning_credential,
)

if SERVICE_ROOT.name == "audiveris-service":
    from scoremosaic_audiveris.app import make_handler
    from scoremosaic_audiveris.authenticated_dispatch_receiver import ReceiverCredentialRotation
    from scoremosaic_audiveris.config import load_config
    from scoremosaic_audiveris.receiver_authority import EngineReceiverAuthority
    from scoremosaic_audiveris.receiver_http import (
        DISPATCH_PATH,
        PROVISIONING_SIGNATURE_HEADER,
        ReceiverHttpContext,
        handle_receiver_http_request,
        receiver_body_length,
    )
    ENGINE = "audiveris"
elif SERVICE_ROOT.name == "homr-service":
    from scoremosaic_homr.app import make_handler
    from scoremosaic_homr.authenticated_dispatch_receiver import ReceiverCredentialRotation
    from scoremosaic_homr.config import load_config
    from scoremosaic_homr.receiver_authority import EngineReceiverAuthority
    from scoremosaic_homr.receiver_http import (
        DISPATCH_PATH,
        PROVISIONING_SIGNATURE_HEADER,
        ReceiverHttpContext,
        handle_receiver_http_request,
        receiver_body_length,
    )
    ENGINE = "homr"
elif SERVICE_ROOT.name == "clarity-service":
    from scoremosaic_clarity.app import make_handler
    from scoremosaic_clarity.authenticated_dispatch_receiver import ReceiverCredentialRotation
    from scoremosaic_clarity.config import load_config
    from scoremosaic_clarity.receiver_authority import EngineReceiverAuthority
    from scoremosaic_clarity.receiver_http import (
        DISPATCH_PATH,
        PROVISIONING_SIGNATURE_HEADER,
        ReceiverHttpContext,
        handle_receiver_http_request,
        receiver_body_length,
    )
    ENGINE = "clarity"
else:
    raise RuntimeError("unexpected engine service root")


class ReceiverHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = 1_800_400_000
        self.authority = EngineReceiverAuthority(
            root=Path(self.temp.name) / "authority",
            integrity_key=secrets.token_bytes(32),
        )
        self.endpoint = EngineEndpoint(
            ENGINE,
            APPROVED_ENGINE_ORIGINS["staging"][ENGINE],
        )
        self.source = b"%PDF-1.4\n" + b"stage4c2" * 64
        self.plan = build_orchestration_plan(
            "job_stage4c2http01",
            source_artifact_ref="sources/job_stage4c2http01/source.pdf",
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

        self.provisioning_generation = "gen-stage4c2-provision"
        self.provisioning_secret = secrets.token_bytes(32)
        self.provisioning_binding = build_trusted_plan_provisioning_binding(
            self.endpoint,
            environment="staging",
        )
        self.provisioning_credential = resolve_trusted_plan_provisioning_credential(
            self.provisioning_binding,
            generation_id=self.provisioning_generation,
            resolver=lambda key, generation: (
                self.provisioning_secret
                if key == self.provisioning_binding.credential_key
                and generation == self.provisioning_generation
                else None
            ),
        )
        self.provisioning_request = build_trusted_plan_provisioning_request(
            capsule=self.capsule,
            credential=self.provisioning_credential,
            issued_at=self.now,
            nonce="11111111111111111111111111111111",
        )

        self.dispatch_generation = "gen-stage4c2-dispatch"
        self.dispatch_secret = secrets.token_bytes(32)
        self.dispatch_binding = build_engine_auth_binding(self.endpoint, "staging")
        self.dispatch_target = build_engine_dispatch_target(
            self.dispatch_binding,
            self.endpoint,
        )
        gateway_dispatch_credential = resolve_engine_credential_generation(
            self.dispatch_binding,
            self.dispatch_generation,
            lambda key, generation: (
                self.dispatch_secret
                if key == self.dispatch_binding.credential_key
                and generation == self.dispatch_generation
                else None
            ),
        )
        gateway_rotation = build_rotation_set(
            current=gateway_dispatch_credential,
            previous=None,
            rotation_started_at=self.now - 1,
            previous_valid_until=None,
        )
        self.dispatch_body = dispatch_identity_payload(self.identity)
        signed = sign_rotation_authenticated_request(
            gateway_rotation,
            method=self.dispatch_target.method,
            path=self.dispatch_target.path,
            timestamp=self.now,
            nonce="22222222222222222222222222222222",
            payload=self.dispatch_body,
            now_seconds=self.now,
        )
        self.dispatch_wire = serialize_controlled_staging_dispatch_wire(
            target=self.dispatch_target,
            request=signed,
            payload=self.dispatch_body,
        )

        self.context = ReceiverHttpContext(
            authority=self.authority,
            provisioning_credential_resolver=lambda key, generation: (
                self.provisioning_secret
                if key == self.provisioning_binding.credential_key
                and generation == self.provisioning_generation
                else None
            ),
            dispatch_rotation=ReceiverCredentialRotation(
                current_generation_id=self.dispatch_generation,
                current_activated_at=self.now - 1,
            ),
            dispatch_credential_resolver=lambda key, generation: (
                self.dispatch_secret
                if key == self.dispatch_binding.credential_key
                and generation == self.dispatch_generation
                else None
            ),
            now_seconds=lambda: self.now,
        )

    @staticmethod
    def base_headers(length: int) -> tuple[tuple[str, str], ...]:
        return (
            ("Content-Type", "application/json"),
            ("Content-Length", str(length)),
        )

    def provisioning_headers(self):
        return self.base_headers(
            len(self.provisioning_request.canonical_request_bytes)
        ) + ((PROVISIONING_SIGNATURE_HEADER, self.provisioning_request.signature),)

    def dispatch_headers(self):
        return self.base_headers(len(self.dispatch_body)) + self.dispatch_wire.headers

    def test_framing_rejects_duplicate_content_length_transfer_encoding_and_query(self) -> None:
        base = self.provisioning_headers()
        with self.assertRaises(Exception) as context:
            receiver_body_length(
                method="POST",
                target=TRUSTED_PLAN_PROVISIONING_PATH,
                headers=base + (("Content-Length", str(len(self.provisioning_request.canonical_request_bytes))),),
            )
        self.assertEqual(getattr(context.exception, "category", None), "receiver_header_ambiguous")

        with self.assertRaises(Exception) as context:
            receiver_body_length(
                method="POST",
                target=TRUSTED_PLAN_PROVISIONING_PATH,
                headers=base + (("Transfer-Encoding", "chunked"),),
            )
        self.assertEqual(
            getattr(context.exception, "category", None),
            "receiver_transfer_encoding_forbidden",
        )

        response = handle_receiver_http_request(
            method="POST",
            target=TRUSTED_PLAN_PROVISIONING_PATH + "?x=1",
            headers=base,
            body=self.provisioning_request.canonical_request_bytes,
            context=self.context,
        )
        self.assertEqual(response.status, 400)

    def test_receiver_context_is_fail_closed(self) -> None:
        response = handle_receiver_http_request(
            method="POST",
            target=TRUSTED_PLAN_PROVISIONING_PATH,
            headers=self.provisioning_headers(),
            body=self.provisioning_request.canonical_request_bytes,
            context=None,
        )
        self.assertEqual(response.status, 503)
        self.assertEqual(response.payload, {"error": "receiver_context_unavailable"})

    def test_method_and_security_header_sets_are_exact(self) -> None:
        response = handle_receiver_http_request(
            method="GET",
            target=DISPATCH_PATH,
            headers=self.dispatch_headers(),
            body=self.dispatch_body,
            context=self.context,
        )
        self.assertEqual(response.status, 405)
        self.assertEqual(response.allow, "POST")

        response = handle_receiver_http_request(
            method="POST",
            target=DISPATCH_PATH,
            headers=self.dispatch_headers() + (("x-scoremosaic-extra", "x"),),
            body=self.dispatch_body,
            context=self.context,
        )
        self.assertEqual(response.status, 400)

    def test_real_http_provision_then_dispatch_accepts_but_never_executes(self) -> None:
        server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            make_handler(load_config({}), receiver_context=self.context),
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

        host, port = server.server_address
        connection = HTTPConnection(host, port, timeout=5)
        self.addCleanup(connection.close)

        connection.request(
            "POST",
            TRUSTED_PLAN_PROVISIONING_PATH,
            body=self.provisioning_request.canonical_request_bytes,
            headers={
                "Content-Type": "application/json",
                PROVISIONING_SIGNATURE_HEADER: self.provisioning_request.signature,
            },
        )
        response = connection.getresponse()
        provision_payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual(response.status, 201)
        self.assertEqual(provision_payload["kind"], "trusted_plan")
        self.assertFalse(provision_payload["engineExecutionAllowed"])

        connection.request(
            "POST",
            DISPATCH_PATH,
            body=self.dispatch_body,
            headers={"Content-Type": "application/json", **dict(self.dispatch_wire.headers)},
        )
        response = connection.getresponse()
        dispatch_payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual(response.status, 202)
        self.assertEqual(dispatch_payload["kind"], "dispatch")
        self.assertFalse(dispatch_payload["engineExecutionAllowed"])
        self.assertFalse(dispatch_payload["evidence"]["engineExecutionAllowed"])

        connection.close()
        connection = HTTPConnection(host, port, timeout=5)
        connection.request(
            "POST",
            DISPATCH_PATH,
            body=self.dispatch_body,
            headers={"Content-Type": "application/json", **dict(self.dispatch_wire.headers)},
        )
        response = connection.getresponse()
        replay_payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual(response.status, 409)
        self.assertEqual(replay_payload["error"], "receiver_replay_detected")
        connection.close()

    def test_http_response_and_context_do_not_expose_secrets_or_auth_proofs(self) -> None:
        response = handle_receiver_http_request(
            method="POST",
            target=TRUSTED_PLAN_PROVISIONING_PATH,
            headers=self.provisioning_headers(),
            body=self.provisioning_request.canonical_request_bytes,
            context=self.context,
        )
        rendered = repr(response.payload)
        for sensitive in (
            self.provisioning_secret.hex(),
            self.dispatch_secret.hex(),
            self.provisioning_request.signature,
            self.provisioning_request.canonical_request_bytes.decode("ascii"),
        ):
            self.assertNotIn(sensitive, rendered)


if __name__ == "__main__":
    unittest.main()
