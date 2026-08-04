from __future__ import annotations

from dataclasses import replace
from fractions import Fraction
from pathlib import Path
import json
import sys
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_ensemble.canonical import (
    CanonicalEvent,
    CanonicalMeasure,
    CanonicalPart,
    CanonicalScore,
    EventProvenance,
    Pitch,
    SourceIdentity,
    TabPosition,
    TimeSignature,
    TupletRatio,
)
from scoremosaic_ensemble.comparator import (
    COMPARISON_FORMAT_VERSION,
    ComparisonError,
    compare_candidates,
)


def _source(engine: str, digit: str) -> SourceIdentity:
    return SourceIdentity(
        engine=engine,
        engine_version=f"{engine}-test",
        model_version="fixture-model",
        artifact_ref=f"candidates/{engine}/{digit}.musicxml",
        artifact_sha256=digit * 64,
    )


def _score(engine: str = "homr", digit: str = "1") -> CanonicalScore:
    note = CanonicalEvent(
        event_id=f"event-{digit}-1",
        xml_order=1,
        kind="note",
        onset=Fraction(0),
        effective_duration=Fraction(1),
        written_duration=Fraction(1),
        written_type="quarter",
        dots=0,
        tuplet=None,
        voice="1",
        staff=1,
        pitch=Pitch("C", Fraction(0), 4),
        tab=None,
        grace=False,
        chord_group=None,
        chord_index=None,
        ties=(),
        provenance=EventProvenance(
            xml_path=f"/score-partwise/part[1]/measure[1]/note[1]/{digit}",
            source_event_index=0,
        ),
    )
    rest = CanonicalEvent(
        event_id=f"event-{digit}-2",
        xml_order=2,
        kind="rest",
        onset=Fraction(1),
        effective_duration=Fraction(1),
        written_duration=Fraction(1),
        written_type="quarter",
        dots=0,
        tuplet=None,
        voice="1",
        staff=1,
        pitch=None,
        tab=None,
        grace=False,
        chord_group=None,
        chord_index=None,
        ties=(),
        provenance=EventProvenance(
            xml_path=f"/score-partwise/part[1]/measure[1]/note[2]/{digit}",
            source_event_index=1,
        ),
    )
    measure = CanonicalMeasure(
        measure_id=f"measure-{digit}-1",
        number="1",
        ordinal=1,
        implicit=False,
        divisions_at_start=4,
        time_signature_at_start=TimeSignature("4", 4),
        expected_duration=Fraction(4),
        observed_duration=Fraction(2),
        divisions_changes=(),
        time_signature_changes=(),
        timing_movements=(),
        events=(note, rest),
    )
    part = CanonicalPart(
        part_id=f"part-{digit}-1",
        name="Music",
        ordinal=1,
        measures=(measure,),
    )
    return CanonicalScore(
        source=_source(engine, digit),
        root_type="score-partwise",
        movement_title="Comparator fixture",
        parts=(part,),
    )


def _replace_measure(score: CanonicalScore, measure: CanonicalMeasure) -> CanonicalScore:
    part = replace(score.parts[0], measures=(measure,))
    return replace(score, parts=(part,))


def _replace_event(
    score: CanonicalScore,
    event_index: int,
    **changes: object,
) -> CanonicalScore:
    measure = score.parts[0].measures[0]
    events = list(measure.events)
    events[event_index] = replace(events[event_index], **changes)
    return _replace_measure(score, replace(measure, events=tuple(events)))


class ComparatorFoundationTests(unittest.TestCase):
    def test_identical_music_has_no_differences(self) -> None:
        result = compare_candidates((_score("homr", "1"), _score("clarity", "2")))

        self.assertEqual(result.differences, ())
        self.assertTrue(result.identical)
        payload = result.as_dict()
        self.assertEqual(payload["formatVersion"], COMPARISON_FORMAT_VERSION)
        self.assertEqual(payload["candidateCount"], 2)
        self.assertEqual(payload["differenceCount"], 0)
        self.assertTrue(payload["boundaries"]["readOnly"])
        self.assertFalse(payload["boundaries"]["engineRanking"])
        self.assertFalse(payload["boundaries"]["winnerSelection"])
        self.assertFalse(payload["boundaries"]["automaticMerge"])
        self.assertFalse(payload["boundaries"]["automaticCorrection"])

    def test_candidate_order_does_not_change_result(self) -> None:
        left = _score("homr", "1")
        right = _replace_event(
            _score("clarity", "2"),
            0,
            pitch=Pitch("D", Fraction(0), 4),
        )

        forward = compare_candidates((left, right))
        reverse = compare_candidates((right, left))

        self.assertEqual(forward.to_json(indent=None), reverse.to_json(indent=None))
        self.assertEqual(forward.result_sha256, reverse.result_sha256)

    def test_all_requested_comparison_domains_are_reported(self) -> None:
        baseline = _score("homr", "1")
        variant = _score("clarity", "2")
        first = replace(
            variant.parts[0].measures[0].events[0],
            onset=Fraction(1, 4),
            effective_duration=Fraction(1, 2),
            written_duration=Fraction(1, 2),
            written_type="eighth",
            pitch=Pitch("D", Fraction(1), 5),
            chord_group="chord-variant",
            chord_index=0,
            voice="2",
            staff=2,
            ties=("start",),
            dots=1,
            tuplet=TupletRatio(3, 2),
            tab=TabPosition(2, 3),
        )
        second = replace(
            variant.parts[0].measures[0].events[1],
            kind="unpitched",
        )
        measure = replace(
            variant.parts[0].measures[0],
            number="A",
            implicit=True,
            time_signature_at_start=TimeSignature("3", 4),
            expected_duration=Fraction(3),
            observed_duration=Fraction(3),
            events=(first, second),
        )
        variant = _replace_measure(variant, measure)

        result = compare_candidates((baseline, variant))
        fields = {difference.field for difference in result.differences}
        categories = {difference.category for difference in result.differences}

        self.assertTrue(
            {
                "measure.number",
                "measure.implicit",
                "measure.expectedDuration",
                "measure.observedDuration",
                "measure.timeSignature",
                "event.onset",
                "event.kind",
                "event.effectiveDuration",
                "event.writtenDuration",
                "event.writtenType",
                "event.pitch",
                "event.chord",
                "event.voice",
                "event.staff",
                "event.ties",
                "event.dots",
                "event.tuplet",
                "event.tab",
            }.issubset(fields)
        )
        self.assertEqual(
            categories,
            {
                "measure",
                "event_time",
                "pitch",
                "duration",
                "rest",
                "chord",
                "voice",
                "staff",
                "tie",
                "dot",
                "tuplet",
                "tab",
            },
        )

    def test_missing_event_reports_presence_without_field_flood(self) -> None:
        baseline = _score("homr", "1")
        variant = _score("clarity", "2")
        measure = variant.parts[0].measures[0]
        variant = _replace_measure(variant, replace(measure, events=measure.events[:1]))

        result = compare_candidates((baseline, variant))
        event_two = [
            difference
            for difference in result.differences
            if difference.location.event_ordinal == 2
        ]

        self.assertEqual(len(event_two), 1)
        self.assertEqual(event_two[0].field, "event.presence")
        self.assertEqual(
            {observation.present for observation in event_two[0].observations},
            {False, True},
        )

    def test_missing_measure_is_reported_once(self) -> None:
        baseline = _score("homr", "1")
        variant = _score("clarity", "2")
        variant = replace(variant, parts=(replace(variant.parts[0], measures=()),))

        result = compare_candidates((baseline, variant))

        self.assertEqual(len(result.differences), 1)
        self.assertEqual(result.differences[0].field, "measure.presence")

    def test_event_provenance_and_source_identity_are_preserved(self) -> None:
        baseline = _score("homr", "1")
        variant = _replace_event(
            _score("clarity", "2"),
            0,
            pitch=Pitch("E", Fraction(-1), 4),
        )

        result = compare_candidates((baseline, variant))
        pitch_difference = next(
            difference
            for difference in result.differences
            if difference.field == "event.pitch"
        )

        self.assertEqual(len(pitch_difference.observations), 2)
        for observation in pitch_difference.observations:
            self.assertIsNotNone(observation.event_id)
            self.assertIsNotNone(observation.xml_path)
            self.assertIsNotNone(observation.source_event_index)
            self.assertIn(observation.source.engine, {"homr", "clarity"})
            self.assertEqual(len(observation.canonical_sha256), 64)

    def test_three_candidates_produce_one_neutral_difference_per_field(self) -> None:
        first = _score("homr", "1")
        second = _replace_event(
            _score("clarity", "2"),
            0,
            pitch=Pitch("D", Fraction(0), 4),
        )
        third = _replace_event(
            _score("audiveris", "3"),
            0,
            pitch=Pitch("E", Fraction(0), 4),
        )

        result = compare_candidates((first, second, third))
        pitch_differences = [
            difference
            for difference in result.differences
            if difference.field == "event.pitch"
        ]

        self.assertEqual(len(pitch_differences), 1)
        self.assertEqual(len(pitch_differences[0].observations), 3)
        serialized = json.loads(result.to_json(indent=None))
        text = json.dumps(serialized, sort_keys=True).lower()
        self.assertNotIn("recommendation", text)
        self.assertNotIn("selectedcandidate", text)
        self.assertNotIn("winnercandidate", text)

    def test_comparison_does_not_mutate_candidates(self) -> None:
        left = _score("homr", "1")
        right = _replace_event(
            _score("clarity", "2"),
            0,
            pitch=Pitch("F", Fraction(0), 4),
        )
        before = (left.canonical_sha256, right.canonical_sha256)

        compare_candidates((left, right))

        self.assertEqual(before, (left.canonical_sha256, right.canonical_sha256))

    def test_duplicate_source_identity_is_rejected(self) -> None:
        score = _score("homr", "1")
        duplicate = replace(score, movement_title="Same source, different title")

        with self.assertRaisesRegex(ComparisonError, "duplicate candidate source"):
            compare_candidates((score, duplicate))

    def test_candidate_count_limits_are_enforced(self) -> None:
        with self.assertRaisesRegex(ComparisonError, "two to eight"):
            compare_candidates((_score("homr", "1"),))

        candidates = []
        engines = ("homr", "clarity", "audiveris")
        digits = "123456789"
        for index, digit in enumerate(digits):
            candidates.append(_score(engines[index % len(engines)], digit))
        with self.assertRaisesRegex(ComparisonError, "two to eight"):
            compare_candidates(candidates)

    def test_difference_identifiers_and_result_hash_are_deterministic(self) -> None:
        left = _score("homr", "1")
        right = _replace_event(
            _score("clarity", "2"),
            0,
            pitch=Pitch("G", Fraction(0), 4),
        )

        first = compare_candidates((left, right))
        second = compare_candidates((left, right))

        self.assertEqual(first.result_sha256, second.result_sha256)
        self.assertEqual(
            [item.difference_id for item in first.differences],
            [item.difference_id for item in second.differences],
        )


if __name__ == "__main__":
    unittest.main()
