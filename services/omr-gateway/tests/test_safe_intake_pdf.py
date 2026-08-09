from __future__ import annotations

from io import BytesIO
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_gateway.safe_intake import (
    SafeIntakePdfError,
    inspect_pdf_pages,
)


def _build_pdf(page_count: int) -> bytes:
    objects: list[bytes] = []
    kids = " ".join(f"{index} 0 R" for index in range(3, 3 + page_count))
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(
        f"<< /Type /Pages /Kids [{kids}] /Count {page_count} >>".encode("ascii")
    )
    for _ in range(page_count):
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << >> >>"
        )

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


def _build_encrypted_pdf() -> bytes:
    from pypdf import PdfWriter

    stream = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.encrypt("scoremosaic-test-password")
    writer.write(stream)
    return stream.getvalue()


class PdfPageBudgetTests(unittest.TestCase):
    def test_accepts_one_page_and_exact_page_limit(self) -> None:
        self.assertEqual(inspect_pdf_pages(_build_pdf(1), max_pages=40), 1)
        self.assertEqual(inspect_pdf_pages(_build_pdf(3), max_pages=3), 3)

    def test_rejects_page_limit_plus_one_fail_closed(self) -> None:
        with self.assertRaises(SafeIntakePdfError) as raised:
            inspect_pdf_pages(_build_pdf(4), max_pages=3)
        self.assertEqual(raised.exception.code, "pdf_page_budget_exceeded")

    def test_rejects_invalid_page_limits_fail_closed(self) -> None:
        for limit in (True, False, 0, -1, 201, "40"):
            with self.subTest(limit=limit):
                with self.assertRaises(SafeIntakePdfError) as raised:
                    inspect_pdf_pages(_build_pdf(1), max_pages=limit)  # type: ignore[arg-type]
                self.assertEqual(raised.exception.code, "pdf_page_limit_invalid")

    def test_rejects_truncated_or_malformed_pdf_fail_closed(self) -> None:
        samples = (
            _build_pdf(1)[:-24],
            b"%PDF-1.7\nnot-a-valid-pdf\n",
        )
        for sample in samples:
            with self.subTest(length=len(sample)):
                with self.assertRaises(SafeIntakePdfError) as raised:
                    inspect_pdf_pages(sample, max_pages=40)
                self.assertEqual(raised.exception.code, "pdf_structure_invalid")

    def test_rejects_encrypted_pdf_fail_closed(self) -> None:
        with self.assertRaises(SafeIntakePdfError) as raised:
            inspect_pdf_pages(_build_encrypted_pdf(), max_pages=40)
        self.assertEqual(raised.exception.code, "pdf_encrypted_unsupported")

    def test_rejects_non_pdf_bytes_without_trusting_caller_metadata(self) -> None:
        with self.assertRaises(SafeIntakePdfError) as raised:
            inspect_pdf_pages(b"\x89PNG\r\n\x1a\nrest", max_pages=40)
        self.assertEqual(raised.exception.code, "pdf_structure_invalid")

    def test_maps_inspector_timeout_to_stable_fail_closed_category(self) -> None:
        with patch(
            "scoremosaic_gateway.safe_intake.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=("python",), timeout=2),
        ):
            with self.assertRaises(SafeIntakePdfError) as raised:
                inspect_pdf_pages(_build_pdf(1), max_pages=40, timeout_seconds=2)
        self.assertEqual(raised.exception.code, "pdf_inspection_timeout")


if __name__ == "__main__":
    unittest.main()
