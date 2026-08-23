# ScoreMosaic licensing and asset-governance architecture

Status: **repository policy active; commercial production dependency clearance
not complete**

Current-state contract: `contracts/architecture-current-state-v1.json`

This document records the technical governance boundary. It is not a substitute
for the license texts or deployment-specific legal advice.

## 1. Rights layers

| Layer | Current rule | Commercial path |
|---|---|---|
| First-party software | PolyForm Noncommercial 1.0.0 | Signed commercial agreement |
| First-party prose and identified synthetic assets | CC BY-NC 4.0 | Express signed grant |
| ScoreMosaic brand | Trademark rights reserved | Express written permission |
| External contributions | Contributor retains ownership and grants CLA rights | Licensor can dual-license accepted contribution |
| Third-party code/models/data | Upstream terms only | Upstream compliance or separate upstream license |
| Critical production models/data | Private; all rights reserved unless identified | Asset-specific signed agreement |

`LICENSE-SCOPE.md` is the path-level source of truth. A narrower file-level
notice overrides the general path rule.

## 2. Commercial-use decision boundary

A signed ScoreMosaic agreement can grant rights only in assets the ScoreMosaic
licensor controls. It does not clear the complete runtime automatically.
Commercial production or redistribution requires all of the following:

1. a signed ScoreMosaic commercial agreement for first-party rights;
2. exact deployment and distribution classification;
3. clearance of every included third-party component and model/data asset;
4. a release SBOM and preserved source/notices where required;
5. trademark permission if official branding is requested; and
6. the independent security, accuracy, infrastructure and operations gates.

No repository workflow currently declares commercial production approved.

## 3. Current third-party blockers

The inventory at `third_party/dependency-licenses.json` records exact pinned
Python dependencies and the principal engine/model artifacts. Current blockers
include:

- AGPL: Audiveris, HOMR, PyMuPDF, Ultralytics and Ultralytics-THOP;
- GPL: Clarity-OMR source;
- unverified asset licenses: HOMR ONNX checkpoints and Clarity model weights;
- incomplete production-distribution evidence: operating-system packages,
  bundled artifacts, corresponding source and aggregate notices.

“Blocked” means no production/redistribution approval has been recorded. It
does not assert that every use is prohibited; the exact use must be evaluated
under the upstream terms or replaced/licensed separately.

## 4. Automated controls

`scripts/validate_license_policy.py` and License Policy CI fail when:

- a runtime Python dependency is unpinned or absent from the inventory;
- an inventory entry silently changes version or classification;
- a review-required or strong-copyleft item is marked production/redistribution
  approved without changing the closed policy and evidence;
- required license, notice, trademark, commercial, scope, CLA, contribution,
  or architecture markers disappear; or
- an external pull request lacks exact CLA assent.

The inventory is an engineering gate and audit trail, not an automated legal
opinion. Adding a dependency requires source/provenance review in the same pull
request. Before a release, generate a complete SBOM and archive all required
license texts, notices, source offers/source bundles and model provenance.

## 5. Private asset boundary

Production weights, training datasets, teacher-gold corpora, user documents,
private labels and commercial evaluation evidence must not be committed to the
public repository. Access must use a private asset registry with identity,
least privilege, immutable version/checksum, audit logging, backup policy and
revocation. A public manifest may disclose only safe identifiers and evidence;
it must not embed credentials, private URLs, personal data or the assets.

## 6. Idea and disclosure boundary

Licenses control copyrighted expression and granted rights; they do not create
ownership of abstract ideas or prevent independent development. Patent and
trade-secret strategy must be decided before publishing novel details. Any
future patent-sensitive design should remain private until professional filing
and disclosure advice is completed.
