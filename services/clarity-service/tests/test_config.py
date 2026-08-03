from __future__ import annotations

import sys
from pathlib import Path
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_clarity.config import ConfigError, load_config


class ServiceConfigTests(unittest.TestCase):
    def test_defaults_are_bounded_and_disabled(self) -> None:
        config = load_config({})

        self.assertEqual(config.host, "127.0.0.1")
        self.assertEqual(config.port, 8081)
        self.assertEqual(config.log_level, "INFO")
        self.assertEqual(config.compute_mode, "disabled")
        self.assertEqual(config.source_revision, "c6bb8a4d2a5b52842a9c41bd0f761f58d02f6f82")
        self.assertEqual(config.model_revision, "ee14c1e41ab371fe27bf8a2707ea588560077e73")
        self.assertEqual(config.probe_timeout_seconds, 90)
        self.assertEqual(config.max_request_bytes, 20 * 1024 * 1024)
        self.assertEqual(config.max_pages, 40)
        self.assertEqual(config.max_image_pixels, 80_000_000)
        self.assertEqual(config.request_timeout_seconds, 1200)
        self.assertEqual(config.pdf_dpi, 300)
        self.assertEqual(config.beam_width, 2)
        self.assertTrue(config.workspace_root.is_absolute())
        self.assertTrue(config.source_root.is_absolute())

    def test_cpu_compute_mode_is_allowed(self) -> None:
        config = load_config({"SCOREMOSAIC_CLARITY_COMPUTE_MODE": "cpu"})
        self.assertEqual(config.compute_mode, "cpu")

    def test_internal_container_bind_address_is_allowed(self) -> None:
        config = load_config({"SCOREMOSAIC_CLARITY_HOST": "0.0.0.0"})
        self.assertEqual(config.host, "0.0.0.0")

    def test_unapproved_hostname_is_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigError, "approved bind address"):
            load_config({"SCOREMOSAIC_CLARITY_HOST": "example.com"})

    def test_gpu_compute_mode_is_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigError, "disabled or cpu"):
            load_config({"SCOREMOSAIC_CLARITY_COMPUTE_MODE": "gpu"})

    def test_invalid_source_revision_is_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigError, "40-character"):
            load_config({"SCOREMOSAIC_CLARITY_SOURCE_REVISION": "main"})

    def test_out_of_range_page_limit_is_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigError, "between 1 and 200"):
            load_config({"SCOREMOSAIC_CLARITY_MAX_PAGES": "0"})

    def test_out_of_range_pixel_limit_is_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigError, "between 1000000 and 200000000"):
            load_config({"SCOREMOSAIC_CLARITY_MAX_IMAGE_PIXELS": "999999"})

    def test_non_integer_limit_is_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigError, "must be an integer"):
            load_config({"SCOREMOSAIC_CLARITY_PORT": "eight"})

    def test_relative_workspace_is_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigError, "absolute non-root"):
            load_config({"SCOREMOSAIC_CLARITY_WORKSPACE_ROOT": "relative/path"})

    def test_root_source_path_is_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigError, "absolute non-root"):
            load_config({"SCOREMOSAIC_CLARITY_SOURCE_ROOT": "/"})


if __name__ == "__main__":
    unittest.main()
