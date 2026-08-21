from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_gateway.controlled_private_execution import (
    AUTHENTICATED_EXECUTION_TRIGGER_VERSION,
    CONTROLLED_PRIVATE_EXECUTION_VERSION,
    AuthenticatedExecutionTriggerRequest,
    ControlledPrivateExecutionError,
    ControlledPrivateExecutionResult,
)


class ControlledPrivateExecutionHardeningTests(unittest.TestCase):
    def test_result_shape_uses_stable_error_for_wrong_types(self) -> None:
        base = dict(
            version=CONTROLLED_PRIVATE_EXECUTION_VERSION,
            job_id="job_stage5b3bhardening01",
            engine="audiveris",
            run_id="run_" + "1" * 24,
            dispatch_identity_sha256="2" * 64,
            source_artifact_id="artifact_" + "3" * 24,
            source_sha256="4" * 64,
            candidate_id="candidate_" + "5" * 24,
            target_origin="http://audiveris-foundation:8082",
            claim_key="6" * 64,
            http_status=200,
            execution_attempt_count=1,
            reconciliation_required_on_restart=True,
        )
        for field in (
            "job_id",
            "run_id",
            "dispatch_identity_sha256",
            "source_artifact_id",
            "source_sha256",
            "candidate_id",
            "claim_key",
        ):
            value = dict(base)
            value[field] = None
            with self.subTest(field=field):
                with self.assertRaises(ControlledPrivateExecutionError) as ctx:
                    ControlledPrivateExecutionResult(**value)
                self.assertEqual(ctx.exception.category, "staging_execution_result_invalid")

    def test_request_shape_rejects_ambiguous_or_mistyped_headers(self) -> None:
        valid = dict(
            engine="audiveris",
            generation_id="gen-stage5b3b-hardening",
            timestamp=1_800_700_000,
            timeout_seconds=3600,
            nonce_sha256="1" * 64,
            payload_sha256="2" * 64,
            body=b"{}",
            headers=(
                ("content-type", "application/json"),
                ("content-length", "2"),
                ("x-scoremosaic-execution-generation", "gen-stage5b3b-hardening"),
                ("x-scoremosaic-execution-timestamp", "1800700000"),
                ("x-scoremosaic-execution-nonce", "3" * 32),
                ("x-scoremosaic-execution-signature", "4" * 64),
            ),
        )
        request = AuthenticatedExecutionTriggerRequest(**valid)
        self.assertEqual(request.engine, "audiveris")

        for bad_headers in (
            valid["headers"] + (("x-scoremosaic-execution-signature", "5" * 64),),
            tuple(reversed(valid["headers"])),
            valid["headers"][:-1] + (("x-scoremosaic-execution-signature", None),),
        ):
            with self.subTest(headers=bad_headers):
                value = dict(valid)
                value["headers"] = bad_headers
                with self.assertRaises(ControlledPrivateExecutionError) as ctx:
                    AuthenticatedExecutionTriggerRequest(**value)
                self.assertEqual(ctx.exception.category, "staging_execution_request_invalid")

    def test_safe_request_diagnostics_do_not_export_secret_bearing_fields(self) -> None:
        request = AuthenticatedExecutionTriggerRequest(
            engine="audiveris",
            generation_id="gen-stage5b3b-hardening",
            timestamp=1_800_700_000,
            timeout_seconds=3600,
            nonce_sha256="1" * 64,
            payload_sha256="2" * 64,
            body=b"{}",
            headers=(
                ("content-type", "application/json"),
                ("content-length", "2"),
                ("x-scoremosaic-execution-generation", "gen-stage5b3b-hardening"),
                ("x-scoremosaic-execution-timestamp", "1800700000"),
                ("x-scoremosaic-execution-nonce", "3" * 32),
                ("x-scoremosaic-execution-signature", "4" * 64),
            ),
        )
        safe = request.as_safe_dict()
        self.assertEqual(safe["version"], AUTHENTICATED_EXECUTION_TRIGGER_VERSION)
        self.assertFalse(safe["rawNonceExportAllowed"])
        self.assertFalse(safe["signatureExportAllowed"])
        serialized = repr(request) + repr(safe)
        self.assertNotIn("3" * 32, serialized)
        self.assertNotIn("4" * 64, serialized)


if __name__ == "__main__":
    unittest.main()
