from __future__ import annotations

import sys
from pathlib import Path
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_gateway.config import ConfigError, load_config


class ServiceConfigTests(unittest.TestCase):
    def test_defaults_are_bounded_and_disabled(self) -> None:
        config = load_config({})

        self.assertEqual(config.host, "127.0.0.1")
        self.assertEqual(config.port, 8090)
        self.assertEqual(config.log_level, "INFO")
        self.assertEqual(config.orchestration_mode, "disabled")
        self.assertEqual(config.probe_timeout_seconds, 1)
        self.assertEqual(config.max_request_bytes, 20 * 1024 * 1024)
        self.assertEqual(config.max_pages, 40)
        self.assertEqual(config.max_image_pixels, 80_000_000)
        self.assertTrue(config.workspace_root.is_absolute())
        self.assertEqual(
            [endpoint.name for endpoint in config.engine_endpoints],
            ["audiveris", "homr", "clarity"],
        )

    def test_container_bind_address_is_allowed(self) -> None:
        config = load_config({"SCOREMOSAIC_GATEWAY_HOST": "0.0.0.0"})
        self.assertEqual(config.host, "0.0.0.0")

    def test_orchestration_cannot_be_enabled(self) -> None:
        with self.assertRaisesRegex(ConfigError, "must remain disabled"):
            load_config({"SCOREMOSAIC_GATEWAY_ORCHESTRATION_MODE": "enabled"})

    def test_unapproved_bind_address_is_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigError, "approved bind address"):
            load_config({"SCOREMOSAIC_GATEWAY_HOST": "gateway.example.com"})

    def test_engine_url_credentials_are_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigError, "must not include credentials"):
            load_config(
                {
                    "SCOREMOSAIC_GATEWAY_HOMR_BASE_URL":
                        "http://user:password@homr-foundation:8080"
                }
            )

    def test_engine_url_path_is_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigError, "must not include a path"):
            load_config(
                {
                    "SCOREMOSAIC_GATEWAY_CLARITY_BASE_URL":
                        "http://clarity-foundation:8081/private"
                }
            )

    def test_invalid_scheme_is_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigError, "must use http or https"):
            load_config(
                {
                    "SCOREMOSAIC_GATEWAY_AUDIVERIS_BASE_URL":
                        "file:///tmp/audiveris"
                }
            )

    def test_out_of_range_probe_timeout_is_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigError, "between 1 and 10"):
            load_config({"SCOREMOSAIC_GATEWAY_PROBE_TIMEOUT_SECONDS": "11"})

    def test_non_integer_port_is_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigError, "must be an integer"):
            load_config({"SCOREMOSAIC_GATEWAY_PORT": "nine"})

    def test_relative_workspace_is_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigError, "must be absolute"):
            load_config(
                {"SCOREMOSAIC_GATEWAY_WORKSPACE_ROOT": "relative/workspace"}
            )


if __name__ == "__main__":
    unittest.main()
