# Teacher-Gold DoReMi real-hash pilot

Status: **DRAFT / research-only / non-counting**

This pilot proves that ScoreMosaic can acquire real source/gold artifact identity without filling GitHub or Google Drive with corpus blobs. It does **not** claim that the artifacts are Teacher-Gold yet.

## What was proven

A temporary GitHub Actions run downloaded the published DoReMi v1 archive, inspected the archive, paired score images with matching MusicXML score artifacts, computed SHA-256 digests directly from the archive bytes, emitted a small metadata manifest, and deleted the temporary archive.

Observed dataset structure during discovery:

- 5,218 PNG page images;
- 44 MusicXML score files in the published `MusicXML` directory;
- 45 image score keys;
- 43 unique image-to-MusicXML score matches;
- 25 named-repertoire matches after excluding notation-feature exercise fixtures from the pilot selection;
- one unmatched image score key and one ambiguous notation-exercise key, both left unadmitted.

The committed pilot keeps five named-repertoire pairs:

1. Alkan — Posement;
2. Bach — Goldberg Variation 16;
3. Bartók — Mikrokosmos 144;
4. Bartók — Night's Music;
5. Bartók — Solo Violin Sonata, movement 4.

For each pair, `evaluation/polyphonic-teacher-gold-v1/pilots/doremi-v1-repertoire-pilot.json` records:

- exact archive member for the PNG source;
- source SHA-256 and byte size;
- exact archive member for the MusicXML gold candidate;
- gold-candidate SHA-256 and byte size;
- `teacherVerificationStatus=DRAFT`;
- `evaluationEligibility=REVIEW_REQUIRED`;
- `countTowardTeacherGoldMinimum=false`.

## Why the counter remains 0/500

A byte-level source/gold pairing is necessary evidence, but it is not sufficient for Teacher-Gold admission. Before any pilot record can enter the SM-POLY-03 verified registry, a separate qualification step must establish all of the following:

1. evaluation rights are explicitly acceptable for the selected artifact;
2. the PNG page is correctly paired to the intended symbolic score/page scope;
3. the MusicXML is reviewed as an acceptable reference for that scope;
4. a teacher or review panel performs the required verification;
5. the resulting fixture is materialized under the existing benchmark fixture contract with its own metadata SHA-256;
6. only then may a `VERIFIED` + `evaluationAllowed=YES` fixture count toward the 500 minimum.

The current public registry therefore remains truthfully empty and readiness remains `NOT_READY`.

## Storage policy

The DoReMi v1 ZIP was downloaded only into temporary CI storage and removed at the end of the run. The repository stores only code and small metadata. This pilot also does not persist corpus blobs into the user's Google Drive.

This preserves the external storage architecture:

- GitHub = contracts, metadata, hashes, tests and audit evidence;
- external source archives = on-demand source material;
- Google Drive = later small review/verified artifacts when explicitly needed;
- no bulk corpus copy is required to begin qualification.

## Authority locks

The pilot grants none of the following:

- automatic fixture admission;
- teacher verification;
- automatic training authorization;
- engine ranking or winner selection;
- Stage 7 score authority;
- ST-OMR Gateway/quorum membership;
- production decision authority.

The next gate is a teacher-review package for these five records plus a separate artifact-rights decision. Until both are complete, the pilot remains non-counting.
