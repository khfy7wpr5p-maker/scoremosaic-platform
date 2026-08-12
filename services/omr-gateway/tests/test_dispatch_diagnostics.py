from __future__ import annotations

from pathlib import Path
import sys
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_gateway.dispatch_deadline import DispatchDeadlineError
from scoremosaic_gateway.dispatch_retry import DispatchRetryError
from scoremosaic_gateway.receiver_verification import ReceiverVerificationError
from scoremosaic_gateway.dispatch_diagnostics import (
    DISPATCH_DIAGNOSTIC_CONTRACT_VERSION,
    SafeDispatchDiagnostic,
    map_dispatch_failure,
)


SENSITIVE = "TOKEN_DO_NOT_LEAK_123 /private/runtime/path?secret=VALUE"


class DispatchDiagnosticContractTests(unittest.TestCase):
    def test_receiver_failure_maps_to_one_bounded_public_reason(self) -> None:
        for category in (
            "signature_invalid",
            "dispatch_identity_payload_mismatch",
            SENSITIVE,
        ):
            with self.subTest(category=category):
                diagnostic = map_dispatch_failure(ReceiverVerificationError(category))
                self.assertEqual(
                    diagnostic,
                    SafeDispatchDiagnostic(
                        version=DISPATCH_DIAGNOSTIC_CONTRACT_VERSION,
                        stage="receiver_verification",
                        reason="receiver_request_rejected",
                    ),
                )
                self.assertNotIn(category, repr(diagnostic))
                self.assertNotIn(category, repr(diagnostic.as_safe_dict()))

    def test_deadline_failure_maps_without_internal_category_or_timing_detail(self) -> None:
        diagnostic = map_dispatch_failure(DispatchDeadlineError(SENSITIVE))

        self.assertEqual(diagnostic.stage, "dispatch_deadline")
        self.assertEqual(diagnostic.reason, "dispatch_deadline_rejected")
        self.assertNotIn(SENSITIVE, repr(diagnostic))
        self.assertEqual(
            diagnostic.as_safe_dict(),
            {
                "version": DISPATCH_DIAGNOSTIC_CONTRACT_VERSION,
                "stage": "dispatch_deadline",
                "reason": "dispatch_deadline_rejected",
            },
        )

    def test_retry_failure_maps_without_internal_category_or_attempt_detail(self) -> None:
        diagnostic = map_dispatch_failure(DispatchRetryError(SENSITIVE))

        self.assertEqual(diagnostic.stage, "dispatch_retry")
        self.assertEqual(diagnostic.reason, "dispatch_retry_rejected")
        self.assertNotIn(SENSITIVE, repr(diagnostic))
        self.assertNotIn("attempt", repr(diagnostic.as_safe_dict()).lower())

    def test_unknown_exception_fails_closed_without_reading_exception_text(self) -> None:
        class SensitiveFailure(RuntimeError):
            def __str__(self) -> str:
                raise AssertionError("safe mapper must not stringify unknown exceptions")

            def __repr__(self) -> str:
                raise AssertionError("safe mapper must not repr unknown exceptions")

        diagnostic = map_dispatch_failure(SensitiveFailure())

        self.assertEqual(diagnostic.stage, "dispatch_internal")
        self.assertEqual(diagnostic.reason, "dispatch_internal_failure")
        self.assertEqual(
            diagnostic.as_safe_dict(),
            {
                "version": DISPATCH_DIAGNOSTIC_CONTRACT_VERSION,
                "stage": "dispatch_internal",
                "reason": "dispatch_internal_failure",
            },
        )

    def test_subclasses_do_not_inherit_a_trusted_specific_mapping(self) -> None:
        class ForgedReceiverFailure(ReceiverVerificationError):
            pass

        diagnostic = map_dispatch_failure(ForgedReceiverFailure(SENSITIVE))

        self.assertEqual(diagnostic.stage, "dispatch_internal")
        self.assertEqual(diagnostic.reason, "dispatch_internal_failure")
        self.assertNotIn(SENSITIVE, repr(diagnostic))

    def test_non_exception_input_is_rejected_with_fixed_error(self) -> None:
        with self.assertRaisesRegex(TypeError, "dispatch failure must be an exception"):
            map_dispatch_failure(SENSITIVE)


if __name__ == "__main__":
    unittest.main()
