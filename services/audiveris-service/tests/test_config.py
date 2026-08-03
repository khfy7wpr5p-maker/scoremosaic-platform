from __future__ import annotations

import sys
from pathlib import Path
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_audiveris.config import ConfigError, load_config


class ServiceConfigTests(unittest.TestCase):
    def test_defaults_are_bounded_and_disabled(self) -> None:
        config = load_config({})

        self.assertEqual(config.host, "127.0.0.1")
        self.assertEqual(config.port, 8082)
        self.assertEqual(config.log_level, "INFO")
        self.assertEqual(config.runtime_mode, "disabled")
        self.assertEqual(config.max_request_bytes, 20 * 1024 * 1024)
        self.assertEqual(config.max_pages, 40)
        self.assertEqual(config.max_image_pixels, 80_000_000)
        self.assertEqual(config.request_timeout_seconds, 300)
        self.assertTrue(config.workspace_root.is_absolute())

    def test_internal_container_bind_address_is_allowed(self) -> None:
        config = load_config({"SCOREMOSAIC_AUDIVERIS_HOST": "0.0.0.0"})
        self.assertEqual(config.host, "0.0.0.0")

    def test_unapproved_hostname_is_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigError, "approved bind address"):
            load_config({"SCOREMOSAIC_AUDIVERIS_HOST": "example.com"})

    def test_runtime_mode_cannot_enable_java(self) -> None:
        with self.assertRaisesRegex(ConfigError, "must remain disabled"):
            load_config({"SCOREMOSAIC_AUDIVERIS_RUNTIME_MODE": "java"})

    def test_out_of_range_page_limit_is_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigError, "between 1 and 200"):
            load_config({"SCOREMOSAIC_AUDIVERIS_MAX_PAGES": "0"})

    def test_out_of_range_pixel_limit_is_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigError, "between 1000000 and 200000000"):
            load_config({"SCOREMOSAIC_AUDIVERIS_MAX_IMAGE_PIXELS": "999999"})

    def test_non_integer_limit_is_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigError, "must be an integer"):
            load_config({"SCOREMOSAIC_AUDIVERIS_PORT": "eight"})

    def test_relative_workspace_is_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigError, "must be absolute"):
            load_config(
                {"SCOREMOSAIC_AUDIVERIS_WORKSPACE_ROOT": "relative/path"}
            )


if __name__ == "__main__":
    unittest.main()
