# ScoreMosaic Design System Music-Domain Components v1

Status: **approved repository music-domain component architecture; Figma implementation not yet applied**  
Parent core components: `contracts/design-system-core-components-v1.json`  
Machine-readable contract: `contracts/design-system-music-domain-components-v1.json`

This package defines ScoreMosaic-specific review components on top of the generic core Design System. It is repository specification only. No high-fidelity, live API, server write, approval, publication or production authority is activated.

## 1. Core rule

Music-domain UI presents and coordinates evidence; it does not become musical authority.

```text
visual selection != score mutation
renderer coordinate != stable domain identity
evidence != authoritative truth
validation badge != approval
local edit value != ScoreEditCommand
revision label != revision creation
```

## 2. Issue Card

Required content:
- issue identity;
- severity text;
- summary;
- musical location context.

Optional content:
- engine evidence summary;
- confidence evidence;
- suggested review action.

Selecting an Issue Card may synchronize Score View, Source Evidence and Structured Edit focus. It cannot mutate the score or resolve an issue by presentation state alone.

## 3. Validation Status

States:
`PASS / WARNING / BLOCKING / UNKNOWN / STALE`.

Every displayed state is bound to an exact revision identity. A displayed PASS does not approve a revision and does not create publication eligibility. Local visual recalculation cannot replace authoritative validation.

## 4. Revision Indicator

Required:
- exact revision identity;
- current/historical/stale/read-only text.

Historical revisions must never look current. Staleness is explicit and fail-closed. The component never creates or switches authoritative revisions itself.

## 5. Evidence Viewer

Modes:
- source image;
- engine evidence;
- comparison.

Optional tools include zoom, pan, region highlight, engine toggle and split comparison. Source crops and engine predictions remain evidence only. Viewer pixel coordinates never become mutation identity. Evidence remains tied to exact document/candidate context.

## 6. Structured Edit Field

Initial operation families remain aligned with Stage 10/11:
- pitch;
- effective duration;
- dots;
- remove event.

Every edit field is bound to:
- stable target identity;
- exact revision identity;
- old-value precondition.

The component may show current and proposed values and prepare a local intent. It cannot directly write to the server, create a ScoreEditCommand, create a TeacherScoreRevision or expose raw MusicXML editing.

## 7. Measure Marker and Issue Marker

Markers are navigation/presentation aids. They require stable domain context and accessible descriptions. Selected/severity meaning cannot rely only on color.

Renderer/pixel position is never the identity of a measure or issue. Markers cannot mutate measures or resolve issues.

## 8. Composition patterns

### Issue selection synchronization

```text
Issue Card
  -> Score focus
  -> Evidence focus
  -> Structured Edit target
```

### Revision safety strip

```text
Revision Indicator
+ Validation Status
+ Stale state
```

### Edit inspection

```text
Structured Edit Field
+ Evidence Viewer
+ Validation Status
```

These patterns synchronize presentation only; they do not bypass typed application/server boundaries.

## 9. Figma build gate

When Figma tool access returns:
1. foundations must already exist;
2. core components must already exist;
3. build one music-domain component family at a time;
4. reuse core components instead of duplicating them;
5. validate metadata;
6. validate screenshots;
7. review keyboard/accessibility behavior.

The current Starter MCP call limit prevents claiming these components as built in Figma.

## 10. Fixed non-activation boundary

Current truth:

```text
repository specification ready       YES
Figma music components applied       NO
production components implemented    NO
high-fidelity started                NO
live API/server writes               NO
approval/publication execution       NO
production infrastructure            NO
```
