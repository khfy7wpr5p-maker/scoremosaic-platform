from __future__ import annotations

import sys
from pathlib import Path
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_clarity.app import route_request
from scoremosaic_clarity.config import load_config
from scoremosaic_clarity.runtime import RuntimeProbe


class RouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_config({"SCOREMOSAIC_CLARITY_COMPUTE_MODE": "cpu"})

    def test_health_reports_pinned_runtime_and_native_pdf_only(self) -> None:
        response = route_request("GET", "/health?ignored=1", self.config)

        self.assertEqual(response.status, 200)
        self.assertEqual(response.payload["status"], "ok")
        self.assertTrue(response.payload["engine"]["installed"])
        self.assertEqual(response.payload["engine"]["expectedModels"], 2)
        self.assertEqual(
            response.payload["capabilities"]["acceptedInputFormats"],
            ["application/pdf"],
        )
        self.assertEqual(response.payload["capabilities"]["computeMode"], "cpu")
        self.assertTrue(response.payload["capabilities"]["nativePdfOnly"])
        self.assertFalse(response.payload["capabilities"]["uploadEnabled"])
        self.assertFalse(response.payload["capabilities"]["conversionEnabled"])

    def test_ready_reports_verified_runtime(self) -> None:
        probe = RuntimeProbe(
            True,
            "ready",
            self.config.source_revision,
            self.config.model_revision,
            2,
            "2.13.0+cpu",
        )
        response = route_request(
            "GET", "/ready", self.config, probe=lambda _: probe
        )

        self.assertEqual(response.status, 200)
        self.assertEqual(response.payload["status"], "ready")
        self.assertEqual(response.payload["reason"], "ready")
        self.assertEqual(response.payload["engine"]["verifiedModels"], 2)
        self.assertEqual(response.payload["engine"]["torchVersion"], "2.13.0+cpu")
        self.assertFalse(response.payload["capabilities"]["uploadEnabled"])
        self.assertFalse(response.payload["capabilities"]["conversionEnabled"])

    def test_ready_isolated_failure_returns_503_without_diagnostic(self) -> None:
        sensitive = "TOKEN_DO_NOT_LEAK_123 /private/runtime/path?token=SHOULD_NOT_LEAK"
        probe = RuntimeProbe(
            False,
            "clarity_model_checksum_mismatch:info/yolo.pt",
            self.config.source_revision,
            self.config.model_revision,
            0,
            None,
            sensitive,
        )
        response = route_request(
            "GET", "/ready", self.config, probe=lambda _: probe
        )

        self.assertEqual(response.status, 503)
        self.assertEqual(response.payload["status"], "not_ready")
        self.assertIn("checksum_mismatch", response.payload["reason"])
        self.assertNotIn("diagnostic", response.payload)
        self.assertNotIn(sensitive, repr(response.payload))

    def test_ready_rejects_untrusted_failed_probe_fields(self) -> None:
        sensitive = "TOKEN_DO_NOT_LEAK_123 /private/runtime/path"
        probe = RuntimeProbe(
            False,
            sensitive,
            sensitive,
            sensitive,
            0,
            sensitive,
            sensitive,
        )
        response = route_request(
            "GET", "/ready", self.config, probe=lambda _: probe
        )

        self.assertEqual(response.status, 503)
        self.assertEqual(response.payload["reason"], "clarity_runtime_not_ready")
        self.assertIsNone(response.payload["engine"]["sourceRevision"])
        self.assertIsNone(response.payload["engine"]["modelRevision"])
        self.assertIsNone(response.payload["engine"]["torchVersion"])
        self.assertNotIn(sensitive, repr(response.payload))

    def test_unknown_path_is_not_found(self) -> None:
        response = route_request("GET", "/internal/jobs", self.config)
        self.assertEqual(response.status, 404)
        self.assertEqual(response.payload, {"error": "not_found"})

    def test_mutating_methods_are_not_enabled(self) -> None:
        response = route_request("POST", "/internal/jobs", self.config)
        self.assertEqual(response.status, 405)
        self.assertEqual(response.allow, "GET")
        self.assertEqual(response.payload, {"error": "method_not_allowed"})


if __name__ == "__main__":
    unittest.main()
