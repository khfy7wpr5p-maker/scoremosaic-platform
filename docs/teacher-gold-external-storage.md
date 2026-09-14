# Teacher-Gold External Storage

## Purpose

The Teacher-Gold corpus is intentionally stored outside the public GitHub repository. GitHub stores contracts, fixture metadata, hashes, provenance and evaluation logic. Large PDF/image/gold assets remain in external storage.

The current external provider is Google Drive. The public repository does **not** publish the user's Drive folder IDs or Drive URLs.

## Logical Drive layout

The external root is expected to contain:

```text
ScoreMosaic_Teacher_Gold/
  00_registry/
  01_imslp/
  02_openscore/
  03_mutopia/
  04_kernscores/
  05_mei/
  06_cpdl/
  07_teacher_verified/
  08_benchmark_outputs/
```

The corresponding public logical mapping is stored in:

`evaluation/polyphonic-teacher-gold-v1/storage-manifest.json`

The root folder is supplied at runtime through:

`SCOREMOSAIC_TEACHER_GOLD_DRIVE_ROOT_ID`

Do not commit the actual environment-variable value to GitHub.

## Current corpus truth

The public Teacher-Gold registry remains empty until real, provenance-checked fixtures are admitted. The current truthful count is therefore:

```text
fixtureCount=0
eligibleVerifiedFixtureCount=0
minimumVerifiedFixtures=500
targetVerifiedFixtures=1000
readiness=NOT_READY
```

No synthetic fixture, unverified external score, inaccessible asset, or license-unclear source may be counted toward the 500-fixture minimum.

## Intake boundary

A future real fixture may be registered only when all of the following are available:

- stable fixture metadata;
- source provenance;
- source SHA-256;
- evaluation permission recorded in license metadata;
- teacher-gold artifact SHA-256;
- teacher or review-panel verification;
- notation/scan classification required by the existing SM-POLY-03 harness.

External source assets can remain source-hosted or Drive-hosted. A source URL alone does not make a fixture verified Teacher-Gold.

## Storage policy

- GitHub is not the corpus blob store.
- The Google Drive root identifier remains private runtime configuration.
- Automatic download is not authorized by this manifest.
- Automatic upload is not authorized by this manifest.
- Corpus storage does not grant production decision authority.
- Teacher corrections do not automatically become training data.
- Training authorization remains a separate explicit field and gate.

## Validation

Validate the public storage manifest without requiring private Drive configuration:

```bash
python scripts/polyphonic_teacher_gold_storage.py
python -m unittest tests.test_teacher_gold_external_storage -v
```

A local or Colab runtime that is explicitly configured with the private Drive root can additionally run:

```bash
python scripts/polyphonic_teacher_gold_storage.py --require-root-binding
```

The validation report confirms the binding exists but never emits the Drive folder ID.

## Next intake step

The next repository task is not bulk downloading. It is to qualify the first small real intake batch and create fixture metadata for sources whose provenance, evaluation permission and gold reference are actually verifiable. Large source files should be downloaded only on demand and deleted from temporary compute after the required benchmark work unless retention is explicitly justified.
