# Teacher-Gold rights qualification — 2026-09-14

This note records the source-rights decision used by the ScoreMosaic Teacher-Gold intake. It is research/evaluation evidence only and does not admit any Teacher-Gold fixture.

## Decisions

### DoReMi v1 — REVIEW_REQUIRED

Evidence reviewed:

- https://github.com/steinbergmedia/DoReMi/blob/main/README.md
- https://github.com/steinbergmedia/DoReMi/releases/tag/v1.0

The DoReMi lifecycle document states that the published dataset contains only copyright-free / openly distributable scores and that copyright-protected material was excluded from the final published dataset. The repository root, however, does not expose a separate dataset LICENSE file or another explicit license grant covering the dataset compilation/annotations. ScoreMosaic therefore keeps DoReMi at `REVIEW_REQUIRED` and does not count the existing five real-hash pilot pairs toward Teacher-Gold readiness.

### OpenScore Lieder — CLEAR_CC0

Evidence reviewed:

- https://github.com/OpenScore/Lieder
- https://github.com/OpenScore/Lieder/blob/main/LICENSE.txt

OpenScore Lieder explicitly releases its scores under Creative Commons Zero (CC0). It is suitable as a rights-clear symbolic source. Image/render evidence must still be generated or independently obtained, hashed, paired to the exact symbolic source, and teacher-verified before fixture admission.

### OSSQ-OMR — CLEAR_CC0 for annotation sources and bulk-derived formats

Evidence reviewed:

- https://github.com/MALerLab/ossq-omr/tree/omr-dev
- https://github.com/MALerLab/ossq-omr/blob/omr-dev/LICENSE.txt
- https://github.com/MALerLab/ossq-omr/blob/omr-dev/README.md

OSSQ-OMR explicitly states that CC0 covers both the tracked annotation sources and the bulk-distributed derived formats. This is sufficient to move the corpus-level candidate from `REVIEW_REQUIRED` to `CLEAR_CC0` for those materials.

Scanned exemplars remain conditional. The repository documents optional scanned PDFs sourced from IMSLP and per-score source metadata. ScoreMosaic will therefore use synthetic/rendered OSSQ evidence first. A scanned fixture must still carry exact source-level provenance and rights evidence before admission.

## Intake consequence

Current source-candidate rights states after this review:

- DoReMi v1: `REVIEW_REQUIRED`
- OpenScore Lieder: `CLEAR_CC0`
- OSSQ-OMR: `CLEAR_CC0`

This rights qualification does **not** change the Teacher-Gold counter. The verified fixture registry remains authoritative, and candidates remain non-counting until exact image/symbolic SHA-256 evidence and teacher/review verification are present.

## Next gate

Build the first OSSQ synthetic fixture pilot using the source version required by the corpus (`MuseScore 3.6.2`), record the exact renderer/version and source commit, hash both rendered image evidence and symbolic gold, then present the resulting pairs for teacher verification. No automatic fixture admission, training authorization, ST-OMR promotion, correction, or production decision authority is granted by this document.
