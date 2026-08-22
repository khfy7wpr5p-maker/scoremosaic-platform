# Stage 8-F — Corrected MusicXML Derivative and Canonical Round-Trip Gate

## Purpose

Stage 8-F proves a fail-closed derivative path from one exact immutable `TeacherScoreRevision` and its exact `ReviewMusicalState` to deterministic corrected MusicXML.

This stage is not a writable editor, approval endpoint, publication path, or production artifact store.

## Trust chain

```text
exact RevisionScope
  + immutable TeacherScoreRevision
  + exact ReviewMusicalState
    -> revalidate revision/store contract
    -> exact resulting state SHA-256 binding
    -> recompute revision validation report/counts
    -> deterministic MusicXML materialization
    -> generated-XML structural safety validation
    -> Teacher Review provenance-safe Canonical re-normalization
    -> editable-musical semantic round-trip comparison
    -> immutable draft CorrectedMusicXmlArtifact evidence
```

Any failure stops the derivative. Nothing is silently repaired.

## Deterministic MusicXML materialization

The materializer emits uncompressed UTF-8 `score-partwise` MusicXML only. It does not read paths, fetch URLs, extract MXL, execute external programs, invoke a renderer, or use a network.

Per measure it chooses the smallest exact integer `divisions` representable by the bounded LCM of event onset and effective-duration denominators. If the required divisions exceed the contract limit, export fails closed.

The serializer preserves the review-state fields that MusicXML and the current Canonical normalizer can represent deterministically:

- part order/identity;
- measure order/number/implicit state;
- active measure-start time signature;
- event presence/order semantics;
- event onset and effective duration;
- note/rest kind;
- pitch step/alter/octave;
- written type and dots;
- tuplet ratio;
- staff and voice;
- chord membership/order;
- ties;
- guitar string/fret;
- grace state.

Unsupported or ambiguous export states fail closed. Initial v1 examples include unpitched-event presentation, mid-measure time-signature changes, malformed/non-contiguous chord structures, divisions beyond the exact bound, and pitch alterations that cannot be represented as an exact finite MusicXML decimal.

## Structural safety

Generated XML is independently re-parsed through a bounded streaming safety validator before Canonical re-normalization. It rejects:

- empty/oversized output;
- NUL bytes;
- DTD or entity declarations;
- malformed XML;
- roots other than `score-partwise`;
- excessive nesting;
- excessive element or attribute counts.

The safety report is deterministic and its SHA-256 is bound into the corrected artifact record.

## Provenance-safe Canonical re-normalization

The ordinary OMR Canonical normalizer remains restricted to `homr`, `clarity`, and `audiveris` inputs.

Stage 8-F adds a dedicated internal re-normalization adapter that reuses the same Canonical MusicXML parsing and structural-budget implementation while assigning an explicit `teacher-review` source identity. It never labels a teacher-derived artifact as if an OMR engine produced it.

The regenerated `CanonicalScore` is round-trip evidence, not a new machine candidate and not an Ensemble winner.

## Semantic round-trip contract

Exact revision identity is already protected by `revisionSha256` and `stateSha256`. Re-generated XML necessarily produces fresh XML-order event identities/provenance and can renumber remaining events after `remove_event`; those transport identities are therefore not compared as musical truth.

The round-trip contract compares the MusicXML-represented editable semantics listed above. It intentionally excludes:

- event IDs;
- XML source paths/source event indices;
- OMR source identity;
- `xmlOrder` identity;
- `observedDuration`, which is derived validation evidence rather than an edit field;
- `writtenDuration`, which is derived from written type/dots and is not itself an allowlisted Stage 8 edit field.

Both expected and regenerated semantic projections receive deterministic SHA-256 identities. A corrected artifact is produced only if these hashes match exactly.

## Corrected artifact contract

`contracts/corrected-musicxml-artifact-v1.schema.json` binds at minimum:

- tenant/job/reviewer/report scope;
- base Canonical SHA-256;
- exact revision ID/SHA-256;
- exact review-state SHA-256;
- current validation report SHA-256 and issue counts;
- MusicXML SHA-256/byte size/media type;
- safety policy/report SHA-256;
- regenerated Canonical SHA-256;
- round-trip contract and both semantic SHA-256 values;
- immutable draft status.

`approvalEligible=false` and `publicationEligible=false` are constants in Stage 8-F.

## Non-authority boundaries

Stage 8-F does **not**:

- expose corrected MusicXML over HTTP;
- accept browser writes;
- activate the Structured Edit controls;
- persist corrected artifacts to a production object store;
- approve any revision or artifact;
- publish any score;
- activate renderer, cursor, MIDI, audio, or playback authority;
- modify OMR candidates or Stage 7 Canonical artifacts in place.

The service flag remains `corrected-musicxml-materialization-enabled=false`; only the repository foundation flag is enabled because production artifact persistence/transport is not active.

## Exit evidence

Stage 8-F can merge only when exact-head CI proves:

- Stage 8-A through Stage 8-E regressions remain green;
- corrected MusicXML is byte-deterministic across repeated materialization;
- exact revision/state/validation/scope binding;
- hostile XML safety failures are fail closed;
- the ordinary OMR normalizer still rejects `teacher-review` as an engine;
- the dedicated derivative normalizer emits explicit Teacher Review provenance;
- pitch, removal, written-type and representative timeline edits survive semantic round-trip;
- unrepresentable chord/alter structures fail closed;
- corrected artifact JSON schema validates;
- diff formatting is clean;
- no unresolved review thread or incompatible `main` drift exists.

Browser mutation, approval and publication remain locked after this gate.
