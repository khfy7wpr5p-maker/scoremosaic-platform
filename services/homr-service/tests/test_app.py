from __future__ import annotations

import sys
from pathlib import Path
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_homr.app import route_request
from scoremosaic_homr.config import load_config
from scoremosaic_homr.runtime import RuntimeProbe


class RouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.disabled_config = load_config({})
        self.runtime_config = load_config({"SCOREMOSAIC_HOMR_RUNTIME_MODE": "homr"})

    def test_health_reports_runtime_metadata_without_enabling_upload(self) -> None:
        response = route_request("GET", "/health?ignored=1", self.runtime_config)

        self.assertEqual(response.status, 200)
        self.assertEqual(response.payload["status"], "ok")
        self.assertTrue(response.payload["engine"]["installed"])
        self.assertEqual(response.payload["engine"]["expectedVersion"], "0.7.0")
        self.assertEqual(response.payload["engine"]["expectedModels"], 3)
        self.assertEqual(
            response.payload["capabilities"]["acceptedInputFormats"],
            ["image/jpeg", "image/png"],
        )
        self.assertFalse(response.payload["capabilities"]["uploadEnabled"])
        self.assertFalse(response.payload["capabilities"]["conversionEnabled"])

    def test_ready_returns_503_for_disabled_runtime(self) -> None:
        response = route_request("GET", "/ready", self.disabled_config)

        self.assertEqual(response.status, 503)
        self.assertEqual(response.payload["reason"], "homr_runtime_disabled")
        self.assertEqual(response.payload["engine"]["verifiedModels"], 0)

    def test_ready_returns_200_for_verified_runtime(self) -> None:
        response = route_request(
            "GET",
            "/ready",
            self.runtime_config,
            runtime_probe=lambda _: RuntimeProbe(True, "ready", "0.7.0", 3),
        )

        self.assertEqual(response.status, 200)
        self.assertEqual(response.payload["status"], "ready")
        self.assertEqual(response.payload["engine"]["version"], "0.7.0")
        self.assertEqual(response.payload["engine"]["verifiedModels"], 3)

    def test_unknown_path_is_not_found(self) -> None:
        response = route_request("GET", "/internal/jobs", self.disabled_config)
        self.assertEqual(response.status, 404)
        self.assertEqual(response.payload, {"error": "not_found"})

    def test_mutating_methods_are_not_enabled(self) -> None:
        response = route_request("POST", "/internal/jobs", self.disabled_config)
        self.assertEqual(response.status, 405)
        self.assertEqual(response.allow, "GET")
        self.assertEqual(response.payload, {"error": "method_not_allowed"})


if __name__ == "__main__":
    unittest.main()
