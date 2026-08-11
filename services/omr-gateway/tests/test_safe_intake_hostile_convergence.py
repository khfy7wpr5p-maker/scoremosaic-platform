from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_gateway import image_inspector_worker, pdf_inspector_worker
from scoremosaic_gateway.filename_safety import SafeIntakeFilenameError
from scoremosaic_gateway.intake_decision import (
    SafeIntakeDecisionError,
    decide_safe_intake,
)
from scoremosaic_gateway.safe_intake import (
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

APNG_1X1_TWO_FRAMES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAACGFjVEwAAAACAAAAAPONk3AAAAAaZmNUTAAAAAAAAAABAAAAAQAAAAAAAAAAAAEACgAAWn8w0AAAAA1JREFUeJxjYGBg+A8AAQQBAF/lw0sAAAAaZmNUTAAAAAEAAAABAAAAAQAAAAAAAAAAAAEACgAAwQzaBAAAABFmZEFUAAAAAnicY/j///9/AAn7A/05ik3zAAAAAElFTkSuQmCC"
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
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {page_count} >>".encode("ascii"),
    ]
    for _ in range(page_count):
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << >> >>"
        )
    return _serialize_pdf_objects(objects)


def _build_pdf_with_missing_contents_reference() -> bytes:
    return _serialize_pdf_objects(
        [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            (
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                b"/Resources << >> /Contents 99 0 R >>"
            ),
        ]
    )


def _build_encrypted_pdf() -> bytes:
    from pypdf import PdfWriter

    stream = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.encrypt("scoremosaic-hostile-convergence")
    writer.write(stream)
    return stream.getvalue()


def _decide(
    payload: bytes,
    *,
    filename: str,
    media_type: str,
    max_bytes: int | None = None,
    max_pages: int = 40,
):
    return decide_safe_intake(
        payload,
        original_filename=filename,
        declared_media_type=media_type,
        max_bytes=len(payload) if max_bytes is None else max_bytes,
        max_pages=max_pages,
    )


class SafeIntakeHostileConvergenceTests(unittest.TestCase):
    def test_rejects_mutable_or_non_byte_payload_before_intake(self) -> None:
        for payload in (bytearray(PNG_1X1), memoryview(PNG_1X1), "not-bytes"):
            with self.subTest(payload_type=type(payload).__name__):
                with self.assertRaises(SafeIntakeDecisionError) as raised:
                    decide_safe_intake(  # type: ignore[arg-type]
                        payload,
                        original_filename="scan.png",
                        declared_media_type="image/png",
                        max_bytes=len(PNG_1X1),
                        max_pages=40,
                    )
                self.assertEqual(raised.exception.code, "intake_payload_invalid")

    def test_byte_budget_rejects_before_content_acceptance(self) -> None:
        with self.assertRaises(SafeIntakeByteBudgetError) as raised:
            _decide(
                PNG_1X1,
                filename="scan.png",
                media_type="image/png",
                max_bytes=len(PNG_1X1) - 1,
            )
        self.assertEqual(raised.exception.code, "byte_budget_exceeded")

    def test_renamed_or_unsupported_content_stays_fail_closed(self) -> None:
        for payload, filename, media_type in (
            (b"GIF89a", "renamed.png", "image/png"),
            (b"<html></html>", "renamed.pdf", "application/pdf"),
            (b"PK\x03\x04archive", "renamed.pdf", "application/pdf"),
        ):
            with self.subTest(payload=payload[:8]):
                with self.assertRaises(SafeIntakeSignatureError) as raised:
                    _decide(payload, filename=filename, media_type=media_type)
                self.assertEqual(raised.exception.code, "unsupported_signature")

    def test_declared_mime_mismatch_stays_fail_closed(self) -> None:
        with self.assertRaises(SafeIntakeMediaTypeError) as raised:
            _decide(
                PNG_1X1,
                filename="scan.png",
                media_type="application/pdf",
            )
        self.assertEqual(raised.exception.code, "signature_media_type_mismatch")

    def test_filename_path_and_control_attacks_stay_fail_closed(self) -> None:
        pdf = _build_pdf(1)
        cases = (
            ("../score.pdf", "filename_path_unsafe"),
            ("COM¹.pdf", "filename_path_unsafe"),
            ("bad\u202e.pdf", "filename_invalid"),
        )
        for filename, expected_code in cases:
            with self.subTest(filename=filename):
                with self.assertRaises(SafeIntakeFilenameError) as raised:
                    _decide(
                        pdf,
                        filename=filename,
                        media_type="application/pdf",
                    )
                self.assertEqual(raised.exception.code, expected_code)

    def test_malformed_and_missing_reference_pdfs_stay_fail_closed(self) -> None:
        samples = (
            b"%PDF-1.7\nnot-a-valid-pdf\n",
            _build_pdf_with_missing_contents_reference(),
        )
        for payload in samples:
            with self.subTest(length=len(payload)):
                with self.assertRaises(SafeIntakePdfError) as raised:
                    _decide(
                        payload,
                        filename="broken.pdf",
                        media_type="application/pdf",
                    )
                self.assertEqual(raised.exception.code, "pdf_structure_invalid")

    def test_encrypted_pdf_and_page_budget_categories_propagate(self) -> None:
        encrypted = _build_encrypted_pdf()
        with self.assertRaises(SafeIntakePdfError) as raised:
            _decide(
                encrypted,
                filename="encrypted.pdf",
                media_type="application/pdf",
            )
        self.assertEqual(raised.exception.code, "pdf_encrypted_unsupported")

        two_pages = _build_pdf(2)
        with self.assertRaises(SafeIntakePdfError) as raised:
            _decide(
                two_pages,
                filename="two-pages.pdf",
                media_type="application/pdf",
                max_pages=1,
            )
        self.assertEqual(raised.exception.code, "pdf_page_budget_exceeded")

    def test_truncated_jpeg_and_png_stay_fail_closed(self) -> None:
        samples = (
            (JPEG_1X1[:-2], "broken.jpeg", "image/jpeg"),
            (PNG_1X1[:-8], "broken.png", "image/png"),
        )
        for payload, filename, media_type in samples:
            with self.subTest(filename=filename):
                with self.assertRaises(SafeIntakeImageError) as raised:
                    _decide(payload, filename=filename, media_type=media_type)
                self.assertEqual(raised.exception.code, "image_structure_invalid")

    def test_apng_animation_stays_fail_closed(self) -> None:
        with self.assertRaises(SafeIntakeImageError) as raised:
            _decide(
                APNG_1X1_TWO_FRAMES,
                filename="animated.png",
                media_type="image/png",
            )
        self.assertEqual(raised.exception.code, "image_animation_unsupported")

    def test_dimension_and_pixel_budget_categories_propagate_unchanged(self) -> None:
        for code in (
            "image_dimension_budget_exceeded",
            "image_pixel_budget_exceeded",
        ):
            with self.subTest(code=code):
                with patch(
                    "scoremosaic_gateway.intake_decision.inspect_image_pixels",
                    side_effect=SafeIntakeImageError(code),
                ):
                    with self.assertRaises(SafeIntakeImageError) as raised:
                        _decide(
                            PNG_1X1,
                            filename="oversized.png",
                            media_type="image/png",
                        )
                self.assertEqual(raised.exception.code, code)

    def test_inspector_timeout_categories_propagate_unchanged(self) -> None:
        pdf = _build_pdf(1)
        with patch(
            "scoremosaic_gateway.intake_decision.inspect_pdf_pages",
            side_effect=SafeIntakePdfError("pdf_inspection_timeout"),
        ):
            with self.assertRaises(SafeIntakePdfError) as raised:
                _decide(
                    pdf,
                    filename="timeout.pdf",
                    media_type="application/pdf",
                )
        self.assertEqual(raised.exception.code, "pdf_inspection_timeout")

        with patch(
            "scoremosaic_gateway.intake_decision.inspect_image_pixels",
            side_effect=SafeIntakeImageError("image_inspection_timeout"),
        ):
            with self.assertRaises(SafeIntakeImageError) as raised:
                _decide(
                    PNG_1X1,
                    filename="timeout.png",
                    media_type="image/png",
                )
        self.assertEqual(raised.exception.code, "image_inspection_timeout")

    def test_worker_memory_boundaries_remain_bounded_without_allocating_hostile_size(self) -> None:
        self.assertEqual(
            pdf_inspector_worker._PDF_WORKER_MAX_ADDRESS_SPACE_BYTES,
            256 * 1024 * 1024,
        )
        self.assertEqual(
            image_inspector_worker._IMAGE_WORKER_MAX_ADDRESS_SPACE_BYTES,
            256 * 1024 * 1024,
        )


if __name__ == "__main__":
    unittest.main()
