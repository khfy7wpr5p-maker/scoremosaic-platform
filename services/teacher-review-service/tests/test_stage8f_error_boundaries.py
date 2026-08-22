from __future__ import annotations

import ast
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
TEACHER_SRC = ROOT / "services" / "teacher-review-service" / "src"
ENSEMBLE_SRC = ROOT / "services" / "ensemble-service" / "src"
sys.path.insert(0, str(ENSEMBLE_SRC))
sys.path.insert(0, str(TEACHER_SRC))

from scoremosaic_teacher_review.corrected_musicxml import (  # noqa: E402
    CorrectedMusicXmlError,
    semantic_projection_from_canonical,
)

MODULE_PATH = (
    ROOT
    / "services"
    / "teacher-review-service"
    / "src"
    / "scoremosaic_teacher_review"
    / "corrected_musicxml.py"
)


class Stage8FErrorBoundaryTests(unittest.TestCase):
    def test_derivative_module_never_catches_generic_exception_or_base_exception(self) -> None:
        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        broad_handlers: list[tuple[int, str]] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            if node.type is None:
                broad_handlers.append((node.lineno, "bare"))
            elif isinstance(node.type, ast.Name) and node.type.id in {"Exception", "BaseException"}:
                broad_handlers.append((node.lineno, node.type.id))
        self.assertEqual([], broad_handlers)

    def test_canonical_projection_rejects_duck_typed_or_untrusted_objects(self) -> None:
        class FakeCanonical:
            parts = ()

        with self.assertRaisesRegex(CorrectedMusicXmlError, "CORRECTED_XML_CANONICAL_TYPE_INVALID"):
            semantic_projection_from_canonical(FakeCanonical())  # type: ignore[arg-type]

    def test_external_entity_resolution_is_explicitly_disabled(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn("XML_PARAM_ENTITY_PARSING_NEVER", source)
        self.assertIn("ExternalEntityRefHandler", source)
        self.assertIn("CORRECTED_XML_SAFETY_EXTERNAL_ENTITY_FORBIDDEN", source)

    def test_expected_error_classes_are_narrowly_named(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn("except DurableRevisionStoreError as exc:", source)
        self.assertIn("except CanonicalModelError as exc:", source)
        self.assertNotIn("except Exception as exc:", source)


if __name__ == "__main__":
    unittest.main()
