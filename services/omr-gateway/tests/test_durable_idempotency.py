from dataclasses import FrozenInstanceError
import re
import unittest

from scoremosaic_gateway.dispatch_identity import build_dispatch_identity
from scoremosaic_gateway.durable_job_state import build_durable_job_state
from scoremosaic_gateway.durable_idempotency import (
    DURABLE_IDEMPOTENCY_CONTRACT_VERSION,
    DurableIdempotencyError,
    apply_durable_transition_idempotently,
    build_durable_idempotency_ledger,
)
from scoremosaic_gateway.orchestration import build_orchestration_plan


_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_SLOT_RE = re.compile(r"^idem_[a-f0-9]{24}$")


class _StringSubclass(str):
    pass


class DurableIdempotencyTests(unittest.TestCase):
    def setUp(self) -> None:
        plan = build_orchestration_plan(
            "job_idempotency01",
            source_artifact_ref="sources/job_idempotency01/source.pdf",
            source_sha256="3" * 64,
            source_size_bytes=4096,
            source_media_type="application/pdf",
        )
        self.binding = build_dispatch_identity(plan.as_dict(), "homr")
        self.initial = build_durable_job_state(self.binding)

    def test_fresh_transition_records_one_server_derived_slot(self) -> None:
        ledger = build_durable_idempotency_ledger(self.initial)
        result = apply_durable_transition_idempotently(ledger, self.initial, "queued")

        self.assertFalse(result.replayed)
        self.assertEqual(result.snapshot.state, "queued")
        self.assertEqual(result.snapshot.revision, 1)
        self.assertIs(result.snapshot.binding, self.binding)
        self.assertEqual(len(result.ledger.records), 1)

        record = result.ledger.records[0]
        self.assertRegex(record.slot_id, _SLOT_RE)
        self.assertRegex(record.request_sha256, _SHA256_RE)
        self.assertEqual(record.from_state, "planned")
        self.assertEqual(record.from_revision, 0)
        self.assertEqual(record.to_state, "queued")
        self.assertEqual(record.result_state, "queued")
        self.assertEqual(record.result_revision, 1)

    def test_exact_replay_returns_recorded_result_without_duplicate_revision(self) -> None:
        ledger = build_durable_idempotency_ledger(self.initial)
        first = apply_durable_transition_idempotently(ledger, self.initial, "queued")
        replay = apply_durable_transition_idempotently(
            first.ledger,
            self.initial,
            "queued",
        )

        self.assertTrue(replay.replayed)
        self.assertIs(replay.ledger, first.ledger)
        self.assertEqual(replay.snapshot, first.snapshot)
        self.assertEqual(replay.snapshot.revision, 1)
        self.assertEqual(len(replay.ledger.records), 1)

    def test_same_slot_with_different_valid_transition_fails_closed(self) -> None:
        ledger = build_durable_idempotency_ledger(self.initial)
        first = apply_durable_transition_idempotently(ledger, self.initial, "queued")

        with self.assertRaises(DurableIdempotencyError) as caught:
            apply_durable_transition_idempotently(
                first.ledger,
                self.initial,
                "cancelled",
            )
        self.assertEqual(caught.exception.category, "idempotency_conflict")

    def test_next_revision_uses_a_new_slot_and_preserves_binding(self) -> None:
        ledger = build_durable_idempotency_ledger(self.initial)
        first = apply_durable_transition_idempotently(ledger, self.initial, "queued")
        second = apply_durable_transition_idempotently(
            first.ledger,
            first.snapshot,
            "dispatching",
        )

        self.assertFalse(second.replayed)
        self.assertEqual(second.snapshot.state, "dispatching")
        self.assertEqual(second.snapshot.revision, 2)
        self.assertIs(second.snapshot.binding, self.binding)
        self.assertEqual(len(second.ledger.records), 2)
        self.assertNotEqual(
            second.ledger.records[0].slot_id,
            second.ledger.records[1].slot_id,
        )

    def test_ledger_rejects_state_from_another_dispatch_identity(self) -> None:
        other_plan = build_orchestration_plan(
            "job_idempotency02",
            source_artifact_ref="sources/job_idempotency02/source.pdf",
            source_sha256="4" * 64,
            source_size_bytes=4096,
            source_media_type="application/pdf",
        )
        other_binding = build_dispatch_identity(other_plan.as_dict(), "homr")
        other_state = build_durable_job_state(other_binding)
        ledger = build_durable_idempotency_ledger(self.initial)

        with self.assertRaises(DurableIdempotencyError) as caught:
            apply_durable_transition_idempotently(ledger, other_state, "queued")
        self.assertEqual(caught.exception.category, "dispatch_identity_mismatch")

    def test_slot_and_request_digest_are_deterministic(self) -> None:
        first = apply_durable_transition_idempotently(
            build_durable_idempotency_ledger(self.initial),
            self.initial,
            "queued",
        )
        second = apply_durable_transition_idempotently(
            build_durable_idempotency_ledger(self.initial),
            self.initial,
            "queued",
        )

        self.assertEqual(first.ledger.records[0], second.ledger.records[0])

    def test_extensible_or_unknown_transition_state_fails_closed(self) -> None:
        ledger = build_durable_idempotency_ledger(self.initial)

        for next_state in (_StringSubclass("queued"), "unknown"):
            with self.subTest(next_state=repr(next_state)):
                with self.assertRaises(DurableIdempotencyError) as caught:
                    apply_durable_transition_idempotently(
                        ledger,
                        self.initial,
                        next_state,
                    )
                self.assertEqual(caught.exception.category, "transition_invalid")

    def test_ledger_and_records_are_immutable(self) -> None:
        ledger = build_durable_idempotency_ledger(self.initial)
        result = apply_durable_transition_idempotently(ledger, self.initial, "queued")

        with self.assertRaises(FrozenInstanceError):
            result.ledger.records = ()  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            result.ledger.records[0].to_state = "cancelled"  # type: ignore[misc]

    def test_safe_dict_is_bounded_and_keeps_runtime_authority_disabled(self) -> None:
        ledger = build_durable_idempotency_ledger(self.initial)
        result = apply_durable_transition_idempotently(ledger, self.initial, "queued")
        payload = result.ledger.as_safe_dict()

        self.assertEqual(payload["version"], DURABLE_IDEMPOTENCY_CONTRACT_VERSION)
        self.assertEqual(payload["dispatchIdentitySha256"], self.binding.identity_sha256)
        self.assertEqual(payload["recordCount"], 1)
        self.assertEqual(
            payload["boundaries"],
            {
                "persistenceEnabled": False,
                "storageWritesEnabled": False,
                "queueEnabled": False,
                "networkDispatchEnabled": False,
                "orchestrationEnabled": False,
            },
        )
        self.assertEqual(
            set(payload),
            {
                "version",
                "dispatchIdentitySha256",
                "recordCount",
                "records",
                "boundaries",
            },
        )
        self.assertEqual(len(payload["records"]), 1)
        self.assertEqual(
            set(payload["records"][0]),
            {
                "slotId",
                "requestSha256",
                "fromState",
                "fromRevision",
                "toState",
                "resultState",
                "resultRevision",
            },
        )


if __name__ == "__main__":
    unittest.main()
