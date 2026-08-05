# ST-OMR Structured Synthetic Symbol Output Contract

## Status

Phase 22 is implemented on draft PR #27 from `main` commit `8796a8896b6868a67ab7812b807578e03485e7c6` on `feature/st-omr-structured-symbol-output-contract`.

This phase validates a **static repository-owned synthetic contract sample**. It does not run a symbol-producing model, perform real symbol detection, interpret music, or measure inference accuracy. Repeated execution means repeated validation and canonicalization of the same pinned static sample only.

## Objective

Define and execute a closed, versioned, deterministic JSON contract for a repository-owned synthetic symbol sample while keeping artifact pinning separate from reusable contract validation.

## Implemented boundary

- closed JSON Schema 2020-12 document with every nested object explicitly defined
- independent manual semantic validator for the same closed contract
- separate repository artifact verifier with allowed-root, direct-child, symlink, path-escape, raw SHA-256, and canonical SHA-256 checks
- repository-owned pinned artifact manifest
- stable symbol IDs and canonical ascending order
- integer coordinate space from 0 through 4096
- integer confidence from 0 through 1000
- static fixture and repository-test-model provenance fields
- byte-identical repeated validation/canonicalization evidence
- positive and fail-closed negative tests
- dedicated Phase 22 CI plus all historical ST-OMR regression suites

## Symbol record scope

Each symbol record contains only:

- symbol type
- bounding box
- confidence

Phase 22 does **not** define or infer:

- staff or measure membership
- notehead–stem attachment
- beam membership
- pitch
- duration
- voice
- chord relation
- reading-order semantics
- notation graph

Those capabilities require separate future phases and are not implied by this contract.

## Schema closure

The JSON Schema independently closes:

- `fixture`
- `model`
- `coordinateSpace`
- every `symbols` item
- every `bbox`
- `boundaries`

Every nested object uses `additionalProperties: false`, explicit `required` fields, bounded types, closed patterns or enums, and fixed false boundary constants. A dependency-free repository contract tool executes this schema in tests and CI. The Python semantic validator applies the same closed rules and additionally enforces canonical symbol ordering and bounding-box containment.

## Repository artifact ownership

General contract validation is not tied to one artifact hash. Repository artifact verification is a separate function that requires:

- an allowed root named `contracts`
- manifest and artifact as direct children
- no symlink
- no path escape
- exact pinned artifact filename
- pinned raw-file SHA-256
- pinned canonical SHA-256
- static repository sample purpose

## Fixed exclusions

- no real or trained OMR model
- no externally sourced model weights
- no symbol-producing model
- no real symbol detection
- no musical interpretation
- no inference accuracy claim
- no PDF, photograph, image, upload, or user file
- no HTTP inference, upload, or model-loading endpoint
- no MusicXML generation
- no Gateway integration
- no Ensemble integration
- no automatic correction, ranking, winner selection, or merge
- no training or self-training
- no teacher approval or publication workflow
- no external network
- no GPU/CUDA
- no persistent storage
- no production deployment
- no readiness promotion; `/ready` remains 503

## Verification requirements

- all ST-OMR unit and regression tests pass
- JSON Schema accepts the canonical sample
- JSON Schema rejects nested extras, unknown symbols, invalid coordinates, invalid confidence, and missing fields
- manual validator rejects duplicate IDs, malformed nested objects, ordering changes, invalid provenance, invalid boundaries, and nondeterminism
- repository verifier rejects outside-root artifacts, path escape, symlinks, wrong root names, and artifact tampering
- `/health` remains 200 and reports the capability as a static sample not requested
- `/ready` remains 503
- all nine CI workflows complete successfully
- PR remains draft until separate architectural re-review and explicit merge approval
