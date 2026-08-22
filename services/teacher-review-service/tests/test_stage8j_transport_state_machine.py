from __future__ import annotations

from pathlib import Path
from types import MappingProxyType
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "services" / "teacher-review-service" / "src"
TESTS = ROOT / "services" / "teacher-review-service" / "tests"
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(TESTS))

from scoremosaic_teacher_review import DurableRevisionStore, materialize_canonical_state  # noqa: E402
from scoremosaic_teacher_review.review_timeline import (  # noqa: E402
    ReviewTimelineProjection,
    build_review_timeline_projection,
)
from scoremosaic_teacher_review.review_transport import (  # noqa: E402
    ReviewTransportPlan,
    ReviewTransportState,
    Stage8TransportError,
    advance_cursor,
    build_review_transport_plan,
    initialize_review_transport,
    pause_navigation,
    request_loop_execution,
    seek_cursor,
    start_navigation,
    stop_navigation,
)
from test_stage8i_rational_timeline import (  # noqa: E402
    AUTHZ_KEY,
    STORE_KEY,
    fixture,
    grant,
    scope_for,
)


class Stage8JTransportStateMachineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base = fixture()
        self.scope = scope_for(self.base)
        self.state = materialize_canonical_state(self.scope, self.base)

    def _timeline(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        store = DurableRevisionStore(Path(temp.name) / "store", signing_key=STORE_KEY)
        return build_review_timeline_projection(
            grant=grant(self.base["canonicalSha256"]),
            signing_key=AUTHZ_KEY,
            expected_reviewer_id="teacher_stage8i",
            scope=self.scope,
            store=store,
            state=self.state,
            base_canonical_payload=self.base,
        )

    def test_plan_is_deterministic_and_bound_to_exact_timeline_snapshot(self):
        timeline = self._timeline()
        plans = [build_review_transport_plan(timeline).to_dict() for _ in range(10)]
        self.assertEqual(1, len({item["planSha256"] for item in plans}))
        self.assertEqual(timeline.timeline_sha256, plans[0]["timelineSha256"])
        self.assertEqual(timeline.to_dict()["snapshot"], plans[0]["snapshot"])
        self.assertTrue(plans[0]["capabilities"]["presentationOnly"])
        for name in (
            "loopExecutionAllowed",
            "audioExecutionAllowed",
            "mutationAllowed",
            "approvalAllowed",
            "publicationAllowed",
        ):
            self.assertFalse(plans[0]["capabilities"][name], name)

    def test_plan_projects_only_cursor_timing_and_minimal_event_refs(self):
        plan = build_review_transport_plan(self._timeline()).to_dict()
        self.assertTrue(plan["cursorPoints"])
        first = plan["cursorPoints"][0]
        self.assertEqual(
            {"index", "cursorPointId", "measureOrdinal", "onset", "eventRefs"},
            set(first),
        )
        self.assertEqual(
            {"partId", "measureId", "eventId", "staff", "voice", "kind"},
            set(first["eventRefs"][0]),
        )
        banned = {
            "pitch", "tab", "provenance", "xmlPath", "sourceEventIndex",
            "artifactRef", "artifactSha256", "musicXml", "authorization",
        }

        def walk(value):
            if isinstance(value, dict):
                self.assertTrue(banned.isdisjoint(value))
                for item in value.values():
                    walk(item)
            elif isinstance(value, list):
                for item in value:
                    walk(item)

        walk(plan)

    def test_plan_and_state_cannot_be_forged_through_public_constructor(self):
        with self.assertRaisesRegex(Stage8TransportError, "TRANSPORT_PLAN_CONSTRUCTION_FORBIDDEN"):
            ReviewTransportPlan(MappingProxyType({}))
        with self.assertRaisesRegex(Stage8TransportError, "TRANSPORT_STATE_CONSTRUCTION_FORBIDDEN"):
            ReviewTransportState(MappingProxyType({}))

    def test_start_pause_seek_stop_are_deterministic_and_non_executing(self):
        plan = build_review_transport_plan(self._timeline())
        initial = initialize_review_transport(plan)
        self.assertEqual("stopped", initial.to_dict()["mode"])

        running = start_navigation(plan, initial)
        self.assertEqual("navigating", running.to_dict()["mode"])
        self.assertEqual(running.state_sha256, start_navigation(plan, running).state_sha256)

        paused = pause_navigation(plan, running)
        self.assertEqual("paused", paused.to_dict()["mode"])
        self.assertEqual(paused.state_sha256, pause_navigation(plan, paused).state_sha256)

        point_count = len(plan.to_dict()["cursorPoints"])
        target = min(1, point_count - 1)
        sought = seek_cursor(plan, paused, cursor_index=target)
        self.assertEqual(target, sought.to_dict()["cursorIndex"])
        self.assertEqual(
            sought.state_sha256,
            seek_cursor(plan, sought, cursor_index=target).state_sha256,
        )

        stopped = stop_navigation(plan, sought)
        stopped_again = stop_navigation(plan, stopped)
        self.assertEqual("stopped", stopped.to_dict()["mode"])
        self.assertEqual(0, stopped.to_dict()["cursorIndex"])
        self.assertEqual(stopped.state_sha256, stopped_again.state_sha256)
        for state in (initial, running, paused, sought, stopped):
            data = state.to_dict()
            for name in (
                "executionAllowed",
                "audioEmissionAllowed",
                "loopExecutionAllowed",
                "mutationAllowed",
                "approvalAllowed",
                "publicationAllowed",
            ):
                self.assertFalse(data[name], name)

    def test_advance_requires_navigation_and_naturally_converges_to_stopped(self):
        plan = build_review_transport_plan(self._timeline())
        state = initialize_review_transport(plan)
        with self.assertRaisesRegex(Stage8TransportError, "TRANSPORT_ADVANCE_INVALID_STATE"):
            advance_cursor(plan, state)
        state = start_navigation(plan, state)
        total = len(plan.to_dict()["cursorPoints"])
        for _ in range(total):
            if state.to_dict()["mode"] != "navigating":
                break
            state = advance_cursor(plan, state)
        self.assertEqual("stopped", state.to_dict()["mode"])
        self.assertEqual(total - 1, state.to_dict()["cursorIndex"])
        reset = stop_navigation(plan, state)
        self.assertEqual(0, reset.to_dict()["cursorIndex"])

    def test_loop_execution_is_explicitly_forbidden(self):
        plan = build_review_transport_plan(self._timeline())
        state = initialize_review_transport(plan)
        with self.assertRaisesRegex(Stage8TransportError, "TRANSPORT_LOOP_EXECUTION_FORBIDDEN"):
            request_loop_execution(plan, state)

    def test_timeline_capability_expansion_fails_closed(self):
        timeline = self._timeline()
        forged = timeline.to_dict()
        forged.pop("timelineSha256")
        forged["capabilities"]["canPlay"] = True
        forged_timeline = ReviewTimelineProjection(MappingProxyType(forged))
        with self.assertRaisesRegex(Stage8TransportError, "TRANSPORT_TIMELINE_CAPABILITY_INVALID"):
            build_review_transport_plan(forged_timeline)

    def test_state_from_different_plan_is_rejected_as_stale(self):
        plan = build_review_transport_plan(self._timeline())
        state = initialize_review_transport(plan)

        forged_payload = self._timeline().to_dict()
        forged_payload.pop("timelineSha256")
        forged_payload["snapshot"] = dict(forged_payload["snapshot"])
        forged_payload["snapshot"]["stateSha256"] = "f" * 64
        different_timeline = ReviewTimelineProjection(MappingProxyType(forged_payload))
        different_plan = build_review_transport_plan(different_timeline)
        with self.assertRaisesRegex(Stage8TransportError, "TRANSPORT_STALE_PLAN"):
            start_navigation(different_plan, state)

    def test_transport_module_contains_no_audio_network_clock_or_process_runtime(self):
        source = (
            SRC / "scoremosaic_teacher_review" / "review_transport.py"
        ).read_text(encoding="utf-8").lower()
        for forbidden in (
            "subprocess", "os.system", "socket.", "requests.", "urllib.",
            "websocket", "midi", "soundfont", "pyaudio", "sounddevice",
            "time.sleep", "perf_counter", "monotonic(", "datetime.now",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)
        self.assertNotIn("except exception", source)
        self.assertNotIn("except baseexception", source)


if __name__ == "__main__":
    unittest.main()
