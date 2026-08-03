from __future__ import annotations

import sys
from pathlib import Path
import unittest
from unittest.mock import patch

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_audiveris.app import route_request
from scoremosaic_audiveris.config import load_config
from scoremosaic_audiveris.runtime import RuntimeProbe


class RouteTests(unittest.TestCase):
    def test_health_reports_runtime_metadata_without_enabling_upload(self) -> None:
        config = load_config(
            {"SCOREMOSAIC_AUDIVERIS_RUNTIME_MODE": "audiveris"}
        )
        with patch.object(Path, "is_file", return_value=True):
            response = route_request("GET", "/health?ignored=1", config)

        self.assertEqual(response.status, 200)
        self.assertTrue(response.payload["engine"]["installed"])
        self.assertEqual(response.payload["engine"]["expectedVersion"], "5.11.0")
        self.assertEqual(
            response.payload["capabilities"]["acceptedInputFormats"],
            ["application/pdf", "image/jpeg", "image/png"],
        )
        self.assertTrue(response.payload["capabilities"]["internalRuntimeEnabled"])
        self.assertFalse(response.payload["capabilities"]["uploadEnabled"])
        self.assertFalse(response.payload["capabilities"]["conversionEnabled"])

    def test_ready_returns_200_for_matching_runtime(self) -> None:
        config = load_config(
            {"SCOREMOSAIC_AUDIVERIS_RUNTIME_MODE": "audiveris"}
        )
        response = route_request(
            "GET",
            "/ready",
            config,
            runtime_probe=lambda _: RuntimeProbe(True, "ready", "5.11.0", True),
        )
        self.assertEqual(response.status, 200)
        self.assertEqual(response.payload["status"], "ready")
        self.assertEqual(response.payload["engine"]["version"], "5.11.0")

    def test_ready_returns_503_for_disabled_runtime(self) -> None:
        config = load_config({})
        response = route_request(
            "GET",
            "/ready",
            config,
            runtime_probe=lambda _: RuntimeProbe(
                False, "audiveris_runtime_disabled", None, False
            ),
        )
        self.assertEqual(response.status, 503)
        self.assertEqual(response.payload["reason"], "audiveris_runtime_disabled")

    def test_unknown_path_is_not_found(self) -> None:
        response = route_request("GET", "/internal/jobs", load_config({}))
        self.assertEqual(response.status, 404)

    def test_mutating_methods_are_not_enabled(self) -> None:
        response = route_request("POST", "/internal/jobs", load_config({}))
        self.assertEqual(response.status, 405)
        self.assertEqual(response.allow, "GET")


if __name__ == "__main__":
    unittest.main()
