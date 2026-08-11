from __future__ import annotations

import base64
from dataclasses import FrozenInstanceError
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

import scoremosaic_gateway
from scoremosaic_gateway.filename_safety import SafeIntakeFilenameError
from scoremosaic_gateway.intake_decision import (
    SafeIntakeDecision,
    SafeIntakeDecisionError,
    decide_safe_intake,
)
from scoremosaic_gateway.safe_intake import (
    ImageInspectionResult,
    SafeIntakeByteBudgetError,
    SafeIntakeImageError,
    SafeIntakeMediaTypeError,
    SafeIntakePdfError,
    SafeIntakeSignatureError,
)


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAAAAAA6fptVAAAACklEQVR4nGNgAAAAAgABSK+kcQAAAABJRU5ErkJggg=="
)

JPEG_1X1 = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwD3+iiigD//2Q=="
)


def _serialize_pdf_objects(objects: list[bytes]) -> bytes:
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for object_number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{object_number} 0 obj\n".encode("ascii"))
        output.extend(body)
        output.extend(b"\nendobj\n")

    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(output)


def _build_pdf(page_count: int) -> bytes:
    kids = " ".join(f"{index} 0 R" for index in range(3, 3 + page_count))
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {page_count} >>".encode("ascii"),
    ]
    for _ in range(page_count):
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << >> >>"
        )
    return _serialize_pdf_objects(objects)


class IntegratedSafeIntakeDecisionTests(unittest.TestCase):
    def test_accepts_pdf_jpeg_and_png_with_bounded_server_evidence(self) -> None:
        pdf = _build_pdf(1)
        pdf_decision = decide_safe_intake(
            pdf,
            original_filename="score.pdf",
            declared_media_type="application/pdf",
            max_bytes=len(pdf),
            max_pages=1,
        )
        self.assertEqual(
            (
                pdf_decision.policy_version,
                pdf_decision.format_id,
                pdf_decision.media_type,
                pdf_decision.observed_bytes,
                pdf_decision.page_count,
            ),
            ("1.0", "pdf", "application/pdf", len(pdf), 1),
        )
        self.assertIsNone(pdf_decision.image_pixel_count)

        image_examples = (
            ("scan.jpeg", "image/jpeg", JPEG_1X1, "jpeg"),
            ("scan.png", "image/png", PNG_1X1, "png"),
        )
        for filename, media_type, payload, format_id in image_examples:
            with self.subTest(format_id=format_id):
                decision = decide_safe_intake(
                    payload,
                    original_filename=filename,
                    declared_media_type=media_type,
                    max_bytes=len(payload),
                    max_pages=1,
                )
                self.assertEqual(decision.format_id, format_id)
                self.assertEqual(decision.media_type, media_type)
                self.assertEqual(decision.observed_bytes, len(payload))
                self.assertEqual(
                    (decision.image_width, decision.image_height, decision.image_pixel_count),
                    (1, 1, 1),
                )
                self.assertIsNone(decision.page_count)

    def test_decision_is_immutable_and_retains_no_payload_or_filename(self) -> None:
        decision = decide_safe_intake(
            PNG_1X1,
            original_filename="scan.png",
            declared_media_type="image/png",
            max_bytes=len(PNG_1X1),
            max_pages=1,
        )
        with self.assertRaises(FrozenInstanceError):
            decision.format_id = "pdf"  # type: ignore[misc]
        self.assertFalse(hasattr(decision, "payload"))
        self.assertFalse(hasattr(decision, "original_filename"))

    def test_requires_exact_immutable_bytes(self) -> None:
        for payload in (bytearray(PNG_1X1), memoryview(PNG_1X1), "not-bytes"):
            with self.subTest(payload_type=type(payload).__name__):
                with self.assertRaises(SafeIntakeDecisionError) as raised:
                    decide_safe_intake(  # type: ignore[arg-type]
                        payload,
                        original_filename="scan.png",
                        declared_media_type="image/png",
                        max_bytes=len(PNG_1X1),
                        max_pages=1,
                    )
                self.assertEqual(raised.exception.code, "intake_payload_invalid")

    def test_byte_budget_rejects_before_downstream_evidence_checks(self) -> None:
        payload = _build_pdf(1)
        with (
            patch("scoremosaic_gateway.intake_decision.verify_signature_media_type") as media,
            patch("scoremosaic_gateway.intake_decision.validate_original_filename") as filename,
            patch("scoremosaic_gateway.intake_decision.inspect_pdf_pages") as pdf_inspector,
            patch("scoremosaic_gateway.intake_decision.inspect_image_pixels") as image_inspector,
        ):
            with self.assertRaises(SafeIntakeByteBudgetError) as raised:
                decide_safe_intake(
                    payload,
                    original_filename="score.pdf",
                    declared_media_type="application/pdf",
                    max_bytes=len(payload) - 1,
                    max_pages=1,
                )
            self.assertEqual(raised.exception.code, "byte_budget_exceeded")
            media.assert_not_called()
            filename.assert_not_called()
            pdf_inspector.assert_not_called()
            image_inspector.assert_not_called()

    def test_rejects_mime_and_filename_mismatch_without_extension_trust(self) -> None:
        pdf = _build_pdf(1)
        with self.assertRaises(SafeIntakeMediaTypeError) as raised:
            decide_safe_intake(
                pdf,
                original_filename="score.pdf",
                declared_media_type="image/png",
                max_bytes=len(pdf),
                max_pages=1,
            )
        self.assertEqual(raised.exception.code, "signature_media_type_mismatch")

        with self.assertRaises(SafeIntakeFilenameError) as raised:
            decide_safe_intake(
                PNG_1X1,
                original_filename="renamed.pdf",
                declared_media_type="image/png",
                max_bytes=len(PNG_1X1),
                max_pages=1,
            )
        self.assertEqual(raised.exception.code, "filename_extension_mismatch")

    def test_rejects_unsupported_and_malformed_content_fail_closed(self) -> None:
        with self.assertRaises(SafeIntakeSignatureError) as raised:
            decide_safe_intake(
                b"GIF89a",
                original_filename="renamed.png",
                declared_media_type="image/png",
                max_bytes=6,
                max_pages=1,
            )
        self.assertEqual(raised.exception.code, "unsupported_signature")

        malformed_pdf = b"%PDF-1.7\nnot-a-valid-pdf\n"
        with self.assertRaises(SafeIntakePdfError) as raised:
            decide_safe_intake(
                malformed_pdf,
                original_filename="broken.pdf",
                declared_media_type="application/pdf",
                max_bytes=len(malformed_pdf),
                max_pages=1,
            )
        self.assertEqual(raised.exception.code, "pdf_structure_invalid")

        truncated_png = PNG_1X1[:-8]
        with self.assertRaises(SafeIntakeImageError) as raised:
            decide_safe_intake(
                truncated_png,
                original_filename="broken.png",
                declared_media_type="image/png",
                max_bytes=len(truncated_png),
                max_pages=1,
            )
        self.assertEqual(raised.exception.code, "image_structure_invalid")

    def test_pdf_page_budget_propagates_fail_closed(self) -> None:
        pdf = _build_pdf(2)
        with self.assertRaises(SafeIntakePdfError) as raised:
            decide_safe_intake(
                pdf,
                original_filename="two-pages.pdf",
                declared_media_type="application/pdf",
                max_bytes=len(pdf),
                max_pages=1,
            )
        self.assertEqual(raised.exception.code, "pdf_page_budget_exceeded")

    def test_routes_only_to_the_matching_format_inspector(self) -> None:
        pdf = _build_pdf(1)
        with (
            patch("scoremosaic_gateway.intake_decision.inspect_pdf_pages", return_value=1) as pdf_inspector,
            patch("scoremosaic_gateway.intake_decision.inspect_image_pixels") as image_inspector,
        ):
            decision = decide_safe_intake(
                pdf,
                original_filename="score.pdf",
                declared_media_type="application/pdf",
                max_bytes=len(pdf),
                max_pages=1,
            )
            self.assertEqual(decision.format_id, "pdf")
            pdf_inspector.assert_called_once_with(pdf, max_pages=1)
            image_inspector.assert_not_called()

        with (
            patch("scoremosaic_gateway.intake_decision.inspect_pdf_pages") as pdf_inspector,
            patch(
                "scoremosaic_gateway.intake_decision.inspect_image_pixels",
                return_value=ImageInspectionResult("png", 1, 1, 1),
            ) as image_inspector,
        ):
            decision = decide_safe_intake(
                PNG_1X1,
                original_filename="scan.png",
                declared_media_type="image/png",
                max_bytes=len(PNG_1X1),
                max_pages=1,
            )
            self.assertEqual(decision.format_id, "png")
            image_inspector.assert_called_once_with(PNG_1X1)
            pdf_inspector.assert_not_called()

    def test_package_exports_integrated_public_primitives(self) -> None:
        self.assertIs(scoremosaic_gateway.SafeIntakeDecision, SafeIntakeDecision)
        self.assertIs(
            scoremosaic_gateway.SafeIntakeDecisionError,
            SafeIntakeDecisionError,
        )
        self.assertIs(scoremosaic_gateway.decide_safe_intake, decide_safe_intake)


if __name__ == "__main__":
    unittest.main()
