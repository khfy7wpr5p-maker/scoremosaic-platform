# ScoreMosaic Design System Product Interaction Patterns v1

Status: **approved repository product-pattern architecture; Figma pattern implementation not yet applied**  
Parent music-domain components: `contracts/design-system-music-domain-components-v1.json`  
Machine-readable contract: `contracts/design-system-product-patterns-v1.json`

This package closes the repository-side interaction-pattern architecture needed before professional Figma implementation. It defines how ScoreMosaic screens compose the approved brand, foundations, core components and music-domain components. It grants no live/API/production authority.

## 1. Async state vocabulary

Every asynchronous product surface must be able to represent:

```text
Idle
Loading
Success
Empty
Error
Unavailable
Stale
```

`Empty` is not `Error`; `Unavailable` is not `Empty`; `Stale` must be explicit. The browser must not fabricate server-derived success or completion.

## 2. Application shell

Normal product pages contain:
- Compact ScoreMosaic brand;
- primary navigation;
- current page/document context;
- account context;
- content region.

Teacher Review may enter a focused workspace shell. Navigation state and displayed account identity remain presentation only and do not grant authorization.

## 3. Dashboard

The Dashboard answers one primary question:

> What needs my attention now?

Required patterns:
- New Document action;
- Needs Review summary;
- Processing summary;
- Continue Review.

It should not default to analytics-heavy charts. Counts reflect read-model state only and cannot create or modify document state. Continue Review must resolve an exact document/revision context.

## 4. Documents

Each row presents stable document identity, title, readable status and modified context. Status filters are:

```text
All / Processing / Needs Review / Approved / Published
```

Filtering is presentation-only. `Published` must never be visually collapsed into `Publicly Visible`.

## 5. New Document

The pre-live interaction model supports:

```text
Select input
-> Selected locally
-> Validating
-> Rejected | Processing
-> Review Ready | Failed | Unavailable
```

Current Phase 1 remains presentation-only. Local file selection is not an upload, and local validation is not server safety admission. Real upload remains locked.

## 6. Processing

Progress vocabulary:

```text
Validating
Preparing
OMR Processing
Building Review
Review Ready
```

Completion cannot be fabricated with a timer. Failure does not auto-advance to Ready, and Review Ready does not imply validation PASS or approval.

## 7. Teacher Review Workspace

The workspace composes:

```text
Issues | Score View | Source Evidence | Structured Edit | Validation/Revision
```

Issue selection may synchronize Score, Evidence and Edit focus. Synchronization is presentation-only. A stale workspace becomes read-only. Missing evidence is shown as missing rather than invented.

## 8. Revision History

Required patterns:
- immutable ordered revision list;
- current revision marker;
- change summary;
- validation summary.

Historical revisions never appear current. Compare is read-only. Stale current context fails closed.

## 9. Approval

Approval is visually separated from Structured Edit and must show:
- exact revision identity;
- blocking issue count;
- validation state;
- corrected MusicXML identity.

Validation PASS does not auto-approve. The repository UI pattern itself does not execute approval.

## 10. Publication preparation

UI states remain distinct:

```text
Not Eligible
Eligible
Prepared
Published
Publicly Visible
```

Approval and publication remain separate; Published and Public Visibility remain separate; the actual external publication effect remains behind a later gate.

## 11. Recovery

Read failure:
```text
Error summary -> safe retry if available -> preserve context
```

Stale revision:
```text
Explicit stale banner -> mutation intent disabled -> reload/return to current
```

Processing failure:
```text
Failed step -> readable safe reason -> retry or return
```

Future network unavailability must never be shown as success.

## 12. Responsive patterns

Desktop is primary. Narrow layout priority:

```text
Score View
Issues
Source Evidence
Structured Edit
```

Issues and Structured Edit may become accessible drawers/tabs; Source Evidence may stack. Collapsed surfaces remain keyboard reachable.

## 13. Repository pre-Figma exit

After this contract, repository-side pre-Figma design architecture consists of:

```text
Web Brand Rules           READY
Design Foundations        READY
Core Components           READY
Music-Domain Components   READY
Product Patterns          READY

Figma application         REQUIRED / BLOCKED BY STARTER MCP LIMIT
High Fidelity             LOCKED
```

No high-fidelity readiness may be claimed until the actual Figma variables/styles/components/patterns are built and visually validated.
