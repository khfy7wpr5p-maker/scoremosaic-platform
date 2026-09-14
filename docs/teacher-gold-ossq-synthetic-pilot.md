# Teacher-Gold OSSQ synthetic real-hash pilot

## Status

This package records five rights-clear, reproducible OSSQ-OMR image/symbolic pairs for teacher review. It is **not** Teacher-Gold admission.

- source corpus: `MALerLab/ossq-omr`
- source commit: `7a17e45cddc0b7064fc3a179b62caeb57595e993`
- rights: `CC0-1.0`
- renderer: MuseScore 3.6.2, build `3224f34`
- renderer AppImage SHA-256: `c59a41ee88bc7c565a939b9c73498ac0451bbd86574e95cb6e359302c1465290`
- render resolution: 150 DPI
- discovery workflow run: `34880978800`
- review artifact ID: `10362957231`
- artifact ZIP SHA-256: `1b7c75ebefbf2af0bf043721ee96c42d58d1e69149f1b0ae4809f2ac839ed36f`
- artifact retention: 14 days

The discovery workflow downloaded only the five pinned MusicXML sources and the pinned renderer into ephemeral GitHub Actions storage, rendered page-one PNG evidence under Xvfb, hashed both sides, uploaded a temporary review packet, and removed the temporary renderer/corpus bytes. Nothing from this pilot was persisted to Google Drive.

## Pilot records

| ID | Work | MusicXML SHA-256 | PNG page-1 SHA-256 |
| --- | --- | --- | --- |
| `ossq_13744399` | Arriaga — String Quartet No.1 in D minor | `e24a5d843693a538896bbbece71130c6a2da66ced35779c4f5295e4893b9fd48` | `aaad0862b69b54909ced34bb6513b69b56b5d03038086d907f3e06c9d39c8b67` |
| `ossq_7313978` | Andrée — String Quartet in A major | `a12b23404b4d8d4516e084721298b923a3c1f5621fd84e479b351eee179e7649` | `5c192dcd3c1460b3f7bdb02a824dcefc1f45344ae1bf6461d28480022e6c0958` |
| `ossq_7383977` | Arriaga — String Quartet No.3 in E-flat Major | `ae821554999bfc0cb70ad4651106f50b9879e227d44daedc97c0e48e8ddf8ea2` | `095fe471b012bf7d909f30c348ec48b123219bf64ff48d2049d827103549f6a4` |
| `ossq_8071278` | Beethoven — String Quartet No.1, Op.18 No.1 | `6350ea0668db7e4773423293df62507987442dc4b313ca0a38e61de92f5a4631` | `b87ea167199099d26f303f69d9590874faa22199fceaca18f07ef72693f1547d` |
| `ossq_8454356` | Boccherini — String Quartet in A major, G.213 (Op.39) | `bd04cdd017a1e098e358cf9515253c7d7adf473f06e9087e642e55a820636243` | `f62f0f98380494336fd89854890c7444b9af29e555a9244879e7fbe2cb6e4499` |

## Why these still count as zero Teacher-Gold fixtures

Rights-clear evidence and deterministic hashing are necessary but not sufficient. Every record remains:

- `teacherVerificationStatus=DRAFT`
- `evaluationEligibility=REVIEW_REQUIRED`
- `countTowardTeacherGoldMinimum=false`

The verified registry is not modified by this package. No fixture is admitted until the human review gate confirms the exact rendered evidence and symbolic reference under the Teacher-Gold policy.

## Authority boundaries

This package grants no automatic fixture admission, training authorization, ST-OMR quorum membership, automatic repair/correction, approval/publication capability, or production decision authority. Stage 7 production engines and quorum rules remain unchanged.

## Next gate

Present the five temporary review pairs to the teacher/review process. A later, explicit verification record may admit an exact pair only when its human review evidence and required provenance bindings are complete. Verification must not be inferred from `CLEAR_CC0`, a successful render, or a successful CI run.
