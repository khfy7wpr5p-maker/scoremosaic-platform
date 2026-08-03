from __future__ import annotations

import sys
from pathlib import Path
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_gateway.app import route_request
from scoremosaic_gateway.config import load_config


class RouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_config({})

    def test_health_reports_disabled_gateway_and_formats(self) -> None:
        response = route_request("GET", "/health?ignored=1", self.config)

        self.assertEqual(response.status, 200)
        self.assertEqual(response.payload["gateway"], "running")
        self.assertEqual(
            response.payload["capabilities"]["acceptedInputFormats"],
            ["application/pdf", "image/jpeg", "image/png"],
        )
        self.assertFalse(response.payload["capabilities"]["uploadEnabled"])
        self.assertFalse(
            response.payload["capabilities"]["orchestrationEnabled"]
        )
        self.assertTrue(response.payload["capabilities"]["candidateIsolation"])
        self.assertEqual(
            response.payload["engines"],
            {
                "audiveris": "not_ready",
                "homr": "not_ready",
                "clarity": "not_ready",
            },
        )

    def test_ready_is_503_and_includes_isolated_probe_states(self) -> None:
        response = route_request(
            "GET",
            "/ready",
            self.config,
            engine_states={
                "audiveris": "not_ready",
                "homr": "unavailable",
                "clarity": "invalid_response",
            },
        )

        self.assertEqual(response.status, 503)
        self.assertEqual(response.payload["reason"], "orchestration_disabled")
        self.assertEqual(response.payload["engines"]["homr"], "unavailable")

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
