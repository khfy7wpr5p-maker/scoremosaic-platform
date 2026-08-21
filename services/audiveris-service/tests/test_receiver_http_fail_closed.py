from __future__ import annotations

from dataclasses import replace
import unittest

import test_receiver_http as helpers


class ReceiverHttpFailClosedTests(unittest.TestCase):
    def _fixture(self):
        fixture = helpers.ReceiverHttpTests(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        return fixture

    def _request(self, fixture, context):
        return helpers.handle_receiver_http_request(
            method="POST",
            target=helpers.TRUSTED_PLAN_PROVISIONING_PATH,
            headers=fixture.provisioning_headers(),
            body=fixture.provisioning_request.canonical_request_bytes,
            context=context,
        )

    def test_clock_backend_exception_is_bounded_503_without_leakage(self) -> None:
        fixture = self._fixture()
        sensitive = "TOKEN_DO_NOT_LEAK /private/clock/path"

        def broken_clock() -> int:
            raise RuntimeError(sensitive)

        response = self._request(
            fixture,
            replace(fixture.context, now_seconds=broken_clock),
        )
        self.assertEqual(response.status, 503)
        self.assertEqual(response.payload, {"error": "receiver_state_unavailable"})
        self.assertNotIn(sensitive, repr(response.payload))

    def test_invalid_clock_values_fail_closed_before_credential_resolution(self) -> None:
        fixture = self._fixture()
        calls = 0

        def credential_resolver(key, generation):
            nonlocal calls
            calls += 1
            return fixture.provisioning_secret

        for invalid_now in (-1, "1800400000", None, True):
            with self.subTest(invalid_now=invalid_now):
                context = replace(
                    fixture.context,
                    now_seconds=lambda value=invalid_now: value,
                    provisioning_credential_resolver=credential_resolver,
                )
                response = self._request(fixture, context)
                self.assertEqual(response.status, 503)
                self.assertEqual(response.payload, {"error": "receiver_state_unavailable"})
        self.assertEqual(calls, 0)


if __name__ == "__main__":
    unittest.main()
