from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from scoremosaic_st_omr import PHASE
from scoremosaic_st_omr.app import health_payload, readiness_payload
from scoremosaic_st_omr.runtime import load_runtime_limits, runtime_evidence


class ModelFreeRuntimeHarnessTests(unittest.TestCase):
    def test_runtime_evidence_keeps_model_and_network_disabled(self) -> None:
        evidence = runtime_evidence()
        self.assertEqual(evidence["devicePolicy"], "cpu_only")
        self.assertIs(evidence["gpuEnabled"], False)
        self.assertIs(evidence["modelLoadingEnabled"], False)
        self.assertIs(evidence["inferenceEnabled"], False)
        self.assertIs(evidence["outboundNetworkEnabled"], False)

    def test_default_limits_are_bounded(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            limits = load_runtime_limits()
        self.assertEqual(limits.max_workers, 1)
        self.assertEqual(limits.max_memory_mb, 512)
        self.assertEqual(limits.max_temp_mb, 256)
        self.assertEqual(limits.operation_timeout_seconds, 30)

    def test_invalid_limits_fail_closed(self) -> None:
        with patch.dict(os.environ, {"ST_OMR_MAX_WORKERS": "0"}, clear=True):
            with self.assertRaisesRegex(ValueError, "between 1 and 4"):
                load_runtime_limits()
        with patch.dict(os.environ, {"ST_OMR_MAX_MEMORY_MB": "unbounded"}, clear=True):
            with self.assertRaisesRegex(ValueError, "must be an integer"):
                load_runtime_limits()

    def test_health_exposes_runtime_evidence_without_readiness(self) -> None:
        health = health_payload()
        self.assertEqual(health["status"], "healthy")
        self.assertEqual(health["phase"], PHASE)
        self.assertIn("runtime", health)

        ready = readiness_payload()
        self.assertEqual(ready["status"], "not_ready")
        self.assertIs(ready["modelLoaded"], False)
        self.assertIs(ready["inferenceEnabled"], False)
        self.assertEqual(ready["reason"], "model_runtime_disabled")


if __name__ == "__main__":
    unittest.main()
