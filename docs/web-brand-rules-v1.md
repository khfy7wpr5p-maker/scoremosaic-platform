# ScoreMosaic Web Brand Rules v1

Status: **approved brand and web-usage baseline for UI Architecture Phase 1**  
Parent UI architecture: `contracts/ui-architecture-phase1-v1.json`  
Machine-readable brand contract: `contracts/web-brand-rules-v1.json`

This document defines how the approved ScoreMosaic mosaic-`M` identity is used in the web product. It does not assign a new Stage number and does not change any musical, review, approval, publication or production authority.

## 1. Brand hierarchy

The master brand is always:

```text
ScoreMosaic
```

`OMR Gateway` is a product/module label, not the master brand.

Approved lockup model:

```text
SCOREMOSAIC
OMR GATEWAY

SCOREMOSAIC
TEACHER REVIEW

SCOREMOSAIC
GUITAR WORKSPACE
```

A module label must never replace `ScoreMosaic` as the brand root.

## 2. Core symbol

The approved identity concept is the mosaic-square `M` symbol.

The symbol represents:

- mosaic composition;
- multiple evidence/data paths converging into one coherent musical result;
- a modular rather than monolithic product architecture;
- a scalable technology/music identity.

The core `M` geometry is preserved across the logo system. Small-size variants may simplify the smallest center tiles for legibility, but must remain recognizably the same brand mark.

## 3. Logo system

### 3.1 Primary Logo

Composition:

```text
[M mosaic symbol]
SCOREMOSAIC
```

No subtitle.

Preferred use:

- landing hero;
- product overview;
- About/brand surfaces;
- large presentation moments.

The primary logo is the default master-brand expression.

### 3.2 Compact Logo

Composition:

```text
[M mosaic symbol]  SCOREMOSAIC
```

Preferred use:

- web navigation;
- application header;
- sidebar header;
- footer;
- narrow horizontal surfaces.

### 3.3 App Icon

Composition:

```text
[ simplified mosaic M ]
inside an approved rounded-square icon master
```

Preferred use:

- favicon;
- PWA icon;
- web app icon;
- small product tile.

The full-detail mosaic mark must not be forced into a size where the center tiles become visually noisy or disappear. Below 32 CSS px, use the dedicated simplified app-symbol master.

### 3.4 Product Lockup

Composition:

```text
[M mosaic symbol]
SCOREMOSAIC
MODULE NAME
```

Examples:

- `OMR Gateway`;
- `Teacher Review`;
- `Guitar Workspace`.

The module label is secondary. `ScoreMosaic` remains visually and semantically the brand.

### 3.5 Monochrome

A one-color version is mandatory for:

- technical documentation;
- printing;
- low-color contexts;
- high-contrast fallback;
- constrained surfaces.

Preferred monochrome ink: `#0B1D3A`. A white/reversed version is also required for dark backgrounds.

## 4. Brand palette

Approved brand palette:

| Token | Hex | Primary role |
|---|---|---|
| Brand Navy | `#0B1D3A` | wordmark, monochrome mark, strong text |
| Brand Blue | `#1D4ED8` | mosaic gradient / accent |
| Brand Teal | `#0EA5A6` | mosaic gradient / accent |
| Brand Violet | `#7C3AED` | mosaic gradient / accent |
| Brand Green | `#22C55E` | mosaic gradient / accent |

The mosaic mark may use the approved blue/violet → teal → green progression.

### Important semantic rule

Brand color is not application authority.

The brand gradient must never be used by itself to mean:

- validation PASS/FAIL;
- approval;
- publication;
- blocking/non-blocking issue severity.

UI status must continue to use explicit status text, icon/shape and semantic status tokens. Color alone is never sufficient.

## 5. Typography

### Product UI

Primary UI type family: **Inter**.

### Wordmark

The `SCOREMOSAIC` wordmark is approved artwork, not ordinary UI text.

Do not recreate the wordmark by simply typing `SCOREMOSAIC` in the UI font. Production logos must use the approved vector artwork/master.

Module labels may use a controlled UI/display type treatment with restrained wide tracking.

## 6. Clear space

Define `x` as one outer mosaic tile width in the active vector logo master.

Minimum clear space:

- Primary Logo: `2x` on all sides;
- Compact Logo: `1.5x` on all sides;
- App Icon: use the safe area encoded in the rounded-square icon master.

No text, border, icon, image detail or unrelated control may enter this protected region.

## 7. Minimum digital size

Initial v1 digital minimums:

| Variant | Minimum |
|---|---:|
| Primary Logo | 160 CSS px wide |
| Compact Logo | 120 CSS px wide |
| Full-detail standalone mosaic M | 32 CSS px wide |
| App/Favicon simplified mark | required below 32 CSS px |

Target favicon exports:

- 16 px;
- 24 px;
- 32 px.

These small-size exports must come from the simplified app-icon master, not from an automatically shrunken full-detail logo.

## 8. Light and dark surfaces

### Light background

Preferred:

- color mosaic symbol;
- navy wordmark.

### Dark background

Preferred:

- approved color symbol only when contrast remains sufficient;
- otherwise monochrome white symbol;
- white/reversed wordmark.

### Busy photography or artwork

Do not place the logo directly on visually noisy material without a dedicated clear surface, overlay or tested contrast treatment.

## 9. Web placement map

```text
Navbar / App Header      -> Compact Logo
Landing Hero             -> Primary Logo
Favicon / PWA            -> App Icon
Module Header            -> Product Lockup
Technical / single-color -> Monochrome
```

### Application shell rule

The regular ScoreMosaic application shell should default to the Compact Logo. Large Primary Logo usage is reserved for brand moments rather than repeated inside dense professional workspaces.

## 10. Module naming architecture

The web UI may grow without changing the master identity:

```text
ScoreMosaic
├── OMR Gateway
├── Teacher Review
├── Guitar Workspace
├── Score Viewer
└── future product modules
```

Module lockups must remain visually related and must not invent independent master brands unless a future explicit brand-governance decision says otherwise.

## 11. Prohibited usage

Do not:

- stretch, squash or distort the mark;
- rotate the logo;
- recolor individual mosaic tiles outside the approved palette/monochrome system;
- make `OMR Gateway` the master brand name;
- place the wordmark on insufficient-contrast backgrounds;
- use the full-detail symbol at sizes where the center mosaic becomes illegible;
- add unapproved glow, bevel, 3D or ornamental effects;
- replace semantic validation/approval/publication status with the brand gradient;
- redraw or re-typeset the wordmark casually in production.

## 12. Asset governance

Before production export, ScoreMosaic requires a versioned vector master for:

- Primary Logo;
- Compact Logo;
- App Icon / simplified small-size mark;
- Product Lockup template;
- Monochrome navy;
- Monochrome white/reverse.

Raster concept/reference artwork is not itself the production master.

Future optical refinement may adjust spacing, tile geometry, wordmark kerning or small-size simplification without changing this brand architecture.

## 13. Relationship to Design System

Brand identity sits above semantic product UI tokens:

```text
Brand Identity
  -> brand palette / logo / wordmark
  -> Design System
      -> semantic surface/text/action/status tokens
      -> components
      -> screens
```

The design system may reference brand colors for accents and selected visual treatments, but application semantics must remain explicit and accessible.

## 14. Non-activation boundary

These brand rules do not activate or modify:

- live API;
- real upload;
- OMR execution authority;
- browser write authority;
- TeacherScoreRevision authority;
- approval execution;
- publication execution;
- production infrastructure.

They are presentation/brand governance only.

## 15. v1 acceptance criteria

Web Brand Rules v1 is satisfied when:

1. `ScoreMosaic` is the only master brand root;
2. Primary Logo has no subtitle;
3. Compact, App Icon, Product Lockup and Monochrome variants are defined;
4. `OMR Gateway` is treated as a module label;
5. brand palette is explicit;
6. small-size simplification is required;
7. clear-space and initial digital-minimum rules are explicit;
8. light/dark and web-placement policies are explicit;
9. prohibited uses are explicit;
10. raster reference art is not mistaken for the production vector master;
11. UI authority/status semantics remain separate from branding.
