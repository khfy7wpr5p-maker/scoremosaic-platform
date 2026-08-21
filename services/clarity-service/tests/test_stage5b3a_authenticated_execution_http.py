from __future__ import annotations

from hashlib import sha256
from hmac import new as hmac_new
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

if SERVICE_ROOT.name == "audiveris-service":
    from scoremosaic_audiveris.authenticated_dispatch_receiver import ReceiverCredentialRotation
    from scoremosaic_audiveris.authenticated_execution_trigger import (
        AUTHENTICATED_EXECUTION_TRIGGER_VERSION,
        AUDIENCE_IDENTITY,
        CALLER_SERVICE_IDENTITY,
        EXECUTION_TRIGGER_HEADER_NAMES,
        EXECUTION_TRIGGER_PATH,
        EngineExecutionHttpContext,
        ExecutionCredentialRotation,
        execution_trigger_credential_key,
    )
    from scoremosaic_audiveris.config import load_config
    from scoremosaic_audiveris.controlled_engine_execution import EngineExecutionClaimStore
    from scoremosaic_audiveris.dispatch_acceptance import EngineDispatchAcceptanceStore
    from scoremosaic_audiveris.receiver_authority import EngineReceiverAuthority
    from scoremosaic_audiveris.receiver_http import ReceiverHttpContext, handle_receiver_http_request, receiver_body_length
    from scoremosaic_audiveris.runtime import TranscriptionResult
    from scoremosaic_audiveris.source_delivery import EngineSourceStore, SourceDeliveryRotation, source_delivery_credential_key
    ENGINE = "audiveris"
elif SERVICE_ROOT.name == "homr-service":
    from scoremosaic_homr.authenticated_dispatch_receiver import ReceiverCredentialRotation
    from scoremosaic_homr.authenticated_execution_trigger import (
        AUTHENTICATED_EXECUTION_TRIGGER_VERSION,
        AUDIENCE_IDENTITY,
        CALLER_SERVICE_IDENTITY,
        EXECUTION_TRIGGER_HEADER_NAMES,
        EXECUTION_TRIGGER_PATH,
        EngineExecutionHttpContext,
        ExecutionCredentialRotation,
        execution_trigger_credential_key,
    )
    from scoremosaic_homr.config import load_config
    from scoremosaic_homr.controlled_engine_execution import EngineExecutionClaimStore
    from scoremosaic_homr.dispatch_acceptance import EngineDispatchAcceptanceStore
    from scoremosaic_homr.receiver_authority import EngineReceiverAuthority
    from scoremosaic_homr.receiver_http import ReceiverHttpContext, handle_receiver_http_request, receiver_body_length
    from scoremosaic_homr.runtime import TranscriptionResult
    from scoremosaic_homr.source_delivery import EngineSourceStore, SourceDeliveryRotation, source_delivery_credential_key
    ENGINE = "homr"
elif SERVICE_ROOT.name == "clarity-service":
    from scoremosaic_clarity.authenticated_dispatch_receiver import ReceiverCredentialRotation
    from scoremosaic_clarity.authenticated_execution_trigger import (
        AUTHENTICATED_EXECUTION_TRIGGER_VERSION,
        AUDIENCE_IDENTITY,
        CALLER_SERVICE_IDENTITY,
        EXECUTION_TRIGGER_HEADER_NAMES,
        EXECUTION_TRIGGER_PATH,
        EngineExecutionHttpContext,
        ExecutionCredentialRotation,
        execution_trigger_credential_key,
    )
    from scoremosaic_clarity.config import load_config
    from scoremosaic_clarity.controlled_engine_execution import EngineExecutionClaimStore
    from scoremosaic_clarity.dispatch_acceptance import EngineDispatchAcceptanceStore
    from scoremosaic_clarity.receiver_authority import EngineReceiverAuthority
    from scoremosaic_clarity.receiver_http import ReceiverHttpContext, handle_receiver_http_request, receiver_body_length
    from scoremosaic_clarity.runtime import TranscriptionResult
    from scoremosaic_clarity.source_delivery import EngineSourceStore, SourceDeliveryRotation, source_delivery_credential_key
    ENGINE = "clarity"
else:
    raise RuntimeError("unexpected engine service root")

_SIGNATURE_DOMAIN = b"scoremosaic-authenticated-execution-trigger-v1"


def canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("ascii")


class Stage5B3aAuthenticatedExecutionHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.now = 1_800_700_000
        if ENGINE == "clarity":
            self.source = b"%PDF-1.4\n" + b"stage5b3a" * 64
            media_type = "application/pdf"
            source_ref = "sources/job_stage5b3a123/source.pdf"
        else:
            self.source = b"\x89PNG\r\n\x1a\n" + b"stage5b3a" * 64
            media_type = "image/png"
            source_ref = "sources/job_stage5b3a123/source.png"
        self.plan = build_orchestration_plan(
            "job_stage5b3a123",
            source_artifact_ref=source_ref,
            source_sha256=sha256(self.source).hexdigest(),
            source_size_bytes=len(self.source),
            source_media_type=media_type,
            requested_engines=(ENGINE,),
            timeout_seconds_by_engine={ENGINE: 1800},
        ).as_dict()
        self.identity = build_dispatch_identity(self.plan, ENGINE)
        self.authority = EngineReceiverAuthority(root=root / "authority", integrity_key=secrets.token_bytes(32))
        self.acceptance = EngineDispatchAcceptanceStore(root=root / "acceptance", integrity_key=secrets.token_bytes(32))
        self.sources = EngineSourceStore(root=root / "sources", integrity_key=secrets.token_bytes(32))
        self.claims = EngineExecutionClaimStore(root=root / "claims", integrity_key=secrets.token_bytes(32))
        raw_plan = canonical(self.plan)
        self.authority.register_trusted_plan(job_id=self.identity.job_id, canonical_plan_bytes=raw_plan)
        self.acceptance.publish(job_id=self.identity.job_id, run_id=self.identity.run_id, dispatch_identity_sha256=self.identity.identity_sha256)
        self.sources.publish(
            job_id=self.identity.job_id,
            run_id=self.identity.run_id,
            dispatch_identity_sha256=self.identity.identity_sha256,
            source_artifact_id=self.identity.source_artifact_id,
            source_bytes=self.source,
            source_sha256=sha256(self.source).hexdigest(),
            source_media_type=media_type,
        )
        self.secret = secrets.token_bytes(32)
        self.generation = "gen-stage5b3a"
        self.transcriber_calls = 0

        def fake_transcriber(_input_path: Path, output_dir: Path, _config) -> TranscriptionResult:
            self.transcriber_calls += 1
            output = output_dir / "candidate.musicxml"
            output.write_bytes(b"<score-partwise version=\"4.0\"></score-partwise>")
            return TranscriptionResult(0, (output,), (), "runtime_output_redacted")

        execution_context = EngineExecutionHttpContext(
            claim_store=self.claims,
            config=load_config({}),
            rotation=ExecutionCredentialRotation(
                current_generation_id=self.generation,
                current_activated_at=self.now - 5,
            ),
            credential_resolver=lambda key, generation: self.secret if key == execution_trigger_credential_key() and generation == self.generation else None,
            transcriber=fake_transcriber,
        )
        self.context = ReceiverHttpContext(
            authority=self.authority,
            provisioning_credential_resolver=lambda _key, _generation: None,
            dispatch_rotation=ReceiverCredentialRotation(current_generation_id="gen-dispatch", current_activated_at=self.now - 10),
            dispatch_credential_resolver=lambda _key, _generation: None,
            now_seconds=lambda: self.now,
            dispatch_acceptance_store=self.acceptance,
            source_store=self.sources,
            source_rotation=SourceDeliveryRotation(current_generation_id="gen-source", current_activated_at=self.now - 10),
            source_credential_resolver=lambda _key, _generation: None,
            execution_http_context=execution_context,
        )

    def body(self, **overrides: object) -> bytes:
        run = next(item for item in self.plan["engineRuns"] if item["engine"] == ENGINE)
        value = {
            "version": AUTHENTICATED_EXECUTION_TRIGGER_VERSION,
            "environment": "staging",
            "engine": ENGINE,
            "jobId": self.identity.job_id,
            "runId": self.identity.run_id,
            "dispatchIdentitySha256": self.identity.identity_sha256,
            "sourceArtifactId": self.identity.source_artifact_id,
            "sourceSha256": sha256(self.source).hexdigest(),
            "candidateId": self.identity.candidate_id,
            "timeoutSeconds": run["timeoutSeconds"],
        }
        value.update(overrides)
        return canonical(value)

    def signed_headers(self, body: bytes, *, timestamp: int | None = None, nonce: str = "44" * 16, secret: bytes | None = None) -> tuple[tuple[str, str], ...]:
        ts = self.now if timestamp is None else timestamp
        metadata = canonical({
            "version": AUTHENTICATED_EXECUTION_TRIGGER_VERSION,
            "environment": "staging",
            "callerIdentity": CALLER_SERVICE_IDENTITY,
            "engine": ENGINE,
            "audienceIdentity": AUDIENCE_IDENTITY,
            "credentialKey": execution_trigger_credential_key(),
            "method": "POST",
            "path": EXECUTION_TRIGGER_PATH,
            "credentialGenerationId": self.generation,
            "timestamp": ts,
            "nonce": nonce,
            "payloadBytes": len(body),
            "payloadSha256": sha256(body).hexdigest(),
        })
        signature = hmac_new(self.secret if secret is None else secret, b"\0".join((_SIGNATURE_DOMAIN, metadata, body)), sha256).hexdigest()
        values = (
            self.generation,
            str(ts),
            nonce,
            signature,
        )
        return tuple(zip(EXECUTION_TRIGGER_HEADER_NAMES, values, strict=True))

    def http_headers(self, body: bytes, **kwargs: object) -> tuple[tuple[str, str], ...]:
        return (("Content-Type", "application/json"), ("Content-Length", str(len(body))), *self.signed_headers(body, **kwargs))

    def test_authenticated_route_executes_exactly_once_and_returns_no_result_bytes(self) -> None:
        body = self.body()
        response = handle_receiver_http_request(method="POST", target=EXECUTION_TRIGGER_PATH, headers=self.http_headers(body), body=body, context=self.context)
        self.assertEqual(response.status, 200)
        self.assertEqual(response.payload["kind"], "execution")
        self.assertTrue(response.payload["engineExecutionPerformed"])
        self.assertFalse(response.payload["resultReturnAllowed"])
        self.assertFalse(response.payload["resultPersistenceAllowed"])
        self.assertEqual(self.transcriber_calls, 1)
        rendered = repr(response.payload)
        self.assertNotIn(str(Path(self.temp.name)), rendered)
        second = handle_receiver_http_request(method="POST", target=EXECUTION_TRIGGER_PATH, headers=self.http_headers(body), body=body, context=self.context)
        self.assertEqual(second.status, 409)
        self.assertEqual(self.transcriber_calls, 1)

    def test_prerequisites_fail_before_execution_credential_resolution(self) -> None:
        calls = 0
        def resolver(_key: str, _generation: str):
            nonlocal calls
            calls += 1
            return self.secret
        root = Path(self.temp.name) / "empty"
        empty_authority = EngineReceiverAuthority(root=root / "authority", integrity_key=secrets.token_bytes(32))
        empty_acceptance = EngineDispatchAcceptanceStore(root=root / "acceptance", integrity_key=secrets.token_bytes(32))
        empty_sources = EngineSourceStore(root=root / "sources", integrity_key=secrets.token_bytes(32))
        empty_context = ReceiverHttpContext(
            authority=empty_authority,
            provisioning_credential_resolver=lambda _k, _g: None,
            dispatch_rotation=ReceiverCredentialRotation(current_generation_id="gen-dispatch", current_activated_at=self.now - 10),
            dispatch_credential_resolver=lambda _k, _g: None,
            now_seconds=lambda: self.now,
            dispatch_acceptance_store=empty_acceptance,
            source_store=empty_sources,
            source_rotation=SourceDeliveryRotation(current_generation_id="gen-source", current_activated_at=self.now - 10),
            source_credential_resolver=lambda _k, _g: None,
            execution_http_context=EngineExecutionHttpContext(
                claim_store=EngineExecutionClaimStore(root=root / "claims", integrity_key=secrets.token_bytes(32)),
                config=load_config({}),
                rotation=ExecutionCredentialRotation(current_generation_id=self.generation, current_activated_at=self.now - 5),
                credential_resolver=resolver,
                transcriber=lambda *_args: (_ for _ in ()).throw(AssertionError("must not execute")),
            ),
        )
        body = self.body()
        response = handle_receiver_http_request(method="POST", target=EXECUTION_TRIGGER_PATH, headers=self.http_headers(body), body=body, context=empty_context)
        self.assertEqual(response.status, 409)
        self.assertEqual(calls, 0)

    def test_bad_signature_and_pre_activation_timestamp_never_execute(self) -> None:
        body = self.body()
        bad = handle_receiver_http_request(
            method="POST", target=EXECUTION_TRIGGER_PATH,
            headers=self.http_headers(body, secret=secrets.token_bytes(32)),
            body=body, context=self.context,
        )
        self.assertEqual(bad.status, 403)
        self.assertEqual(self.transcriber_calls, 0)
        early = handle_receiver_http_request(
            method="POST", target=EXECUTION_TRIGGER_PATH,
            headers=self.http_headers(body, timestamp=self.now - 6, nonce="55" * 16),
            body=body, context=self.context,
        )
        self.assertEqual(early.status, 403)
        self.assertEqual(self.transcriber_calls, 0)

    def test_execution_framing_is_exact_and_fail_closed_without_context(self) -> None:
        body = self.body()
        headers = self.http_headers(body)
        with self.assertRaises(Exception) as caught:
            receiver_body_length(method="POST", target=EXECUTION_TRIGGER_PATH, headers=headers + (("Transfer-Encoding", "chunked"),))
        self.assertEqual(getattr(caught.exception, "category", None), "receiver_transfer_encoding_forbidden")
        query = handle_receiver_http_request(method="POST", target=EXECUTION_TRIGGER_PATH + "?x=1", headers=headers, body=body, context=self.context)
        self.assertEqual(query.status, 400)
        duplicate = handle_receiver_http_request(method="POST", target=EXECUTION_TRIGGER_PATH, headers=headers + ((EXECUTION_TRIGGER_HEADER_NAMES[0], self.generation),), body=body, context=self.context)
        self.assertEqual(duplicate.status, 400)
        legacy = ReceiverHttpContext(
            authority=self.authority,
            provisioning_credential_resolver=lambda _k, _g: None,
            dispatch_rotation=ReceiverCredentialRotation(current_generation_id="gen-dispatch", current_activated_at=self.now - 10),
            dispatch_credential_resolver=lambda _k, _g: None,
            now_seconds=lambda: self.now,
            dispatch_acceptance_store=self.acceptance,
            source_store=self.sources,
            source_rotation=SourceDeliveryRotation(current_generation_id="gen-source", current_activated_at=self.now - 10),
            source_credential_resolver=lambda _k, _g: None,
        )
        disabled = handle_receiver_http_request(method="POST", target=EXECUTION_TRIGGER_PATH, headers=headers, body=body, context=legacy)
        self.assertEqual(disabled.status, 503)
        self.assertEqual(self.transcriber_calls, 0)

    def test_execution_credential_domain_is_separate_from_source_domain(self) -> None:
        self.assertNotEqual(execution_trigger_credential_key(), source_delivery_credential_key())
        self.assertIn("authenticated-execution-trigger", execution_trigger_credential_key())


if __name__ == "__main__":
    unittest.main()
