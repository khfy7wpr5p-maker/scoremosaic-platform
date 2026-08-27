from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[3]
TEACHER_SRC = ROOT / "services" / "teacher-review-service" / "src"
sys.path.insert(0, str(TEACHER_SRC))

from scoremosaic_teacher_review.real_score_intake import (  # noqa: E402
    REAL_SCORE_INTAKE_VERSION,
    RealScoreIntakeError,
    validate_real_score_intake,
)
from scoremosaic_teacher_review.real_score_intake_v1_1 import (  # noqa: E402
    MAPPING_POLICY_V1_1,
    REAL_SCORE_INTAKE_VERSION_V1_1,
    validate_real_score_intake_v1_1,
)
from test_real_score_intake_contract_v1 import MUSICXML, valid_payload  # noqa: E402


SCHEMA_PATH = ROOT / "contracts" / "real-score-intake-v1.1.schema.json"


def canonical_digest(score: dict) -> str:
    payload = {key: value for key, value in score.items() if key != "canonicalSha256"}
    return sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def provenance(index: int) -> dict:
    return {
        "xmlPath": f"/score-partwise/part[1]/measure[1]/note[{index + 1}]",
        "sourceEventIndex": index,
    }


def note_event(event_id: str, pitch_step: str, index: int, chord_index: int) -> dict:
    return {
        "eventId": event_id,
        "xmlOrder": index,
        "kind": "note",
        "onset": {"numerator": 0, "denominator": 1},
        "effectiveDuration": {"numerator": 1, "denominator": 4},
        "writtenDuration": {"numerator": 1, "denominator": 4},
        "writtenType": "quarter",
        "dots": 0,
        "tuplet": None,
        "voice": "1",
        "staff": 1,
        "pitch": {
            "step": pitch_step,
            "alter": {"numerator": 0, "denominator": 1},
            "octave": 4,
        },
        "tab": None,
        "grace": False,
        "chordGroup": "chord-group-001",
        "chordIndex": chord_index,
        "ties": [],
        "provenance": provenance(index),
    }


def rest_event() -> dict:
    return {
        "eventId": "canonical-rest-001",
        "xmlOrder": 2,
        "kind": "rest",
        "onset": {"numerator": 1, "denominator": 4},
        "effectiveDuration": {"numerator": 3, "denominator": 4},
        "writtenDuration": {"numerator": 3, "denominator": 4},
        "writtenType": "half",
        "dots": 1,
        "tuplet": None,
        "voice": "1",
        "staff": 1,
        "pitch": None,
        "tab": None,
        "grace": False,
        "chordGroup": None,
        "chordIndex": None,
        "ties": [],
        "provenance": provenance(2),
    }


def canonical_score() -> dict:
    musicxml_sha = sha256(MUSICXML).hexdigest()
    score = {
        "schemaVersion": "1.0",
        "source": {
            "engine": "audiveris",
            "engineVersion": "5.8.1",
            "modelVersion": None,
            "artifactRef": "candidates/audiveris/musicxml.xml",
            "artifactSha256": musicxml_sha,
        },
        "rootType": "score-partwise",
        "movementTitle": "Contract fixture",
        "parts": [
            {
                "partId": "P1",
                "name": "Piano",
                "ordinal": 1,
                "measures": [
                    {
                        "measureId": "measure-1",
                        "number": "1",
                        "ordinal": 1,
                        "implicit": False,
                        "divisionsAtStart": 4,
                        "timeSignatureAtStart": {"beats": "4", "beatType": 4},
                        "expectedDuration": {"numerator": 1, "denominator": 1},
                        "observedDuration": {"numerator": 1, "denominator": 1},
                        "divisionsChanges": [],
                        "timeSignatureChanges": [],
                        "timingMovements": [],
                        "events": [
                            note_event("canonical-note-001", "C", 0, 0),
                            note_event("canonical-note-002", "E", 1, 1),
                            rest_event(),
                        ],
                    }
                ],
            }
        ],
        "diagnostics": [],
        "canonicalSha256": "0" * 64,
    }
    score["canonicalSha256"] = canonical_digest(score)
    return score


def review_binding(payload: dict, score: dict, *, issue_id: str, event_id: str, target: dict) -> dict:
    event = next(
        event
        for part in score["parts"]
        for measure in part["measures"]
        for event in measure["events"]
        if event["eventId"] == event_id
    )
    return {
        "issueId": issue_id,
        "sourceRegion": "page-1/measure-1",
        "candidateId": payload["candidate"]["candidateId"],
        "candidateSha256": payload["candidate"]["candidateSha256"],
        "canonicalSha256": score["canonicalSha256"],
        "canonicalEventId": event_id,
        "coreTarget": target,
        "provenance": deepcopy(event["provenance"]),
    }


def v1_1_payload(score: dict | None = None) -> tuple[dict, dict]:
    score = canonical_score() if score is None else score
    payload = valid_payload()
    payload["schemaVersion"] = REAL_SCORE_INTAKE_VERSION_V1_1
    payload["mappingPolicy"] = dict(MAPPING_POLICY_V1_1)
    payload["canonical"]["canonicalSha256"] = score["canonicalSha256"]
    payload["reviewBindings"] = [
        review_binding(
            payload,
            score,
            issue_id="issue-chord-c",
            event_id="canonical-note-001",
            target={"kind": "note", "eventId": "core-chord-001", "noteId": "core-note-c"},
        ),
        review_binding(
            payload,
            score,
            issue_id="issue-chord-e",
            event_id="canonical-note-002",
            target={"kind": "note", "eventId": "core-chord-001", "noteId": "core-note-e"},
        ),
        review_binding(
            payload,
            score,
            issue_id="issue-rest",
            event_id="canonical-rest-001",
            target={"kind": "event", "eventId": "core-rest-001"},
        ),
    ]
    return payload, score


class RealScoreIntakeContractV1_1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    def assert_error(self, payload: dict, score: dict, code: str) -> None:
        with self.assertRaises(RealScoreIntakeError) as caught:
            validate_real_score_intake_v1_1(payload, musicxml=MUSICXML, canonical_score=score)
        self.assertEqual(caught.exception.code, code)

    def test_schema_is_closed_versioned_and_uses_explicit_semantic_targets(self) -> None:
        self.assertTrue(SCHEMA_PATH.is_file())
        self.assertFalse(SCHEMA_PATH.is_symlink())
        self.assertIs(self.schema["additionalProperties"], False)
        self.assertEqual(
            self.schema["properties"]["schemaVersion"]["const"],
            REAL_SCORE_INTAKE_VERSION_V1_1,
        )
        policy = self.schema["$defs"]["mappingPolicy"]["properties"]
        self.assertEqual(policy["eventIdentity"]["const"], "preserve-canonical-event-id")
        self.assertEqual(policy["coreTargetIdentity"]["const"], "explicit-semantic-target")
        self.assertEqual(policy["chordMapping"]["const"], "canonical-note-to-core-chord-note")
        self.assertIs(policy["syntheticScoreAllowed"]["const"], False)
        self.assertIs(policy["rendererAuthority"]["const"], False)
        alternatives = self.schema["$defs"]["coreTarget"]["oneOf"]
        self.assertEqual({item["properties"]["kind"]["const"] for item in alternatives}, {"note", "event"})

    def test_valid_chord_notes_share_core_event_but_keep_distinct_note_targets(self) -> None:
        payload, score = v1_1_payload()
        result = validate_real_score_intake_v1_1(payload, musicxml=MUSICXML, canonical_score=score)
        self.assertEqual(result.review_binding_count, 3)
        self.assertEqual(result.note_target_count, 2)
        self.assertEqual(result.event_target_count, 1)
        self.assertEqual(result.canonical_sha256, score["canonicalSha256"])
        safe = result.as_safe_dict()
        self.assertNotIn("musicxml", safe)
        self.assertNotIn("coreTarget", safe)
        self.assertIs(safe["authoritative"], False)
        self.assertIs(safe["persistent"], False)
        self.assertIs(safe["networkCapable"], False)

    def test_same_canonical_event_may_have_multiple_issues_only_with_same_target(self) -> None:
        payload, score = v1_1_payload()
        extra = deepcopy(payload["reviewBindings"][0])
        extra["issueId"] = "issue-chord-c-duration"
        payload["reviewBindings"].append(extra)
        result = validate_real_score_intake_v1_1(payload, musicxml=MUSICXML, canonical_score=score)
        self.assertEqual(result.review_binding_count, 4)

        payload, score = v1_1_payload()
        extra = deepcopy(payload["reviewBindings"][0])
        extra["issueId"] = "issue-chord-c-conflict"
        extra["coreTarget"]["noteId"] = "different-core-note"
        payload["reviewBindings"].append(extra)
        self.assert_error(payload, score, "INTAKE_V1_1_TARGET_MAPPING_CONFLICT")

    def test_distinct_canonical_events_cannot_collide_on_same_core_target(self) -> None:
        payload, score = v1_1_payload()
        payload["reviewBindings"][1]["coreTarget"] = deepcopy(payload["reviewBindings"][0]["coreTarget"])
        self.assert_error(payload, score, "INTAKE_V1_1_CORE_TARGET_COLLISION")

    def test_one_canonical_chord_group_must_map_to_one_core_chord_event(self) -> None:
        payload, score = v1_1_payload()
        payload["reviewBindings"][1]["coreTarget"]["eventId"] = "different-core-chord"
        self.assert_error(payload, score, "INTAKE_V1_1_CHORD_TARGET_MISMATCH")

    def test_note_and_rest_target_kinds_are_fail_closed(self) -> None:
        payload, score = v1_1_payload()
        payload["reviewBindings"][0]["coreTarget"] = {"kind": "event", "eventId": "core-note-as-event"}
        self.assert_error(payload, score, "INTAKE_V1_1_TARGET_KIND_MISMATCH")

        payload, score = v1_1_payload()
        payload["reviewBindings"][2]["coreTarget"] = {
            "kind": "note",
            "eventId": "core-rest-as-note",
            "noteId": "core-rest-note",
        }
        self.assert_error(payload, score, "INTAKE_V1_1_TARGET_KIND_MISMATCH")

    def test_provenance_and_actual_canonical_hash_are_rechecked(self) -> None:
        payload, score = v1_1_payload()
        payload["reviewBindings"][0]["provenance"]["sourceEventIndex"] = 99
        self.assert_error(payload, score, "INTAKE_V1_1_PROVENANCE_MISMATCH")

        payload, score = v1_1_payload()
        score["movementTitle"] = "Tampered after hash"
        self.assert_error(payload, score, "INTAKE_V1_1_CANONICAL_HASH_MISMATCH")

    def test_unknown_or_coordinate_like_core_target_fields_fail_closed(self) -> None:
        payload, score = v1_1_payload()
        payload["reviewBindings"][0]["coreTarget"]["x"] = 120
        self.assert_error(payload, score, "INTAKE_V1_1_CORE_TARGET_INVALID")

        payload, score = v1_1_payload()
        payload["reviewBindings"][0]["coreTarget"]["eventId"] = "x" * 129
        self.assert_error(payload, score, "INTAKE_V1_1_CORE_TARGET_INVALID")

    def test_unpitched_canonical_event_is_not_silently_dropped_or_coerced(self) -> None:
        score = canonical_score()
        event = score["parts"][0]["measures"][0]["events"][0]
        event["kind"] = "unpitched"
        event["pitch"] = None
        score["canonicalSha256"] = canonical_digest(score)
        payload, score = v1_1_payload(score)
        self.assert_error(payload, score, "INTAKE_V1_1_UNSUPPORTED_CANONICAL_EVENT_KIND")

    def test_v1_contract_remains_unchanged_and_valid(self) -> None:
        payload = valid_payload()
        self.assertEqual(payload["schemaVersion"], REAL_SCORE_INTAKE_VERSION)
        result = validate_real_score_intake(payload, musicxml=MUSICXML)
        self.assertEqual(result.review_binding_count, 1)


if __name__ == "__main__":
    unittest.main()
