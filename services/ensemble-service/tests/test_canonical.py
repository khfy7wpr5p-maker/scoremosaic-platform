from __future__ import annotations

from fractions import Fraction
from pathlib import Path
import json
import sys
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_ensemble.canonical import (
    CanonicalModelError,
    Pitch,
    SourceIdentity,
    TabPosition,
    TimeSignature,
    TupletRatio,
    canonical_json_digest,
)


class CanonicalPrimitiveTests(unittest.TestCase):
    def test_source_identity_rejects_unsafe_artifact_reference(self) -> None:
        with self.assertRaisesRegex(CanonicalModelError, "unsafe"):
            SourceIdentity(
                engine="homr",
                artifact_ref="candidate/../secret.musicxml",
                artifact_sha256="0" * 64,
            )

    def test_source_identity_requires_known_engine(self) -> None:
        with self.assertRaisesRegex(CanonicalModelError, "unsupported"):
            SourceIdentity(
                engine="unknown",
                artifact_ref="candidate.musicxml",
                artifact_sha256="0" * 64,
            )

    def test_pitch_preserves_fractional_alteration(self) -> None:
        pitch = Pitch(step="F", alter=Fraction(1, 2), octave=4)
        self.assertEqual(
            pitch.as_dict(),
            {
                "step": "F",
                "alter": {"numerator": 1, "denominator": 2},
                "octave": 4,
            },
        )

    def test_tab_position_bounds_are_enforced(self) -> None:
        self.assertEqual(TabPosition(string=6, fret=12).as_dict(), {"string": 6, "fret": 12})
        with self.assertRaises(CanonicalModelError):
            TabPosition(string=0, fret=0)
        with self.assertRaises(CanonicalModelError):
            TabPosition(string=1, fret=-1)

    def test_time_signature_payload_is_stable(self) -> None:
        signature = TimeSignature(beats="3+2", beat_type=8)
        self.assertEqual(signature.as_dict(), {"beats": "3+2", "beatType": 8})

    def test_tuplet_ratio_requires_positive_values(self) -> None:
        self.assertEqual(
            TupletRatio(actual_notes=3, normal_notes=2).as_dict(),
            {"actualNotes": 3, "normalNotes": 2},
        )
        with self.assertRaises(CanonicalModelError):
            TupletRatio(actual_notes=0, normal_notes=2)

    def test_canonical_json_digest_is_key_order_independent(self) -> None:
        left = {"b": 2, "a": [1, {"x": "y"}]}
        right = {"a": [1, {"x": "y"}], "b": 2}
        self.assertEqual(canonical_json_digest(left), canonical_json_digest(right))

    def test_contract_schema_is_valid_json(self) -> None:
        schema_path = SERVICE_ROOT.parents[1] / "contracts" / "canonical-score.schema.json"
        payload = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(payload["properties"]["schemaVersion"]["const"], "1.0")


if __name__ == "__main__":
    unittest.main()
