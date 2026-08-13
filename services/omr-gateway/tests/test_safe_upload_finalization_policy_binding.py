from __future__ import annotations

from pathlib import Path
import sys
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

import test_safe_upload_finalization as helpers
from scoremosaic_gateway.safe_intake import SAFE_INTAKE_POLICY_VERSION
from scoremosaic_gateway.safe_upload_finalization import finalize_safe_upload_session


class SafeUploadFinalizationPolicyBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = helpers.SafeUploadFinalizationContractTests(methodName="runTest")
        self.fixture.setUp()

    def test_safe_intake_policy_version_is_explicit_finalization_evidence(self) -> None:
        provider_requests = []

        def finalizer(request):
            provider_requests.append(request)
            self.assertEqual(request.intake_policy_version, SAFE_INTAKE_POLICY_VERSION)
            return self.fixture._receipt_for(request)

        decision = finalize_safe_upload_session(
            session=self.fixture.session,
            payload=helpers.PNG_1X1,
            original_filename="scan.png",
            declared_media_type="image/png",
            observed_at_epoch_s=self.fixture.now + 4,
            finalizer=finalizer,
        )

        self.assertEqual(len(provider_requests), 1)
        self.assertEqual(decision.intake_policy_version, SAFE_INTAKE_POLICY_VERSION)
        self.assertEqual(
            decision.as_safe_dict()["safeIntakePolicyVersion"],
            SAFE_INTAKE_POLICY_VERSION,
        )


if __name__ == "__main__":
    unittest.main()
