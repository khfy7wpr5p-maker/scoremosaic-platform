# ST-OMR Synthetic Symbol Membership Contract

## Status

Phase 23 is implemented on draft PR #28 from verified `main` commit `0e5b46cea1cb64677dc6dd2ec6f7b387030a6e6a`.

## Objective

Validate a closed, versioned and deterministic static repository-owned contract that assigns the Phase 22 synthetic symbols to static synthetic staff and measure records.

This phase validates membership records only. It does not run a producer, perform detection, infer musical meaning or measure accuracy.

## Implemented contract boundary

- closed JSON Schema 2020-12 membership contract
- repository-owned static membership sample and pinned manifest
- stable `staffId`, `measureId` and `symbolId` references
- exact coverage of all source synthetic symbol IDs
- unique and canonically ordered staff, measure and membership records
- bounded integer staff and measure geometry
- measure-to-staff reference and containment checks
- membership-to-staff and optional membership-to-measure consistency checks
- allowed `contracts` root, direct-child, symlink and path-escape enforcement
- raw artifact SHA-256 and canonical SHA-256
- byte-identical repeated validation/canonicalization
- positive and fail-closed negative tests
- dedicated Phase 23 CI plus all historical ST-OMR regression workflows

## Record scope

The membership layer contains only:

- staff geometry
- measure geometry and its staff reference
- symbol-to-staff reference
- optional symbol-to-measure reference

It does not define or imply:

- pitch, duration or voice
- notehead–stem attachment
- beam membership
- chord relations
- reading-order semantics
- notation graph
- musical correctness of the static membership sample

## Fail-closed coverage

- duplicate or non-canonical staff, measure and symbol IDs
- missing or extra source symbol membership
- unknown staff or measure references
- inconsistent measure/staff references
- invalid or non-contained geometry
- nested additional properties
- forbidden pitch or other out-of-scope fields
- changed closed boundary values
- schema or provenance mismatch
- artifact tampering
- outside-root path, wrong root name and symlink
- nondeterministic output

## Fixed exclusions

- no real or trained OMR model or external weights
- no PDF, image or user input
- no symbol-producing model or real symbol detection
- no musical interpretation or accuracy claim
- no MusicXML
- no HTTP upload, inference or model-loading endpoint
- no Gateway or Ensemble integration
- no correction, ranking, winner selection or merge
- no training, self-training, teacher approval or publication
- no network, GPU, persistent storage or production
- no readiness promotion; `/ready` remains 503

## Safety invariants

- `/health` remains 200 and reports the capability as not requested
- `/ready` remains 503
- the Phase 22 static structured symbol contract remains intact
- the Phase 21 repository test model remains outside the service container
- all historical ST-OMR regression tests remain enabled

## Merge policy

PR #28 remains draft until all test and CI runs succeed, review threads are clear, a separate architectural review is complete and explicit merge approval is provided.
