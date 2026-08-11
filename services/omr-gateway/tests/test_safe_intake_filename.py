from __future__ import annotations

import sys
from pathlib import Path
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

import scoremosaic_gateway
from scoremosaic_gateway.filename_safety import (
    SafeIntakeFilenameError,
    validate_original_filename,
)
from scoremosaic_gateway.safe_intake import SafeIntakeSignatureError


class SafeIntakeFilenameTests(unittest.TestCase):
    def test_accepts_safe_filename_metadata_for_server_derived_format(self) -> None:
        examples = (
            ("partisyon.PDF", b"%PDF-1.7\nrest"),
            ("öğretmen-notası.JpEg", b"\xff\xd8\xff\xe0rest"),
            ("sayfa-01.PNG", b"\x89PNG\r\n\x1a\nrest"),
            (("a" * 251) + ".pdf", b"%PDF-2.0\rrest"),
        )

        for filename, header in examples:
            with self.subTest(filename=filename):
                self.assertEqual(
                    validate_original_filename(filename, header),
                    filename,
                )

    def test_rejects_traversal_separators_drive_paths_and_device_names(self) -> None:
        unsafe = (
            "../score.pdf",
            "..\\score.pdf",
            "folder/score.pdf",
            "folder\\score.pdf",
            "/score.pdf",
            "\\\\server\\share\\score.pdf",
            "C:\\score.pdf",
            "C:score.pdf",
            "score:stream.pdf",
            "CON.pdf",
            "AUX.jpeg",
            "LPT1.png",
            "COM¹.pdf",
            "COM².pdf",
            "COM³.pdf",
            "LPT¹.pdf",
            "LPT².pdf",
            "LPT³.pdf",
            ".hidden.pdf",
        )

        for filename in unsafe:
            with self.subTest(filename=filename):
                with self.assertRaises(SafeIntakeFilenameError) as raised:
                    validate_original_filename(filename, b"%PDF-1.7\nrest")
                self.assertEqual(raised.exception.code, "filename_path_unsafe")

    def test_rejects_missing_overlong_ambiguous_and_control_metadata(self) -> None:
        invalid = (
            "",
            " score.pdf",
            "score.pdf ",
            "score.pdf.",
            "bad\x00.pdf",
            "bad\n.pdf",
            "bad\u202e.pdf",
            ("a" * 252) + ".pdf",
        )

        for filename in invalid:
            with self.subTest(filename=repr(filename)):
                with self.assertRaises(SafeIntakeFilenameError) as raised:
                    validate_original_filename(filename, b"%PDF-1.7\nrest")
                self.assertEqual(raised.exception.code, "filename_invalid")

        for filename in (None, b"score.pdf", Path("score.pdf")):
            with self.subTest(filename=repr(filename)):
                with self.assertRaises(SafeIntakeFilenameError) as raised:
                    validate_original_filename(  # type: ignore[arg-type]
                        filename,
                        b"%PDF-1.7\nrest",
                    )
                self.assertEqual(raised.exception.code, "filename_invalid")

    def test_rejects_extension_mismatch_without_trusting_extension(self) -> None:
        cases = (
            ("score.jpg", b"%PDF-1.7\nrest"),
            ("score", b"%PDF-1.7\nrest"),
            ("score.gif", b"%PDF-1.7\nrest"),
            ("score.pdf.jpg", b"%PDF-1.7\nrest"),
            ("score.pdf", b"\xff\xd8\xff\xe0rest"),
            ("score.jpeg", b"\x89PNG\r\n\x1a\nrest"),
        )

        for filename, header in cases:
            with self.subTest(filename=filename):
                with self.assertRaises(SafeIntakeFilenameError) as raised:
                    validate_original_filename(filename, header)
                self.assertEqual(
                    raised.exception.code,
                    "filename_extension_mismatch",
                )

    def test_extension_cannot_make_unsupported_content_acceptable(self) -> None:
        with self.assertRaises(SafeIntakeSignatureError) as raised:
            validate_original_filename("renamed.pdf", b"GIF89a")
        self.assertEqual(raised.exception.code, "unsupported_signature")

        with self.assertRaises(SafeIntakeSignatureError) as raised:
            validate_original_filename("truncated.png", b"\x89PNG")
        self.assertEqual(raised.exception.code, "truncated_signature")

    def test_package_exports_b6_public_primitives(self) -> None:
        self.assertIs(
            scoremosaic_gateway.SafeIntakeFilenameError,
            SafeIntakeFilenameError,
        )
        self.assertIs(
            scoremosaic_gateway.validate_original_filename,
            validate_original_filename,
        )


if __name__ == "__main__":
    unittest.main()
