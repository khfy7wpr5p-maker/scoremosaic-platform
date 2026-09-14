# Teacher-Gold OpenScore Lieder coverage pilot

## Status

This package records five CC0 OpenScore Lieder MXL/render pairs for human Teacher-Gold review. It is **not** fixture admission.

- source: `OpenScore/Lieder`
- pinned source commit: `38c5db510224d9facdc4b08d741fc788cfb58ea8`
- license: `CC0-1.0`
- pinned `LICENSE.txt` SHA-256: `a2010f343487d3f7618affe54f789f5487602331c0a8d03f49e9a7c547cf0499`
- renderer: MuseScore 3.6.2, build `3224f34`, 150 DPI
- renderer AppImage SHA-256: `c59a41ee88bc7c565a939b9c73498ac0451bbd86574e95cb6e359302c1465290`
- review PNG processing: ImageMagick 6.9.12-98; white `#FFFFFF`; alpha removed
- discovery run: `34887250970`
- discovery head: `b61798e43752233d2de80b8249a2f2b2899c6b2c`
- review artifact ID: `10365755626`
- artifact ZIP SHA-256: `220ffffeea22d9f7b1c817ca8043b53ff025b1fd8de8adae8768c3b0ed1fe620`
- artifact size: 545,558 bytes
- artifact retention: 14 days

No corpus bytes from this pilot are persisted to Google Drive by this package. The workflow downloads five pinned MXL files into ephemeral Actions storage, renders only review evidence, uploads the temporary review packet, then deletes the temporary corpus and renderer bytes.

## Pilot records

| ID | Work | MXL SHA-256 | first-page PNG SHA-256 |
| --- | --- | --- | --- |
| `osl_01` | Schubert — Das Rosenband, D.280 | `a6798bffeae124d256acbd21d998baa215887126676739c2c5d19e7651d64c75` | `b6c7b641891fe718449f46a953b4d74dcdf005749c89cc28956cf46e3993d63e` |
| `osl_02` | Robert Schumann — Dein Angesicht, Op.127 No.2 | `e9610dd969b6e556f42b086e3d122842f19644373aee699fe8c74262a1fcbff4` | `cfe8ed7e0996ab19d727e79d013cf15008ad22c6dcf61b93b71023cbccfbee06` |
| `osl_03` | Brahms — Geistliches Wiegenlied, Op.91 No.2 | `8ef00c7ac76c56b74c7183417bf8ea04068bb33a251dd5dbfe8e08f47797b250` | `d6030170efd440a5c248385a02d46de89baac3b5214e0cf8bc28efd73f189bfb` |
| `osl_04` | Fanny Hensel — Verlust | `eeb985968e1a8398f92b0aeac65e098692a9c71a62a3f458e2e9eec8d4f90f11` | `9aaf65b083f6a2c4a312331251900fd1aabb95c00b5c9e624c5b36424f808627` |
| `osl_05` | Clara Schumann — Lorelei | `504dd02b4061e16d91750af5808a80abaa0cab04b955cb0b8f4b38cdd539eeac` | `b08adaa8bb7782c87bc978a4ced6620653d39914eb85aa45ec83880eaf7246e0` |

## Why this batch was selected

The first five admitted OSSQ fixtures are useful clean `VOICE_4_PLUS` material, but they do not fill the broader notation-feature matrix. OpenScore Lieder provides voice-plus-keyboard material with two-staff accompaniment and richer symbolic structures. The discovery parser observed chords, ties, slurs and accidentals in all five records, grace-note elements in `osl_01` and `osl_05`, and tuplet elements in `osl_03` and `osl_05`.

These are **structural observations only**. They do not automatically become benchmark classification labels. Human review and an explicit admission change are still required before any new coverage is counted.

## Human gate

Every record remains:

- `teacherVerificationStatus=DRAFT`
- `evaluationEligibility=REVIEW_REQUIRED`
- `countTowardTeacherGoldMinimum=false`

A teacher should compare each white-background PNG to its matching MXL/reference score and, where useful, playback. A later admission PR may bind only the exact reviewed hashes.

## Authority boundaries

This pilot does not authorize fixture admission, model training, ST-OMR quorum membership, automatic winner selection, automatic MusicXML merge/repair, publication, or production decision authority. The existing verified Teacher-Gold registry remains separate from this DRAFT pilot.
