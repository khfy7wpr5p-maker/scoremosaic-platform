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


_ABSOLUTE_MAX_REQUEST_BYTES = 100 * 1024 * 1024
_ABSOLUTE_MAX_PDF_PAGES = 200


def _emit(payload: dict[str, object]) -> int:
    sys.stdout.write(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return 0


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
