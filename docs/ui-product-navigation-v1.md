# ScoreMosaic Product Navigation v1

This note records the approved preview navigation extension within UI Architecture Phase 1.

Primary navigation:

```text
Dashboard
Documents
Upload
Teacher Review
Guitar TAB
```

`Upload` is presentation-only until authenticated API, Safe Intake, object storage, job creation and OMR Gateway runtime evidence exist. The current preview must not submit files.

`Guitar TAB` is a separate downstream derivative workspace. The current preview may show standard-notation context, TAB presentation, fingering options and playability evidence placeholders, but must not call `MusicXML-to-GuitarTab-Engine` from the browser or gain authority over Canonical Score, Teacher Review, approval or publication.

The public GitHub Pages preview remains fixture-only and non-production. Product navigation switching is local browser presentation state only; it creates no server state and performs no network requests.
