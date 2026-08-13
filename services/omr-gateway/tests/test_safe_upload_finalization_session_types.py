from __future__ import annotations

from pathlib import Path
import sys
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

import test_safe_upload_finalization as helpers
from scoremosaic_gateway.safe_intake import SAFE_INTAKE_MEDIA_TYPES
from scoremosaic_gateway.safe_upload_finalization import (
    SafeUploadFinalizationError,
    finalize_safe_upload_session,
)


class _EqualitySpoofingAllowlist:
    def __eq__(self, other: object) -> bool:
        return True

    def __iter__(self):
        return iter(SAFE_INTAKE_MEDIA_TYPES)

    def __contains__(self, item: object) -> bool:
        return True


class SafeUploadFinalizationSessionTypeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = helpers.SafeUploadFinalizationContractTests(methodName="runTest")
        self.fixture.setUp()

    def test_session_allowlist_must_remain_exact_canonical_tuple(self) -> None:
        object.__setattr__(
            self.fixture.session,
            "allowed_media_types",
            _EqualitySpoofingAllowlist(),
        )
        provider_calls = []

        def finalizer(request):
            provider_calls.append(request)
            return self.fixture._receipt_for(request)

        with self.assertRaises(SafeUploadFinalizationError) as raised:
            finalize_safe_upload_session(
                session=self.fixture.session,
                payload=helpers.PNG_1X1,
                original_filename="scan.png",
                declared_media_type="image/png",
                observed_at_epoch_s=self.fixture.now + 4,
                finalizer=finalizer,
            )

        self.assertEqual(raised.exception.category, "upload_session_invalid")
        self.assertEqual(provider_calls, [])


if __name__ == "__main__":
    unittest.main()
