from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "services" / "teacher-review-service" / "src"
ENSEMBLE_SRC = ROOT / "services" / "ensemble-service" / "src"
TESTS = ROOT / "services" / "teacher-review-service" / "tests"
sys.path.insert(0, str(ENSEMBLE_SRC))
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(TESTS))

from scoremosaic_teacher_review.corrected_musicxml import CorrectedMusicXmlArtifact  # noqa: E402
from scoremosaic_teacher_review.publication_handoff import (  # noqa: E402
    PUBLICATION_HANDOFF_AUTHZ_VERSION,
    PUBLICATION_HANDOFF_VERSION,
    Stage8PublicationHandoffError,
    build_publication_handoff_request,
    issue_publication_handoff_grant,
)
from test_stage8n_publication_eligibility import (  # noqa: E402
    DECISION_KEY,
    HANDOFF_KEY,
    Stage8NPublicationEligibilityTests,
)

PUBLISH_HANDOFF_KEY = b"stage8o-publication-handoff-purpose-key-32bytes!!"
WRONG_PUBLISH_HANDOFF_KEY = b"stage8o-wrong-publication-handoff-key-32bytes!!"


class Stage8OPublicationHandoffTests(unittest.TestCase):
    def _fixture(self):
        helper = Stage8NPublicationEligibilityTests(
            methodName="test_exact_approval_record_is_deterministic_publication_handoff_candidate_only"
        )
        values = helper._approved_fixture()
        self.addCleanup(helper.doCleanups)
        eligibility = helper._build(values)
        grant = issue_publication_handoff_grant(
            request_id="publication_handoff_stage8o_0001",
            publisher_id="publisher_stage8o",
            eligibility=eligibility,
            signing_key=PUBLISH_HANDOFF_KEY,
        )
        return values, eligibility, grant

    def _build(self, fixture, *, artifact=None, grant=None, publisher="publisher_stage8o", signing_key=PUBLISH_HANDOFF_KEY):
        values, _, original_grant = fixture
        helper, state, revision, original_artifact, approval_handoff_grant, approval_handoff, decision_grant, approval_record = values
        return build_publication_handoff_request(
            scope=helper.scope,
            store=helper.store,
            revision=revision,
            state=state,
            artifact=original_artifact if artifact is None else artifact,
            approval_handoff_grant=approval_handoff_grant,
            approval_handoff_signing_key=HANDOFF_KEY,
            approval_handoff=approval_handoff,
            decision_grant=decision_grant,
            decision_signing_key=DECISION_KEY,
            expected_approver_id="teacher_stage8f",
            approval_record=approval_record,
            grant=original_grant if grant is None else grant,
            expected_publisher_id=publisher,
            signing_key=signing_key,
        )

    def test_exact_handoff_is_deterministic_and_non_executing(self):
        fixture = self._fixture()
        requests = [self._build(fixture) for _ in range(10)]
        self.assertEqual(1, len({item.request_sha256 for item in requests}))
        data = requests[0].to_dict()
        self.assertEqual(PUBLICATION_HANDOFF_VERSION, data["schemaVersion"])
        self.assertEqual("awaiting_external_publication_execution", data["state"]["status"])
        self.assertTrue(data["capabilities"]["canPresentForPublicationExecution"])
        self.assertFalse(data["authorization"]["productionPublicationAuthority"])
        for key in ("canExecutePublication", "canWriteExternal", "canPersistProduction", "canMutate", "publicationGranted", "authoritativeMusicalTruth"):
            self.assertFalse(data["capabilities"][key])

    def test_grant_is_bound_to_exact_publisher_and_signature(self):
        fixture = self._fixture()
        _, eligibility, grant = fixture
        safe = grant.safe_dict()
        self.assertEqual(PUBLICATION_HANDOFF_AUTHZ_VERSION, safe["schemaVersion"])
        self.assertEqual("<redacted>", safe["signature"])
        duplicate = issue_publication_handoff_grant(
            request_id="publication_handoff_stage8o_0001",
            publisher_id="publisher_stage8o",
            eligibility=eligibility,
            signing_key=PUBLISH_HANDOFF_KEY,
        )
        self.assertEqual(grant.grant_sha256, duplicate.grant_sha256)
        with self.assertRaisesRegex(Stage8PublicationHandoffError, "PUBLICATION_HANDOFF_GRANT_SCOPE_MISMATCH"):
            self._build(fixture, publisher="other_publisher")
        with self.assertRaisesRegex(Stage8PublicationHandoffError, "PUBLICATION_HANDOFF_SIGNATURE_INVALID"):
            self._build(fixture, signing_key=WRONG_PUBLISH_HANDOFF_KEY)
        tampered = replace(grant, music_xml_sha256="0" * 64)
        with self.assertRaisesRegex(Stage8PublicationHandoffError, "PUBLICATION_HANDOFF_GRANT_SCOPE_MISMATCH"):
            self._build(fixture, grant=tampered)

    def test_artifact_substitution_fails_during_fresh_eligibility_revalidation(self):
        fixture = self._fixture()
        artifact = fixture[0][3]
        forged = CorrectedMusicXmlArtifact(document=artifact.document + b"\n", _record=artifact._record)
        with self.assertRaisesRegex(Stage8PublicationHandoffError, "PUBLICATION_HANDOFF_ELIGIBILITY_REVALIDATION_REJECTED"):
            self._build(fixture, artifact=forged)


if __name__ == "__main__":
    unittest.main()
