from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_ensemble.visual_evidence import (
    CURRENT_ENGINES,
    SCHEMA_VERSION,
    VisualEvidenceError,
    build_visual_evidence_sidecar,
    validate_visual_evidence_core,
    validate_visual_evidence_sidecar,
)

SCHEMA = json.loads(
    (REPOSITORY_ROOT / "contracts" / "polyphonic-visual-evidence-sidecar-v1.schema.json").read_text(
        encoding="utf-8"
    )
)
ARCHITECTURE = json.loads(
    (REPOSITORY_ROOT / "contracts" / "architecture-current-state-v1.json").read_text(
        encoding="utf-8"
    )
)


def _core(*, localized: bool = True) -> dict:
    localization = {
        "available": localized,
        "evidenceSource": "ENGINE_NATIVE_BBOX" if localized else "UNAVAILABLE",
        "methodVersion": "audiveris-page-geometry-v1" if localized else None,
        "systemId": "system_1" if localized else None,
        "measureRegionId": "measure_region_4" if localized else None,
        "staffId": 1 if localized else None,
        "bbox": {"x": 100, "y": 200, "width": 120, "height": 80} if localized else None,
        "symbolRegions": (
            [
                {
                    "regionId": "notehead_1",
                    "kind": "NOTEHEAD",
                    "bbox": {"x": 120, "y": 225, "width": 24, "height": 18},
                },
                {
                    "regionId": "stem_1",
                    "kind": "STEM",
                    "bbox": {"x": 143, "y": 205, "width": 4, "height": 55},
                },
            ]
            if localized
            else []
        ),
        "crop": {
            "available": localized,
            "artifactRef": "private/visual-crops/page-0/event-7.png" if localized else None,
            "sha256": "9" * 64 if localized else None,
        },
    }
    return {
        "schemaVersion": SCHEMA_VERSION,
        "evidenceId": "visual_evidence_" + "1" * 24,
        "candidate": {
            "engine": "audiveris",
            "runId": "run_" + "2" * 24,
            "candidateId": "candidate_" + "3" * 24,
            "candidateSha256": "4" * 64,
            "musicxmlSha256": "5" * 64,
            "canonicalScoreSha256": "6" * 64,
        },
        "sourcePage": {
            "sourceArtifactId": "artifact_" + "7" * 24,
            "sourceSha256": "8" * 64,
            "pageArtifactRef": "private/source-pages/source-a/page-0.png",
            "pageSha256": "a" * 64,
            "pageIndex": 0,
            "widthPx": 2480,
            "heightPx": 3508,
        },
        "canonicalIdentity": {
            "partId": "part_P1",
            "measureId": "measure_P1_4",
            "eventId": "event_P1_4_7",
            "sourceEventIndex": 7,
            "xmlPath": "/score-partwise/part[1]/measure[4]/note[8]",
        },
        "localization": localization,
        "engineConfidence": {
            "available": True,
            "rawValue": "0.91",
            "scale": "engine-native",
            "calibratedProbability": None,
        },
        "visualConfidence": {
            "available": False,
            "rawValue": None,
            "scale": None,
            "calibratedProbability": None,
        },
        "sourceQuality": {
            "available": False,
            "profileRef": None,
            "profileSha256": None,
            "authoritative": False,
        },
        "boundaries": {
            "researchOnly": True,
            "readOnly": True,
            "sourceMutation": False,
            "productionDecisionAuthority": False,
            "engineRanking": False,
            "winnerSelection": False,
            "automaticMerge": False,
            "automaticCorrection": False,
            "teacherAuthorityOverride": False,
            "stage7EvidenceMutation": False,
            "stOmrQuorumChange": False,
        },
    }


class SmPoly05VisualEvidenceTests(unittest.TestCase):
    def test_schema_version_and_engine_scope_are_closed(self) -> None:
        self.assertEqual(SCHEMA_VERSION, SCHEMA["properties"]["schemaVersion"]["const"])
        self.assertEqual(
            list(CURRENT_ENGINES),
            SCHEMA["properties"]["candidate"]["properties"]["engine"]["enum"],
        )
        self.assertNotIn("st-omr", CURRENT_ENGINES)
        self.assertNotIn("st_omr", CURRENT_ENGINES)

    def test_localized_sidecar_is_deterministic_and_hash_pinned(self) -> None:
        first = build_visual_evidence_sidecar(_core())
        second = build_visual_evidence_sidecar(_core())
        self.assertEqual(first, second)
        self.assertEqual(first, validate_visual_evidence_sidecar(first))
        core = dict(first)
        actual = core.pop("sidecarSha256")
        expected = sha256(
            json.dumps(
                core,
                ensure_ascii=True,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("ascii")
        ).hexdigest()
        self.assertEqual(expected, actual)

    def test_unavailable_localization_is_explicit_and_contains_no_geometry(self) -> None:
        sidecar = build_visual_evidence_sidecar(_core(localized=False))
        localization = sidecar["localization"]
        self.assertIs(localization["available"], False)
        self.assertEqual("UNAVAILABLE", localization["evidenceSource"])
        self.assertIsNone(localization["bbox"])
        self.assertEqual([], localization["symbolRegions"])
        self.assertIs(localization["crop"]["available"], False)

    def test_unavailable_localization_cannot_smuggle_bbox(self) -> None:
        core = _core(localized=False)
        core["localization"]["bbox"] = {"x": 0, "y": 0, "width": 1, "height": 1}
        with self.assertRaisesRegex(
            VisualEvidenceError, "unavailable_localization_contains_evidence"
        ):
            validate_visual_evidence_core(core)

    def test_bbox_must_be_inside_bound_page(self) -> None:
        core = _core()
        core["localization"]["bbox"] = {
            "x": 2470,
            "y": 3500,
            "width": 20,
            "height": 20,
        }
        with self.assertRaisesRegex(VisualEvidenceError, "bbox_invalid"):
            validate_visual_evidence_core(core)

    def test_symbol_region_must_be_inside_primary_event_bbox(self) -> None:
        core = _core()
        core["localization"]["symbolRegions"][0]["bbox"] = {
            "x": 10,
            "y": 10,
            "width": 10,
            "height": 10,
        }
        with self.assertRaisesRegex(
            VisualEvidenceError, "symbol_region_outside_event_bbox"
        ):
            validate_visual_evidence_core(core)

    def test_page_dimensions_are_bounded_by_total_pixel_area(self) -> None:
        core = _core()
        core["sourcePage"]["widthPx"] = 50_000
        core["sourcePage"]["heightPx"] = 50_000
        with self.assertRaisesRegex(VisualEvidenceError, "source_page_invalid"):
            validate_visual_evidence_core(core)

    def test_crop_ref_and_hash_are_paired_and_path_traversal_fails_closed(self) -> None:
        core = _core()
        core["localization"]["crop"]["artifactRef"] = "../secret.png"
        with self.assertRaisesRegex(VisualEvidenceError, "crop_evidence_invalid"):
            validate_visual_evidence_core(core)

        core = _core()
        core["localization"]["crop"]["sha256"] = None
        with self.assertRaisesRegex(VisualEvidenceError, "crop_evidence_invalid"):
            validate_visual_evidence_core(core)

    def test_confidence_is_raw_evidence_not_calibrated_probability(self) -> None:
        core = _core()
        core["engineConfidence"]["calibratedProbability"] = 0.91
        with self.assertRaisesRegex(VisualEvidenceError, "engine_confidence_invalid"):
            validate_visual_evidence_core(core)

        core = _core()
        core["visualConfidence"]["available"] = False
        core["visualConfidence"]["rawValue"] = "0.5"
        with self.assertRaisesRegex(VisualEvidenceError, "visual_confidence_invalid"):
            validate_visual_evidence_core(core)

    def test_source_quality_is_only_a_versioned_reference_for_sm_poly_06(self) -> None:
        core = _core()
        core["sourceQuality"] = {
            "available": True,
            "profileRef": "research/source-quality/profile-001.json",
            "profileSha256": "b" * 64,
            "authoritative": False,
        }
        validate_visual_evidence_core(core)

        core["sourceQuality"]["authoritative"] = True
        with self.assertRaisesRegex(VisualEvidenceError, "source_quality_link_invalid"):
            validate_visual_evidence_core(core)

    def test_hash_tampering_fails_closed(self) -> None:
        sidecar = build_visual_evidence_sidecar(_core())
        sidecar["canonicalIdentity"]["eventId"] = "event_P1_4_8"
        with self.assertRaisesRegex(VisualEvidenceError, "visual_evidence_hash_invalid"):
            validate_visual_evidence_sidecar(sidecar)

    def test_authority_boundaries_cannot_use_numeric_boolean_lookalikes(self) -> None:
        core = _core()
        core["boundaries"]["researchOnly"] = 1
        with self.assertRaisesRegex(VisualEvidenceError, "authority_boundary_invalid"):
            validate_visual_evidence_core(core)

    def test_existing_stage7_and_teacher_authority_remain_unchanged(self) -> None:
        current = ARCHITECTURE["currentOmr"]
        self.assertEqual(["audiveris", "homr", "clarity"], current["productionCandidateEngines"])
        self.assertEqual(2, current["stage7MinimumCanonicalCandidates"])
        self.assertIs(current["stOmrIntegratedIntoGateway"], False)
        self.assertIs(current["automaticWinnerAuthority"], False)
        self.assertIs(ARCHITECTURE["teacherReview"]["productionWriteActivated"], False)
        self.assertIs(ARCHITECTURE["production"]["productionReady"], False)

        convergence_source = (
            SERVICE_ROOT / "src" / "scoremosaic_ensemble" / "convergence.py"
        ).read_text(encoding="utf-8")
        self.assertIn('"bboxEvidenceAvailable": False', convergence_source)
        self.assertIn('"reason": "not_in_stage6_candidate_contract"', convergence_source)
        self.assertNotIn("visual_evidence", convergence_source)


if __name__ == "__main__":
    unittest.main()
