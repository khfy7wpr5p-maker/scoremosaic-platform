from __future__ import annotations

import io
import sys
from pathlib import Path
import unittest
from urllib.error import HTTPError, URLError

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_gateway.config import EngineEndpoint
from scoremosaic_gateway.engine_client import probe_engine, probe_engines


class FakeResponse:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = io.BytesIO(body)

    def read(self, amount: int = -1) -> bytes:
        return self._body.read(amount)

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None


class EngineProbeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.endpoint = EngineEndpoint("homr", "http://homr-foundation:8080")

    def test_ready_engine_is_reported(self) -> None:
        def opener(request: object, timeout: int) -> FakeResponse:
            self.assertEqual(timeout, 2)
            return FakeResponse(200, b'{"status":"ready"}')

        result = probe_engine(self.endpoint, 2, opener=opener)
        self.assertEqual(result.status, "ready")
        self.assertEqual(result.http_status, 200)

    def test_503_engine_is_not_ready(self) -> None:
        def opener(request: object, timeout: int) -> FakeResponse:
            raise HTTPError(
                "http://homr-foundation:8080/ready",
                503,
                "not ready",
                {},
                None,
            )

        result = probe_engine(self.endpoint, 2, opener=opener)
        self.assertEqual(result.status, "not_ready")
        self.assertEqual(result.http_status, 503)

    def test_connection_failure_is_isolated(self) -> None:
        def opener(request: object, timeout: int) -> FakeResponse:
            raise URLError("offline")

        result = probe_engine(self.endpoint, 2, opener=opener)
        self.assertEqual(result.status, "unavailable")
        self.assertIsNone(result.http_status)

    def test_invalid_json_is_rejected(self) -> None:
        def opener(request: object, timeout: int) -> FakeResponse:
            return FakeResponse(200, b"not-json")

        result = probe_engine(self.endpoint, 2, opener=opener)
        self.assertEqual(result.status, "invalid_response")

    def test_multiple_engines_keep_separate_results(self) -> None:
        endpoints = (
            EngineEndpoint("audiveris", "http://audiveris-foundation:8082"),
            EngineEndpoint("homr", "http://homr-foundation:8080"),
        )

        def opener(request: object, timeout: int) -> FakeResponse:
            return FakeResponse(200, b'{"status":"ready"}')

        results = probe_engines(endpoints, 1, opener=opener)
        self.assertEqual(set(results), {"audiveris", "homr"})
        self.assertIsNot(results["audiveris"], results["homr"])


if __name__ == "__main__":
    unittest.main()
