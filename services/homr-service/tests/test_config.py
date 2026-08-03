from __future__ import annotations

import sys
from pathlib import Path
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_homr.config import ConfigError, load_config


class ServiceConfigTests(unittest.TestCase):
    def test_defaults_are_bounded_and_local(self) -> None:
        config = load_config({})

        self.assertEqual(config.host, "127.0.0.1")
        self.assertEqual(config.port, 8080)
        self.assertEqual(config.log_level, "INFO")
        self.assertEqual(config.max_request_bytes, 20 * 1024 * 1024)
        self.assertEqual(config.max_pages, 40)
        self.assertEqual(config.request_timeout_seconds, 120)
        self.assertTrue(config.workspace_root.is_absolute())

    def test_internal_container_bind_address_is_allowed(self) -> None:
        config = load_config({"SCOREMOSAIC_HOMR_HOST": "0.0.0.0"})
        self.assertEqual(config.host, "0.0.0.0")

    def test_unapproved_hostname_is_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigError, "approved bind address"):
            load_config({"SCOREMOSAIC_HOMR_HOST": "example.com"})

    def test_out_of_range_limits_are_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigError, "between 1 and 200"):
            load_config({"SCOREMOSAIC_HOMR_MAX_PAGES": "0"})

    def test_non_integer_limit_is_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigError, "must be an integer"):
            load_config({"SCOREMOSAIC_HOMR_PORT": "eight"})

    def test_relative_workspace_is_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigError, "must be absolute"):
            load_config({"SCOREMOSAIC_HOMR_WORKSPACE_ROOT": "relative/path"})


if __name__ == "__main__":
    unittest.main()
