from __future__ import annotations

from io import BytesIO
from pathlib import Path
import resource
import subprocess
import sys
import tomllib
import unittest
from unittest.mock import patch

SERVICE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SERVICE_ROOT.parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_gateway import pdf_inspector_worker
from scoremosaic_gateway.safe_intake import (
    SafeIntakePdfError,
    inspect_pdf_pages,
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
    return _serialize_pdf_objects(objects)


def _build_pdf_with_missing_page_reference(entry_name: str) -> bytes:
    return _serialize_pdf_objects(
        [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            (
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                + f"/{entry_name} 99 0 R >>".encode("ascii")
            ),
        ]
    )


def _build_pdf_with_scalar_page_reference(entry_name: str) -> bytes:
    return _serialize_pdf_objects(
        [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            (
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                + f"/{entry_name} 4 0 R >>".encode("ascii")
            ),
            b"42",
        ]
    )


def _build_pdf_with_widget_missing_parent_reference() -> bytes:
    return _serialize_pdf_objects(
        [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            (
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                b"/Resources << >> /Annots [4 0 R] >>"
            ),
            (
                b"<< /Type /Annot /Subtype /Widget /Rect [0 0 10 10] "
                b"/Parent 99 0 R >>"
            ),
        ]
    )


def _build_pdf_with_missing_page_parent_reference() -> bytes:
    return _serialize_pdf_objects(
        [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            (
                b"<< /Type /Page /Parent 99 0 R /MediaBox [0 0 612 792] "
                b"/Resources << >> >>"
            ),
        ]
    )


def _build_pdf_with_stream_resources() -> bytes:
    return _serialize_pdf_objects(
        [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            (
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                b"/Resources 4 0 R >>"
            ),
            b"<< /Length 0 >>\nstream\n\nendstream",
        ]
    )


def _build_pdf_with_inline_page_parent() -> bytes:
    return _serialize_pdf_objects(
        [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            (
                b"<< /Type /Page /Parent << /Type /Pages /Kids [3 0 R] >> "
                b"/MediaBox [0 0 612 792] /Resources << >> >>"
            ),
        ]
    )


def _build_pdf_with_stream_annotation() -> bytes:
    return _serialize_pdf_objects(
        [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            (
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                b"/Resources << >> /Annots [4 0 R] >>"
            ),
            (
                b"<< /Type /Annot /Subtype /Text /Rect [0 0 10 10] /Length 0 >>\n"
                b"stream\n\nendstream"
            ),
        ]
    )



def _build_pdf_with_non_catalog_root() -> bytes:
    return _serialize_pdf_objects(
        [
            b"<< /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            (
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                b"/Resources << >> >>"
            ),
        ]
    )



def _build_pdf_with_orphan_declared_page_parent() -> bytes:
    return _serialize_pdf_objects(
        [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            (
                b"<< /Type /Page /Parent 4 0 R /MediaBox [0 0 612 792] "
                b"/Resources << >> >>"
            ),
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        ]
    )


def _build_pdf_with_inline_annotation() -> bytes:
    return _serialize_pdf_objects(
        [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            (
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                b"/Resources << >> "
                b"/Annots [<< /Type /Annot /Subtype /Text /Rect [0 0 10 10] >>] >>"
            ),
        ]
    )


def _build_annotated_pdf_with_page_backrefs(page_count: int) -> bytes:
    page_start = 3
    annotation_start = page_start + page_count
    kids = " ".join(
        f"{page_start + index} 0 R"
        for index in range(page_count)
    )
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {page_count} >>".encode("ascii"),
    ]
    for index in range(page_count):
        annotation_object = annotation_start + index
        objects.append(
            (
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                b"/Resources << >> /Annots ["
                + f"{annotation_object} 0 R".encode("ascii")
                + b"] >>"
            )
        )
    for index in range(page_count):
        page_object = page_start + index
        objects.append(
            (
                b"<< /Type /Annot /Subtype /Text /Rect [0 0 10 10] /P "
                + f"{page_object} 0 R".encode("ascii")
                + b" >>"
            )
        )
    return _serialize_pdf_objects(objects)


def _build_encrypted_pdf() -> bytes:
    from pypdf import PdfWriter

    stream = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.encrypt("scoremosaic-test-password")
    writer.write(stream)
    return stream.getvalue()


class PdfPageBudgetTests(unittest.TestCase):
    def test_parser_dependency_is_exact_pinned(self) -> None:
        metadata = tomllib.loads(
            (SERVICE_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )
        self.assertEqual(metadata["project"]["dependencies"], ["pypdf==6.14.2"])

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

    def test_rejects_missing_referenced_page_objects_fail_closed(self) -> None:
        for entry_name in ("Contents", "Resources", "Annots"):
            with self.subTest(entry_name=entry_name):
                with self.assertRaises(SafeIntakePdfError) as raised:
                    inspect_pdf_pages(
                        _build_pdf_with_missing_page_reference(entry_name),
                        max_pages=40,
                    )
                self.assertEqual(raised.exception.code, "pdf_structure_invalid")

    def test_rejects_scalar_objects_for_typed_page_entries_fail_closed(self) -> None:
        for entry_name in ("Contents", "Resources", "Annots"):
            with self.subTest(entry_name=entry_name):
                with self.assertRaises(SafeIntakePdfError) as raised:
                    inspect_pdf_pages(
                        _build_pdf_with_scalar_page_reference(entry_name),
                        max_pages=40,
                    )
                self.assertEqual(raised.exception.code, "pdf_structure_invalid")

    def test_rejects_missing_widget_annotation_parent_fail_closed(self) -> None:
        with self.assertRaises(SafeIntakePdfError) as raised:
            inspect_pdf_pages(
                _build_pdf_with_widget_missing_parent_reference(),
                max_pages=40,
            )
        self.assertEqual(raised.exception.code, "pdf_structure_invalid")

    def test_rejects_missing_page_parent_reference_fail_closed(self) -> None:
        with self.assertRaises(SafeIntakePdfError) as raised:
            inspect_pdf_pages(
                _build_pdf_with_missing_page_parent_reference(),
                max_pages=40,
            )
        self.assertEqual(raised.exception.code, "pdf_structure_invalid")

    def test_rejects_stream_used_as_resources_dictionary_fail_closed(self) -> None:
        with self.assertRaises(SafeIntakePdfError) as raised:
            inspect_pdf_pages(
                _build_pdf_with_stream_resources(),
                max_pages=40,
            )
        self.assertEqual(raised.exception.code, "pdf_structure_invalid")

    def test_rejects_inline_page_parent_fail_closed(self) -> None:
        with self.assertRaises(SafeIntakePdfError) as raised:
            inspect_pdf_pages(
                _build_pdf_with_inline_page_parent(),
                max_pages=40,
            )
        self.assertEqual(raised.exception.code, "pdf_structure_invalid")

    def test_rejects_stream_used_as_annotation_dictionary_fail_closed(self) -> None:
        with self.assertRaises(SafeIntakePdfError) as raised:
            inspect_pdf_pages(
                _build_pdf_with_stream_annotation(),
                max_pages=40,
            )
        self.assertEqual(raised.exception.code, "pdf_structure_invalid")


    def test_rejects_non_catalog_trailer_root_fail_closed(self) -> None:
        with self.assertRaises(SafeIntakePdfError) as raised:
            inspect_pdf_pages(
                _build_pdf_with_non_catalog_root(),
                max_pages=40,
            )
        self.assertEqual(raised.exception.code, "pdf_structure_invalid")


    def test_rejects_page_parent_not_anchored_to_catalog_tree_fail_closed(self) -> None:
        with self.assertRaises(SafeIntakePdfError) as raised:
            inspect_pdf_pages(
                _build_pdf_with_orphan_declared_page_parent(),
                max_pages=40,
            )
        self.assertEqual(raised.exception.code, "pdf_structure_invalid")

    def test_rejects_inline_annotation_dictionary_fail_closed(self) -> None:
        with self.assertRaises(SafeIntakePdfError) as raised:
            inspect_pdf_pages(
                _build_pdf_with_inline_annotation(),
                max_pages=40,
            )
        self.assertEqual(raised.exception.code, "pdf_structure_invalid")

    def test_reuses_worker_visited_set_across_page_validations(self) -> None:
        from pypdf import PdfReader

        reader = PdfReader(
            BytesIO(_build_annotated_pdf_with_page_backrefs(2)),
            strict=True,
        )
        pages = list(reader.pages)
        seen_indirect_objects: set[tuple[int, int]] = set()

        pdf_inspector_worker._validate_page_references(
            pages[0],
            seen_indirect_objects,
        )
        first_seen = set(seen_indirect_objects)
        self.assertTrue(first_seen)

        pdf_inspector_worker._validate_page_references(
            pages[1],
            seen_indirect_objects,
        )
        self.assertEqual(seen_indirect_objects, first_seen)

    def test_rejects_encrypted_pdf_fail_closed(self) -> None:
        with self.assertRaises(SafeIntakePdfError) as raised:
            inspect_pdf_pages(_build_encrypted_pdf(), max_pages=40)
        self.assertEqual(raised.exception.code, "pdf_encrypted_unsupported")

    def test_rejects_non_pdf_bytes_without_trusting_caller_metadata(self) -> None:
        with self.assertRaises(SafeIntakePdfError) as raised:
            inspect_pdf_pages(b"\x89PNG\r\n\x1a\nrest", max_pages=40)
        self.assertEqual(raised.exception.code, "pdf_structure_invalid")

    def test_rejects_mutable_pdf_buffers_fail_closed(self) -> None:
        mutable_pdf = bytearray(_build_pdf(1))
        for sample in (mutable_pdf, memoryview(mutable_pdf)):
            with self.subTest(sample_type=type(sample).__name__):
                with self.assertRaises(SafeIntakePdfError) as raised:
                    inspect_pdf_pages(sample, max_pages=40)  # type: ignore[arg-type]
                self.assertEqual(raised.exception.code, "pdf_structure_invalid")

    def test_maps_inspector_timeout_to_stable_fail_closed_category(self) -> None:
        with patch(
            "scoremosaic_gateway.safe_intake.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=("python",), timeout=2),
        ):
            with self.assertRaises(SafeIntakePdfError) as raised:
                inspect_pdf_pages(_build_pdf(1), max_pages=40)
        self.assertEqual(raised.exception.code, "pdf_inspection_timeout")

    def test_maps_inspector_launch_oserror_to_stable_fail_closed_category(self) -> None:
        with patch(
            "scoremosaic_gateway.safe_intake.subprocess.run",
            side_effect=OSError("worker launch unavailable"),
        ):
            with self.assertRaises(SafeIntakePdfError) as raised:
                inspect_pdf_pages(_build_pdf(1), max_pages=40)
        self.assertEqual(raised.exception.code, "pdf_structure_invalid")

    def test_forwards_immutable_pdf_bytes_without_parent_copy(self) -> None:
        pdf_bytes = _build_pdf(1)

        def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
            self.assertIs(kwargs["input"], pdf_bytes)
            return subprocess.CompletedProcess(
                args[0],
                0,
                stdout=b'{"page_count":1,"status":"ok"}',
            )

        with patch(
            "scoremosaic_gateway.safe_intake.subprocess.run",
            side_effect=fake_run,
        ):
            self.assertEqual(inspect_pdf_pages(pdf_bytes, max_pages=40), 1)

    def test_worker_address_space_is_bounded_against_staging_container(self) -> None:
        self.assertEqual(
            pdf_inspector_worker._PDF_WORKER_MAX_ADDRESS_SPACE_BYTES,
            256 * 1024 * 1024,
        )
        staging_compose = (
            REPO_ROOT / "deploy" / "coolify" / "staging" / "compose.yaml"
        ).read_text(encoding="utf-8")
        self.assertIn(
            'mem_limit: "${GATEWAY_MEMORY_LIMIT:-512m}"',
            staging_compose,
        )

        with patch.object(pdf_inspector_worker.resource, "setrlimit") as setrlimit:
            self.assertTrue(pdf_inspector_worker._apply_address_space_limit())
        setrlimit.assert_called_once_with(
            resource.RLIMIT_AS,
            (
                pdf_inspector_worker._PDF_WORKER_MAX_ADDRESS_SPACE_BYTES,
                pdf_inspector_worker._PDF_WORKER_MAX_ADDRESS_SPACE_BYTES,
            ),
        )


if __name__ == "__main__":
    unittest.main()
