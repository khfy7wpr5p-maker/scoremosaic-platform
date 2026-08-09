from __future__ import annotations

from dataclasses import FrozenInstanceError
import sys
from pathlib import Path
import tomllib
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_gateway.app import ACCEPTED_INPUT_FORMATS
from scoremosaic_gateway.orchestration import ACCEPTED_SOURCE_MEDIA_TYPES
from scoremosaic_gateway.safe_intake import (
    SAFE_INTAKE_MEDIA_TYPES,
    SAFE_INTAKE_POLICY_V1,
    SafeIntakeMediaTypeError,
    SafeIntakeSignatureError,
    SignatureMatch,
    match_input_signature,
    verify_signature_media_type,
)


class SafeIntakePolicyTests(unittest.TestCase):
    def test_v1_policy_is_immutable_and_has_one_canonical_allowlist(self) -> None:
        self.assertEqual(SAFE_INTAKE_POLICY_V1.schema_version, "1.0")
        self.assertEqual(
            SAFE_INTAKE_MEDIA_TYPES,
            ("application/pdf", "image/jpeg", "image/png"),
        )
        self.assertEqual(ACCEPTED_INPUT_FORMATS, SAFE_INTAKE_MEDIA_TYPES)
        self.assertEqual(ACCEPTED_SOURCE_MEDIA_TYPES, SAFE_INTAKE_MEDIA_TYPES)

        with self.assertRaises(FrozenInstanceError):
            SAFE_INTAKE_POLICY_V1.schema_version = "2.0"  # type: ignore[misc]

    def test_package_metadata_allowlist_matches_runtime_policy(self) -> None:
        metadata = tomllib.loads(
            (SERVICE_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )
        self.assertEqual(
            tuple(metadata["tool"]["scoremosaic"]["accepted-input-formats"]),
            SAFE_INTAKE_MEDIA_TYPES,
        )


class FileSignatureTests(unittest.TestCase):
    def test_recognizes_supported_signatures_without_extension_or_mime_trust(
        self,
    ) -> None:
        examples = (
            (b"%PDF-1.7\nrest", "pdf", "application/pdf"),
            (b"%PDF-2.0\r\nrest", "pdf", "application/pdf"),
            (b"\xff\xd8\xff\xe0rest", "jpeg", "image/jpeg"),
            (b"\x89PNG\r\n\x1a\nrest", "png", "image/png"),
        )

        for header, expected_format, expected_media_type in examples:
            with self.subTest(expected_format):
                match = match_input_signature(header)
                self.assertEqual(match.policy_version, "1.0")
                self.assertEqual(match.format_id, expected_format)
                self.assertEqual(match.media_type, expected_media_type)

    def test_accepts_bounded_bytes_like_headers(self) -> None:
        self.assertEqual(
            match_input_signature(bytearray(b"%PDF-1.4\n")).format_id,
            "pdf",
        )
        self.assertEqual(
            match_input_signature(memoryview(b"\x89PNG\r\n\x1a\n")).format_id,
            "png",
        )

    def test_rejects_empty_and_truncated_supported_signatures(self) -> None:
        for header in (b"", b"%", b"%PDF-", b"\xff\xd8", b"\x89PNG\r\n"):
            with self.subTest(header=header):
                with self.assertRaises(SafeIntakeSignatureError) as raised:
                    match_input_signature(header)
                self.assertIn(
                    raised.exception.code,
                    {"empty_header", "truncated_signature"},
                )

    def test_rejects_renamed_or_unsupported_content_fail_closed(self) -> None:
        unsupported = (
            b"not a pdf",
            b"<html></html>",
            b'{"type":"document"}',
            b"GIF89a",
            b"II*\x00",
            b"MM\x00*",
            b"BMrest",
            b"PK\x03\x04",
            b"%PDF-1.9\n",
        )

        for header in unsupported:
            with self.subTest(header=header):
                with self.assertRaises(SafeIntakeSignatureError) as raised:
                    match_input_signature(header)
                self.assertEqual(raised.exception.code, "unsupported_signature")

    def test_rejects_invalid_pdf_version_terminators(self) -> None:
        for header in (
            b"%PDF-1.70",
            b"%PDF-1.7X",
            b"%PDF-2.00",
            b"%PDF-2.0X",
        ):
            with self.subTest(header=header):
                with self.assertRaises(SafeIntakeSignatureError) as raised:
                    match_input_signature(header)
                self.assertEqual(raised.exception.code, "unsupported_signature")

    def test_rejects_text_and_non_byte_memory_views(self) -> None:
        for header in ("%PDF-1.7", [0x25, 0x50, 0x44, 0x46]):
            with self.subTest(header=header):
                with self.assertRaises(TypeError):
                    match_input_signature(header)  # type: ignore[arg-type]

        with self.assertRaises(TypeError):
            match_input_signature(memoryview(bytearray(16)).cast("I"))


class DeclaredMediaTypeTests(unittest.TestCase):
    def test_accepts_supported_declared_media_type_when_signature_matches(self) -> None:
        examples = (
            (b"%PDF-1.7\nrest", "application/pdf", "pdf"),
            (b"\xff\xd8\xff\xe0rest", "IMAGE/JPEG", "jpeg"),
            (b"\x89PNG\r\n\x1a\nrest", "image/png", "png"),
        )

        for header, declared_media_type, expected_format in examples:
            with self.subTest(expected_format):
                verified = verify_signature_media_type(
                    header,
                    declared_media_type,
                )
                self.assertEqual(verified.format_id, expected_format)

    def test_rejects_missing_declared_media_type_fail_closed(self) -> None:
        header = b"%PDF-1.7\nrest"
        for declared_media_type in (None, ""):
            with self.subTest(declared_media_type=declared_media_type):
                with self.assertRaises(SafeIntakeMediaTypeError) as raised:
                    verify_signature_media_type(
                        header,
                        declared_media_type,
                    )
                self.assertEqual(raised.exception.code, "media_type_missing")

    def test_rejects_invalid_declared_media_type_fail_closed(self) -> None:
        header = b"%PDF-1.7\nrest"
        invalid = (
            " application/pdf",
            "application/pdf ",
            "application/pdf; charset=binary",
            "application/pdf,image/png",
            "application//pdf",
            "application",
            "application/",
            "application/p\x00df",
            "应用/pdf",
            "a/" + ("b" * 80),
        )

        for declared_media_type in invalid:
            with self.subTest(declared_media_type=declared_media_type):
                with self.assertRaises(SafeIntakeMediaTypeError) as raised:
                    verify_signature_media_type(
                        header,
                        declared_media_type,
                    )
                self.assertEqual(raised.exception.code, "media_type_invalid")

    def test_rejects_unsupported_declared_media_type_fail_closed(self) -> None:
        header = b"%PDF-1.7\nrest"
        for declared_media_type in ("application/octet-stream", "image/gif"):
            with self.subTest(declared_media_type=declared_media_type):
                with self.assertRaises(SafeIntakeMediaTypeError) as raised:
                    verify_signature_media_type(
                        header,
                        declared_media_type,
                    )
                self.assertEqual(raised.exception.code, "media_type_unsupported")

    def test_rejects_signature_media_type_mismatch_fail_closed(self) -> None:
        header = b"%PDF-1.7\nrest"
        for declared_media_type in ("image/jpeg", "image/png"):
            with self.subTest(declared_media_type=declared_media_type):
                with self.assertRaises(SafeIntakeMediaTypeError) as raised:
                    verify_signature_media_type(
                        header,
                        declared_media_type,
                    )
                self.assertEqual(
                    raised.exception.code,
                    "signature_media_type_mismatch",
                )

    def test_rejects_fabricated_signature_match_as_byte_evidence(self) -> None:
        fabricated = SignatureMatch(
            policy_version="1.0",
            format_id="png",
            media_type="image/png",
        )

        with self.assertRaises(TypeError):
            verify_signature_media_type(
                fabricated,  # type: ignore[arg-type]
                "image/png",
            )


if __name__ == "__main__":
    unittest.main()
