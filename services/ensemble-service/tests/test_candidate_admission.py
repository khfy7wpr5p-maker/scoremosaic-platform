from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sys
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_ensemble import (
    CanonicalCandidateInput,
    admit_and_compare_candidates,
)


VALID_DOCUMENT = (SERVICE_ROOT / "tests" / "fixtures" / "canonical-smoke.musicxml").read_bytes()
INVALID_DOCUMENT = b"""<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<score-partwise version=\"4.0\">
  <part-list>
    <score-part id=\"P1\"><part-name>Rejected candidate</part-name></score-part>
  </part-list>
  <part id=\"P1\">
    <measure number=\"1\">
      <attributes><divisions>1</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
      <note><rest/><duration>1</duration><voice>1</voice><type>quarter</type></note>
      <note><chord/><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration><voice>1</voice><type>quarter</type></note>
    </measure>
  </part>
</score-partwise>
"""


def _candidate(engine: str, document: bytes) -> CanonicalCandidateInput:
    return CanonicalCandidateInput(
        document=document,
        engine=engine,
        engine_version=f"{engine}-test-v1",
        model_version=None,
        artifact_ref=f"tests/ensemble-r1/{engine}.musicxml",
    )


class CandidateAdmissionIsolationTests(unittest.TestCase):
    def test_one_rejected_candidate_does_not_abort_two_valid_candidates(self) -> None:
        result = admit_and_compare_candidates(
            (
                _candidate("audiveris", VALID_DOCUMENT),
                _candidate("homr", INVALID_DOCUMENT),
                _candidate("clarity", VALID_DOCUMENT),
            )
        )
        payload = result.as_dict()

        self.assertEqual(payload["totalCandidateCount"], 3)
        self.assertEqual(payload["acceptedCandidateCount"], 2)
        self.assertEqual(payload["rejectedCandidateCount"], 1)
        self.assertTrue(payload["comparisonEligible"])
        self.assertFalse(payload["failClosed"])
        self.assertIsNone(payload["failClosedReason"])
        self.assertIsNotNone(payload["comparison"])
        self.assertEqual(payload["comparison"]["candidateCount"], 2)
        self.assertEqual(payload["comparison"]["comparisonMode"], "neutral-all-candidates")

        rejected = [item for item in payload["admissions"] if item["status"] == "rejected"]
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0]["source"]["engine"], "homr")
        self.assertEqual(
            rejected[0]["source"]["artifactSha256"],
            sha256(INVALID_DOCUMENT).hexdigest(),
        )
        self.assertEqual(rejected[0]["reason"], "canonical_normalization_rejected")
        self.assertIsNone(rejected[0]["canonicalSha256"])

    def test_rejected_candidate_evidence_does_not_expose_normalizer_text(self) -> None:
        result = admit_and_compare_candidates(
            (
                _candidate("audiveris", VALID_DOCUMENT),
                _candidate("homr", INVALID_DOCUMENT),
                _candidate("clarity", VALID_DOCUMENT),
            )
        )
        serialized = json.dumps(result.as_dict(), sort_keys=True)

        self.assertNotIn("chord note follows a rest", serialized)
        self.assertNotIn("/score-partwise/part[", serialized)
        self.assertNotIn("Rejected candidate", serialized)

    def test_fewer_than_two_valid_candidates_fails_closed_without_comparison(self) -> None:
        result = admit_and_compare_candidates(
            (
                _candidate("audiveris", VALID_DOCUMENT),
                _candidate("homr", INVALID_DOCUMENT),
                _candidate("clarity", INVALID_DOCUMENT),
            )
        )
        payload = result.as_dict()

        self.assertEqual(payload["acceptedCandidateCount"], 1)
        self.assertEqual(payload["rejectedCandidateCount"], 2)
        self.assertFalse(payload["comparisonEligible"])
        self.assertTrue(payload["failClosed"])
        self.assertEqual(payload["failClosedReason"], "insufficient_canonical_candidates")
        self.assertIsNone(payload["comparison"])

    def test_admission_result_is_deterministic_independent_of_input_order(self) -> None:
        candidates = (
            _candidate("audiveris", VALID_DOCUMENT),
            _candidate("homr", INVALID_DOCUMENT),
            _candidate("clarity", VALID_DOCUMENT),
        )

        forward = admit_and_compare_candidates(candidates)
        reverse = admit_and_compare_candidates(tuple(reversed(candidates)))

        self.assertEqual(forward.as_dict(), reverse.as_dict())
        self.assertEqual(
            forward.as_dict()["boundaries"],
            {
                "readOnly": True,
                "canonicalRulesRelaxed": False,
                "rejectedCandidateRepair": False,
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
