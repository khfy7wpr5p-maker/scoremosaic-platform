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
    REAL_SCORE_INTAKE_BINDING_TYPE,
    REAL_SCORE_INTAKE_VERSION,
    RealScoreIntakeError,
    validate_real_score_intake,
)


SCHEMA_PATH = ROOT / "contracts" / "real-score-intake-v1.schema.json"
MUSICXML = b'<?xml version="1.0" encoding="UTF-8"?><score-partwise version="4.0"></score-partwise>'
MUSICXML_SHA = sha256(MUSICXML).hexdigest()


def valid_payload() -> dict:
    return {
        "schemaVersion": REAL_SCORE_INTAKE_VERSION,
        "bindingType": REAL_SCORE_INTAKE_BINDING_TYPE,
        "document": {
            "documentId": "score.review.001",
            "revision": "rev_0123456789abcdef0123456789abcdef",
        },
        "source": {
            "sourceArtifactId": "artifact_111111111111111111111111",
            "sourceSha256": "1" * 64,
        },
        "candidate": {
            "engine": "audiveris",
            "candidateId": "candidate_222222222222222222222222",
            "candidateNamespace": "candidate/audiveris/v1",
            "candidateSha256": "2" * 64,
            "sourceArtifactId": "artifact_111111111111111111111111",
            "sourceSha256": "1" * 64,
            "musicxmlArtifactId": "artifact_333333333333333333333333",
            "musicxmlSha256": MUSICXML_SHA,
            "engineVersion": "5.8.1",
            "modelVersion": None,
        },
        "canonical": {
            "canonicalSha256": "4" * 64,
            "sourceEngine": "audiveris",
            "sourceArtifactRef": "artifact_333333333333333333333333",
            "sourceArtifactSha256": MUSICXML_SHA,
        },
        "mappingPolicy": {
            "scoreSource": "canonical",
            "eventIdentity": "preserve-canonical-event-id",
            "musicXmlRole": "immutable-candidate-evidence",
            "syntheticScoreAllowed": False,
            "rendererAuthority": False,
        },
        "reviewBindings": [
            {
                "issueId": "issue-duration-001",
                "sourceRegion": "page-1/measure-3",
                "candidateId": "candidate_222222222222222222222222",
                "candidateSha256": "2" * 64,
                "canonicalSha256": "4" * 64,
                "canonicalEventId": "event-003-04",
                "coreEventId": "event-003-04",
                "provenance": {
                    "xmlPath": "/score-partwise/part[1]/measure[3]/note[4]",
                    "sourceEventIndex": 11,
                },
            }
        ],
        "authority": {
            "bindingOnly": True,
            "networkCapable": False,
            "persistent": False,
            "finalTruthAuthority": False,
            "writeAuthority": False,
            "approvalAuthority": False,
            "publicationAuthority": False,
            "automaticCorrectionAuthority": False,
        },
    }


class RealScoreIntakeContractV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    def assert_error(self, payload: dict, code: str, *, musicxml: bytes = MUSICXML) -> None:
        with self.assertRaises(RealScoreIntakeError) as caught:
            validate_real_score_intake(payload, musicxml=musicxml)
        self.assertEqual(caught.exception.code, code)

    def test_schema_is_closed_versioned_and_non_authoritative(self) -> None:
        self.assertTrue(SCHEMA_PATH.is_file())
        self.assertFalse(SCHEMA_PATH.is_symlink())
        self.assertEqual(
            self.schema["$schema"],
            "https://json-schema.org/draft/2020-12/schema",
        )
        self.assertIs(self.schema["additionalProperties"], False)
        self.assertEqual(
            self.schema["properties"]["schemaVersion"]["const"],
            REAL_SCORE_INTAKE_VERSION,
        )
        self.assertEqual(
            self.schema["properties"]["bindingType"]["const"],
            REAL_SCORE_INTAKE_BINDING_TYPE,
        )
        authority = self.schema["$defs"]["authority"]["properties"]
        self.assertIs(authority["bindingOnly"]["const"], True)
        for key in (
            "networkCapable",
            "persistent",
            "finalTruthAuthority",
            "writeAuthority",
            "approvalAuthority",
            "publicationAuthority",
            "automaticCorrectionAuthority",
        ):
            self.assertIs(authority[key]["const"], False, key)

    def test_mapping_policy_forbids_synthetic_score_and_renderer_authority(self) -> None:
        policy = self.schema["$defs"]["mappingPolicy"]["properties"]
        self.assertEqual(policy["scoreSource"]["const"], "canonical")
        self.assertEqual(
            policy["eventIdentity"]["const"],
            "preserve-canonical-event-id",
        )
        self.assertEqual(
            policy["musicXmlRole"]["const"],
            "immutable-candidate-evidence",
        )
        self.assertIs(policy["syntheticScoreAllowed"]["const"], False)
        self.assertIs(policy["rendererAuthority"]["const"], False)

    def test_valid_binding_is_deterministic_and_does_not_return_musicxml(self) -> None:
        first = validate_real_score_intake(valid_payload(), musicxml=MUSICXML)
        second = validate_real_score_intake(valid_payload(), musicxml=MUSICXML)
        self.assertEqual(first.binding_sha256, second.binding_sha256)
        self.assertEqual(first.review_binding_count, 1)
        self.assertEqual(first.musicxml_sha256, MUSICXML_SHA)
        safe = first.as_safe_dict()
        self.assertNotIn("musicxml", safe)
        self.assertIs(safe["authoritative"], False)
        self.assertIs(safe["persistent"], False)
        self.assertIs(safe["networkCapable"], False)

    def test_clean_score_may_bind_without_review_issues(self) -> None:
        payload = valid_payload()
        payload["reviewBindings"] = []
        result = validate_real_score_intake(payload, musicxml=MUSICXML)
        self.assertEqual(result.review_binding_count, 0)

    def test_exact_musicxml_bytes_are_hash_bound(self) -> None:
        self.assert_error(
            valid_payload(),
            "INTAKE_MUSICXML_HASH_MISMATCH",
            musicxml=MUSICXML + b" ",
        )

    def test_candidate_must_bind_to_same_immutable_source(self) -> None:
        payload = valid_payload()
        payload["candidate"]["sourceSha256"] = "9" * 64
        self.assert_error(payload, "INTAKE_SOURCE_BINDING_MISMATCH")

    def test_canonical_must_bind_to_exact_candidate_musicxml(self) -> None:
        payload = valid_payload()
        payload["canonical"]["sourceEngine"] = "homr"
        self.assert_error(payload, "INTAKE_CANONICAL_BINDING_MISMATCH")

        payload = valid_payload()
        payload["canonical"]["sourceArtifactRef"] = "artifact_aaaaaaaaaaaaaaaaaaaaaaaa"
        self.assert_error(payload, "INTAKE_CANONICAL_BINDING_MISMATCH")

        payload = valid_payload()
        payload["canonical"]["sourceArtifactSha256"] = "a" * 64
        self.assert_error(payload, "INTAKE_CANONICAL_BINDING_MISMATCH")

    def test_review_issue_must_bind_to_candidate_canonical_and_same_event_id(self) -> None:
        payload = valid_payload()
        payload["reviewBindings"][0]["candidateSha256"] = "8" * 64
        self.assert_error(payload, "INTAKE_ISSUE_BINDING_MISMATCH")

        payload = valid_payload()
        payload["reviewBindings"][0]["canonicalSha256"] = "8" * 64
        self.assert_error(payload, "INTAKE_ISSUE_BINDING_MISMATCH")

        payload = valid_payload()
        payload["reviewBindings"][0]["coreEventId"] = "different-event"
        self.assert_error(payload, "INTAKE_EVENT_BINDING_MISMATCH")

    def test_duplicate_issue_binding_fails_closed(self) -> None:
        payload = valid_payload()
        payload["reviewBindings"].append(deepcopy(payload["reviewBindings"][0]))
        self.assert_error(payload, "INTAKE_DUPLICATE_ISSUE_BINDING")

    def test_unknown_fields_and_authority_escalation_fail_closed(self) -> None:
        payload = valid_payload()
        payload["unexpected"] = True
        self.assert_error(payload, "INTAKE_SCHEMA_CLOSED")

        payload = valid_payload()
        payload["authority"]["writeAuthority"] = True
        self.assert_error(payload, "INTAKE_AUTHORITY_INVALID")

        payload = valid_payload()
        payload["mappingPolicy"]["syntheticScoreAllowed"] = True
        self.assert_error(payload, "INTAKE_MAPPING_POLICY_INVALID")


if __name__ == "__main__":
    unittest.main()
