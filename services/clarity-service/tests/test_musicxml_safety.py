from __future__ import annotations

from pathlib import Path
from unittest.mock import patch
import sys
import tempfile
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_clarity.runtime import (
    RuntimeExecutionError,
    _sanitize_musicxml_document,
    _validate_musicxml,
)


class MusicXmlSafetyTests(unittest.TestCase):
    def test_canonical_partwise_doctype_is_removed_before_parsing(self) -> None:
        document = b"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">
<score-partwise version="4.0"/>
"""

        sanitized = _sanitize_musicxml_document(document)

        self.assertNotIn(b"<!DOCTYPE", sanitized.upper())
        self.assertIn(b"<score-partwise", sanitized)

    def test_canonical_timewise_doctype_is_removed(self) -> None:
        document = b"""<?xml version='1.0'?>
<!DOCTYPE score-timewise PUBLIC '-//Recordare//DTD MusicXML 3.1 Timewise//EN' 'https://musicxml.org/dtds/timewise.dtd'>
<score-timewise version='3.1'/>
"""

        sanitized = _sanitize_musicxml_document(document)

        self.assertNotIn(b"<!DOCTYPE", sanitized.upper())
        self.assertIn(b"<score-timewise", sanitized)

    def test_internal_entity_declaration_is_rejected(self) -> None:
        document = b"""<!DOCTYPE score-partwise [
<!ENTITY secret SYSTEM "file:///etc/passwd">
]>
<score-partwise>&secret;</score-partwise>
"""

        with self.assertRaisesRegex(RuntimeExecutionError, "unsafe_declaration"):
            _sanitize_musicxml_document(document)

    def test_noncanonical_doctype_is_rejected(self) -> None:
        document = b"<!DOCTYPE score-partwise><score-partwise/>"

        with self.assertRaisesRegex(RuntimeExecutionError, "unsafe_declaration"):
            _sanitize_musicxml_document(document)

    def test_mismatched_root_and_dtd_are_rejected(self) -> None:
        document = b"""<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Timewise//EN" "http://www.musicxml.org/dtds/timewise.dtd">
<score-partwise/>
"""

        with self.assertRaisesRegex(RuntimeExecutionError, "unsafe_declaration"):
            _sanitize_musicxml_document(document)

    def test_validator_rewrites_only_sanitized_musicxml(self) -> None:
        document = b"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">
<score-partwise version="4.0"/>
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.musicxml"
            path.write_bytes(document)

            _validate_musicxml(path)

            rewritten = path.read_bytes()
            self.assertNotIn(b"<!DOCTYPE", rewritten.upper())
            self.assertIn(b"<score-partwise", rewritten)
            self.assertFalse(path.with_name(".result.musicxml.sanitized").exists())

    def test_validator_does_not_parse_element_tree_before_candidate_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.musicxml"
            path.write_bytes(b"<score-partwise><part/></score-partwise>")

            with patch(
                "scoremosaic_clarity.candidate_safety.ET.fromstring",
                side_effect=AssertionError("full XML tree parse must not run"),
            ):
                _validate_musicxml(path)

    def test_validator_rejects_excessive_xml_depth(self) -> None:
        document = (
            b"<score-partwise>"
            + (b"<x>" * 64)
            + (b"</x>" * 64)
            + b"</score-partwise>"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.musicxml"
            path.write_bytes(document)

            with self.assertRaisesRegex(
                RuntimeExecutionError,
                "clarity_candidate_unsafe:musicxml_depth_exceeded",
            ):
                _validate_musicxml(path)


if __name__ == "__main__":
    unittest.main()
