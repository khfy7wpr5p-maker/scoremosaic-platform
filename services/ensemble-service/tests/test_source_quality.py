from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_ensemble.source_quality import (
    MEASUREMENT_POLICY,
    QUALITY_DIMENSIONS,
    SCHEMA_VERSION,
    SourceQualityError,
    build_source_quality_profile,
    derive_source_quality_state,
    validate_source_quality_core,
    validate_source_quality_profile,
)
from scoremosaic_ensemble.visual_evidence import _validate_source_quality

SCHEMA = json.loads(
    (
        REPOSITORY_ROOT
        / "contracts"
        / "polyphonic-source-quality-profile-v1.schema.json"
    ).read_text(encoding="utf-8")
)
ARCHITECTURE = json.loads(
    (REPOSITORY_ROOT / "contracts" / "architecture-current-state-v1.json").read_text(
        encoding="utf-8"
    )
)


def _measurement(
    risk: int | None,
    *,
    raw: str = "0.25",
    unit: str = "normalized",
    method: str = "heuristic-v1",
) -> dict:
    if risk is None:
        return {
            "available": False,
            "riskBasisPoints": None,
            "rawValue": None,
            "unit": None,
            "method": None,
        }
    return {
        "available": True,
        "riskBasisPoints": risk,
        "rawValue": raw,
        "unit": unit,
        "method": method,
    }


def _core(*, risks: dict[str, int | None] | None = None) -> dict:
    supplied = risks or {}
    dimensions = {
        name: _measurement(supplied.get(name)) for name in QUALITY_DIMENSIONS
    }
    return {
        "schemaVersion": SCHEMA_VERSION,
        "profileId": "source_quality_" + "1" * 24,
        "sourcePage": {
            "sourceArtifactId": "artifact_" + "2" * 24,
            "sourceSha256": "3" * 64,
            "pageArtifactRef": "private/source-pages/source-a/page-0.png",
            "pageSha256": "4" * 64,
            "pageIndex": 0,
            "widthPx": 2480,
            "heightPx": 3508,
        },
        "method": {
            "evidenceSource": "DETERMINISTIC_HEURISTIC",
            "methodVersion": "source-quality-heuristics-v1",
            "measurementPolicy": MEASUREMENT_POLICY,
            "calibrated": False,
            "qualityProbability": None,
        },
        "dimensions": dimensions,
        "boundaries": {
            "researchOnly": True,
            "readOnly": True,
            "sourceMutation": False,
            "productionDecisionAuthority": False,
            "engineConfidenceIndependent": True,
            "singleQualityScoreAuthority": False,
            "winnerSelection": False,
            "automaticMerge": False,
            "automaticCorrection": False,
            "teacherAuthorityOverride": False,
            "stage7EvidenceMutation": False,
            "stOmrQuorumChange": False,
        },
    }


class SmPoly06SourceQualityTests(unittest.TestCase):
    def test_schema_covers_exact_required_quality_dimensions_without_engine_identity(self) -> None:
        self.assertEqual(SCHEMA_VERSION, SCHEMA["properties"]["schemaVersion"]["const"])
        schema_dimensions = SCHEMA["properties"]["dimensions"]
        self.assertEqual(set(QUALITY_DIMENSIONS), set(schema_dimensions["properties"]))
        self.assertEqual(set(QUALITY_DIMENSIONS), set(schema_dimensions["required"]))
        self.assertNotIn("engine", SCHEMA["properties"])
        self.assertNotIn("engineConfidence", SCHEMA["properties"])

    def test_profile_is_deterministic_hash_pinned_and_keeps_no_single_score(self) -> None:
        core = _core(risks={"blur": 2100, "contrast": 7200, "compression": 1800})
        first = build_source_quality_profile(core)
        second = build_source_quality_profile(core)
        self.assertEqual(first, second)
        self.assertEqual(first, validate_source_quality_profile(first))
        self.assertEqual("SEVERE", first["derivedState"]["severity"])
        self.assertEqual(7200, first["derivedState"]["maxDegradationRiskBasisPoints"])
        self.assertEqual(["contrast"], first["derivedState"]["dominantDimensions"])
        self.assertIsNone(first["derivedState"]["singleQualityScore"])
        self.assertIsNone(first["derivedState"]["calibratedProbability"])

    def test_zero_coverage_is_explicitly_unavailable_not_assumed_good(self) -> None:
        state = derive_source_quality_state(_core())
        self.assertEqual(0, state["coverageCount"])
        self.assertEqual("UNAVAILABLE", state["severity"])
        self.assertIsNone(state["maxDegradationRiskBasisPoints"])
        self.assertEqual([], state["dominantDimensions"])

    def test_method_evidence_source_rejects_unhashable_values_cleanly(self) -> None:
        for malformed in ([], {}, ["DETERMINISTIC_HEURISTIC"]):
            with self.subTest(malformed=malformed):
                core = _core()
                core["method"]["evidenceSource"] = malformed
                with self.assertRaisesRegex(
                    SourceQualityError, "source_quality_method_invalid"
                ):
                    validate_source_quality_core(core)

    def test_severity_is_worst_observed_not_average_and_ties_are_deterministic(self) -> None:
        state = derive_source_quality_state(
            _core(
                risks={
                    "blur": 4500,
                    "skew": 100,
                    "perspective": 4500,
                    "compression": 200,
                }
            )
        )
        self.assertEqual("HIGH", state["severity"])
        self.assertEqual(4500, state["maxDegradationRiskBasisPoints"])
        self.assertEqual(["blur", "perspective"], state["dominantDimensions"])

        thresholds = ((1999, "LOW"), (2000, "MODERATE"), (4000, "HIGH"), (7000, "SEVERE"))
        for risk, expected in thresholds:
            with self.subTest(risk=risk):
                self.assertEqual(
                    expected,
                    derive_source_quality_state(_core(risks={"blur": risk}))["severity"],
                )

    def test_unavailable_dimension_cannot_smuggle_measurement(self) -> None:
        core = _core()
        core["dimensions"]["blur"]["rawValue"] = "12.0"
        with self.assertRaisesRegex(
            SourceQualityError, "unavailable_quality_contains_measurement"
        ):
            validate_source_quality_core(core)

    def test_risk_basis_points_are_bounded(self) -> None:
        for risk in (-1, 10001, 1.5, True):
            with self.subTest(risk=risk):
                core = _core(risks={"blur": 100})
                core["dimensions"]["blur"]["riskBasisPoints"] = risk
                with self.assertRaisesRegex(
                    SourceQualityError, "quality_measurement_invalid"
                ):
                    validate_source_quality_core(core)

    def test_source_page_ref_and_pixel_area_fail_closed(self) -> None:
        core = _core()
        core["sourcePage"]["pageArtifactRef"] = "../secret.png"
        with self.assertRaisesRegex(SourceQualityError, "source_page_invalid"):
            validate_source_quality_core(core)

        core = _core()
        core["sourcePage"]["widthPx"] = 50_000
        core["sourcePage"]["heightPx"] = 50_000
        with self.assertRaisesRegex(SourceQualityError, "source_page_invalid"):
            validate_source_quality_core(core)

    def test_profile_hash_and_derived_state_tampering_fail_closed(self) -> None:
        profile = build_source_quality_profile(_core(risks={"rotation": 3200}))
        profile["derivedState"]["severity"] = "LOW"
        with self.assertRaisesRegex(
            SourceQualityError, "source_quality_derived_state_invalid"
        ):
            validate_source_quality_profile(profile)

        profile = build_source_quality_profile(_core(risks={"rotation": 3200}))
        profile["dimensions"]["rotation"]["rawValue"] = "tampered"
        with self.assertRaisesRegex(SourceQualityError, "source_quality_hash_invalid"):
            validate_source_quality_profile(profile)

    def test_sm_poly_05_accepts_sha_pinned_source_quality_reference(self) -> None:
        profile = build_source_quality_profile(_core(risks={"blur": 2200}))
        _validate_source_quality(
            {
                "available": True,
                "profileRef": "research/source-quality/source-a-page-0.json",
                "profileSha256": profile["profileSha256"],
                "authoritative": False,
            }
        )

    def test_authority_boundaries_and_stage7_remain_unchanged(self) -> None:
        core = _core(risks={"illumination": 8000})
        core["boundaries"]["researchOnly"] = 1
        with self.assertRaisesRegex(SourceQualityError, "authority_boundary_invalid"):
            validate_source_quality_core(core)

        current = ARCHITECTURE["currentOmr"]
        self.assertEqual(
            ["audiveris", "homr", "clarity"], current["productionCandidateEngines"]
        )
        self.assertEqual(2, current["stage7MinimumCanonicalCandidates"])
        self.assertIs(current["stOmrIntegratedIntoGateway"], False)
        self.assertIs(current["automaticWinnerAuthority"], False)
        self.assertIs(ARCHITECTURE["teacherReview"]["productionWriteActivated"], False)
        self.assertIs(ARCHITECTURE["production"]["productionReady"], False)

        convergence_source = (
            SERVICE_ROOT / "src" / "scoremosaic_ensemble" / "convergence.py"
        ).read_text(encoding="utf-8")
        self.assertIn('"sourceQuality": {', convergence_source)
        self.assertIn('"available": False', convergence_source)
        self.assertIn('"reason": "not_in_stage6_candidate_contract"', convergence_source)
        self.assertNotIn("source_quality", convergence_source)


if __name__ == "__main__":
    unittest.main()
