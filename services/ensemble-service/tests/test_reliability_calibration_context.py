from __future__ import annotations

from fractions import Fraction
from pathlib import Path
import sys
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_ensemble.canonical import (
    CanonicalMeasure,
    CanonicalPart,
    CanonicalScore,
    SourceIdentity,
)
from scoremosaic_ensemble.polyphony_complexity import build_polyphony_complexity_profile
from scoremosaic_ensemble.reliability_calibration import (
    build_reliability_observation,
    build_reliability_report,
    complexity_context_from_profile,
)


class ReliabilityCalibrationContextTests(unittest.TestCase):
    def test_empty_measure_preserves_unavailable_multistaff_context(self) -> None:
        score = CanonicalScore(
            source=SourceIdentity(
                engine="audiveris",
                artifact_ref="fixtures/sm-poly-08-empty.xml",
                artifact_sha256="a" * 64,
                engine_version="test-v1",
                model_version=None,
            ),
            root_type="score-partwise",
            parts=(
                CanonicalPart(
                    part_id="P1",
                    name="Empty",
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
                            observed_duration=Fraction(0),
                            divisions_changes=(),
                            time_signature_changes=(),
                            timing_movements=(),
                            events=(),
                        ),
                    ),
                ),
            ),
        )
        profile = build_polyphony_complexity_profile(
            score, part_id="P1", measure_id="P1:M1"
        )
        context = complexity_context_from_profile(profile)

        self.assertTrue(context["available"])
        self.assertEqual(context["voiceCount"], 0)
        self.assertIsNone(context["maxSimultaneousVoiceCount"])
        self.assertIsNone(context["multiStaffPresent"])
        self.assertFalse(context["tupletPresent"])
        self.assertEqual(context["overlapDensityBasisPoints"], 0)

        observation = build_reliability_observation(
            fixture_id="poly_fixture_empty0001",
            target_category="voice",
            target_unit_id="P1:M1",
            correct=True,
            engine="audiveris",
            engine_version="test-v1",
            model_version="test-model-v1",
            confidence_basis_points=7500,
            confidence_evidence_source="REPOSITORY_RESEARCH_FIXTURE",
            confidence_method_version="fixture-confidence-v1",
            teacher_gold_reference_sha256="b" * 64,
            semantic_evidence_sha256="c" * 64,
            context_binding_method_version="benchmark-binding-v1",
            complexity=context,
        )
        report = build_reliability_report([observation])
        slices = {(row["dimension"], row["value"]) for row in report["contextSlices"]}
        self.assertNotIn(("multiStaffPresent", "false"), slices)
        self.assertFalse(any(dimension == "multiStaffPresent" for dimension, _ in slices))
        self.assertFalse(
            any(dimension == "maxSimultaneousVoiceCount" for dimension, _ in slices)
        )


if __name__ == "__main__":
    unittest.main()
