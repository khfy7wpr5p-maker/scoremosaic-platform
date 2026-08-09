"""Private Gate B.4 PDF inspection worker.

This helper parses only PDF structure/page evidence. It does not render pages,
extract text/images/attachments, follow links, execute JavaScript, access network
resources, or persist input bytes.
"""

from __future__ import annotations

from io import BytesIO
import json
import sys

from pypdf import PdfReader
from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject


_ABSOLUTE_MAX_REQUEST_BYTES = 100 * 1024 * 1024
_ABSOLUTE_MAX_PDF_PAGES = 200
_PAGE_GRAPH_ROOT_KEYS = ("/Contents", "/Resources", "/Annots")
_PAGE_GRAPH_BACK_REFERENCE_KEYS = frozenset({"/Parent", "/P"})


def _emit(payload: dict[str, object]) -> int:
    sys.stdout.write(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return 0


def _validate_referenced_object_graph(
    value: object,
    seen_indirect_objects: set[tuple[int, int]],
) -> None:
    if isinstance(value, IndirectObject):
        identity = (value.idnum, value.generation)
        if identity in seen_indirect_objects:
            return
        seen_indirect_objects.add(identity)
        resolved = value.get_object()
        if resolved is None:
            raise ValueError("missing referenced PDF object")
        _validate_referenced_object_graph(resolved, seen_indirect_objects)
        return

    if isinstance(value, ArrayObject):
        for item in value:
            _validate_referenced_object_graph(item, seen_indirect_objects)
        return

    if isinstance(value, DictionaryObject):
        for key in value.keys():
            if str(key) in _PAGE_GRAPH_BACK_REFERENCE_KEYS:
                continue
            _validate_referenced_object_graph(
                value.raw_get(key),
                seen_indirect_objects,
            )


def _validate_page_references(page: DictionaryObject) -> None:
    seen_indirect_objects: set[tuple[int, int]] = set()
    for key in _PAGE_GRAPH_ROOT_KEYS:
        if key in page:
            _validate_referenced_object_graph(
                page.raw_get(key),
                seen_indirect_objects,
            )


def main() -> int:
    if len(sys.argv) != 2:
        return 2
    try:
        max_pages = int(sys.argv[1], 10)
    except ValueError:
        return 2
    if not 1 <= max_pages <= _ABSOLUTE_MAX_PDF_PAGES:
        return 2

    data = sys.stdin.buffer.read(_ABSOLUTE_MAX_REQUEST_BYTES + 1)
    if not data or len(data) > _ABSOLUTE_MAX_REQUEST_BYTES:
        return _emit({"status": "error", "code": "pdf_structure_invalid"})

    reader = None
    try:
        reader = PdfReader(BytesIO(data), strict=True)
        if reader.is_encrypted:
            return _emit({"status": "error", "code": "pdf_encrypted_unsupported"})

        page_count = len(reader.pages)
        if page_count < 1:
            return _emit({"status": "error", "code": "pdf_structure_invalid"})
        if page_count > max_pages:
            return _emit({"status": "error", "code": "pdf_page_budget_exceeded"})

        for page in reader.pages:
            _validate_page_references(page)

        return _emit({"status": "ok", "page_count": page_count})
    except Exception:
        return _emit({"status": "error", "code": "pdf_structure_invalid"})
    finally:
        if reader is not None:
            try:
                reader.close()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
