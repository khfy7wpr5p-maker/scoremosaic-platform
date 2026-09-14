# Teacher-Gold degradation pilot

Status: research/evaluation only, non-counting, teacher review required.

This pilot reuses five already teacher-verified OpenScore Lieder symbolic pairs and derives five deterministic degraded first-page PNGs. The purpose is to add controlled scan-condition evidence without inventing new symbolic gold or changing any production authority.

## Pinned source and renderer

- source: `OpenScore/Lieder`
- source commit: `38c5db510224d9facdc4b08d741fc788cfb58ea8`
- source license: `CC0-1.0`
- MuseScore: 3.6.2, AppImage SHA-256 `c59a41ee88bc7c565a939b9c73498ac0451bbd86574e95cb6e359302c1465290`
- render resolution: 150 DPI
- degradation tool: ImageMagick 6.9.12-98

## Five controlled scan conditions

1. `LOW_CONTRAST` — Schubert, *Das Rosenband, D.280* — deterministic gray blend.
2. `ROTATION` — Robert Schumann, *Dein Angesicht, Op.127 No.2* — +2.25 degree rotation.
3. `SKEW` — Brahms, *Geistliches Wiegenlied, Op.91 No.2* — 3 degree horizontal shear.
4. `PERSPECTIVE_DISTORTION` — Fanny Hensel, *Verlust* — deterministic four-corner perspective warp.
5. `LOW_QUALITY_SCAN` — Clara Schumann, *Lorelei* — 42% downsample, mild blur, then upscale.

Every degraded image is opaque and passed non-empty image checks. The degraded source SHA-256, clean render SHA-256, symbolic SHA-256, transform identifier, renderer lineage, and GitHub Actions artifact lineage are pinned in `evaluation/polyphonic-teacher-gold-v1/pilots/degradation-v1.json`.

## Discovery evidence

- workflow run: `34891983599`
- workflow head: `6c0bf942abbbda2db62bd0628b8796e9adf7d270`
- artifact: `10367261196`
- artifact ZIP SHA-256: `f2362cb798a368829d08eed621659b3d08400de30276e2438e6d4dbafbbfcd15`
- artifact retention: 14 days

The review packet contains each MXL file, the clean first-page render, the degraded first-page render, the CC0 license, and the discovery manifest.

## Admission boundary

The clean/symbolic pairs were already teacher-verified, but that does not automatically verify a newly degraded source image. Each degraded image remains `DRAFT`, `REVIEW_REQUIRED`, and `countTowardTeacherGoldMinimum=false` until the teacher confirms that the degradation did not change, crop, hide, or otherwise invalidate the musical content for benchmark use.

No model training is authorized. ST-OMR remains outside the Stage 7 production engine set/quorum. No automatic correction, MusicXML merge, publication, or production-decision authority is granted by this pilot.
