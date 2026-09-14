# Teacher-Gold OSSQ synthetic real-hash pilot

## Status

The active review package is **v2**. It records five rights-clear, reproducible OSSQ-OMR image/symbolic pairs for human notation review. It is **not** Teacher-Gold admission.

- source corpus: `MALerLab/ossq-omr`
- source commit: `7a17e45cddc0b7064fc3a179b62caeb57595e993`
- rights: `CC0-1.0`
- renderer: MuseScore 3.6.2, build `3224f34`
- renderer AppImage SHA-256: `c59a41ee88bc7c565a939b9c73498ac0451bbd86574e95cb6e359302c1465290`
- render resolution: 150 DPI
- review-image processing: ImageMagick 6.9.12-98, white `#FFFFFF` background, alpha removed
- review-image validation: `OPAQUE_NONEMPTY_PAGE_V1`
- discovery workflow run: `34883487564`
- review artifact ID: `10363841418`
- artifact ZIP SHA-256: `7815fe6c144e1b85e13c994879ff78aa57c78846be2a8f1f504cb22ea95b6b7d`
- artifact retention: 14 days

The workflow downloads only the five pinned MusicXML sources and the pinned renderer into ephemeral GitHub Actions storage, renders page-one PNG evidence under Xvfb, flattens each PNG onto white, verifies that each image is opaque and neither blank-white nor black, hashes both sides, uploads a temporary review packet, and removes the temporary renderer/corpus bytes. Nothing from this pilot is persisted to Google Drive.

## v1 invalidation

The earlier review artifact `10362957231` is **not authorized for review use**. Its PNGs retained transparency and could appear fully black in dark-mode/iOS previews. v2 explicitly supersedes that review media with reason:

`TRANSPARENT_REVIEW_RENDER_UNREADABLE_ON_DARK_PREVIEW`

The old v1 manifest remains only as historical lineage. It must not be used as human-review evidence or admitted into Teacher-Gold.

## Active v2 pilot records

| ID | Work | MusicXML SHA-256 | Opaque white PNG page-1 SHA-256 |
| --- | --- | --- | --- |
| `ossq_13744399` | Arriaga — String Quartet No.1 in D minor | `e24a5d843693a538896bbbece71130c6a2da66ced35779c4f5295e4893b9fd48` | `858c16667d609d81cce0a9e472688a795c80654c55e8faea003f2b5ae21fcc1e` |
| `ossq_7313978` | Andrée — String Quartet in A major | `a12b23404b4d8d4516e084721298b923a3c1f5621fd84e479b351eee179e7649` | `c5230e2949dc8906d9f4c6b17b4a85cbdd2a1caaae8e20de5b1d272c4714e937` |
| `ossq_7383977` | Arriaga — String Quartet No.3 in E-flat Major | `ae821554999bfc0cb70ad4651106f50b9879e227d44daedc97c0e48e8ddf8ea2` | `c210c4fbd0423790f0833bdc26e3e5c0f0498af0c4f46077a61155c1025f01e8` |
| `ossq_8071278` | Beethoven — String Quartet No.1, Op.18 No.1 | `6350ea0668db7e4773423293df62507987442dc4b313ca0a38e61de92f5a4631` | `d62c2578911b9d9685c841a4a6d1c78dc4a25d9c2075fef619fa9b21e979f76c` |
| `ossq_8454356` | Boccherini — String Quartet in A major, G.213 (Op.39) | `bd04cdd017a1e098e358cf9515253c7d7adf473f06e9087e642e55a820636243` | `f0e748d4adaa67ee5ea26e7cc9b9c111755715b4fff30705959687a529a20235` |

The successful v2 discovery run reported all five outputs as `opaque=true`, with grayscale mean values between approximately `0.933` and `0.957`; the guard rejects all-black and blank-white pages.

## Why these still count as zero Teacher-Gold fixtures

Rights-clear evidence, deterministic hashing, and readable review media are necessary but not sufficient. Every record remains:

- `teacherVerificationStatus=DRAFT`
- `evaluationEligibility=REVIEW_REQUIRED`
- `countTowardTeacherGoldMinimum=false`

The verified registry is not modified by this package. No fixture is admitted until the human review gate confirms the exact v2 rendered evidence and symbolic reference under the Teacher-Gold policy.

## Authority boundaries

This package grants no automatic fixture admission, training authorization, ST-OMR quorum membership, automatic repair/correction, approval/publication capability, or production decision authority. Stage 7 production engines and quorum rules remain unchanged.

## Next gate

Present only the v2 opaque-white review pairs to the teacher/review process. A later, explicit verification record may admit an exact pair only when its human review evidence and required provenance bindings are complete. Verification must not be inferred from `CLEAR_CC0`, a successful render, or a successful CI run.
