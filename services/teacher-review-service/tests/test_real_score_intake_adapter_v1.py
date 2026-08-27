from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
TEACHER_SRC = ROOT / "services" / "teacher-review-service" / "src"
sys.path.insert(0, str(TEACHER_SRC))

from scoremosaic_teacher_review.real_score_intake_adapter_v1 import (  # noqa: E402
    CORE_COMMIT,
    REAL_SCORE_RUNTIME_VERSION,
    RealScoreIntakeAdapterError,
    build_real_score_runtime_projection,
)
from test_real_score_intake_contract_v1 import MUSICXML  # noqa: E402
from test_real_score_intake_contract_v1_1 import (  # noqa: E402
    canonical_digest,
    canonical_score,
    note_event,
    v1_1_payload,
)


def rehash(score: dict) -> None:
    score["canonicalSha256"] = "0" * 64
    score["canonicalSha256"] = canonical_digest(score)


def extra_measure(score: dict) -> None:
    event = note_event("canonical-note-101", "G", 0, 0)
    event["chordGroup"] = None
    event["chordIndex"] = None
    event["onset"] = {"numerator": 0, "denominator": 1}
    event["effectiveDuration"] = {"numerator": 1, "denominator": 1}
    event["writtenDuration"] = {"numerator": 1, "denominator": 1}
    event["provenance"] = {
        "xmlPath": "/score-partwise/part[1]/measure[2]/note[1]",
        "sourceEventIndex": 0,
    }
    score["parts"][0]["measures"].append(
        {
            "measureId": "measure-2",
            "number": "2",
            "ordinal": 2,
            "implicit": False,
            "divisionsAtStart": 4,
            "timeSignatureAtStart": {"beats": "4", "beatType": 4},
            "expectedDuration": {"numerator": 1, "denominator": 1},
            "observedDuration": {"numerator": 1, "denominator": 1},
            "divisionsChanges": [],
            "timeSignatureChanges": [],
            "timingMovements": [],
            "events": [event],
        }
    )
    rehash(score)


class RealScoreIntakeAdapterV1Tests(unittest.TestCase):
    def assert_adapter_error(self, payload: dict, score: dict, code: str) -> None:
        with self.assertRaises(RealScoreIntakeAdapterError) as caught:
            build_real_score_runtime_projection(payload, musicxml=MUSICXML, canonical_score=score)
        self.assertEqual(caught.exception.code, code)

    def test_verified_full_score_projects_chord_rest_notation_and_targets(self) -> None:
        payload, score = v1_1_payload()
        runtime = build_real_score_runtime_projection(payload, musicxml=MUSICXML, canonical_score=score).as_dict()
        self.assertEqual(runtime["version"], REAL_SCORE_RUNTIME_VERSION)
        self.assertEqual(runtime["coreCommit"], CORE_COMMIT)
        self.assertEqual(runtime["scoreSource"], "canonical")
        self.assertIs(runtime["synthetic"], False)
        self.assertEqual(runtime["canonicalSha256"], score["canonicalSha256"])
        self.assertEqual(runtime["score"]["source"], {
            "sha256": score["canonicalSha256"], "format": "canonical", "byteLength": None
        })
        measures = runtime["score"]["parts"][0]["staves"][0]["measures"]
        self.assertEqual(len(measures), 1)
        events = measures[0]["voices"][0]["events"]
        self.assertEqual([event["kind"] for event in events], ["chord", "rest"])
        self.assertEqual(events[0]["id"], "core-chord-001")
        self.assertEqual([note["id"] for note in events[0]["notes"]], ["core-note-c", "core-note-e"])
        self.assertEqual(events[1]["id"], "core-rest-001")
        self.assertTrue(any(entry["target"]["eventId"] == "core-rest-001" and entry["notation"]["dots"] == 1 for entry in runtime["notation"]["events"]))
        self.assertEqual(len(runtime["issueTargets"]), 3)
        self.assertTrue(all(value is False for value in runtime["authority"].values()))

    def test_projection_uses_full_score_not_issue_count(self) -> None:
        score = canonical_score()
        extra_measure(score)
        payload, score = v1_1_payload(score)
        runtime = build_real_score_runtime_projection(payload, musicxml=MUSICXML, canonical_score=score).as_dict()
        measures = runtime["score"]["parts"][0]["staves"][0]["measures"]
        self.assertEqual(len(measures), 2)
        self.assertEqual(len(runtime["issueTargets"]), 3)
        second_events = measures[1]["voices"][0]["events"]
        self.assertEqual(len(second_events), 1)
        self.assertEqual(second_events[0]["kind"], "note")
        self.assertEqual(second_events[0]["note"]["pitch"]["step"], "G")

    def test_unnamed_part_uses_canonical_part_id_as_core_name(self) -> None:
        score = canonical_score()
        canonical_part_id = score["parts"][0]["partId"]
        score["parts"][0]["name"] = None
        rehash(score)
        payload, score = v1_1_payload(score)
        runtime = build_real_score_runtime_projection(payload, musicxml=MUSICXML, canonical_score=score).as_dict()
        self.assertEqual(runtime["score"]["parts"][0]["name"], canonical_part_id)

    def test_projection_is_deterministic(self) -> None:
        payload, score = v1_1_payload()
        first = build_real_score_runtime_projection(payload, musicxml=MUSICXML, canonical_score=score).as_dict()
        second = build_real_score_runtime_projection(payload, musicxml=MUSICXML, canonical_score=score).as_dict()
        self.assertEqual(first, second)

    def test_unbound_unsupported_event_still_fails_closed(self) -> None:
        score = canonical_score()
        extra_measure(score)
        event = score["parts"][0]["measures"][1]["events"][0]
        event["kind"] = "unpitched"
        event["pitch"] = None
        rehash(score)
        payload, score = v1_1_payload(score)
        self.assert_adapter_error(payload, score, "ADAPTER_V1_UNPITCHED_UNSUPPORTED")

    def test_microtonal_pitch_is_not_coerced(self) -> None:
        score = canonical_score()
        score["parts"][0]["measures"][0]["events"][0]["pitch"]["alter"] = {"numerator": 1, "denominator": 2}
        rehash(score)
        payload, score = v1_1_payload(score)
        self.assert_adapter_error(payload, score, "ADAPTER_V1_PITCH_UNSUPPORTED")

    def test_grace_tab_and_excess_dots_fail_closed(self) -> None:
        for field, value, code in (
            ("grace", True, "ADAPTER_V1_GRACE_UNSUPPORTED"),
            ("tab", {"string": 1, "fret": 3}, "ADAPTER_V1_TAB_UNSUPPORTED"),
            ("dots", 4, "ADAPTER_V1_DOTS_UNSUPPORTED"),
        ):
            score = canonical_score()
            score["parts"][0]["measures"][0]["events"][0][field] = value
            rehash(score)
            payload, score = v1_1_payload(score)
            self.assert_adapter_error(payload, score, code)

    def test_core_document_ids_are_not_truncated(self) -> None:
        payload, score = v1_1_payload()
        payload["document"]["documentId"] = "d" * 129
        self.assert_adapter_error(payload, score, "ADAPTER_V1_DOCUMENT_ID_UNSUPPORTED")

    def test_bound_core_ids_cannot_collide_with_document_identity(self) -> None:
        payload, score = v1_1_payload()
        payload["document"]["documentId"] = "core-chord-001"
        self.assert_adapter_error(payload, score, "ADAPTER_V1_CORE_TARGET_COLLISION")

    def test_measure_start_time_signature_change_is_preserved_but_midmeasure_change_fails(self) -> None:
        score = canonical_score()
        score["parts"][0]["measures"][0]["timeSignatureChanges"] = [{
            "xmlOrder": 0,
            "onset": {"numerator": 0, "denominator": 1},
            "timeSignature": {"beats": "4", "beatType": 4},
        }]
        rehash(score)
        payload, score = v1_1_payload(score)
        runtime = build_real_score_runtime_projection(payload, musicxml=MUSICXML, canonical_score=score).as_dict()
        self.assertEqual(runtime["notation"]["measures"][0]["notation"]["timeSignature"], {"beats": 4, "beatType": 4})

        score = deepcopy(score)
        score["parts"][0]["measures"][0]["timeSignatureChanges"][0]["onset"] = {"numerator": 1, "denominator": 4}
        rehash(score)
        payload, score = v1_1_payload(score)
        self.assert_adapter_error(payload, score, "ADAPTER_V1_TIME_SIGNATURE_UNSUPPORTED")

    def test_ignored_canonical_musical_structure_is_not_silently_lost(self) -> None:
        score = canonical_score()
        score["diagnostics"] = [{
            "code": "ignored-attribute",
            "severity": "warning",
            "message": "MusicXML attribute 'clef' is preserved only in the raw candidate.",
            "xmlPath": "/score-partwise/part[1]/measure[1]/attributes[1]/clef",
        }]
        rehash(score)
        payload, score = v1_1_payload(score)
        self.assert_adapter_error(payload, score, "ADAPTER_V1_NOTATION_COVERAGE_UNSUPPORTED")

    def test_truncated_diagnostics_fail_closed(self) -> None:
        score = canonical_score()
        score["diagnostics"] = [{
            "code": "diagnostics-truncated",
            "severity": "warning",
            "message": "Additional normalization diagnostics were omitted.",
            "xmlPath": None,
        }]
        rehash(score)
        payload, score = v1_1_payload(score)
        self.assert_adapter_error(payload, score, "ADAPTER_V1_NOTATION_COVERAGE_UNSUPPORTED")


if __name__ == "__main__":
    unittest.main()
