from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "services" / "teacher-review-service" / "src"
sys.path.insert(0, str(SRC))

from scoremosaic_teacher_review.contracts import (  # noqa: E402
    COMMAND_VERSION,
    Stage8ContractError,
    build_score_edit_command,
    build_teacher_score_revision,
    issue_authorization_grant,
    validate_score_edit_command,
    verify_authorization_grant,
)


KEY = b"stage8-test-purpose-separated-key-32bytes!!"
OTHER_KEY = b"stage8-other-purpose-separated-key-32bytes!"
H_A = "a" * 64
H_B = "b" * 64
H_C = "c" * 64
H_D = "d" * 64


def command_payload(**overrides):
    payload = {
        "schemaVersion": COMMAND_VERSION,
        "commandId": "cmd_stage8_0001",
        "jobId": "job_stage8_0001",
        "reviewerId": "teacher_001",
        "authorizationDecisionId": "authz_stage8_0001",
        "reviewReportId": "report_stage8_0001",
        "reviewReportSha256": H_A,
        "baseCanonicalSha256": H_B,
        "baseRevisionId": None,
        "baseRevisionSha256": None,
        "issueId": "issue_stage8_01",
        "location": {
            "partId": "P1",
            "measureId": "P1:M1",
            "eventId": "P1:M1:E1",
            "staff": 1,
            "voice": "1",
            "onset": {"numerator": 0, "denominator": 1},
        },
        "operation": {
            "type": "set_pitch",
            "value": {"step": "C", "alter": {"numerator": 1, "denominator": 1}, "octave": 4},
        },
        "oldValueSha256": H_C,
        "reason": "Source evidence shows C-sharp.",
    }
    payload.update(overrides)
    return payload


def make_grant(parent_id=None, parent_sha=None, actions=("revision:read", "revision:propose")):
    return issue_authorization_grant(
        decision_id="authz_stage8_0001",
        reviewer_id="teacher_001",
        tenant_id="school_001",
        job_id="job_stage8_0001",
        review_report_id="report_stage8_0001",
        review_report_sha256=H_A,
        canonical_score_sha256=H_B,
        parent_revision_id=parent_id,
        parent_revision_sha256=parent_sha,
        allowed_actions=actions,
        signing_key=KEY,
    )


def verify(grant, parent_id=None, parent_sha=None):
    return verify_authorization_grant(
        grant,
        signing_key=KEY,
        required_action="revision:propose",
        expected_job_id="job_stage8_0001",
        expected_reviewer_id="teacher_001",
        expected_review_report_id="report_stage8_0001",
        expected_review_report_sha256=H_A,
        expected_canonical_score_sha256=H_B,
        expected_parent_revision_id=parent_id,
        expected_parent_revision_sha256=parent_sha,
    )


class Stage8AuthorizationTests(unittest.TestCase):
    def test_grant_is_deterministic_and_repr_redacts_signature(self):
        grants = [make_grant() for _ in range(10)]
        self.assertEqual(1, len({g.grant_sha256 for g in grants}))
        self.assertEqual(1, len({g.signature_hex for g in grants}))
        self.assertNotIn(grants[0].signature_hex, repr(grants[0]))
        self.assertEqual("<redacted>", grants[0].safe_dict()["signature"])

    def test_tampered_grant_and_wrong_key_fail_closed(self):
        grant = make_grant()
        with self.assertRaisesRegex(Stage8ContractError, "AUTHZ_GRANT_HASH_MISMATCH"):
            verify(replace(grant, job_id="job_stage8_9999"))
        with self.assertRaisesRegex(Stage8ContractError, "AUTHZ_SIGNATURE_INVALID"):
            verify_authorization_grant(
                grant,
                signing_key=OTHER_KEY,
                required_action="revision:propose",
                expected_job_id="job_stage8_0001",
                expected_reviewer_id="teacher_001",
                expected_review_report_id="report_stage8_0001",
                expected_review_report_sha256=H_A,
                expected_canonical_score_sha256=H_B,
                expected_parent_revision_id=None,
                expected_parent_revision_sha256=None,
            )

    def test_cross_resource_and_denied_action_fail_closed(self):
        grant = make_grant(actions=("revision:read",))
        with self.assertRaisesRegex(Stage8ContractError, "AUTHZ_ACTION_DENIED"):
            verify(grant)
        grant = make_grant()
        with self.assertRaisesRegex(Stage8ContractError, "AUTHZ_CANONICAL_HASH_MISMATCH"):
            verify_authorization_grant(
                grant,
                signing_key=KEY,
                required_action="revision:propose",
                expected_job_id="job_stage8_0001",
                expected_reviewer_id="teacher_001",
                expected_review_report_id="report_stage8_0001",
                expected_review_report_sha256=H_A,
                expected_canonical_score_sha256=H_C,
                expected_parent_revision_id=None,
                expected_parent_revision_sha256=None,
            )


class Stage8EditCommandTests(unittest.TestCase):
    def test_command_is_closed_deterministic_and_immutable(self):
        commands = [build_score_edit_command(command_payload()) for _ in range(10)]
        self.assertEqual(1, len({c.command_sha256 for c in commands}))
        with self.assertRaises(TypeError):
            commands[0].location["eventId"] = "other"
        with self.assertRaises(TypeError):
            commands[0].location["onset"]["numerator"] = 99
        with self.assertRaises(TypeError):
            commands[0].operation["value"]["octave"] = 9
        self.assertEqual("C", commands[0].to_dict()["operation"]["value"]["step"])
        with self.assertRaises(FrozenInstanceError):
            commands[0].reason = "changed"

    def test_arbitrary_path_xml_and_extra_fields_are_rejected(self):
        payload = command_payload()
        payload["xml"] = "<score-partwise/>"
        with self.assertRaisesRegex(Stage8ContractError, "COMMAND_SCHEMA_CLOSED"):
            build_score_edit_command(payload)

        payload = command_payload(operation={"type": "replace_xml", "value": "<evil/>"})
        with self.assertRaisesRegex(Stage8ContractError, "COMMAND_OPERATION_NOT_ALLOWED"):
            build_score_edit_command(payload)

        payload = command_payload(location={**command_payload()["location"], "path": "$.parts[0]"})
        with self.assertRaisesRegex(Stage8ContractError, "COMMAND_LOCATION_INVALID"):
            build_score_edit_command(payload)

    def test_operation_domains_are_bounded(self):
        bad = [
            {"type": "set_dots", "value": 9},
            {"type": "set_tab", "value": {"string": 0, "fret": 2}},
            {"type": "set_time_signature", "value": {"beats": "0", "beatType": 4}},
            {"type": "remove_event", "value": {}},
        ]
        for operation in bad:
            with self.subTest(operation=operation):
                with self.assertRaisesRegex(Stage8ContractError, "COMMAND_VALUE_INVALID"):
                    build_score_edit_command(command_payload(operation=operation))

    def test_command_hash_tampering_is_detected(self):
        command = build_score_edit_command(command_payload()).to_dict()
        command["reason"] = "tampered"
        with self.assertRaisesRegex(Stage8ContractError, "COMMAND_HASH_MISMATCH"):
            validate_score_edit_command(command)


class Stage8RevisionTests(unittest.TestCase):
    def test_revision_is_deterministic_immutable_and_never_approved_or_publishable(self):
        authorization = verify(make_grant())
        command = build_score_edit_command(command_payload())
        revisions = [
            build_teacher_score_revision(
                authorization=authorization,
                command=command,
                current_parent_revision_id=None,
                current_parent_revision_sha256=None,
                resulting_musical_state_sha256=H_C,
                validation_report_sha256=H_D,
                blocking_issue_count=0,
                unresolved_issue_count=1,
                created_at="2026-08-21T20:00:00Z",
                previous_audit_event_sha256=None,
            )
            for _ in range(10)
        ]
        self.assertEqual(1, len({r.record["revisionSha256"] for r in revisions}))
        record = revisions[0].record
        self.assertEqual("draft", record["status"])
        self.assertFalse(record["approvalEligible"])
        self.assertFalse(record["publicationEligible"])
        self.assertTrue(record["immutable"])
        with self.assertRaises(TypeError):
            record["status"] = "approved"
        self.assertEqual(record["revisionId"], revisions[0].to_dict()["revisionId"])

    def test_stale_parent_rejected_after_first_revision(self):
        root_auth = verify(make_grant())
        root_command = build_score_edit_command(command_payload())
        first = build_teacher_score_revision(
            authorization=root_auth,
            command=root_command,
            current_parent_revision_id=None,
            current_parent_revision_sha256=None,
            resulting_musical_state_sha256=H_C,
            validation_report_sha256=H_D,
            blocking_issue_count=0,
            unresolved_issue_count=0,
            created_at="2026-08-21T20:00:00Z",
            previous_audit_event_sha256=None,
        )
        with self.assertRaisesRegex(Stage8ContractError, "COMMAND_STALE_PARENT"):
            build_teacher_score_revision(
                authorization=root_auth,
                command=root_command,
                current_parent_revision_id=first.record["revisionId"],
                current_parent_revision_sha256=first.record["revisionSha256"],
                resulting_musical_state_sha256=H_D,
                validation_report_sha256=H_C,
                blocking_issue_count=0,
                unresolved_issue_count=0,
                created_at="2026-08-21T20:00:01Z",
                previous_audit_event_sha256=first.record["auditEventSha256"],
            )

    def test_second_revision_binds_exact_parent_and_audit_chain(self):
        root_auth = verify(make_grant())
        root_command = build_score_edit_command(command_payload())
        first = build_teacher_score_revision(
            authorization=root_auth,
            command=root_command,
            current_parent_revision_id=None,
            current_parent_revision_sha256=None,
            resulting_musical_state_sha256=H_C,
            validation_report_sha256=H_D,
            blocking_issue_count=0,
            unresolved_issue_count=0,
            created_at="2026-08-21T20:00:00Z",
            previous_audit_event_sha256=None,
        )
        parent_id = first.record["revisionId"]
        parent_sha = first.record["revisionSha256"]
        auth2 = verify(make_grant(parent_id, parent_sha), parent_id, parent_sha)
        command2 = build_score_edit_command(
            command_payload(
                commandId="cmd_stage8_0002",
                baseRevisionId=parent_id,
                baseRevisionSha256=parent_sha,
                operation={"type": "set_dots", "value": 1},
            )
        )
        second = build_teacher_score_revision(
            authorization=auth2,
            command=command2,
            current_parent_revision_id=parent_id,
            current_parent_revision_sha256=parent_sha,
            resulting_musical_state_sha256=H_D,
            validation_report_sha256=H_C,
            blocking_issue_count=0,
            unresolved_issue_count=0,
            created_at="2026-08-21T20:00:01Z",
            previous_audit_event_sha256=first.record["auditEventSha256"],
        )
        self.assertEqual(parent_id, second.record["parentRevisionId"])
        self.assertEqual(parent_sha, second.record["parentRevisionSha256"])
        self.assertEqual(first.record["auditEventSha256"], second.record["previousAuditEventSha256"])


class Stage8RepositoryContractTests(unittest.TestCase):
    def test_activation_flags_remain_locked(self):
        pyproject = (ROOT / "services" / "teacher-review-service" / "pyproject.toml").read_text(encoding="utf-8")
        for marker in (
            "write-api-enabled = false",
            "public-api-enabled = false",
            "approval-enabled = false",
            "publication-enabled = false",
            "corrected-musicxml-materialization-enabled = false",
            "production-durable-store-enabled = false",
        ):
            self.assertIn(marker, pyproject)

    def test_json_contracts_are_closed_and_locked(self):
        for name in (
            "teacher-review-authorization-v1.schema.json",
            "score-edit-command-v1.schema.json",
            "teacher-score-revision-v1.schema.json",
        ):
            document = json.loads((ROOT / "contracts" / name).read_text(encoding="utf-8"))
            self.assertFalse(document["additionalProperties"])
        revision = json.loads((ROOT / "contracts" / "teacher-score-revision-v1.schema.json").read_text(encoding="utf-8"))
        props = revision["properties"]
        self.assertEqual({"const": False}, props["approvalEligible"])
        self.assertEqual({"const": False}, props["publicationEligible"])


if __name__ == "__main__":
    unittest.main()
