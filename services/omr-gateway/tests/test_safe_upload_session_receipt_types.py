from __future__ import annotations

from pathlib import Path
import sys
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_gateway.safe_intake import SAFE_INTAKE_MEDIA_TYPES
from scoremosaic_gateway.safe_upload_session import (
    SAFE_UPLOAD_SESSION_OPERATION_ID,
    SafeUploadSessionError,
    SafeUploadSessionReservationReceipt,
)


class EqualitySpoofingMediaTypes:
    """Adapter-controlled mutable value that only pretends to equal the allowlist."""

    def __init__(self) -> None:
        self.values = ["application/x-evil"]

    def __eq__(self, other: object) -> bool:
        return other == SAFE_INTAKE_MEDIA_TYPES


class SafeUploadSessionReceiptTypeConvergenceTests(unittest.TestCase):
    def test_receipt_requires_exact_tuple_media_type_allowlist(self) -> None:
        with self.assertRaisesRegex(
            SafeUploadSessionError,
            "upload_session_receipt_invalid",
        ):
            SafeUploadSessionReservationReceipt(
                session_id="upload_" + "a" * 40,
                admission_binding_id="b" * 64,
                principal_id="c" * 64,
                environment="staging",
                operation_id=SAFE_UPLOAD_SESSION_OPERATION_ID,
                request_sha256="d" * 64,
                request_bytes=32,
                max_bytes=1024,
                max_pages=10,
                allowed_media_types=EqualitySpoofingMediaTypes(),  # type: ignore[arg-type]
                created_at_epoch_s=2_000_000_000,
                expires_at_epoch_s=2_000_000_300,
                outcome="reserved",
            )


if __name__ == "__main__":
    unittest.main()
