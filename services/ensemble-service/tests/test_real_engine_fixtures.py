from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import sys
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_ROOT = SERVICE_ROOT / "tests" / "fixtures" / "real-engines"
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_ensemble import compare_candidates, normalize_musicxml


class RealEngineCanonicalFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(
            (FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8")
        )

    def _normalized_candidates(self):
        candidates = []
        for expected in self.manifest["candidates"]:
            engine = expected["engine"]
            musicxml_path = REPOSITORY_ROOT / expected["musicXmlPath"]
            capture_path = REPOSITORY_ROOT / expected["captureMetadataPath"]
            document = musicxml_path.read_bytes()
            capture = json.loads(capture_path.read_text(encoding="utf-8"))

            self.assertFalse(musicxml_path.is_symlink())
            self.assertFalse(capture_path.is_symlink())
            self.assertEqual(
                sha256(document).hexdigest(), expected["capturedMusicXmlSha256"]
            )
            self.assertNotIn(b"<!DOCTYPE", document.upper())
            self.assertNotIn(b"<!ENTITY", document.upper())
            self.assertEqual(capture["engine"], engine)
            self.assertEqual(capture["engineVersion"], expected["engineVersion"])
            self.assertEqual(capture["modelVersion"], expected["modelVersion"])
            self.assertEqual(
                capture["sourceFixtureSha256"], self.manifest["source"]["sha256"]
            )
            for field in (
                "inputArtifactSha256",
                "extractedMusicXmlSha256",
                "capturedMusicXmlSha256",
                "canonicalDoctypeRemoved",
                "containerFormat",
            ):
                self.assertEqual(capture[field], expected[field])

            score = normalize_musicxml(
                document,
                engine=engine,
                engine_version=expected["engineVersion"],
                model_version=expected["modelVersion"],
                artifact_ref=f"fixtures/real-engines/{engine}.musicxml",
            )
            self.assertEqual(score.source.engine, engine)
            self.assertEqual(
                score.source.artifact_sha256, expected["capturedMusicXmlSha256"]
            )
            self.assertEqual(score.canonical_sha256, expected["canonicalSha256"])
            self.assertEqual(len(score.parts), expected["partCount"])
            self.assertEqual(score.measure_count, expected["measureCount"])
            self.assertEqual(score.event_count, expected["eventCount"])
            self.assertEqual(len(score.diagnostics), expected["diagnosticCount"])
            for part in score.parts:
                for measure in part.measures:
                    for event in measure.events:
                        self.assertTrue(event.provenance.xml_path)
                        self.assertGreaterEqual(
                            event.provenance.source_event_index,
                            0,
                        )
            candidates.append(score)
        return tuple(candidates)

    def test_manifest_pins_one_shared_source_and_three_engines(self) -> None:
        source_path = REPOSITORY_ROOT / self.manifest["source"]["path"]

        self.assertEqual(self.manifest["fixtureSetVersion"], "0.1-foundation")
        self.assertFalse(self.manifest["accuracyClaim"])
        self.assertEqual(self.manifest["candidateCount"], 3)
        self.assertEqual(
            {candidate["engine"] for candidate in self.manifest["candidates"]},
            {"audiveris", "homr", "clarity"},
        )
        self.assertEqual(
            sha256(source_path.read_bytes()).hexdigest(),
            self.manifest["source"]["sha256"],
        )

    def test_real_musicxml_fixtures_normalize_to_pinned_canonical_scores(self) -> None:
        candidates = self._normalized_candidates()

        self.assertEqual(len(candidates), 3)
        self.assertEqual({score.measure_count for score in candidates}, {4})
        self.assertEqual({score.event_count for score in candidates}, {16})

    def test_real_candidates_produce_pinned_neutral_comparison(self) -> None:
        candidates = self._normalized_candidates()
        before = tuple(score.canonical_sha256 for score in candidates)

        result = compare_candidates(candidates)
        reversed_result = compare_candidates(tuple(reversed(candidates)))
        payload = result.as_dict()
        expected = self.manifest["comparison"]

        self.assertEqual(result.to_json(indent=None), reversed_result.to_json(indent=None))
        self.assertEqual(before, tuple(score.canonical_sha256 for score in candidates))
        self.assertEqual(payload["candidateCount"], 3)
        self.assertEqual(payload["comparisonMode"], "neutral-all-candidates")
        self.assertFalse(payload["alignment"]["fuzzyAlignment"])
        self.assertEqual(result.result_sha256, expected["resultSha256"])
        self.assertEqual(result.identical, expected["identical"])
        self.assertEqual(len(result.differences), expected["differenceCount"])
        self.assertEqual(
            dict(sorted(Counter(item.category for item in result.differences).items())),
            expected["differenceCategories"],
        )
        for difference in result.differences:
            self.assertEqual(len(difference.observations), 3)
            for observation in difference.observations:
                self.assertIn(
                    observation.source.engine,
                    {"audiveris", "homr", "clarity"},
                )
                self.assertEqual(len(observation.canonical_sha256), 64)
                if observation.event_id is not None:
                    self.assertTrue(observation.xml_path)
                    self.assertIsNotNone(observation.source_event_index)

    def test_real_fixture_comparison_keeps_all_decision_boundaries_disabled(self) -> None:
        result = compare_candidates(self._normalized_candidates())

        self.assertEqual(result.as_dict()["boundaries"], self.manifest["boundaries"])
        self.assertEqual(
            self.manifest["boundaries"],
            {
                "readOnly": True,
                "engineRanking": False,
                "winnerSelection": False,
                "automaticMerge": False,
                "automaticCorrection": False,
                "teacherApproval": False,
                "publication": False,
            },
        )


if __name__ == "__main__":
    unittest.main()
