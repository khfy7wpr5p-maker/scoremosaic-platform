from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ENSEMBLE_ROOT = REPOSITORY_ROOT / "services" / "ensemble-service"
sys.path.insert(0, str(SERVICE_ROOT / "src"))
sys.path.insert(0, str(ENSEMBLE_ROOT / "src"))

from scoremosaic_ensemble.polyphonic_metrics import validate_semantic_observation
from scoremosaic_teacher_review.contracts import (
    build_score_edit_command,
    build_teacher_score_revision,
    issue_authorization_grant,
)
from scoremosaic_teacher_review.teacher_workload import (
    EVIDENCE_SCHEMA_VERSION,
    TEACHER_EDIT_METHOD,
    TeacherWorkloadEvidenceError,
    build_teacher_workload_evidence,
    project_teacher_workload_to_sm_poly_04,
    validate_teacher_workload_evidence,
)


SCHEMA = json.loads(
    (REPOSITORY_ROOT / "contracts" / "polyphonic-teacher-workload-evidence-v1.schema.json").read_text(
        encoding="utf-8"
    )
)
ARCHITECTURE = json.loads(
    (REPOSITORY_ROOT / "contracts" / "architecture-current-state-v1.json").read_text(
        encoding="utf-8"
    )
)


def _hash(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _reseal_revision(record: dict) -> dict:
    body = {key: value for key, value in record.items() if key not in {"revisionId", "revisionSha256"}}
    encoded = json.dumps(
        body,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    revision_sha = sha256(encoded).hexdigest()
    record["revisionSha256"] = revision_sha
    record["revisionId"] = f"rev_{revision_sha[:32]}"
    return record


class SmPoly13TeacherWorkloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.signing_key = b"scoremosaic-sm-poly-13-test-key!!"
        cls.job_id = "job_poly13case01"
        cls.reviewer_id = "teacher.poly13"
        cls.tenant_id = "tenant.poly13"
        cls.review_report_id = "review.poly13"
        cls.review_report_sha = _hash("review-report")
        cls.canonical_sha = _hash("canonical-score")
        cls.fixture_id = "poly_fixture_teacherworkload01"
        cls.revisions, cls.commands = cls._build_chain()

    @classmethod
    def _build_chain(cls) -> tuple[list[dict], list[dict]]:
        revisions: list[dict] = []
        commands: list[dict] = []
        parent_id = None
        parent_sha = None
        previous_audit = None
        for index, measure_id in enumerate(("measure_1", "measure_1", "measure_2"), start=1):
            decision_id = f"decision.poly13.{index}"
            grant = issue_authorization_grant(
                decision_id=decision_id,
                reviewer_id=cls.reviewer_id,
                tenant_id=cls.tenant_id,
                job_id=cls.job_id,
                review_report_id=cls.review_report_id,
                review_report_sha256=cls.review_report_sha,
                canonical_score_sha256=cls.canonical_sha,
                parent_revision_id=parent_id,
                parent_revision_sha256=parent_sha,
                allowed_actions=("revision:propose",),
                signing_key=cls.signing_key,
            )
            command = build_score_edit_command(
                {
                    "schemaVersion": "scoremosaic-score-edit-command-v1",
                    "commandId": f"command.poly13.{index}",
                    "jobId": cls.job_id,
                    "reviewerId": cls.reviewer_id,
                    "authorizationDecisionId": decision_id,
                    "reviewReportId": cls.review_report_id,
                    "reviewReportSha256": cls.review_report_sha,
                    "baseCanonicalSha256": cls.canonical_sha,
                    "baseRevisionId": parent_id,
                    "baseRevisionSha256": parent_sha,
                    "issueId": None,
                    "location": {
                        "partId": "part_1",
                        "measureId": measure_id,
                        "eventId": f"event_{index}",
                        "staff": 1,
                        "voice": "1",
                        "onset": {"numerator": index - 1, "denominator": 1},
                    },
                    "operation": {
                        "type": "set_pitch",
                        "value": {"step": "C", "alter": {"numerator": 0, "denominator": 1}, "octave": 4},
                    },
                    "oldValueSha256": _hash(f"old-{index}"),
                    "reason": "teacher correction",
                }
            )
            revision = build_teacher_score_revision(
                grant=grant,
                signing_key=cls.signing_key,
                expected_tenant_id=cls.tenant_id,
                expected_job_id=cls.job_id,
                expected_reviewer_id=cls.reviewer_id,
                expected_review_report_id=cls.review_report_id,
                expected_review_report_sha256=cls.review_report_sha,
                expected_canonical_score_sha256=cls.canonical_sha,
                command=command,
                current_parent_revision_id=parent_id,
                current_parent_revision_sha256=parent_sha,
                resulting_musical_state_sha256=_hash(f"state-{index}"),
                validation_report_sha256=_hash(f"validation-{index}"),
                blocking_issue_count=0,
                unresolved_issue_count=max(0, 3 - index),
                created_at=f"2026-09-14T12:00:0{index}Z",
                previous_audit_event_sha256=previous_audit,
            )
            command_dict = command.to_dict()
            revision_dict = revision.to_dict()
            commands.append(command_dict)
            revisions.append(revision_dict)
            parent_id = revision_dict["revisionId"]
            parent_sha = revision_dict["revisionSha256"]
            previous_audit = revision_dict["auditEventSha256"]
        return revisions, commands

    def _evidence(self, *, page_count: int | None = 2) -> dict:
        return build_teacher_workload_evidence(
            fixture_id=self.fixture_id,
            revisions=deepcopy(self.revisions),
            commands=deepcopy(self.commands),
            measure_count=8,
            measure_count_source_sha256=self.canonical_sha,
            page_count=page_count,
            page_count_source_sha256=None if page_count is None else _hash("source-pages"),
        )

    def _semantic_observation(self) -> dict:
        unavailable_metric = {"available": False, "correct": None, "total": None}
        return {
            "schemaVersion": "scoremosaic-polyphonic-engine-semantic-observation-v1",
            "observationId": "poly_metric_obs_0123456789abcdef01234567",
            "fixtureId": self.fixture_id,
            "reference": {
                "kind": "TEACHER_GOLD",
                "artifactSha256": _hash("teacher-gold"),
                "verified": True,
            },
            "engine": {
                "name": "audiveris",
                "engineVersion": "test-1",
                "modelVersion": "test-1",
                "candidateArtifactSha256": _hash("candidate"),
                "canonicalSha256": self.canonical_sha,
            },
            "parse": {"attempted": True, "success": True},
            "structuralValidity": {"available": False, "valid": None},
            "semanticMetrics": {
                "pitch": dict(unavailable_metric),
                "duration": dict(unavailable_metric),
                "onset": dict(unavailable_metric),
                "voice": dict(unavailable_metric),
                "staff": dict(unavailable_metric),
                "tie": dict(unavailable_metric),
                "tuplet": dict(unavailable_metric),
            },
            "measureConsistency": {
                "available": False,
                "method": "UNAVAILABLE",
                "correct": None,
                "total": None,
            },
            "relationCorrectness": {
                "available": False,
                "method": "UNAVAILABLE",
                "correct": None,
                "total": None,
            },
            "structuralDistance": {
                "available": False,
                "method": "UNAVAILABLE",
                "numerator": None,
                "denominator": None,
                "lowerIsBetter": True,
            },
            "teacherEdits": {
                "available": False,
                "method": "UNAVAILABLE",
                "editCount": None,
                "measureCount": None,
                "pageCount": None,
            },
            "sourceEvaluationResultSha256": None,
            "boundaries": {
                "researchEvaluationOnly": True,
                "readOnly": True,
                "singleAggregateAccuracyScore": False,
                "engineRanking": False,
                "winnerSelection": False,
                "automaticMerge": False,
                "automaticCorrection": False,
                "teacherApproval": False,
                "productionDecisionAuthority": False,
                "stOmrIntegration": False,
            },
        }

    def test_contract_and_method_are_versioned(self) -> None:
        self.assertEqual(
            EVIDENCE_SCHEMA_VERSION,
            SCHEMA["properties"]["schemaVersion"]["const"],
        )
        self.assertEqual(
            TEACHER_EDIT_METHOD,
            SCHEMA["properties"]["method"]["const"],
        )

    def test_complete_revision_chain_produces_deterministic_exact_workload(self) -> None:
        first = self._evidence()
        second = self._evidence()
        self.assertEqual(first, second)
        self.assertEqual(3, first["workload"]["editCount"])
        self.assertEqual({"numerator": 3, "denominator": 8}, first["workload"]["editsPerMeasure"])
        self.assertEqual({"numerator": 3, "denominator": 2}, first["workload"]["editsPerPage"])
        self.assertEqual(["measure_1", "measure_2"], first["lineage"]["editedMeasureIds"])
        self.assertEqual(3, first["lineage"]["revisionCount"])
        self.assertEqual(self.revisions[-1]["revisionSha256"], first["lineage"]["headRevisionSha256"])
        self.assertEqual(first, validate_teacher_workload_evidence(first))

    def test_repeated_edits_in_same_measure_count_as_separate_teacher_actions(self) -> None:
        evidence = self._evidence()
        self.assertEqual(3, evidence["workload"]["editCount"])
        self.assertEqual(2, len(evidence["lineage"]["editedMeasureIds"]))

    def test_page_denominator_is_optional_and_never_invented(self) -> None:
        evidence = self._evidence(page_count=None)
        self.assertIs(evidence["denominators"]["page"]["available"], False)
        self.assertIsNone(evidence["denominators"]["page"]["count"])
        self.assertIsNone(evidence["workload"]["editsPerPage"])
        self.assertEqual({"numerator": 3, "denominator": 8}, evidence["workload"]["editsPerMeasure"])

    def test_empty_history_is_not_misreported_as_zero_edits(self) -> None:
        with self.assertRaisesRegex(TeacherWorkloadEvidenceError, "empty_revision_history_unprovable"):
            build_teacher_workload_evidence(
                fixture_id=self.fixture_id,
                revisions=[],
                commands=[],
                measure_count=8,
                measure_count_source_sha256=self.canonical_sha,
            )

    def test_duplicate_command_or_revision_replay_fails_closed(self) -> None:
        commands = deepcopy(self.commands)
        commands[-1] = deepcopy(commands[0])
        with self.assertRaisesRegex(TeacherWorkloadEvidenceError, "duplicate_or_replayed_command"):
            build_teacher_workload_evidence(
                fixture_id=self.fixture_id,
                revisions=deepcopy(self.revisions),
                commands=commands,
                measure_count=8,
                measure_count_source_sha256=self.canonical_sha,
            )

        revisions = deepcopy(self.revisions)
        revisions[-1] = deepcopy(revisions[1])
        with self.assertRaisesRegex(TeacherWorkloadEvidenceError, "duplicate_or_replayed_revision"):
            build_teacher_workload_evidence(
                fixture_id=self.fixture_id,
                revisions=revisions,
                commands=deepcopy(self.commands),
                measure_count=8,
                measure_count_source_sha256=self.canonical_sha,
            )

    def test_tampered_revision_hash_fails_closed(self) -> None:
        revisions = deepcopy(self.revisions)
        revisions[1]["resultingMusicalStateSha256"] = _hash("tampered-state")
        with self.assertRaisesRegex(TeacherWorkloadEvidenceError, "revision_audit_hash_mismatch"):
            build_teacher_workload_evidence(
                fixture_id=self.fixture_id,
                revisions=revisions,
                commands=deepcopy(self.commands),
                measure_count=8,
                measure_count_source_sha256=self.canonical_sha,
            )

    def test_validly_resealed_but_wrong_parent_chain_is_rejected(self) -> None:
        revisions = deepcopy(self.revisions)
        revisions[1]["parentRevisionId"] = None
        revisions[1]["parentRevisionSha256"] = None
        revisions[1] = _reseal_revision(revisions[1])
        with self.assertRaisesRegex(TeacherWorkloadEvidenceError, "revision_parent_chain_mismatch"):
            build_teacher_workload_evidence(
                fixture_id=self.fixture_id,
                revisions=revisions,
                commands=deepcopy(self.commands),
                measure_count=8,
                measure_count_source_sha256=self.canonical_sha,
            )

    def test_measure_denominator_must_be_bound_to_edited_canonical(self) -> None:
        with self.assertRaisesRegex(TeacherWorkloadEvidenceError, "measure_denominator_scope_mismatch"):
            build_teacher_workload_evidence(
                fixture_id=self.fixture_id,
                revisions=deepcopy(self.revisions),
                commands=deepcopy(self.commands),
                measure_count=8,
                measure_count_source_sha256=_hash("different-score"),
            )

    def test_sm_poly_04_projection_requires_exact_fixture_canonical_and_page_denominator(self) -> None:
        observation = self._semantic_observation()
        projected = project_teacher_workload_to_sm_poly_04(self._evidence(), observation)
        self.assertIs(projected["teacherEdits"]["available"], True)
        self.assertEqual(TEACHER_EDIT_METHOD, projected["teacherEdits"]["method"])
        self.assertEqual(3, projected["teacherEdits"]["editCount"])
        self.assertEqual(8, projected["teacherEdits"]["measureCount"])
        self.assertEqual(2, projected["teacherEdits"]["pageCount"])
        self.assertIs(observation["teacherEdits"]["available"], False)
        validate_semantic_observation(projected)

        wrong_canonical = self._semantic_observation()
        wrong_canonical["engine"]["canonicalSha256"] = _hash("wrong-canonical")
        with self.assertRaisesRegex(TeacherWorkloadEvidenceError, "semantic_canonical_mismatch"):
            project_teacher_workload_to_sm_poly_04(self._evidence(), wrong_canonical)

        with self.assertRaisesRegex(
            TeacherWorkloadEvidenceError, "page_denominator_unavailable_for_sm_poly_04_v1"
        ):
            project_teacher_workload_to_sm_poly_04(self._evidence(page_count=None), observation)

    def test_tampered_evidence_hash_is_rejected(self) -> None:
        evidence = self._evidence()
        evidence["workload"]["editCount"] = 4
        with self.assertRaises(TeacherWorkloadEvidenceError):
            validate_teacher_workload_evidence(evidence)

    def test_authority_invariants_remain_unchanged(self) -> None:
        evidence = self._evidence()
        self.assertEqual(
            {
                "researchEvaluationOnly": True,
                "readOnly": True,
                "modelTrainingSideEffect": False,
                "engineRanking": False,
                "winnerSelection": False,
                "automaticCorrection": False,
                "teacherApproval": False,
                "publicationAuthority": False,
                "productionDecisionAuthority": False,
            },
            evidence["boundaries"],
        )
        current = ARCHITECTURE["currentOmr"]
        self.assertEqual(["audiveris", "homr", "clarity"], current["productionCandidateEngines"])
        self.assertEqual(2, current["stage7MinimumCanonicalCandidates"])
        self.assertIs(current["stOmrIntegratedIntoGateway"], False)
        self.assertIs(ARCHITECTURE["teacherReview"]["productionWriteActivated"], False)
        self.assertIs(ARCHITECTURE["production"]["productionReady"], False)


if __name__ == "__main__":
    unittest.main()
