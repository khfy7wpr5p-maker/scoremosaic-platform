# ScoreMosaic Design System Core Components v1

Status: **approved repository component-architecture baseline; Figma implementation locked by current Starter MCP limit**  
Parent foundations: `contracts/design-system-foundations-v1.json`  
Machine-readable component contract: `contracts/design-system-core-components-v1.json`

This package defines the first professional ScoreMosaic component family before any high-fidelity screen work. It is specification-only: no production UI, server behavior, approval/publication authority or live integration is activated.

## 1. Component philosophy

ScoreMosaic components are optimized for a professional music-review workstation:

- compact but not cramped;
- keyboard-first;
- visually restrained;
- explicit status semantics;
- semantic-token driven;
- safe under stale/read-only/error states;
- reusable across Dashboard, Documents and Teacher Review.

A component may express emphasis but never create authority.

```text
Primary button != approval authority
Green status != validation authority
Selected tab != score mutation
Disabled browser control != server authorization
```

## 2. Shared sizing

Visual density can vary while pointer targets stay accessible:

```text
Compact       visual 32 px   hit target >= 44 px
Default       visual 36 px   hit target >= 44 px
Comfortable   visual 40 px   hit target >= 44 px
```

The 44 px hit area may be provided by layout/hit-region structure without making every visible control visually oversized.

## 3. Shared state vocabulary

Reusable components should use a consistent state vocabulary where applicable:

```text
Default
Hover
Focus Visible
Pressed / Open / Selected
Disabled
Loading / Invalid / Read-only (component-specific)
```

Visible focus is mandatory. Hover is supplementary and cannot be the sole action cue.

## 4. Button

Variants:

```text
Primary
Secondary
Ghost
Danger
```

Sizes:

```text
Compact / Default / Comfortable
```

States:

```text
Default / Hover / Focus Visible / Pressed / Disabled / Loading
```

Rules:

- label is required;
- leading/trailing icon optional;
- Primary uses the brand-primary semantic token;
- Primary does **not** mean Approve or Publish;
- Danger uses semantic danger and is reserved for destructive intent;
- Danger styling never bypasses domain confirmation requirements;
- Loading preserves the accessible name and exposes busy state.

## 5. Icon Button

Variants:

```text
Neutral / Ghost / Danger
```

Rules:

- icon uses an instance-swap property in Figma;
- accessible name is mandatory;
- tooltip appears on hover **and keyboard focus**;
- tooltip never replaces the accessible name;
- Selected must include a non-color cue;
- 16/18/20 px icon sizes map to Compact/Default/Comfortable controls.

## 6. Tabs

Variants:

```text
Workspace
Subtle
```

A selected tab requires more than a color change. Use an indicator/shape plus text treatment.

Keyboard behavior:

- Left/Right arrow navigation;
- Home/End navigation;
- roving tabindex;
- predictable focus/selection behavior.

Tab selection is navigation/presentation state. It must not directly mutate musical data.

## 7. Status Badge

Tones:

```text
Neutral
Info
Success
Warning
Danger
Locked
```

Every badge includes readable text. Critical states should also include icon/shape cues.

Examples:

```text
PASS       [icon + PASS]
BLOCKING   [icon + BLOCKING]
LOCKED     [lock icon + LOCKED]
```

A badge reflects an existing state. It cannot create validation PASS, approval, publication or authorization.

## 8. Panel

Variants:

```text
Surface
Muted
Floating
```

Slots:

```text
Header
Body
Footer
```

Panel is non-interactive by default. Interactive cards/panels require a separate pattern so that clickability is not accidentally implied by every surface.

Use semantic borders first; elevation remains restrained.

## 9. Input

Initial types:

```text
Text
Search
Number
```

States:

```text
Default / Hover / Focus Visible / Invalid / Disabled / Read-only
```

Rules:

- visible label is preferred; programmatic equivalent required when visually omitted;
- invalid state includes explicit error text;
- error cannot be color-only;
- search clear action requires its own accessible name;
- local field value is not score authority;
- browser-side validation does not replace server/domain validation.

## 10. Select

Select follows the same size/state model as Input.

Accessibility:

- use native select semantics or an accessible combobox/listbox model;
- Arrow navigation required;
- Escape closes an open popup;
- selected value remains local presentation state until it crosses a typed application intent boundary.

## 11. Toolbar

Variants:

```text
Workspace
Score
Contextual
```

Toolbar rules:

- actions are grouped logically;
- reuse Button and IconButton rather than inventing toolbar-only controls;
- narrow widths use an explicit overflow pattern;
- ambiguous destructive icon-only actions are forbidden;
- all actions remain keyboard reachable;
- toolbar visibility/disabled state never replaces server authorization.

## 12. Figma build order

When Figma MCP access becomes available, build one component family at a time:

```text
Button
  -> validate metadata + screenshot
Icon Button
  -> validate metadata + screenshot
Tabs
  -> validate metadata + screenshot
Status Badge
  -> validate metadata + screenshot
Panel
  -> validate metadata + screenshot
Input
  -> validate metadata + screenshot
Select
  -> validate metadata + screenshot
Toolbar
  -> validate metadata + screenshot
```

Foundations must already exist in Figma before any of these are considered production-quality library components.

## 13. Deferred generic components

The following remain in the overall UI architecture but are intentionally deferred from this first core component package:

- Dialog;
- Drawer;
- Toast;
- Empty State;
- Loading State;
- Validation Message.

## 14. Next music-domain package

After generic atoms are stable, the next component package may define:

- Issue Card;
- Validation Status;
- Revision Indicator;
- Evidence Viewer;
- Structured Edit Field.

These music-domain components must compose the generic core rather than bypass it.

## 15. Current Figma boundary

The current Starter-plan MCP call limit prevents creating or validating the actual Figma component library. Therefore the repository records:

```text
repository specification ready     YES
Figma component library applied    NO
production UI implemented          NO
high-fidelity started              NO
```

No visual implementation is claimed until Figma metadata and screenshot validation can be produced.

## 16. Fixed authority boundary

This component architecture does not activate:

- live API;
- server writes;
- score mutation authority in browser components;
- approval execution;
- publication execution;
- production infrastructure.
