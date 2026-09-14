# MusicXML `direction@system` Semantic Gate v1

Status: **research/evaluation gate active; no production decision authority**.

## Purpose

The gate prevents known renderer-specific `direction@system` placement differences from being misclassified as unexplained symbolic MusicXML corruption and repeatedly sent to Teacher Review.

It is deliberately renderer-independent. The source MusicXML is inspected directly; no PNG is treated as a fidelity oracle and no source bytes are rewritten.

## MusicXML 4.0 semantics

The gate follows the MusicXML 4.0 `system-relation` definition used by the `<direction system="...">` attribute:

- `only-top`: display only on the top part of the current system;
- `also-top`: display on both the current part and the top part of the current system;
- `none`: associate only with the current part.

Specification reference: `https://www.w3.org/2021/06/musicxml40/musicxml-reference/data-types/system-relation/`.

## Routing

For a renderer mismatch, suppression of Teacher Review is intentionally narrow and fail-closed.

A mismatch is routed to `RENDERER_COMPATIBILITY_REVIEW_REQUIRED` only when all of the following are true:

1. symbolic parsing succeeds;
2. every `direction@system` value is valid;
3. the caller explicitly identifies the system relation(s) implicated in the mismatch;
4. every implicated relation is one of the known renderer-sensitive values `only-top` or `also-top`;
5. those implicated values actually occur in the inspected MusicXML.

In that case:

- `teacherReviewRequired=false`;
- `technicalReviewRequired=true`;
- the symbolic reference is not rejected merely because the renderer disagrees;
- automatic MusicXML repair remains forbidden.

If the renderer mismatch is not explicitly proven to be one of these known cases, routing fails closed to `TEACHER_REVIEW_REQUIRED`.

Unknown/invalid `direction@system` values go to `SEMANTIC_VALIDATION_REVIEW_REQUIRED`, a technical semantic-review path rather than automatic Teacher-Gold admission.

## Input safety

`scripts/musicxml_direction_system_semantic_gate.py` accepts raw MusicXML or compressed MXL bytes with bounded limits for:

- input size;
- MXL member count and member size;
- encrypted members;
- unsafe ZIP paths;
- XML element count and nesting depth;
- number of `direction@system` records.

MXL is inspected in memory and is not extracted to the filesystem.

## Compatibility evidence

The gate is based on the exact evidence in:

`evaluation/polyphonic-teacher-gold-v1/evidence/musescore-system-direction-compat-v1.json`

That evidence records five OpenScore Core 100 review IDs:

- `TG019`: targeted `also-top` behavior fixed in MuseScore 4.6.5;
- `TG036`, `TG066`, `TG081`, `TG083`: targeted `only-top` behavior remains noncompliant in MuseScore 4.6.5.

The evidence classifies the root cause as `RENDERER_IMPORT_COMPATIBILITY`, not XML corruption and not a playback-system fault.

## Authority boundary

This gate does **not**:

- add fixtures to Teacher-Gold;
- change the current `10/500` verified count;
- turn renderer output into score authority;
- authorize model training;
- change Stage 7 engines or quorum;
- authorize automatic correction, merge, or MusicXML mutation;
- grant production decision authority.

It only improves review routing for a narrow, versioned symbolic-semantic case.

## Local validation

```bash
python -m unittest tests.test_musicxml_direction_system_semantic_gate -v
python -m unittest tests.test_teacher_gold_renderer_direction_compatibility -v
```

To inspect one file:

```bash
python scripts/musicxml_direction_system_semantic_gate.py score.mxl \
  --renderer-mismatch-system only-top
```
