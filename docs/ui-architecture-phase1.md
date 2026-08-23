# ScoreMosaic UI Architecture Phase 1

Status: **approved unnumbered UI/product-design workstream; repository architecture baseline, Figma next**  
Current architecture state contract: `contracts/architecture-current-state-v1.json`  
UI architecture contract: `contracts/ui-architecture-phase1-v1.json`

UI Architecture Phase 1 is deliberately **not Stage 12**. Stage 5-11 numbering remains unchanged. This workstream sits after the completed Stage 10/11 local UI/application foundations and before any live UI↔API activation.

## 1. Purpose

Build the complete ScoreMosaic product-information architecture and interaction model before high-fidelity visual design. The goal is a coherent user journey from opening the product to reviewing, correcting, validating and explicitly approving a score, while preserving every existing authority boundary.

Phase 1 may change presentation architecture, screen organization, navigation and design-system structure. It does not activate real upload, authentication, production reads/writes, approval execution, publication execution, playback or infrastructure.

## 2. Product hierarchy

```text
ScoreMosaic
├── Dashboard
├── Documents
│   ├── All
│   ├── Processing
│   ├── Needs Review
│   ├── Approved
│   └── Published
├── New Document
├── Review
└── Account

Deferred from Phase 1 primary navigation:
├── Settings
├── Admin
└── Billing
```

The navigation must stay task-oriented. The primary workflow is reviewing musical documents, not exploring analytics.

## 3. Primary user journey

```text
Dashboard
  -> New Document
  -> Input Validation
  -> OMR Processing
  -> Review Ready
  -> Teacher Review
  -> Structured Correction
  -> Validation
  -> Revision
  -> Human Approval
  -> Publication Eligibility
```

The UI must preserve these separations:

```text
Save/Edit != Approve
Approve != Publish
Validation PASS != Approval
Published label != Public visibility
```

## 4. Global application shell

Normal product pages use a global shell:

```text
+----------------------------------------------------------------+
| ScoreMosaic | Dashboard | Documents | Review        Account     |
+----------------------------------------------------------------+
|                                                                |
|                         PAGE CONTENT                           |
|                                                                |
+----------------------------------------------------------------+
```

Teacher Review enters a focused workspace while keeping document/revision context visible.

## 5. Dashboard architecture

Dashboard is action-oriented and intentionally not analytics-heavy.

Required regions:

- `New Document` primary action;
- Needs Review count/summary;
- Processing count/summary;
- Continue Review cards;
- recent document state where useful.

Primary question answered by the dashboard: **What needs my attention now?**

## 6. Documents architecture

The Documents screen is the authoritative product list surface for UI purposes.

Required states:

- All;
- Processing;
- Needs Review;
- Approved;
- Published.

Required interactions:

- search;
- status filter;
- open document/review;
- readable status text plus icon/shape; no color-only meaning.

The browser presentation of a status does not itself create that status.

## 7. New Document / OMR processing UX

Phase 1 defines the **presentation flow only**:

```text
Select PDF/Image
  -> Validating
  -> Preparing
  -> OMR Processing
  -> Building Review
  -> Review Ready
```

Required error states:

- rejected input;
- unsupported/unsafe input;
- processing unavailable;
- processing failed;
- stale/replaced source context where applicable.

Real file upload remains locked. A later live-integration gate must map these states to authenticated server evidence.

## 8. Teacher Review Workspace v1

Teacher Review is the core product workspace.

```text
+----------------------------------------------------------------------------+
| ScoreMosaic | Document | Revision | Validation | Reviewer/Account           |
+--------------+-----------------------------------------+---------------------+
|              |                                         |                     |
| Issues       |              SCORE VIEW                 | Structured Edit     |
|              |                                         |                     |
|              |                                         |                     |
|              +-----------------------------------------+                     |
|              |            SOURCE EVIDENCE              |                     |
+--------------+-----------------------------------------+---------------------+
| Validation / unresolved issues / revision state                              |
+----------------------------------------------------------------------------+
```

Score View remains the largest and primary workspace.

Selecting one issue should synchronize, when evidence exists:

```text
Issue
  -> Score location
  -> Source-evidence location
  -> Structured-edit target
```

No synchronization result grants musical authority.

## 9. Score Viewer interaction architecture

Required interaction vocabulary:

- previous/next page;
- zoom in/out;
- fit width;
- fit page;
- measure focus;
- event/note focus;
- issue overlays;
- selected measure/event indication;
- score↔source synchronization;
- next/previous issue keyboard navigation;
- staff/voice context;
- multi-staff-safe focus behavior.

The renderer is presentation-only. Renderer coordinates, selection state or visual glyph state must never become authoritative score mutation input without stable domain identity and server-side checks.

## 10. Structured Edit architecture

The editor uses bounded musical controls instead of unrestricted MusicXML editing.

Initial local operation families remain consistent with Stage 10/11:

- pitch;
- effective duration;
- dots;
- remove event.

Future operation families such as accidentals, ties, tuplets, staff/voice reassignment, meter, articulations, dynamics or guitar-specific edits require explicit typed contract evolution and regression evidence.

The safe flow is:

```text
Selected domain target
  -> bounded edit fields
  -> local correction preview
  -> editIntent.prepare
  -> [future authenticated server boundary]
  -> ScoreEditCommand
```

`editIntent.prepare` is never presented as an authoritative save.

## 11. Validation and revision architecture

Persistent review status must expose:

- exact current revision identity;
- validation summary;
- blocking issue count;
- unresolved issue count;
- stale/read-only state;
- last accepted change summary where available.

Revision History requires:

- ordered immutable revision list;
- current revision marker;
- change summaries;
- validation state.

A future `Revision Compare` view is allowed without changing revision authority.

## 12. Approval UX

Approval is visually and interactionally separated from editing.

Required approval review evidence:

- exact revision identity;
- blocking issue count;
- validation state;
- corrected MusicXML identity;
- explicit human action.

The approval action should not be embedded as an incidental button inside the Structured Edit panel.

## 13. Publication UX

Publication preparation is a separate state after approval.

The UI must distinguish:

```text
Approved
Publication Eligible
Published
Publicly Visible
```

These states must not be collapsed by visual shorthand. Phase 1 does not execute publication.

## 14. Design System architecture

### Foundations

- color tokens;
- typography scale;
- spacing scale;
- grid/layout rules;
- radius;
- elevation;
- iconography;
- focus-state rules.

### Core components

- Button;
- Input;
- Select;
- Tabs;
- Badge/Status;
- Panel;
- Toolbar;
- Dialog;
- Drawer;
- Toast;
- Empty State;
- Loading State;
- Validation Message.

### Music-domain components

- Issue Card;
- Score Viewer;
- Measure Marker;
- Issue Marker;
- Evidence Viewer;
- Revision Indicator;
- Structured Edit Field.

Design tokens should use semantic names such as `color.status.blocking`, `color.text.primary`, `space.200`, `type.label`, rather than screen-specific names.

## 15. Responsive and accessibility architecture

Desktop is the primary review surface, but all design work must preserve:

- full keyboard reachability;
- visible focus;
- programmatic labels;
- screen-reader-readable status and issue text;
- no color-only semantics;
- reduced-motion behavior;
- high-contrast and forced-colors compatibility;
- scalable text;
- Score View priority on narrow layouts;
- Issues and Structured Edit collapsing into accessible drawers/tabs when necessary;
- Source Evidence switching between adjacent and stacked layouts.

## 16. Future modernization model

UI modernization is expected and supported.

```text
Figma / UX
  -> Design System
  -> UI Components
  -> Typed Application Contract
  -> Adapter
  -> Authenticated API
  -> Server / Domain Authority
```

Change ownership:

| Change | Correct starting layer |
|---|---|
| color, typography, spacing | Design System |
| layout, panel structure, navigation | UI / Figma |
| new data field | Typed Application Contract |
| endpoint/transport change | Adapter/API boundary |
| new mutation/business rule | Server/Domain contract |
| authority/approval/publication rule | Authoritative domain boundary |

Breaking contract changes require versioning and backward-compatibility evidence.

## 17. Figma sequence

After this repository baseline is green, Figma should proceed in this order:

```text
Low-fidelity wireframes
  -> Component system
  -> High-fidelity screens
  -> Clickable prototype
  -> Accessibility/interaction review
  -> Design Freeze v1
```

Recommended Figma pages:

```text
00 — Foundations
01 — Components
02 — Patterns
03 — Dashboard
04 — Documents
05 — Upload & Processing
06 — Teacher Review
07 — Revision
08 — Approval & Publication
09 — Prototype
10 — Archive
```

## 18. Fixed non-activation boundary

UI Architecture Phase 1 does not activate:

- live API;
- real upload;
- Authentik/session/RBAC runtime;
- production artifact reads;
- server writes;
- ScoreEditCommand creation in the browser;
- TeacherScoreRevision creation in the browser;
- approval execution;
- publication execution;
- playback;
- production infrastructure.

## 19. Exit criteria before high-fidelity Figma

Repository Phase 1 baseline is ready for Figma only when:

1. product navigation is explicit;
2. end-to-end user flow is explicit;
3. Dashboard/Documents/New Document/Teacher Review/Revision/Approval/Publication screen responsibilities are explicit;
4. Score Viewer interactions are explicit;
5. Structured Edit authority boundary is explicit;
6. validation/revision semantics are explicit;
7. approval/publication separation is explicit;
8. Design System component taxonomy is explicit;
9. accessibility/responsive requirements are explicit;
10. future modernization/change-governance rules are explicit;
11. Stage 10/11 and production locks remain unchanged;
12. architecture and UI contract CI are green.
