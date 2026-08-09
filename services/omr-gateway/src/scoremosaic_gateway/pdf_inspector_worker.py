"""Private Gate B.4 PDF inspection worker.

This helper parses only PDF structure/page evidence. It does not render pages,
extract text/images/attachments, follow links, execute JavaScript, access network
resources, or persist input bytes.
"""

from __future__ import annotations

from io import BytesIO
import json
import resource
import sys

from pypdf import PdfReader
from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject, StreamObject


_ABSOLUTE_MAX_REQUEST_BYTES = 100 * 1024 * 1024
_ABSOLUTE_MAX_PDF_PAGES = 200
_PDF_WORKER_MAX_ADDRESS_SPACE_BYTES = 256 * 1024 * 1024
_PAGE_GRAPH_ROOT_KEYS = ("/Contents", "/Resources", "/Annots")


def _emit(payload: dict[str, object]) -> int:
    sys.stdout.write(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return 0


def _apply_address_space_limit() -> bool:
    try:
        resource.setrlimit(
            resource.RLIMIT_AS,
            (
                _PDF_WORKER_MAX_ADDRESS_SPACE_BYTES,
                _PDF_WORKER_MAX_ADDRESS_SPACE_BYTES,
            ),
        )
    except (OSError, ValueError):
        return False
    return True


def _resolve_indirect(value: object) -> object:
    if not isinstance(value, IndirectObject):
        return value
    resolved = value.get_object()
    if resolved is None:
        raise ValueError("missing referenced PDF object")
    return resolved


def _validate_referenced_object_graph(
    value: object,
    seen_indirect_objects: set[tuple[int, int]],
) -> None:
    if isinstance(value, IndirectObject):
        identity = (value.idnum, value.generation)
        if identity in seen_indirect_objects:
            return
        seen_indirect_objects.add(identity)
        resolved = _resolve_indirect(value)
        _validate_referenced_object_graph(resolved, seen_indirect_objects)
        return

    if isinstance(value, ArrayObject):
        for item in value:
            _validate_referenced_object_graph(item, seen_indirect_objects)
        return

    if isinstance(value, DictionaryObject):
        for key in value.keys():
            _validate_referenced_object_graph(
                value.raw_get(key),
                seen_indirect_objects,
            )


def _validate_contents_entry(value: object) -> None:
    resolved = _resolve_indirect(value)
    if isinstance(resolved, StreamObject):
        return
    if not isinstance(resolved, ArrayObject):
        raise ValueError("invalid page contents object")
    for item in resolved:
        if not isinstance(_resolve_indirect(item), StreamObject):
            raise ValueError("invalid page contents array item")


def _validate_resources_entry(value: object) -> None:
    resolved = _resolve_indirect(value)
    if isinstance(resolved, StreamObject) or not isinstance(resolved, DictionaryObject):
        raise ValueError("invalid page resources object")


def _validate_annots_entry(value: object) -> None:
    resolved = _resolve_indirect(value)
    if not isinstance(resolved, ArrayObject):
        raise ValueError("invalid page annotations object")
    for item in resolved:
        if not isinstance(item, IndirectObject):
            raise ValueError("page annotation must be an indirect reference")
        annotation = _resolve_indirect(item)
        if isinstance(annotation, StreamObject) or not isinstance(annotation, DictionaryObject):
            raise ValueError("invalid page annotation array item")


def _validate_page_parent(
    page: DictionaryObject,
    seen_indirect_objects: set[tuple[int, int]],
) -> None:
    if "/Parent" not in page:
        raise ValueError("missing page parent reference")

    page_reference = getattr(page, "indirect_reference", None)
    if not isinstance(page_reference, IndirectObject):
        raise ValueError("missing page indirect reference")

    reader = getattr(page_reference, "pdf", None)
    catalog = reader.root_object
    catalog_pages_value = catalog.raw_get("/Pages")
    if not isinstance(catalog_pages_value, IndirectObject):
        raise ValueError("invalid catalog pages reference")
    catalog_pages_identity = (
        catalog_pages_value.idnum,
        catalog_pages_value.generation,
    )

    child_identity = (page_reference.idnum, page_reference.generation)
    parent_value = page.raw_get("/Parent")
    parent_chain: set[tuple[int, int]] = set()

    while True:
        if not isinstance(parent_value, IndirectObject):
            raise ValueError("page parent must be an indirect reference")

        parent_identity = (parent_value.idnum, parent_value.generation)
        if parent_identity in parent_chain:
            raise ValueError("cyclic page parent chain")
        parent_chain.add(parent_identity)

        parent = _resolve_indirect(parent_value)
        if isinstance(parent, StreamObject) or not isinstance(parent, DictionaryObject):
            raise ValueError("invalid page parent object")
        if parent.get("/Type") != "/Pages":
            raise ValueError("invalid page parent type")
        if "/Kids" not in parent:
            raise ValueError("missing page parent kids")

        kids = _resolve_indirect(parent.raw_get("/Kids"))
        if not isinstance(kids, ArrayObject):
            raise ValueError("invalid page parent kids")
        if not any(
            isinstance(kid, IndirectObject)
            and (kid.idnum, kid.generation) == child_identity
            for kid in kids
        ):
            raise ValueError("page parent does not reference child")

        if parent_identity == catalog_pages_identity:
            break

        if "/Parent" not in parent:
            raise ValueError("page parent chain is not anchored to catalog")
        child_identity = parent_identity
        parent_value = parent.raw_get("/Parent")

    _validate_referenced_object_graph(
        page.raw_get("/Parent"),
        seen_indirect_objects,
    )


def _validate_page_references(
    page: DictionaryObject,
    seen_indirect_objects: set[tuple[int, int]],
) -> None:
    _validate_page_parent(page, seen_indirect_objects)
    for key in _PAGE_GRAPH_ROOT_KEYS:
        if key not in page:
            continue
        value = page.raw_get(key)
        if key == "/Contents":
            _validate_contents_entry(value)
        elif key == "/Resources":
            _validate_resources_entry(value)
        else:
            _validate_annots_entry(value)
        _validate_referenced_object_graph(value, seen_indirect_objects)


def main() -> int:
    if len(sys.argv) != 2:
        return 2
    try:
        max_pages = int(sys.argv[1], 10)
    except ValueError:
        return 2
    if not 1 <= max_pages <= _ABSOLUTE_MAX_PDF_PAGES:
        return 2
    if not _apply_address_space_limit():
        return 2

    try:
        data = sys.stdin.buffer.read(_ABSOLUTE_MAX_REQUEST_BYTES + 1)
    except MemoryError:
        return _emit({"status": "error", "code": "pdf_structure_invalid"})
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

        seen_indirect_objects: set[tuple[int, int]] = set()
        for page in reader.pages:
            _validate_page_references(page, seen_indirect_objects)

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
