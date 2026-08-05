from __future__ import annotations

import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer

from scoremosaic_st_omr import PHASE, SERVICE_NAME
from scoremosaic_st_omr.app import HealthOnlyHandler, health_payload, readiness_payload


class PayloadTests(unittest.TestCase):
    def test_health_payload_is_deterministic(self) -> None:
        payload = health_payload()
        self.assertEqual(payload["status"], "healthy")
        self.assertEqual(payload["service"], SERVICE_NAME)
        self.assertEqual(payload["phase"], PHASE)

        evaluation = payload["fixedEvaluation"]
        self.assertTrue(evaluation["fixedEvaluationEnabled"])
        self.assertFalse(evaluation["realOmrAccuracyMeasured"])
        self.assertFalse(evaluation["generalAccuracyClaim"])
        self.assertFalse(evaluation["modelLoaded"])
        self.assertFalse(evaluation["realOmrInference"])

        offline_runtime = payload["offlineModelRuntime"]
        self.assertTrue(offline_runtime["offlineModelRuntimeEnabled"])
        self.assertTrue(offline_runtime["repositoryTestModelOnly"])
        self.assertFalse(offline_runtime["modelLoaded"])
        self.assertFalse(offline_runtime["inferenceEnabled"])
        self.assertFalse(offline_runtime["realOmrInference"])
        self.assertFalse(offline_runtime["userInputAccepted"])
        self.assertFalse(offline_runtime["httpInferenceEnabled"])
        self.assertFalse(offline_runtime["gatewayIntegration"])
        self.assertFalse(offline_runtime["ensembleIntegration"])
        self.assertFalse(offline_runtime["productionEligible"])

    def test_readiness_is_explicitly_disabled(self) -> None:
        self.assertEqual(
            readiness_payload(),
            {
                "status": "not_ready",
                "service": SERVICE_NAME,
                "phase": PHASE,
                "modelLoaded": False,
                "inferenceEnabled": False,
                "reason": "model_runtime_disabled",
            },
        )


class EndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), HealthOnlyHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def request(
        self,
        method: str,
        path: str,
    ) -> tuple[int, dict[str, object], dict[str, str]]:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        connection.request(method, path)
        response = connection.getresponse()
        body = json.loads(response.read().decode("utf-8"))
        headers = {key.lower(): value for key, value in response.getheaders()}
        connection.close()
        return response.status, body, headers

    def test_health_returns_200_without_loading_model(self) -> None:
        status, body, headers = self.request("GET", "/health")
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "healthy")
        self.assertTrue(body["fixedEvaluation"]["fixedEvaluationEnabled"])
        self.assertTrue(body["offlineModelRuntime"]["offlineModelRuntimeEnabled"])
        self.assertIs(body["offlineModelRuntime"]["modelLoaded"], False)
        self.assertIs(body["offlineModelRuntime"]["inferenceEnabled"], False)
        self.assertEqual(headers["cache-control"], "no-store")

    def test_ready_returns_explanatory_503(self) -> None:
        status, body, _ = self.request("GET", "/ready")
        self.assertEqual(status, 503)
        self.assertEqual(body["status"], "not_ready")
        self.assertIs(body["modelLoaded"], False)
        self.assertIs(body["inferenceEnabled"], False)
        self.assertEqual(body["reason"], "model_runtime_disabled")

    def test_unknown_route_is_not_available(self) -> None:
        status, body, _ = self.request("GET", "/infer")
        self.assertEqual(status, 404)
        self.assertEqual(body["status"], "not_found")

    def test_mutating_methods_are_rejected(self) -> None:
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            with self.subTest(method=method):
                status, body, headers = self.request(method, "/upload")
                self.assertEqual(status, 405)
                self.assertEqual(body["status"], "method_not_allowed")
                self.assertEqual(headers["allow"], "GET")


if __name__ == "__main__":
    unittest.main()
