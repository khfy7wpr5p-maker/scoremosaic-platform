from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch
import stat
import sys
import unittest
import warnings
import zipfile

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

import scoremosaic_clarity.candidate_safety as candidate_safety
from scoremosaic_clarity.candidate_safety import (
    CandidateSafetyError,
    validate_musicxml_bytes,
    validate_mxl_file,
)


class CandidateSafetyTests(unittest.TestCase):
    @staticmethod
    def _container_xml(*root_paths: str) -> bytes:
        rootfiles = "".join(
            f'<rootfile full-path="{root_path}"/>' for root_path in root_paths
        )
        return f"<container><rootfiles>{rootfiles}</rootfiles></container>".encode()

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
                self._container_xml(root_path),
            )
            archive.writestr(root_path, musicxml)

    def test_valid_musicxml_is_accepted(self) -> None:
        result = validate_musicxml_bytes(b"<score-partwise version='4.0'/>")
        self.assertEqual(result.root_type, "score-partwise")
        self.assertEqual(result.container_format, "xml")

    def test_musicxml_validation_does_not_build_element_tree(self) -> None:
        with patch.object(
            candidate_safety.ET,
            "fromstring",
            side_effect=AssertionError("full XML tree parse must not run"),
        ):
            result = validate_musicxml_bytes(
                b"<score-partwise><part/></score-partwise>"
            )
        self.assertEqual(result.root_type, "score-partwise")

    def test_entity_declaration_is_rejected(self) -> None:
        document = b"<!DOCTYPE score-partwise [<!ENTITY x SYSTEM 'file:///etc/passwd'>]><score-partwise>&x;</score-partwise>"
        with self.assertRaisesRegex(
            CandidateSafetyError, "musicxml_unsafe_declaration"
        ):
            validate_musicxml_bytes(document)

    def test_nul_byte_is_rejected(self) -> None:
        with self.assertRaisesRegex(CandidateSafetyError, "musicxml_nul_byte"):
            validate_musicxml_bytes(b"<score-partwise>\x00</score-partwise>")

    def test_musicxml_byte_limit_is_enforced(self) -> None:
        with patch.object(candidate_safety, "MAX_XML_BYTES", 8):
            with self.assertRaisesRegex(
                CandidateSafetyError, "musicxml_size_invalid"
            ):
                validate_musicxml_bytes(b"<score-partwise/>")

    def test_excessive_xml_depth_is_rejected(self) -> None:
        document = (
            b"<score-partwise>"
            + (b"<x>" * 64)
            + (b"</x>" * 64)
            + b"</score-partwise>"
        )
        with self.assertRaisesRegex(
            CandidateSafetyError, "musicxml_depth_exceeded"
        ):
            validate_musicxml_bytes(document)

    def test_element_count_limit_is_enforced_during_parse(self) -> None:
        with patch.object(candidate_safety, "MAX_XML_ELEMENTS", 2):
            with self.assertRaisesRegex(
                CandidateSafetyError, "musicxml_element_count_exceeded"
            ):
                validate_musicxml_bytes(
                    b"<score-partwise><part/><part/></score-partwise>"
                )

    def test_total_attribute_limit_is_enforced_during_parse(self) -> None:
        with patch.object(candidate_safety, "MAX_XML_ATTRIBUTES", 2):
            with self.assertRaisesRegex(
                CandidateSafetyError, "musicxml_attribute_count_exceeded"
            ):
                validate_musicxml_bytes(
                    b"<score-partwise a='1'><part b='2' c='3'/></score-partwise>"
                )

    def test_per_element_attribute_limit_is_enforced_during_parse(self) -> None:
        with patch.object(candidate_safety, "MAX_ATTRIBUTES_PER_ELEMENT", 1):
            with self.assertRaisesRegex(
                CandidateSafetyError, "musicxml_attributes_per_element_exceeded"
            ):
                validate_musicxml_bytes(
                    b"<score-partwise a='1' b='2'/>"
                )

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
                    self._container_xml("../score.musicxml"),
                )
                archive.writestr("../score.musicxml", "<score-partwise/>")
            with self.assertRaisesRegex(
                CandidateSafetyError, "mxl_member_path_unsafe"
            ):
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

    def test_mxl_entry_count_limit_is_enforced(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "score.mxl"
            self._write_mxl(path)
            with patch.object(candidate_safety, "MAX_ZIP_ENTRIES", 1):
                with self.assertRaisesRegex(
                    CandidateSafetyError, "mxl_entry_count_invalid"
                ):
                    validate_mxl_file(path)

    def test_mxl_total_uncompressed_limit_is_enforced(self) -> None:
        container = self._container_xml("score.musicxml")
        with TemporaryDirectory() as directory:
            path = Path(directory) / "score.mxl"
            with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
                archive.writestr("META-INF/container.xml", container)
                archive.writestr("score.musicxml", b"<score-partwise/>")
            with patch.object(
                candidate_safety,
                "MAX_TOTAL_UNCOMPRESSED_BYTES",
                len(container) + 5,
            ):
                with self.assertRaisesRegex(
                    CandidateSafetyError, "mxl_uncompressed_size_exceeded"
                ):
                    validate_mxl_file(path)

    def test_mxl_compression_ratio_limit_is_enforced(self) -> None:
        container = self._container_xml("score.musicxml")
        musicxml = (
            b"<score-partwise>"
            + (b"x" * 4096)
            + b"</score-partwise>"
        )
        with TemporaryDirectory() as directory:
            path = Path(directory) / "score.mxl"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr(
                    "META-INF/container.xml",
                    container,
                    compress_type=zipfile.ZIP_STORED,
                )
                archive.writestr(
                    "score.musicxml",
                    musicxml,
                    compress_type=zipfile.ZIP_DEFLATED,
                )
            with patch.object(candidate_safety, "MAX_COMPRESSION_RATIO", 3):
                with self.assertRaisesRegex(
                    CandidateSafetyError, "mxl_compression_ratio_exceeded"
                ):
                    validate_mxl_file(path)

    def test_mxl_encrypted_entry_is_rejected(self) -> None:
        encrypted = zipfile.ZipInfo("score.musicxml")
        encrypted.flag_bits = 0x1
        fake_archive = MagicMock()
        fake_archive.__enter__.return_value = fake_archive
        fake_archive.__exit__.return_value = False
        fake_archive.infolist.return_value = [encrypted]

        with TemporaryDirectory() as directory:
            path = Path(directory) / "score.mxl"
            path.write_bytes(b"placeholder")
            with patch.object(
                candidate_safety.zipfile,
                "ZipFile",
                return_value=fake_archive,
            ):
                with self.assertRaisesRegex(
                    CandidateSafetyError, "mxl_encrypted_entry"
                ):
                    validate_mxl_file(path)

    def test_mxl_symlink_entry_is_rejected(self) -> None:
        symlink = zipfile.ZipInfo("score.musicxml")
        symlink.create_system = 3
        symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
        with TemporaryDirectory() as directory:
            path = Path(directory) / "score.mxl"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr(symlink, b"target")
            with self.assertRaisesRegex(
                CandidateSafetyError, "mxl_symlink_entry"
            ):
                validate_mxl_file(path)

    def test_mxl_duplicate_member_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "score.mxl"
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                with zipfile.ZipFile(path, "w") as archive:
                    archive.writestr("duplicate.xml", b"<score-partwise/>")
                    archive.writestr("duplicate.xml", b"<score-partwise/>")
            with self.assertRaisesRegex(
                CandidateSafetyError, "mxl_duplicate_member"
            ):
                validate_mxl_file(path)

    def test_mxl_missing_container_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "score.mxl"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("score.musicxml", b"<score-partwise/>")
            with self.assertRaisesRegex(
                CandidateSafetyError, "mxl_container_missing"
            ):
                validate_mxl_file(path)

    def test_mxl_multiple_rootfiles_are_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "score.mxl"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr(
                    "META-INF/container.xml",
                    self._container_xml("one.musicxml", "two.musicxml"),
                )
                archive.writestr("one.musicxml", b"<score-partwise/>")
                archive.writestr("two.musicxml", b"<score-partwise/>")
            with self.assertRaisesRegex(
                CandidateSafetyError, "mxl_rootfile_count_invalid"
            ):
                validate_mxl_file(path)

    def test_mxl_declared_rootfile_must_exist(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "score.mxl"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr(
                    "META-INF/container.xml",
                    self._container_xml("missing.musicxml"),
                )
            with self.assertRaisesRegex(
                CandidateSafetyError, "mxl_rootfile_missing"
            ):
                validate_mxl_file(path)

    def test_mxl_oversized_rootfile_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "score.mxl"
            with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
                archive.writestr(
                    "META-INF/container.xml",
                    self._container_xml("score.musicxml"),
                )
                archive.writestr("score.musicxml", b"x" * 129)
            with patch.object(candidate_safety, "MAX_XML_BYTES", 128):
                with self.assertRaisesRegex(
                    CandidateSafetyError, "mxl_entry_size_invalid"
                ):
                    validate_mxl_file(path)


if __name__ == "__main__":
    unittest.main()
