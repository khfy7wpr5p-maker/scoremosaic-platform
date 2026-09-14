# Teacher-Gold renderer compatibility: MusicXML `direction@system`

Status: research/evaluation evidence only. No Teacher-Gold admission, model-training authorization, Stage 7, automatic correction/merge, or production authority changes are introduced here.

## Why this evidence exists

The OpenScore Core 100 first-page audit found five review items whose symbolic MusicXML parsed cleanly and whose hashes matched the review manifest, but whose rendered direction text did not match MusicXML 4.0 `direction@system` semantics. The affected records are `TG019`, `TG036`, `TG066`, `TG081`, and `TG083`.

A targeted compatibility run rendered the exact same pinned MXL bytes with MuseScore 3.6.2 and MuseScore 4.6.5. Renderer binaries, source MXL files, outputs, and the comparison artifact are SHA-bound in `evaluation/polyphonic-teacher-gold-v1/evidence/musescore-system-direction-compat-v1.json`.

## Result

- `TG019`: fixed in MuseScore 4.6.5 for the targeted first-page direction. The combined `only-top` / `also-top` directions are represented both at the top system and at the current P2 part as required by the pinned XML semantics.
- `TG036`: `only-top` remains in the piano region in MuseScore 4.6.5.
- `TG066`: `only-top` duplicate/current-part direction copies remain in MuseScore 4.6.5.
- `TG081`: the extra piano-region `rit.` remains in MuseScore 4.6.5.
- `TG083`: MuseScore 4.6.5 adds the top copy but retains the piano-region copy, so the result improves but remains noncompliant.

Therefore MuseScore 3.6.2 is not a fidelity oracle for MusicXML 4.0 `direction@system`, and MuseScore 4.6.5 cannot be promoted to such an oracle either: it fixes the targeted `also-top` case but still fails four targeted `only-top` cases.

## Corpus policy consequence

Rendered PNG and symbolic MusicXML must be treated as separate evidence layers. If a MusicXML fixture contains `direction@system="only-top"` or `direction@system="also-top"`:

1. validate the symbolic `direction@system` value independently of the renderer;
2. record renderer/version/hash provenance separately;
3. do not reject the symbolic reference solely because a known renderer places the direction incorrectly;
4. classify renderer fidelity failures as `RENDERER_COMPATIBILITY_REVIEW_REQUIRED` or an equivalent versioned evidence status;
5. do not silently repair or mutate the MusicXML to make it agree with a renderer.

This boundary reduces unnecessary teacher review: known renderer-specific incompatibilities should be detected by the automated semantic gate rather than repeatedly sent to the teacher as if they were unexplained XML errors.

## Automated semantic gate

The policy above is implemented by `scripts/musicxml_direction_system_semantic_gate.py` and contract `contracts/musicxml-direction-system-semantic-gate-v1.json`.

The gate accepts raw MusicXML or MXL, validates `direction@system` directly from symbolic bytes, and suppresses Teacher Review only when the mismatch is explicitly proven to involve `only-top` and/or `also-top`. Unknown relations, malformed input, or renderer mismatches without explicit semantic attribution fail closed and cannot be silently reclassified.

Detailed routing and safety rules are documented in `docs/musicxml-direction-system-semantic-gate-v1.md`.

## Authority boundary

This evidence and semantic gate do not change the current Teacher-Gold minimum or target, do not admit the 100-review pack, and do not authorize model training. Production Stage 7 engines and quorum remain unchanged.
