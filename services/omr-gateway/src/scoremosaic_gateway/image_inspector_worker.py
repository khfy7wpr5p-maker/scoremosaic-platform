"""Private Gate B.5 JPEG/PNG image inspection worker.

This helper accepts only one expected allowlisted image format, derives dimensions
from the exact input bytes, rejects animation, enforces dimension/pixel budgets,
fully decodes only inside this bounded subprocess, and persists nothing.
"""

from __future__ import annotations

from io import BytesIO
import json
import resource
import sys
import warnings

from PIL import Image, ImageFile


_ABSOLUTE_MAX_REQUEST_BYTES = 100 * 1024 * 1024
_ABSOLUTE_MAX_IMAGE_DIMENSION = 12_000
_ABSOLUTE_MAX_IMAGE_PIXELS = 40_000_000
_IMAGE_WORKER_MAX_ADDRESS_SPACE_BYTES = 256 * 1024 * 1024

_ALLOWED_FORMATS = {
    "jpeg": "JPEG",
    "png": "PNG",
}


def _emit(payload: dict[str, object]) -> int:
    sys.stdout.write(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return 0


def _apply_address_space_limit() -> bool:
    try:
        resource.setrlimit(
            resource.RLIMIT_AS,
            (
                _IMAGE_WORKER_MAX_ADDRESS_SPACE_BYTES,
                _IMAGE_WORKER_MAX_ADDRESS_SPACE_BYTES,
            ),
        )
    except (OSError, ValueError):
        return False
    return True


def _validate_dimensions(width: object, height: object) -> tuple[int, int, int] | str:
    if (
        isinstance(width, bool)
        or isinstance(height, bool)
        or not isinstance(width, int)
        or not isinstance(height, int)
        or width < 1
        or height < 1
    ):
        return "image_structure_invalid"

    if width > _ABSOLUTE_MAX_IMAGE_DIMENSION or height > _ABSOLUTE_MAX_IMAGE_DIMENSION:
        return "image_dimension_budget_exceeded"

    pixel_count = width * height
    if pixel_count > _ABSOLUTE_MAX_IMAGE_PIXELS:
        return "image_pixel_budget_exceeded"

    return width, height, pixel_count


def main() -> int:
    if len(sys.argv) != 2:
        return 2

    expected_format_id = sys.argv[1]
    expected_pillow_format = _ALLOWED_FORMATS.get(expected_format_id)
    if expected_pillow_format is None:
        return 2

    if not _apply_address_space_limit():
        return 2

    try:
        data = sys.stdin.buffer.read(_ABSOLUTE_MAX_REQUEST_BYTES + 1)
    except MemoryError:
        return _emit({"status": "error", "code": "image_structure_invalid"})

    if not data or len(data) > _ABSOLUTE_MAX_REQUEST_BYTES:
        return _emit({"status": "error", "code": "image_structure_invalid"})

    ImageFile.LOAD_TRUNCATED_IMAGES = False
    warnings.simplefilter("error", Image.DecompressionBombWarning)

    image = None
    try:
        image = Image.open(
            BytesIO(data),
            formats=(expected_pillow_format,),
        )

        if image.format != expected_pillow_format:
            return _emit({"status": "error", "code": "image_structure_invalid"})

        dimensions = _validate_dimensions(image.width, image.height)
        if isinstance(dimensions, str):
            return _emit({"status": "error", "code": dimensions})

        width, height, pixel_count = dimensions

        if bool(getattr(image, "is_animated", False)):
            return _emit({"status": "error", "code": "image_animation_unsupported"})
        if getattr(image, "n_frames", 1) != 1:
            return _emit({"status": "error", "code": "image_animation_unsupported"})

        image.verify()
        image.close()
        image = None

        # Reopen before load because verify() invalidates the image core.
        image = Image.open(
            BytesIO(data),
            formats=(expected_pillow_format,),
        )
        if image.format != expected_pillow_format:
            return _emit({"status": "error", "code": "image_structure_invalid"})
        if bool(getattr(image, "is_animated", False)) or getattr(image, "n_frames", 1) != 1:
            return _emit({"status": "error", "code": "image_animation_unsupported"})

        image.load()

        return _emit(
            {
                "status": "ok",
                "format_id": expected_format_id,
                "width": width,
                "height": height,
                "pixel_count": pixel_count,
            }
        )
    except (Image.DecompressionBombWarning, Image.DecompressionBombError):
        return _emit({"status": "error", "code": "image_pixel_budget_exceeded"})
    except (MemoryError, OSError, SyntaxError, ValueError):
        return _emit({"status": "error", "code": "image_structure_invalid"})
    except Exception:
        return _emit({"status": "error", "code": "image_structure_invalid"})
    finally:
        if image is not None:
            try:
                image.close()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
