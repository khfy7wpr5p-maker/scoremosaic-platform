from __future__ import annotations

from fractions import Fraction
import json
from pathlib import Path
import sys
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_ensemble.canonical import (
    CanonicalEvent,
    CanonicalMeasure,
    CanonicalPart,
    CanonicalScore,
    EventProvenance,
    Pitch,
    SourceIdentity,
    TupletRatio,
)
from scoremosaic_ensemble.polyphony_complexity import (
    CALCULATION_METHOD_VERSION,
    MAX_EVENTS_PER_SCOPE,
    SCHEMA_VERSION,
    PolyphonyComplexityError,
    build_polyphony_complexity_profile,
    validate_polyphony_complexity_profile,
    validate_polyphony_complexity_profile_against_score,
)

SCHEMA = json.loads(
    (
        REPOSITORY_ROOT
        / "contracts"
        / "polyphonic-complexity-profile-v1.schema.json"
    ).read_text(encoding="utf-8")
)
ARCHITECTURE = json.loads(
    (REPOSITORY_ROOT / "contracts" / "architecture-current-state-v1.json").read_text(
        encoding="utf-8"
    )
)


def _event(
    index: int,
    *,
    onset: int | Fraction = 0,
    duration: int | Fraction = 1,
    voice: str = "1",
    staff: int = 1,
    chord_group: str | None = None,
    chord_index: int | None = None,
    dots: int = 0,
    tuplet: TupletRatio | None = None,
    ties: tuple[str, ...] = (),
    grace: bool = False,
    kind: str = "note",
) -> CanonicalEvent:
    pitch = None if kind == "rest" else Pitch(step="C", alter=Fraction(0), octave=4)
    return CanonicalEvent(
        event_id=f"e{index}",
        xml_order=index,
        kind=kind,
        onset=Fraction(onset),
        effective_duration=Fraction(0 if grace else duration),
        written_duration=None if grace else Fraction(duration),
        written_type=None if grace else "quarter",
        dots=dots,
        tuplet=tuplet,
        voice=voice,
        staff=staff,
        pitch=pitch,
        tab=None,
        grace=grace,
        chord_group=chord_group,
        chord_index=chord_index,
        ties=ties,
        provenance=EventProvenance(
            xml_path=f"/score-partwise/part[1]/measure[1]/note[{index + 1}]",
            source_event_index=index,
        ),
    )


def _score(events: list[CanonicalEvent]) -> CanonicalScore:
    observed = max((event.end for event in events), default=Fraction(0))
    return CanonicalScore(
        source=SourceIdentity(
            engine="audiveris",
            artifact_ref="fixtures/sm-poly-07.xml",
            artifact_sha256="a" * 64,
            engine_version="test-v1",
            model_version=None,
        ),
        root_type="score-partwise",
        parts=(
            CanonicalPart(
                part_id="P1",
                name="Test",
                ordinal=1,
                measures=(
                    CanonicalMeasure(
                        measure_id="P1:M1",
                        number="1",
                        ordinal=1,
                        implicit=False,
                        divisions_at_start=4,
                        time_signature_at_start=None,
                        expected_duration=None,
                        observed_duration=observed,
                        divisions_changes=(),
                        time_signature_changes=(),
                        timing_movements=(),
                        events=tuple(events),
                    ),
                ),
            ),
        ),
    )


def _profile(events: list[CanonicalEvent]) -> dict:
    return build_polyphony_complexity_profile(
        _score(events), part_id="P1", measure_id="P1:M1"
    )


class SmPoly07PolyphonyComplexityTests(unittest.TestCase):
    def test_schema_and_method_are_versioned_and_engine_independent(self) -> None:
        self.assertEqual(SCHEMA_VERSION, SCHEMA["properties"]["schemaVersion"]["const"])
        self.assertEqual(
            CALCULATION_METHOD_VERSION,
            SCHEMA["properties"]["method"]["properties"]["calculationMethodVersion"]["const"],
        )
        encoded = json.dumps(SCHEMA, sort_keys=True)
        self.assertNotIn("engineConfidence", encoded)
        self.assertNotIn("sourceQualityScore", encoded)
        self.assertNotIn("winnerProbability", encoded)

    def test_monophonic_measure_reports_one_voice_without_aggregate_score(self) -> None:
        profile = _profile(
            [_event(0, onset=0, duration=1), _event(1, onset=1, duration=1)]
        )
        voice = profile["dimensions"]["voiceComplexity"]
        overlap = profile["dimensions"]["overlapComplexity"]["overlapDensity"]
        self.assertEqual(1, voice["voiceCount"]["value"])
        self.assertEqual(1, voice["independentVoiceCount"]["value"])
        self.assertEqual(1, voice["maxSimultaneousVoiceCount"]["value"])
        self.assertEqual(0, overlap["value"])
        self.assertIsNone(profile["derivedState"]["aggregateComplexityScore"])
        self.assertIsNone(profile["derivedState"]["complexityClass"])

    def test_two_independent_voices_and_temporal_overlap_are_measured(self) -> None:
        profile = _profile(
            [
                _event(0, onset=0, duration=2, voice="1"),
                _event(1, onset=1, duration=2, voice="2"),
            ]
        )
        voice = profile["dimensions"]["voiceComplexity"]
        overlap = profile["dimensions"]["overlapComplexity"]
        self.assertEqual(2, voice["independentVoiceCount"]["value"])
        self.assertEqual(2, voice["maxSimultaneousVoiceCount"]["value"])
        self.assertEqual(1, overlap["overlapPairCount"]["value"])
        self.assertEqual(10_000, overlap["overlapDensity"]["value"])
        self.assertEqual(1, overlap["overlapDensity"]["numerator"])
        self.assertEqual(1, overlap["overlapDensity"]["denominator"])

    def test_chord_is_not_misclassified_as_multiple_independent_voices(self) -> None:
        profile = _profile(
            [
                _event(
                    0,
                    onset=0,
                    duration=1,
                    voice="1",
                    chord_group="c1",
                    chord_index=0,
                ),
                _event(
                    1,
                    onset=0,
                    duration=1,
                    voice="1",
                    chord_group="c1",
                    chord_index=1,
                ),
            ]
        )
        voice = profile["dimensions"]["voiceComplexity"]
        density = profile["dimensions"]["simultaneousNoteDensity"]
        self.assertEqual(1, voice["independentVoiceCount"]["value"])
        self.assertEqual(1, voice["maxSimultaneousVoiceCount"]["value"])
        self.assertEqual(10_000, density["simultaneousNoteDensity"]["value"])
        self.assertEqual(10_000, density["chordDensity"]["value"])
        self.assertEqual(0, density["independentVoiceOnsetDensity"]["value"])

    def test_three_and_four_voice_profiles_are_stable(self) -> None:
        for count in (3, 4):
            with self.subTest(count=count):
                profile = _profile(
                    [
                        _event(index, voice=str(index + 1), onset=0, duration=1)
                        for index in range(count)
                    ]
                )
                voice = profile["dimensions"]["voiceComplexity"]
                self.assertEqual(count, voice["independentVoiceCount"]["value"])
                self.assertEqual(count, voice["maxSimultaneousVoiceCount"]["value"])

    def test_grand_staff_is_detected_but_cross_staff_is_unavailable(self) -> None:
        profile = _profile(
            [
                _event(0, staff=1, voice="1"),
                _event(1, staff=2, voice="1"),
            ]
        )
        staff = profile["dimensions"]["staffComplexity"]
        self.assertEqual(2, staff["staffCount"]["value"])
        self.assertIs(staff["multiStaffPresent"]["value"], True)
        self.assertIs(staff["crossStaffPresent"]["available"], False)
        self.assertEqual(
            "canonical_v1_has_no_cross_staff_attachment",
            staff["crossStaffPresent"]["reason"],
        )

    def test_tuplet_tie_grace_and_rhythmic_components_are_explicit(self) -> None:
        triplet = TupletRatio(actual_notes=3, normal_notes=2)
        profile = _profile(
            [
                _event(0, onset=0, duration=Fraction(1, 3), tuplet=triplet, dots=1, ties=("start",)),
                _event(1, onset=Fraction(1, 3), duration=Fraction(1, 3), tuplet=triplet),
                _event(2, onset=Fraction(2, 3), duration=Fraction(1, 3), tuplet=triplet),
                _event(3, onset=0, grace=True),
            ]
        )
        tuplet = profile["dimensions"]["tupletComplexity"]
        tie = profile["dimensions"]["tieComplexity"]
        grace = profile["dimensions"]["graceComplexity"]
        rhythm = profile["dimensions"]["rhythmicComplexity"]
        self.assertIs(tuplet["tupletPresent"]["value"], True)
        self.assertEqual(3, tuplet["tupletEventCount"]["value"])
        self.assertIs(tuplet["nestedTupletAvailable"]["value"], False)
        self.assertIs(tuplet["nestedTupletPresent"]["available"], False)
        self.assertEqual(1, tie["tieCount"]["value"])
        self.assertEqual(3333, tie["tieDensity"]["value"])
        self.assertIs(grace["gracePresent"]["value"], True)
        self.assertEqual(1, grace["graceEventCount"]["value"])
        self.assertGreaterEqual(rhythm["distinctDurationCount"]["value"], 1)
        self.assertEqual(3333, rhythm["dottedEventDensity"]["value"])
        self.assertGreaterEqual(rhythm["onsetSubdivisionDiversity"]["value"], 1)

    def test_missing_or_unsupported_evidence_never_collapses_to_false(self) -> None:
        profile = _profile([_event(0)])
        cross_staff = profile["dimensions"]["staffComplexity"]["crossStaffPresent"]
        nested = profile["dimensions"]["tupletComplexity"]["nestedTupletPresent"]
        self.assertIs(cross_staff["available"], False)
        self.assertIsNone(cross_staff["value"])
        self.assertIs(nested["available"], False)
        self.assertIsNone(nested["value"])

    def test_profile_is_deterministic_sha_pinned_and_recomputable(self) -> None:
        score = _score(
            [
                _event(0, onset=0, duration=2, voice="1"),
                _event(1, onset=1, duration=1, voice="2"),
            ]
        )
        first = build_polyphony_complexity_profile(
            score, part_id="P1", measure_id="P1:M1"
        )
        second = build_polyphony_complexity_profile(
            score, part_id="P1", measure_id="P1:M1"
        )
        self.assertEqual(first, second)
        self.assertEqual(first, validate_polyphony_complexity_profile(first))
        self.assertEqual(
            first, validate_polyphony_complexity_profile_against_score(first, score)
        )

    def test_hash_derived_state_and_metric_tampering_fail_closed(self) -> None:
        profile = _profile([_event(0), _event(1, onset=1)])
        profile["derivedState"]["authoritative"] = True
        with self.assertRaisesRegex(
            PolyphonyComplexityError, "complexity_derived_state_invalid"
        ):
            validate_polyphony_complexity_profile(profile)

        profile = _profile([_event(0), _event(1, onset=1)])
        profile["dimensions"]["voiceComplexity"]["voiceCount"]["value"] = 9
        with self.assertRaisesRegex(
            PolyphonyComplexityError, "polyphony_complexity_hash_invalid"
        ):
            validate_polyphony_complexity_profile(profile)

        profile = _profile([_event(0)])
        profile["dimensions"]["voiceComplexity"]["voiceCount"]["value"] = float("nan")
        with self.assertRaisesRegex(
            PolyphonyComplexityError, "complexity_metric_invalid"
        ):
            validate_polyphony_complexity_profile(profile)

    def test_recompute_detects_validly_rehashed_metric_forgery(self) -> None:
        score = _score([_event(0), _event(1, onset=1)])
        profile = build_polyphony_complexity_profile(
            score, part_id="P1", measure_id="P1:M1"
        )
        profile["dimensions"]["voiceComplexity"]["voiceCount"]["value"] = 2

        import hashlib

        without_hash = dict(profile)
        without_hash.pop("profileSha256")
        profile["profileSha256"] = hashlib.sha256(
            json.dumps(
                without_hash,
                ensure_ascii=True,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("ascii")
        ).hexdigest()

        validate_polyphony_complexity_profile(profile)
        with self.assertRaisesRegex(
            PolyphonyComplexityError, "polyphony_complexity_recompute_mismatch"
        ):
            validate_polyphony_complexity_profile_against_score(profile, score)

    def test_scope_bounds_fail_closed_before_quadratic_overlap_work(self) -> None:
        events = [
            _event(index, onset=index, duration=1)
            for index in range(MAX_EVENTS_PER_SCOPE + 1)
        ]
        with self.assertRaisesRegex(
            PolyphonyComplexityError, "complexity_scope_event_bound_exceeded"
        ):
            _profile(events)

    def test_authority_regression_remains_locked(self) -> None:
        profile = _profile([_event(0), _event(1, voice="2")])
        boundary = profile["boundaries"]
        self.assertIs(boundary["winnerSelection"], False)
        self.assertIs(boundary["automaticMerge"], False)
        self.assertIs(boundary["automaticCorrection"], False)
        self.assertIs(boundary["teacherAuthorityOverride"], False)
        self.assertIs(boundary["stage7EvidenceMutation"], False)
        self.assertIs(boundary["stage7QuorumChange"], False)
        self.assertIs(boundary["stOmrQuorumChange"], False)
        self.assertIs(boundary["productionDecisionAuthority"], False)
        self.assertIs(boundary["engineConfidenceIndependent"], True)
        self.assertIs(boundary["sourceQualityIndependent"], True)
        self.assertIs(boundary["visualEvidenceIndependent"], True)

        current = ARCHITECTURE["currentOmr"]
        self.assertEqual(
            ["audiveris", "homr", "clarity"], current["productionCandidateEngines"]
        )
        self.assertEqual(2, current["stage7MinimumCanonicalCandidates"])
        self.assertIs(current["stOmrIntegratedIntoGateway"], False)
        self.assertIs(current["automaticWinnerAuthority"], False)
        self.assertIs(ARCHITECTURE["teacherReview"]["productionWriteActivated"], False)
        self.assertIs(ARCHITECTURE["production"]["productionReady"], False)


if __name__ == "__main__":
    unittest.main()
