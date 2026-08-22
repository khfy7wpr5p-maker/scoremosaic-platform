from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
TEACHER_SRC = ROOT / "services" / "teacher-review-service" / "src"
ENSEMBLE_SRC = ROOT / "services" / "ensemble-service" / "src"
sys.path.insert(0, str(ENSEMBLE_SRC))
sys.path.insert(0, str(TEACHER_SRC))

from scoremosaic_ensemble.musicxml import MusicXmlNormalizationError, normalize_musicxml  # noqa: E402
from scoremosaic_ensemble.teacher_review_musicxml import (  # noqa: E402
    TEACHER_REVIEW_ENGINE,
    normalize_teacher_review_musicxml,
)
from scoremosaic_teacher_review import (  # noqa: E402
    COMMAND_VERSION,
    RevisionScope,
    apply_score_edit_command,
    build_score_edit_command,
    build_teacher_score_revision,
    canonical_payload_sha256,
    expected_old_value_sha256,
    issue_authorization_grant,
    materialize_canonical_state,
)
from scoremosaic_teacher_review.corrected_musicxml import (  # noqa: E402
    ARTIFACT_VERSION,
    MEDIA_TYPE,
    ROUNDTRIP_VERSION,
    SAFETY_VERSION,
    CorrectedMusicXmlError,
    build_corrected_musicxml_artifact,
    materialize_musicxml_bytes,
    semantic_projection_from_canonical,
    semantic_projection_from_state,
    validate_generated_musicxml,
)

AUTHZ_KEY = b"stage8f-authz-purpose-separated-key-32bytes!!"
H_REPORT = "a" * 64
H_ARTIFACT = "c" * 64


def q(n: int, d: int = 1) -> dict[str, int]:
    return {"numerator": n, "denominator": d}


def ev(eid: str, order: int, onset: int, duration: int, *, kind: str = "note", step: str = "C") -> dict:
    return {
        "eventId": eid,
        "xmlOrder": order,
        "kind": kind,
        "onset": q(onset),
        "effectiveDuration": q(duration),
        "writtenDuration": q(duration),
        "writtenType": "quarter" if duration == 1 else "half",
        "dots": 0,
        "tuplet": None,
        "voice": "1",
        "staff": 1,
        "pitch": None if kind == "rest" else {"step": step, "alter": q(0), "octave": 4},
        "tab": None if kind == "rest" else {"string": 2, "fret": 1},
        "grace": False,
        "chordGroup": None,
        "chordIndex": None,
        "ties": [],
        "provenance": {
            "xmlPath": f"/score-partwise/part[1]/measure[1]/note[{order + 1}]",
            "sourceEventIndex": order,
        },
    }


def fixture() -> dict:
    data = {
        "schemaVersion": "1.0",
        "source": {
            "engine": "audiveris",
            "engineVersion": "5.5",
            "modelVersion": None,
            "artifactRef": "artifact://stage8f/base.musicxml",
            "artifactSha256": H_ARTIFACT,
        },
        "rootType": "score-partwise",
        "movementTitle": "Stage8F",
        "parts": [
            {
                "partId": "P1",
                "name": "Guitar",
                "ordinal": 1,
                "measures": [
                    {
                        "measureId": "P1:M1",
                        "number": "1",
                        "ordinal": 1,
                        "implicit": False,
                        "divisionsAtStart": 1,
                        "timeSignatureAtStart": {"beats": "4", "beatType": 4},
                        "expectedDuration": q(4),
                        "observedDuration": q(4),
                        "divisionsChanges": [],
                        "timeSignatureChanges": [],
                        "timingMovements": [],
                        "events": [
                            ev("P1:M1:E1", 0, 0, 1, step="C"),
                            ev("P1:M1:E2", 1, 1, 1, step="D"),
                            ev("P1:M1:E3", 2, 2, 2, kind="rest"),
                        ],
                    }
                ],
            }
        ],
        "diagnostics": [],
        "canonicalSha256": "0" * 64,
    }
    data["canonicalSha256"] = canonical_payload_sha256(data)
    return data


def scope_for(data: dict) -> RevisionScope:
    return RevisionScope.create(
        tenant_id="school_stage8f",
        job_id="job_stage8f_0001",
        review_report_id="report_stage8f_0001",
        review_report_sha256=H_REPORT,
        base_canonical_sha256=data["canonicalSha256"],
    )


def loc(eid: str = "P1:M1:E1", onset: int = 0) -> dict:
    return {
        "partId": "P1",
        "measureId": "P1:M1",
        "eventId": eid,
        "staff": 1,
        "voice": "1",
        "onset": q(onset),
    }


def command(state, operation: dict, *, target: dict | None = None, command_id: str = "cmd_stage8f_01"):
    target = target or loc()
    return build_score_edit_command(
        {
            "schemaVersion": COMMAND_VERSION,
            "commandId": command_id,
            "jobId": "job_stage8f_0001",
            "reviewerId": "teacher_stage8f",
            "authorizationDecisionId": f"authz_{command_id}",
            "reviewReportId": "report_stage8f_0001",
            "reviewReportSha256": H_REPORT,
            "baseCanonicalSha256": state.to_dict()["baseCanonicalSha256"],
            "baseRevisionId": None,
            "baseRevisionSha256": None,
            "issueId": "issue_stage8f_0001",
            "location": target,
            "operation": operation,
            "oldValueSha256": expected_old_value_sha256(
                state,
                location=target,
                operation_type=operation["type"],
            ),
            "reason": "Stage 8-F deterministic derivative test.",
        }
    )


def revision_for(base: dict, state, operation: dict, *, target: dict | None = None, command_id: str = "cmd_stage8f_01"):
    cmd = command(state, operation, target=target, command_id=command_id)
    applied = apply_score_edit_command(state, cmd)
    grant = issue_authorization_grant(
        decision_id=f"authz_{command_id}",
        reviewer_id="teacher_stage8f",
        tenant_id="school_stage8f",
        job_id="job_stage8f_0001",
        review_report_id="report_stage8f_0001",
        review_report_sha256=H_REPORT,
        canonical_score_sha256=base["canonicalSha256"],
        parent_revision_id=None,
        parent_revision_sha256=None,
        allowed_actions=("revision:read", "revision:propose"),
        signing_key=AUTHZ_KEY,
    )
    revision = build_teacher_score_revision(
        grant=grant,
        signing_key=AUTHZ_KEY,
        expected_tenant_id="school_stage8f",
        expected_job_id="job_stage8f_0001",
        expected_reviewer_id="teacher_stage8f",
        expected_review_report_id="report_stage8f_0001",
        expected_review_report_sha256=H_REPORT,
        expected_canonical_score_sha256=base["canonicalSha256"],
        command=cmd,
        current_parent_revision_id=None,
        current_parent_revision_sha256=None,
        resulting_musical_state_sha256=applied.state.state_sha256,
        validation_report_sha256=applied.validation.report_sha256,
        blocking_issue_count=applied.validation.blocking_issue_count,
        unresolved_issue_count=applied.validation.unresolved_issue_count,
        created_at="2026-08-22T12:30:00Z",
        previous_audit_event_sha256=None,
    )
    return applied.state, revision


class Stage8FCorrectedMusicXmlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base = fixture()
        self.scope = scope_for(self.base)
        self.base_state = materialize_canonical_state(self.scope, self.base)

    def test_pitch_revision_materializes_deterministically_and_roundtrips(self) -> None:
        state, revision = revision_for(
            self.base,
            self.base_state,
            {"type": "set_pitch", "value": {"step": "F", "alter": q(1), "octave": 5}},
        )
        artifacts = [
            build_corrected_musicxml_artifact(scope=self.scope, revision=revision, state=state)
            for _ in range(10)
        ]
        self.assertEqual(1, len({artifact.document for artifact in artifacts}))
        self.assertEqual(1, len({artifact.artifact_record_sha256 for artifact in artifacts}))
        record = artifacts[0].to_dict()
        self.assertEqual(ARTIFACT_VERSION, record["schemaVersion"])
        self.assertEqual(MEDIA_TYPE, record["mediaType"])
        self.assertEqual(SAFETY_VERSION, record["safetyPolicyVersion"])
        self.assertEqual(ROUNDTRIP_VERSION, record["roundTripContractVersion"])
        self.assertTrue(record["roundTripMatch"])
        self.assertFalse(record["approvalEligible"])
        self.assertFalse(record["publicationEligible"])
        self.assertEqual(record["expectedSemanticSha256"], record["regeneratedSemanticSha256"])
        self.assertNotIn(b"<!DOCTYPE", artifacts[0].document.upper())
        self.assertNotIn(b"<!ENTITY", artifacts[0].document.upper())

    def test_remove_event_roundtrip_uses_semantics_not_regenerated_event_ids(self) -> None:
        state, revision = revision_for(
            self.base,
            self.base_state,
            {"type": "remove_event", "value": None},
            target=loc("P1:M1:E2", 1),
            command_id="cmd_stage8f_remove",
        )
        artifact = build_corrected_musicxml_artifact(
            scope=self.scope,
            revision=revision,
            state=state,
        )
        regenerated = normalize_teacher_review_musicxml(
            artifact.document,
            artifact_ref="teacher-review/test/remove.musicxml",
        )
        self.assertEqual(
            semantic_projection_from_state(state),
            semantic_projection_from_canonical(regenerated),
        )
        regenerated_ids = [event.event_id for event in regenerated.parts[0].measures[0].events]
        state_ids = [event["eventId"] for event in state.to_dict()["parts"][0]["measures"][0]["events"]]
        self.assertNotEqual(state_ids, regenerated_ids)

    def test_written_type_edit_roundtrips_editable_semantics_even_if_derived_written_duration_is_stale(self) -> None:
        state, revision = revision_for(
            self.base,
            self.base_state,
            {"type": "set_written_type", "value": "eighth"},
            command_id="cmd_stage8f_type",
        )
        artifact = build_corrected_musicxml_artifact(scope=self.scope, revision=revision, state=state)
        self.assertTrue(artifact.to_dict()["roundTripMatch"])
        self.assertIn(b"<type>eighth</type>", artifact.document)

    def test_revision_state_scope_and_validation_binding_fail_closed(self) -> None:
        state, revision = revision_for(
            self.base,
            self.base_state,
            {"type": "set_dots", "value": 1},
            command_id="cmd_stage8f_bind",
        )
        other_state, _ = revision_for(
            self.base,
            self.base_state,
            {"type": "set_pitch", "value": {"step": "G", "alter": q(0), "octave": 4}},
            command_id="cmd_stage8f_other",
        )
        with self.assertRaisesRegex(CorrectedMusicXmlError, "CORRECTED_XML_REVISION_STATE_MISMATCH"):
            build_corrected_musicxml_artifact(scope=self.scope, revision=revision, state=other_state)

        wrong_scope = RevisionScope.create(
            tenant_id="other_school",
            job_id="job_stage8f_0001",
            review_report_id="report_stage8f_0001",
            review_report_sha256=H_REPORT,
            base_canonical_sha256=self.base["canonicalSha256"],
        )
        with self.assertRaisesRegex(CorrectedMusicXmlError, "CORRECTED_XML_REVISION_VALIDATION_FAILED"):
            build_corrected_musicxml_artifact(scope=wrong_scope, revision=revision, state=state)

    def test_generated_musicxml_safety_rejects_dtd_entity_nul_wrong_root_and_malformed_xml(self) -> None:
        bad_documents = [
            b'<!DOCTYPE score-partwise><score-partwise/>',
            b'<!ENTITY x "y"><score-partwise/>',
            b'<score-partwise>\x00</score-partwise>',
            b'<score-timewise/>',
            b'<score-partwise>',
        ]
        for document in bad_documents:
            with self.subTest(document=document[:30]):
                with self.assertRaises(CorrectedMusicXmlError):
                    validate_generated_musicxml(document)

    def test_unrepresentable_chord_and_non_decimal_alter_fail_closed(self) -> None:
        chord_data = deepcopy(self.base)
        events = chord_data["parts"][0]["measures"][0]["events"]
        events[0]["chordGroup"], events[0]["chordIndex"] = "chord_1", 0
        events[1]["chordGroup"], events[1]["chordIndex"] = "chord_1", 1
        chord_data["canonicalSha256"] = canonical_payload_sha256(chord_data)
        chord_state = materialize_canonical_state(scope_for(chord_data), chord_data)
        with self.assertRaisesRegex(CorrectedMusicXmlError, "CORRECTED_XML_CHORD_STRUCTURE_UNREPRESENTABLE"):
            materialize_musicxml_bytes(chord_state)

        alter_data = deepcopy(self.base)
        alter_data["parts"][0]["measures"][0]["events"][0]["pitch"]["alter"] = q(1, 3)
        alter_data["canonicalSha256"] = canonical_payload_sha256(alter_data)
        alter_state = materialize_canonical_state(scope_for(alter_data), alter_data)
        with self.assertRaisesRegex(CorrectedMusicXmlError, "CORRECTED_XML_ALTER_NOT_EXACT_DECIMAL"):
            materialize_musicxml_bytes(alter_state)

    def test_teacher_review_normalizer_has_explicit_provenance_and_omr_entrypoint_stays_closed(self) -> None:
        document = materialize_musicxml_bytes(self.base_state)
        regenerated = normalize_teacher_review_musicxml(
            document,
            artifact_ref="teacher-review/test/base.musicxml",
        )
        self.assertEqual(TEACHER_REVIEW_ENGINE, regenerated.source.engine)
        with self.assertRaises(MusicXmlNormalizationError):
            normalize_musicxml(
                document,
                engine=TEACHER_REVIEW_ENGINE,
                artifact_ref="teacher-review/test/base.musicxml",
            )


if __name__ == "__main__":
    unittest.main()
