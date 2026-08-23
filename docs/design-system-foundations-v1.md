# ScoreMosaic Design System Foundations v1

Status: **approved repository design-system foundations baseline for UI Architecture Phase 1**  
Parent UI architecture: `contracts/ui-architecture-phase1-v1.json`  
Brand rules: `contracts/web-brand-rules-v1.json`  
Machine-readable foundations contract: `contracts/design-system-foundations-v1.json`

This baseline turns the approved ScoreMosaic brand direction into reusable UI foundations before high-fidelity screens or production UI integration. It assigns no Stage number and grants no runtime, API, review, approval, publication or infrastructure authority.

## 1. Design direction

The UI should feel like a **professional music workstation**, not a generic SaaS dashboard.

The target character is:

- precise;
- dense but readable;
- restrained;
- tool-oriented;
- music-first;
- evidence-aware;
- calm under complex review states.

Score View remains the visual center of gravity. Brand expression should support the musical workspace rather than compete with it.

## 2. Brand vs. semantic UI color

The approved brand palette is:

```text
Navy    #0B1D3A
Blue    #1D4ED8
Teal    #0EA5A6
Violet  #7C3AED
Green   #22C55E
```

These are identity colors. They do **not** automatically mean success, warning, danger, approval, publication or validation.

Operational status colors remain distinct:

```text
Success       #177A57
Success soft  #E9F6EF
Warning       #966317
Warning soft  #FFF6DF
Danger        #A03945
Danger soft   #FFF0F2
Focus         #315FBD
```

This separation is deliberate. A green tile in the ScoreMosaic logo does not imply PASS. A violet/blue gradient does not imply selected/approved. Status text and shape/icon semantics must remain explicit.

## 3. Neutral foundation

```text
neutral.0    #FFFFFF
neutral.25   #F8FAFC
neutral.50   #F5F7FB
neutral.100  #F1F4F7
neutral.200  #DBE3EC
neutral.300  #C4D0DC
neutral.500  #607086
neutral.700  #334155
neutral.900  #10243E
```

Primary surface mapping:

```text
color.background.canvas        -> neutral.50
color.background.surface       -> neutral.0
color.background.surfaceMuted  -> neutral.25
color.text.primary             -> neutral.900
color.text.secondary           -> neutral.500
color.border.default           -> neutral.200
color.border.strong            -> neutral.300
```

## 4. Brand semantic mapping

```text
color.brand.primary        -> brand.teal
color.brand.secondary      -> brand.blue
color.brand.accentViolet   -> brand.violet
```

The Stage 10 prototype used `#19A7A0` as the primary accent. The design-system baseline migrates future semantic brand-primary usage to the approved brand teal `#0EA5A6`. This is a visual-system migration only; it does not alter any authority or application behavior.

## 5. Typography

Primary UI family: **Inter**.

```text
Display      40 / 48   600
Heading 1    28 / 36   600
Heading 2    20 / 28   600
Title        16 / 24   600
Body         14 / 20   400
Body Strong  14 / 20   600
Label        12 / 16   600
Micro        11 / 16   600
```

The ScoreMosaic wordmark is approved artwork and must not be recreated by simply typing `SCOREMOSAIC` with the UI font.

## 6. Spacing

The canonical spacing scale is:

```text
space.0    0
space.50   4
space.100  8
space.150  12
space.200  16
space.250  20
space.300  24
space.400  32
space.500  40
space.600  48
space.800  64
```

Use the scale consistently instead of local arbitrary gaps.

## 7. Radius

```text
radius.xs       4
radius.sm       8
radius.control  9
radius.md       12
radius.panel    14
radius.pill     999
```

Panels should generally use `radius.panel`. Controls use `radius.control` unless a component requires a more specific semantic shape.

## 8. Elevation

ScoreMosaic should avoid heavy card-stack aesthetics.

Three levels are enough for v1:

```text
elevation.none

elevation.panel
0 8 24 0 #10243E14

elevation.floating
0 14 36 0 #10243E1F
```

Use borders and surface contrast before increasing shadow intensity.

## 9. Focus and interactive sizing

Desktop review is dense, but accessibility remains mandatory.

- visual control heights: 32 / 36 / 40 px;
- minimum pointer hit target: 44 px;
- focus outline: 3 px;
- focus offset: 2 px;
- disabled state cannot be opacity-only;
- hover cannot be the only cue that a control is actionable.

Keyboard navigation must remain first-class in Teacher Review and Score Viewer.

## 10. Layout foundation

Current workspace foundation remains compatible with the Stage 10/11 shell:

```text
App header minimum height  72 px
Workspace gap              14 px
Workspace outer padding    14 px
```

Teacher Review uses the structural model:

```text
Issues | Score + Evidence | Structured Edit
```

The center Score column must remain the largest. On narrow layouts, Score View remains first-priority content while Issues/Edit move to accessible stacked/drawer/tab patterns.

## 11. Iconography

V1 icon direction:

- clean geometric outline;
- filled state only when semantically useful;
- 16 px minimum standalone icon;
- 18 px default toolbar icon;
- every icon-only control requires an accessible name;
- icons cannot be the sole carrier of severity/status meaning.

## 12. Figma token architecture

Figma must use two conceptual levels:

```text
Primitive variables
       ↓ alias
Semantic variables
       ↓ bind
Components
       ↓ compose
Patterns / Screens
```

Required variable behavior:

- primitive variables first;
- semantic colors alias primitives;
- scopes explicitly set;
- Web code syntax attached;
- no `ALL_SCOPES` default leakage;
- no screen-specific token names;
- text styles for the typography scale;
- effect styles for elevation.

Components must not be built as production-quality library components before foundations exist.

## 13. Starter-plan mode policy

The current Figma Starter environment is treated as **Light-only for the first variable baseline**.

This does not remove dark-mode architecture.

Rules:

- Light is the only required mode in v1;
- dark mode remains required later;
- do not fake dark mode by duplicating hardcoded frames;
- when additional modes become available, reuse the same semantic token names and add new values by mode.

## 14. Component readiness order

The first professional component family should be built in this order:

```text
Button
Icon Button
Tabs
Status Badge
Panel
Input
Toolbar
Issue Card
Validation Status
Revision Indicator
```

Generic atoms come before music-domain compositions.

## 15. High-fidelity gate

High-fidelity Teacher Review does not begin merely because colors and typography are documented.

Before high-fidelity:

1. Figma primitive variables exist;
2. Figma semantic aliases exist;
3. variable scopes are explicit;
4. text/effect styles exist;
5. first component family is validated structurally and visually;
6. brand/status semantic separation remains intact;
7. accessibility/focus rules are preserved.

## 16. Fixed non-activation boundary

This foundation work does not activate:

- live API;
- real upload;
- production artifact reads;
- server writes;
- browser ScoreEditCommand creation;
- approval execution;
- publication execution;
- playback;
- production infrastructure.

It is presentation/design-system work only.
