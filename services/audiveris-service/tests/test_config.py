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
        self.assertEqual(config.runtime_mode, "disabled")
        self.assertEqual(config.audiveris_command, Path("/usr/bin/audiveris"))
        self.assertEqual(config.audiveris_version, "5.11.0")
        self.assertEqual(config.probe_timeout_seconds, 20)
        self.assertEqual(config.request_timeout_seconds, 600)

    def test_runtime_can_be_enabled_explicitly(self) -> None:
        config = load_config(
            {"SCOREMOSAIC_AUDIVERIS_RUNTIME_MODE": "audiveris"}
        )
        self.assertEqual(config.runtime_mode, "audiveris")

    def test_invalid_runtime_mode_is_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigError, "disabled or audiveris"):
            load_config({"SCOREMOSAIC_AUDIVERIS_RUNTIME_MODE": "shell"})

    def test_relative_command_is_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigError, "must be absolute"):
            load_config({"SCOREMOSAIC_AUDIVERIS_COMMAND": "audiveris"})

    def test_invalid_version_is_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigError, "VERSION is invalid"):
            load_config({"SCOREMOSAIC_AUDIVERIS_VERSION": "latest"})

    def test_root_workspace_is_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigError, "absolute non-root"):
            load_config({"SCOREMOSAIC_AUDIVERIS_WORKSPACE_ROOT": "/"})

    def test_unapproved_hostname_is_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigError, "approved bind address"):
            load_config({"SCOREMOSAIC_AUDIVERIS_HOST": "example.com"})

    def test_out_of_range_probe_timeout_is_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigError, "between 1 and 120"):
            load_config(
                {"SCOREMOSAIC_AUDIVERIS_PROBE_TIMEOUT_SECONDS": "121"}
            )


if __name__ == "__main__":
    unittest.main()
