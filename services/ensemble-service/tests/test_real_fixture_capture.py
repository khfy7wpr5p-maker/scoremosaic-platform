from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "tools"))

from capture_real_fixture import FixtureCaptureError, capture_fixture

_SOURCE_SHA = "a" * 64
_PARTWISE = b"<?xml version='1.0'?><score-partwise version='4.0'><part-list/></score-partwise>"
_CONTAINER = b"""<?xml version='1.0'?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
  <rootfiles>
    <rootfile full-path="score.musicxml" media-type="application/vnd.recordare.musicxml+xml"/>
  </rootfiles>
</container>
"""


def _mxl(score: bytes = _PARTWISE, container: bytes = _CONTAINER) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("META-INF/container.xml", container)
        archive.writestr("score.musicxml", score)
    return output.getvalue()


class RealFixtureCaptureTests(unittest.TestCase):
    def _capture(self, artifact: bytes, *, engine: str = "homr") -> tuple[bytes, dict]:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "input"
            output_path = root / "captured.musicxml"
            metadata_path = root / "capture.json"
            input_path.write_bytes(artifact)

            returned = capture_fixture(
                input_path,
                output_path,
                metadata_path,
                engine=engine,
                engine_version="test-version",
                model_version="test-model",
                source_fixture_sha256=_SOURCE_SHA,
            )

            stored = json.loads(metadata_path.read_text(encoding="utf-8"))
            self.assertEqual(returned, stored)
            return output_path.read_bytes(), stored

    def test_plain_partwise_musicxml_is_captured_deterministically(self) -> None:
        first_document, first_metadata = self._capture(_PARTWISE)
        second_document, second_metadata = self._capture(_PARTWISE)

        self.assertEqual(first_document, _PARTWISE)
        self.assertEqual(first_document, second_document)
        self.assertEqual(first_metadata, second_metadata)
        self.assertEqual(first_metadata["containerFormat"], "xml")
        self.assertFalse(first_metadata["canonicalDoctypeRemoved"])
        self.assertEqual(first_metadata["rootType"], "score-partwise")

    def test_canonical_musicxml_doctype_is_removed(self) -> None:
        document = b"""<?xml version="1.0"?>
<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">
<score-partwise version="4.0"><part-list/></score-partwise>
"""

        captured, metadata = self._capture(document, engine="clarity")

        self.assertNotIn(b"<!DOCTYPE", captured.upper())
        self.assertTrue(metadata["canonicalDoctypeRemoved"])

    def test_canonical_dotted_musicxml_doctype_version_is_removed(self) -> None:
        document = b"""<?xml version="1.0"?>
<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 3.0.1 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">
<score-partwise version="3.0"><part-list/></score-partwise>
"""

        captured, metadata = self._capture(document, engine="audiveris")

        self.assertNotIn(b"<!DOCTYPE", captured.upper())
        self.assertTrue(metadata["canonicalDoctypeRemoved"])

    def test_entity_declaration_is_rejected(self) -> None:
        document = b"""<!DOCTYPE score-partwise [
<!ENTITY secret SYSTEM "file:///etc/passwd">
]><score-partwise>&secret;</score-partwise>
"""

        with self.assertRaisesRegex(FixtureCaptureError, "entity"):
            self._capture(document)

    def test_noncanonical_doctype_is_rejected(self) -> None:
        document = b"<!DOCTYPE score-partwise><score-partwise/>"

        with self.assertRaisesRegex(FixtureCaptureError, "noncanonical"):
            self._capture(document)

    def test_mxl_rootfile_is_extracted_without_other_member_selection(self) -> None:
        captured, metadata = self._capture(_mxl(), engine="audiveris")

        self.assertEqual(captured, _PARTWISE)
        self.assertEqual(metadata["containerFormat"], "mxl")
        self.assertNotEqual(
            metadata["inputArtifactSha256"],
            metadata["extractedMusicXmlSha256"],
        )

    def test_mxl_container_traversal_is_rejected(self) -> None:
        container = _CONTAINER.replace(b"score.musicxml", b"../score.musicxml")

        with self.assertRaisesRegex(FixtureCaptureError, "unsafe MXL member path"):
            self._capture(_mxl(container=container), engine="audiveris")

    def test_mxl_container_with_dtd_is_rejected(self) -> None:
        container = b"""<!DOCTYPE container><container>
<rootfiles><rootfile full-path="score.musicxml"/></rootfiles>
</container>"""

        with self.assertRaisesRegex(FixtureCaptureError, "DTD"):
            self._capture(_mxl(container=container), engine="audiveris")

    def test_score_timewise_is_rejected(self) -> None:
        document = b"<score-timewise version='4.0'/>"

        with self.assertRaisesRegex(FixtureCaptureError, "score-partwise"):
            self._capture(document)

    def test_existing_capture_destination_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "input.musicxml"
            output_path = root / "captured.musicxml"
            metadata_path = root / "capture.json"
            input_path.write_bytes(_PARTWISE)
            output_path.write_bytes(b"do-not-replace")

            with self.assertRaisesRegex(FixtureCaptureError, "must not already exist"):
                capture_fixture(
                    input_path,
                    output_path,
                    metadata_path,
                    engine="homr",
                    engine_version="test-version",
                    model_version="test-model",
                    source_fixture_sha256=_SOURCE_SHA,
                )

            self.assertEqual(output_path.read_bytes(), b"do-not-replace")


if __name__ == "__main__":
    unittest.main()
