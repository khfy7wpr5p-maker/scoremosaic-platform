# ScoreMosaic license scope

This file identifies which repository materials are covered by which license.
A public repository is not a waiver of copyright, trademark, patent, contract,
privacy, or third-party rights.

## First-party software — PolyForm Noncommercial 1.0.0

Unless a path contains a more specific notice, first-party source code,
scripts, tests, schemas, contracts, workflows, deployment configuration, and
prototypes authored for ScoreMosaic are licensed under the root `LICENSE`:
PolyForm Noncommercial License 1.0.0.

This is a source-available noncommercial license, not an OSI-approved open
source license. The exact permitted-purpose rules are in `LICENSE`; this
summary does not replace them. Commercial use requires a separate signed
agreement as described in `COMMERCIAL-LICENSE.md`.

## First-party documentation and synthetic research/test assets — CC BY-NC 4.0

First-party prose under `README.md` and `docs/`, and repository-owned
synthetic fixtures, synthetic evaluation data, and test-only model artifacts
under the following paths are licensed under Creative Commons
Attribution-NonCommercial 4.0 International:

- `evaluation/fixed-v1/`
- `services/ensemble-service/tests/fixtures/`
- `services/st-omr-service/fixtures/`
- `services/st-omr-service/models/st-omr-test-*`

License: <https://creativecommons.org/licenses/by-nc/4.0/legalcode>
Attribution: “ScoreMosaic — Copyright 2026 Önder Özüdoğru”.

Machine-readable schemas/contracts and code examples embedded in
documentation remain first-party software under PolyForm Noncommercial when
their software character is material. The more specific file notice controls.

## Private model, training-data, and evaluation assets

Critical production model weights, training datasets, teacher-gold datasets,
real user scores, private evaluation corpora, labels, and commercial tuning
artifacts are not published in this repository. They remain private and all
rights are reserved unless a separate signed license expressly identifies an
asset. No public repository license authorizes access to or use of private
assets.

The checked-in ST-OMR model is a deliberately small test-only synthetic
artifact. Its presence is not release of a production model, training corpus,
real-world accuracy claim, or production authority.

## Third-party materials

Third-party software, model weights, datasets, fonts, media, generated source
material, and packages are excluded from the ScoreMosaic licenses and retain
their own terms. See `NOTICE`, `third_party/dependency-licenses.json`, and each
`services/*/THIRD_PARTY_NOTICES.md`. Where multiple terms apply, you must
satisfy all applicable terms; ScoreMosaic cannot grant rights it does not own.

## User input and generated output

ScoreMosaic claims no ownership of a user’s pre-existing input. Rights in
generated or corrected output depend on applicable law, the user’s input,
human authorship, and third-party rights. No repository license guarantees
that an input or output is free of third-party restrictions.

## Ideas, methods, patents, and confidentiality

Copyright licenses govern protected expression, not abstract ideas, methods,
algorithms, or business concepts. Public disclosure can also affect patent and
trade-secret strategy. Patent filings, confidentiality controls, access
restrictions, and registrations are separate decisions; nothing here promises
patent protection or prevents independent development of an idea.
