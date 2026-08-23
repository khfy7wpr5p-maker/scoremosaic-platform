# ScoreMosaic Design System — Product Patterns v2

Contract: `contracts/design-system-product-patterns-v2.json`  
Supersedes: `scoremosaic-design-system-product-patterns-v1`  
Current architecture state: `contracts/architecture-current-state-v1.json`

Product Patterns v2 versions the product-shell pattern because the approved ScoreMosaic primary navigation changed from the v1 shell to:

```text
Dashboard
Documents
Upload
Teacher Review
Guitar TAB
```

The change is presentation architecture only. It does not activate live upload, API/auth/session, persistence, server write, approval, publication, production infrastructure, or GuitarTab Engine runtime.

## Dashboard

The Dashboard remains action-oriented and must expose:

- new-document/Upload action;
- Needs Review summary;
- Processing summary;
- Continue Review;
- optional Guitar TAB entry only as a downstream workspace entry.

Counts are derived only from the active read model/fixture and cannot create server state.

## Documents

The Documents pattern requires:

- search;
- status filter (`all`, `processing`, `needs_review`, `approved`, `published`);
- open-document action;
- readable status text.

Search/filter state is presentation-only.

## Upload

`Upload` is the product navigation label for the New Document flow. PDF/JPG/JPEG/PNG are presentation types in the disconnected preview. A local selection is not a server upload, and Coolify availability alone never activates upload. Real submission still requires the separately gated authenticated API + Safe Intake + object storage + job/OMR runtime chain.

## Guitar TAB

Guitar TAB is a downstream derivative workspace with these regions:

```text
standard_notation
guitar_tab
fingering_options
position_playability_evidence
```

The browser cannot call the GuitarTab Engine directly. The workspace cannot mutate Canonical Score, create TeacherScoreRevision, approve, or publish. Production-derived TAB continues to require an approved Teacher Review revision and a separately authorized downstream integration.

## Versioning

v1 remains a historical repository baseline and is not rewritten. `contracts/ui-architecture-phase1-v1.json` and the architecture current-state contract point to v2 as the current product-pattern baseline.
