from __future__ import annotations

import sys
from pathlib import Path
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_audiveris.app import route_request
from scoremosaic_audiveris.config import load_config


class RouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_config({})

    def test_health_reports_disabled_engine_and_declared_formats(self) -> None:
        response = route_request("GET", "/health?ignored=1", self.config)

        self.assertEqual(response.status, 200)
        self.assertEqual(response.payload["status"], "ok")
        self.assertFalse(response.payload["engine"]["installed"])
        self.assertFalse(response.payload["engine"]["javaRuntimeEnabled"])
        self.assertEqual(
            response.payload["capabilities"]["acceptedInputFormats"],
            ["application/pdf", "image/jpeg", "image/png"],
        )
        self.assertEqual(
            response.payload["capabilities"]["runtimeMode"], "disabled"
        )
        self.assertFalse(response.payload["capabilities"]["uploadEnabled"])
        self.assertFalse(response.payload["capabilities"]["conversionEnabled"])

    def test_ready_is_false_until_audiveris_is_installed(self) -> None:
        response = route_request("GET", "/ready", self.config)

        self.assertEqual(response.status, 503)
        self.assertEqual(response.payload["reason"], "audiveris_engine_not_installed")
        self.assertFalse(response.payload["capabilities"]["uploadEnabled"])
        self.assertFalse(response.payload["capabilities"]["conversionEnabled"])

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
