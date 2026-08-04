from __future__ import annotations

from fractions import Fraction
from pathlib import Path
import json
import sys
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_ensemble.musicxml import (
    MusicXmlNormalizationError,
    normalize_musicxml,
)

FIXTURE = SERVICE_ROOT / "tests" / "fixtures" / "canonical-smoke.musicxml"


class MusicXmlNormalizationTests(unittest.TestCase):
    def _normalize(self, document: bytes | None = None):
        return normalize_musicxml(
            FIXTURE.read_bytes() if document is None else document,
            engine="homr",
            engine_version="0.7.0",
            model_version="fixture-model",
            artifact_ref="candidates/homr/original.musicxml",
        )

    def test_fixed_fixture_normalizes_deterministically(self) -> None:
        first = self._normalize()
        second = self._normalize()
        self.assertEqual(first.as_dict(), second.as_dict())
        self.assertEqual(first.canonical_sha256, second.canonical_sha256)
        self.assertEqual(first.to_json(indent=None), second.to_json(indent=None))
        self.assertEqual(
            first.canonical_sha256,
            "dd556d328a26697b19a545a30437a782b895930554c48fa8b6cae7046b6a4744",
        )

    def test_fixture_preserves_source_identity_and_counts(self) -> None:
        score = self._normalize()
        self.assertEqual(score.source.engine, "homr")
        self.assertEqual(score.source.engine_version, "0.7.0")
        self.assertEqual(score.source.model_version, "fixture-model")
        self.assertEqual(score.measure_count, 2)
        self.assertEqual(score.event_count, 9)
        self.assertEqual(score.movement_title, "Canonical Smoke Score")

    def test_measure_timing_is_normalized_to_quarter_note_fractions(self) -> None:
        score = self._normalize()
        first = score.parts[0].measures[0]
        second = score.parts[0].measures[1]
        self.assertEqual(first.expected_duration, Fraction(4))
        self.assertEqual(first.observed_duration, Fraction(4))
        self.assertEqual(second.expected_duration, Fraction(4))
        self.assertEqual(second.observed_duration, Fraction(4))
        self.assertEqual(first.divisions_at_start, 4)
        self.assertEqual(second.divisions_at_start, 12)

    def test_backup_and_forward_movements_are_preserved(self) -> None:
        movements = self._normalize().parts[0].measures[0].timing_movements
        self.assertEqual([movement.kind for movement in movements], ["backup", "forward"])
        self.assertEqual(movements[0].from_position, Fraction(2))
        self.assertEqual(movements[0].to_position, Fraction(0))
        self.assertEqual(movements[1].from_position, Fraction(2))
        self.assertEqual(movements[1].to_position, Fraction(4))

    def test_chord_members_share_onset_and_group(self) -> None:
        events = self._normalize().parts[0].measures[0].events
        first, second = events[0], events[1]
        self.assertEqual(first.onset, Fraction(0))
        self.assertEqual(second.onset, Fraction(0))
        self.assertEqual(first.chord_group, second.chord_group)
        self.assertEqual(first.chord_index, 0)
        self.assertEqual(second.chord_index, 1)

    def test_pitch_rest_tie_tuplet_and_tab_are_preserved(self) -> None:
        score = self._normalize()
        first_measure = score.parts[0].measures[0]
        second_measure = score.parts[0].measures[1]
        first_note = first_measure.events[0]
        rest = first_measure.events[2]
        triplet = second_measure.events[1]
        sharp = second_measure.events[3]
        self.assertEqual(first_note.pitch.step, "C")
        self.assertEqual(first_note.ties, ("start",))
        self.assertEqual(first_note.tab.string, 3)
        self.assertEqual(first_note.tab.fret, 1)
        self.assertEqual(rest.kind, "rest")
        self.assertEqual(triplet.tuplet.actual_notes, 3)
        self.assertEqual(triplet.tuplet.normal_notes, 2)
        self.assertEqual(sharp.pitch.alter, Fraction(1))

    def test_written_and_effective_durations_remain_distinct(self) -> None:
        triplet = self._normalize().parts[0].measures[1].events[1]
        self.assertEqual(triplet.written_duration, Fraction(1, 2))
        self.assertEqual(triplet.effective_duration, Fraction(1, 3))

    def test_provenance_points_back_to_source_event(self) -> None:
        event = self._normalize().parts[0].measures[0].events[0]
        self.assertIn("/score-partwise/part[1]/measure[1]/note[", event.provenance.xml_path)
        self.assertEqual(event.provenance.source_event_index, 0)

    def test_ignored_elements_create_bounded_diagnostics(self) -> None:
        score = self._normalize()
        codes = [diagnostic.code for diagnostic in score.diagnostics]
        self.assertIn("ignored-attribute", codes)
        self.assertIn("ignored-measure-element", codes)

    def test_serialized_payload_contains_self_hash(self) -> None:
        score = self._normalize()
        payload = score.as_dict()
        self.assertEqual(payload["schemaVersion"], "1.0")
        self.assertEqual(payload["canonicalSha256"], score.canonical_sha256)
        self.assertEqual(len(payload["canonicalSha256"]), 64)
        json.loads(score.to_json())

    def test_dtd_and_entity_declarations_are_rejected(self) -> None:
        malicious = b"""<?xml version='1.0'?>
<!DOCTYPE score-partwise [<!ENTITY xxe SYSTEM 'file:///etc/passwd'>]>
<score-partwise><part-list/><part id='P1'><measure number='1'/></part></score-partwise>
"""
        with self.assertRaisesRegex(MusicXmlNormalizationError, "forbidden"):
            self._normalize(malicious)

    def test_non_partwise_root_is_rejected(self) -> None:
        with self.assertRaisesRegex(MusicXmlNormalizationError, "score-partwise"):
            self._normalize(b"<score-timewise version='4.0'/>")

    def test_note_before_divisions_is_rejected(self) -> None:
        document = b"""<score-partwise><part-list><score-part id='P1'><part-name>X</part-name></score-part></part-list><part id='P1'><measure number='1'><note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration><voice>1</voice><type>quarter</type></note></measure></part></score-partwise>"""
        with self.assertRaisesRegex(MusicXmlNormalizationError, "before divisions"):
            self._normalize(document)

    def test_backup_before_measure_start_is_rejected(self) -> None:
        document = b"""<score-partwise><part-list><score-part id='P1'><part-name>X</part-name></score-part></part-list><part id='P1'><measure number='1'><attributes><divisions>1</divisions></attributes><backup><duration>1</duration></backup></measure></part></score-partwise>"""
        with self.assertRaisesRegex(MusicXmlNormalizationError, "before measure start"):
            self._normalize(document)

    def test_chord_without_preceding_note_is_rejected(self) -> None:
        document = b"""<score-partwise><part-list><score-part id='P1'><part-name>X</part-name></score-part></part-list><part id='P1'><measure number='1'><attributes><divisions>1</divisions></attributes><note><chord/><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration><voice>1</voice><type>quarter</type></note></measure></part></score-partwise>"""
        with self.assertRaisesRegex(MusicXmlNormalizationError, "no preceding"):
            self._normalize(document)

    def test_incomplete_string_fret_pair_is_rejected(self) -> None:
        document = b"""<score-partwise><part-list><score-part id='P1'><part-name>X</part-name></score-part></part-list><part id='P1'><measure number='1'><attributes><divisions>1</divisions></attributes><note><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration><voice>1</voice><type>quarter</type><notations><technical><string>1</string></technical></notations></note></measure></part></score-partwise>"""
        with self.assertRaisesRegex(MusicXmlNormalizationError, "incomplete"):
            self._normalize(document)

    def test_unsafe_artifact_reference_is_rejected(self) -> None:
        with self.assertRaisesRegex(MusicXmlNormalizationError, "unsafe"):
            normalize_musicxml(
                FIXTURE.read_bytes(),
                engine="homr",
                artifact_ref="../candidate.musicxml",
            )

    def test_input_must_be_nonempty_bytes(self) -> None:
        with self.assertRaisesRegex(MusicXmlNormalizationError, "bytes"):
            normalize_musicxml("not-bytes", engine="homr", artifact_ref="candidate.musicxml")
        with self.assertRaisesRegex(MusicXmlNormalizationError, "size"):
            self._normalize(b"")


if __name__ == "__main__":
    unittest.main()
