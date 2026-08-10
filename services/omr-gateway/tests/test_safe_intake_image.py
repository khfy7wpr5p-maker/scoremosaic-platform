from __future__ import annotations

import base64
import inspect
from pathlib import Path
import subprocess
import sys
import tomllib
import unittest
from unittest import mock


SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_gateway import safe_intake


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAAAAAA6fptVAAAACklEQVR4nGNgAAAAAgABSK+kcQAAAABJRU5ErkJggg=="
)

JPEG_1X1 = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwD3+iiigD//2Q=="
)

APNG_1X1_TWO_FRAMES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAACGFjVEwAAAACAAAAAPONk3AAAAAaZmNUTAAAAAAAAAABAAAAAQAAAAAAAAAAAAEACgAAWn8w0AAAAA1JREFUeJxjYGBg+A8AAQQBAF/lw0sAAAAaZmNUTAAAAAEAAAABAAAAAQAAAAAAAAAAAAEACgAAwQzaBAAAABFmZEFUAAAAAnicY/j///9/AAn7A/05ik3zAAAAAElFTkSuQmCC"
)


class GateB5ImagePixelContractTests(unittest.TestCase):
    def _error_type(self):
        error_type = getattr(safe_intake, "SafeIntakeImageError", None)
        self.assertIsNotNone(error_type, "Gate B.5 image error type is not implemented")
        return error_type

    def _inspect(self, payload: bytes):
        inspector = getattr(safe_intake, "inspect_image_pixels", None)
        self.assertIsNotNone(inspector, "Gate B.5 image inspector is not implemented")
        return inspector(payload)

    def _validate_dimensions(self, width: object, height: object):
        validator = getattr(safe_intake, "_validate_image_dimensions", None)
        self.assertIsNotNone(
            validator,
            "Gate B.5 server-owned dimension validator is not implemented",
        )
        return validator(width, height)

    def test_server_owned_b5_limits_are_exact(self) -> None:
        self.assertEqual(
            getattr(safe_intake, "_ABSOLUTE_MAX_IMAGE_DIMENSION", None),
            12_000,
        )
        self.assertEqual(
            getattr(safe_intake, "_ABSOLUTE_MAX_IMAGE_PIXELS", None),
            40_000_000,
        )
        self.assertEqual(
            getattr(safe_intake, "_IMAGE_INSPECTION_TIMEOUT_SECONDS", None),
            3,
        )

    def test_dimension_and_pixel_exact_boundaries(self) -> None:
        self.assertEqual(self._validate_dimensions(1, 1), 1)
        self.assertEqual(self._validate_dimensions(12_000, 1), 12_000)
        self.assertEqual(self._validate_dimensions(1, 12_000), 12_000)
        self.assertEqual(
            self._validate_dimensions(10_000, 4_000),
            40_000_000,
        )

        error_type = self._error_type()

        for width, height in ((12_001, 1), (1, 12_001)):
            with self.subTest(width=width, height=height):
                with self.assertRaises(error_type) as raised:
                    self._validate_dimensions(width, height)
                self.assertEqual(
                    raised.exception.code,
                    "image_dimension_budget_exceeded",
                )

        with self.assertRaises(error_type) as raised:
            self._validate_dimensions(8_000, 5_001)
        self.assertEqual(
            raised.exception.code,
            "image_pixel_budget_exceeded",
        )

    def test_rejects_invalid_dimensions_fail_closed(self) -> None:
        error_type = self._error_type()

        for width, height in (
            (0, 1),
            (1, 0),
            (-1, 1),
            (1, -1),
            (True, 1),
            (1, False),
            (1.0, 1),
            (1, "1"),
        ):
            with self.subTest(width=width, height=height):
                with self.assertRaises(error_type) as raised:
                    self._validate_dimensions(width, height)
                self.assertEqual(raised.exception.code, "image_structure_invalid")

    def test_accepts_valid_static_png_and_jpeg(self) -> None:
        png = self._inspect(PNG_1X1)
        self.assertEqual(
            (png.format_id, png.width, png.height, png.pixel_count),
            ("png", 1, 1, 1),
        )

        jpeg = self._inspect(JPEG_1X1)
        self.assertEqual(
            (jpeg.format_id, jpeg.width, jpeg.height, jpeg.pixel_count),
            ("jpeg", 1, 1, 1),
        )

    def test_rejects_truncated_png_and_jpeg_fail_closed(self) -> None:
        error_type = self._error_type()

        for payload in (PNG_1X1[:-8], JPEG_1X1[:-2]):
            with self.subTest(prefix=payload[:8]):
                with self.assertRaises(error_type) as raised:
                    self._inspect(payload)
                self.assertEqual(raised.exception.code, "image_structure_invalid")

    def test_rejects_apng_animation(self) -> None:
        error_type = self._error_type()

        with self.assertRaises(error_type) as raised:
            self._inspect(APNG_1X1_TWO_FRAMES)

        self.assertEqual(
            raised.exception.code,
            "image_animation_unsupported",
        )

    def test_rejects_mutable_image_buffers(self) -> None:
        error_type = self._error_type()

        for payload in (bytearray(PNG_1X1), memoryview(PNG_1X1)):
            with self.subTest(type=type(payload).__name__):
                with self.assertRaises(error_type) as raised:
                    self._inspect(payload)  # type: ignore[arg-type]
                self.assertEqual(raised.exception.code, "image_structure_invalid")

    def test_public_inspector_accepts_no_caller_dimensions(self) -> None:
        inspector = getattr(safe_intake, "inspect_image_pixels", None)
        self.assertIsNotNone(inspector, "Gate B.5 image inspector is not implemented")

        parameters = tuple(inspect.signature(inspector).parameters)
        self.assertEqual(parameters, ("image_bytes",))

    def test_timeout_maps_to_stable_fail_closed_error(self) -> None:
        error_type = self._error_type()

        with mock.patch.object(
            safe_intake.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(
                cmd=["image_inspector_worker"],
                timeout=3,
            ),
        ):
            with self.assertRaises(error_type) as raised:
                self._inspect(PNG_1X1)

        self.assertEqual(raised.exception.code, "image_inspection_timeout")

    def test_pillow_dependency_is_exact_pinned(self) -> None:
        metadata = tomllib.loads(
            (SERVICE_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )
        dependencies = metadata["project"]["dependencies"]

        self.assertIn("pypdf==6.14.2", dependencies)
        self.assertIn("Pillow==12.3.0", dependencies)

    def test_private_image_worker_boundary_exists(self) -> None:
        worker = (
            SERVICE_ROOT
            / "src"
            / "scoremosaic_gateway"
            / "image_inspector_worker.py"
        )
        self.assertTrue(worker.is_file())


if __name__ == "__main__":
    unittest.main()
