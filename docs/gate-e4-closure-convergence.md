# Gate E.4 — Upload-to-Source Convergence Closure

## Status

Gate E.4 is the bounded external upload-intake **contract/convergence foundation** composed of:

- E.4A — Safe Upload Session Reservation;
- E.4B — Safe Intake Session Finalization;
- E.4C — Immutable Source / Job Binding;
- this E.4A→E.4B→E.4C convergence/regression closure.

This closure does not activate a public upload route, persistence, object-storage writes, queue/worker execution, engine dispatch, or orchestration.

## Closed trust chain

```text
E.3C exact external admission
        |
        v
E.4A Safe Upload Session
        |
        | exact bounded session lineage
        v
E.4B Safe Intake Finalization
        |
        | exact document SHA-256 + Safe Intake evidence
        v
E.4C Immutable Source / Job Binding
        |
        | existing orchestration/lifecycle/Gate D.3 authority only
        v
E.4 closure verifier + convergence regression
```

## Closure invariants

1. Exact replay of one accepted E.4A/E.4B lineage must converge to the same E.4C job, source artifact, storage key, and storage-manifest identity.
2. E.4C evidence is not trusted merely because its individual fields remain structurally valid after construction.
3. Before later consumption, E.4C evidence can be reverified against exact E.4B finalization evidence by independently deriving the authoritative E.4C result again.
4. A valid-shape post-construction source/artifact substitution must fail closed.
5. An E.4C binding derived from one finalization must not verify against a different finalization.
6. E.4C continues to reuse existing orchestration, artifact-lifecycle, and Gate D.3 source-storage authority; this closure creates no parallel storage or job authority model.
7. All E.4 safe evidence remains non-executable evidence. Upload, storage write, persistence, job execution, network dispatch, and orchestration authority flags remain false.

## Security finding closed during convergence

### P2 — E.4C post-construction trust-handoff verification

E.4C decisions are construction-sealed, but Python-level frozen dataclasses can still be modified through low-level mutation such as `object.__setattr__`. Before this closure there was no dedicated later-consumer verifier that compared an E.4C decision against the exact E.4B evidence and freshly re-derived Gate D.3-backed E.4C result.

The closure adds a bounded verifier that:

- requires exact E.4B and E.4C decision types;
- revalidates the supplied E.4C structural contract;
- independently reruns the existing authoritative E.4C derivation from exact E.4B evidence;
- requires the supplied E.4C decision to equal that fresh derivation exactly;
- grants no new authority and performs no persistence or I/O.

This is a convergence correction inside E.4, not a new E.4D micro-gate.

## Operational obligations that remain outside the closed foundation

The contract/convergence foundation does not provide production state by itself. Future runtime work must still supply and verify:

- a stateful E.4A reservation provider that preserves the original immutable session record on replay and never refreshes TTL or widens budgets;
- a stateful E.4B finalization provider that preserves one original finalized document identity per session and rejects same-session/different-document conflicts atomically;
- provider-backed durable state and immutable object storage where separately approved;
- versioned authenticated external route wiring, privacy-safe errors/logs, abuse protection, and production rate/idempotency adapters;
- separately approved orchestration/dispatch activation.

## Exit rule

Gate E.4 may be marked **completed contract/convergence foundation** only when:

- E.4A, E.4B, and E.4C are on `main`;
- focused closure replay/tamper/cross-finalization/no-runtime-authority tests pass;
- all OMR Gateway regression tests pass;
- relevant repository CI is green on the exact closure PR head;
- no unresolved P1/P2 remains in the E.4 closure scope;
- documentation continues to state that the public data plane and runtime activation are disabled.

After E.4 closure, the default next direction is the **minimum staging vertical slice**. No E.4D/E.4E foundation chain should be opened unless a concrete P1/P2 or mandatory trust boundary proves it necessary.
