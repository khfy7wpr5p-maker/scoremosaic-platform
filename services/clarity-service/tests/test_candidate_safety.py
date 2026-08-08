from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import sys
import unittest
import zipfile

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_clarity.candidate_safety import (
    CandidateSafetyError,
    validate_musicxml_bytes,
    validate_mxl_file,
)


class CandidateSafetyTests(unittest.TestCase):
    def _write_mxl(
        self,
        path: Path,
        *,
        root_path: str = "score.musicxml",
        musicxml: bytes = b"<score-partwise/>",
    ) -> None:
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                "META-INF/container.xml",
                f'<container><rootfiles><rootfile full-path="{root_path}"/></rootfiles></container>',
            )
            archive.writestr(root_path, musicxml)

    def test_valid_musicxml_is_accepted(self) -> None:
        result = validate_musicxml_bytes(b"<score-partwise version='4.0'/>")
        self.assertEqual(result.root_type, "score-partwise")
        self.assertEqual(result.container_format, "xml")

    def test_musicxml_validation_does_not_build_element_tree(self) -> None:
        with patch(
            "scoremosaic_clarity.candidate_safety.ET.fromstring",
            side_effect=AssertionError("full XML tree parse must not run"),
        ):
            result = validate_musicxml_bytes(b"<score-partwise><part/></score-partwise>")
        self.assertEqual(result.root_type, "score-partwise")

    def test_entity_declaration_is_rejected(self) -> None:
        document = b"<!DOCTYPE score-partwise [<!ENTITY x SYSTEM 'file:///etc/passwd'>]><score-partwise>&x;</score-partwise>"
        with self.assertRaisesRegex(CandidateSafetyError, "musicxml_unsafe_declaration"):
            validate_musicxml_bytes(document)

    def test_excessive_xml_depth_is_rejected(self) -> None:
        document = (
            b"<score-partwise>"
            + (b"<x>" * 64)
            + (b"</x>" * 64)
            + b"</score-partwise>"
        )
        with self.assertRaisesRegex(CandidateSafetyError, "musicxml_depth_exceeded"):
            validate_musicxml_bytes(document)

    def test_valid_mxl_is_accepted(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "score.mxl"
            self._write_mxl(path)
            result = validate_mxl_file(path)
            self.assertEqual(result.container_format, "mxl")
            self.assertEqual(result.root_type, "score-partwise")

    def test_mxl_path_traversal_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "score.mxl"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr(
                    "META-INF/container.xml",
                    '<container><rootfiles><rootfile full-path="../score.musicxml"/></rootfiles></container>',
                )
                archive.writestr("../score.musicxml", "<score-partwise/>")
            with self.assertRaisesRegex(CandidateSafetyError, "mxl_member_path_unsafe"):
                validate_mxl_file(path)

    def test_mxl_container_declarations_are_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "score.mxl"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr(
                    "META-INF/container.xml",
                    '<!DOCTYPE container><container><rootfiles><rootfile full-path="score.musicxml"/></rootfiles></container>',
                )
                archive.writestr("score.musicxml", "<score-partwise/>")
            with self.assertRaisesRegex(
                CandidateSafetyError, "mxl_container_unsafe_declaration"
            ):
                validate_mxl_file(path)


if __name__ == "__main__":
    unittest.main()
