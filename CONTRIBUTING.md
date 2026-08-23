# Contributing to ScoreMosaic

ScoreMosaic welcomes focused contributions consistent with its security and
architecture boundaries. Opening a pull request does not guarantee inclusion.

## Required contributor agreement

Every external contributor must read
[CONTRIBUTOR-LICENSE-AGREEMENT.md](CONTRIBUTOR-LICENSE-AGREEMENT.md) and place
this exact line in the pull-request description:

`CLA: I have read and agree to the ScoreMosaic Contributor License Agreement.`

The repository owner/licensor is exempt for their own contributions. The CLA
check records assent for the pull request; maintainers may request separate
authority evidence for an employer or legal entity.

## Contribution rules

- Keep changes within the declared architecture and production locks.
- Add or update tests and documentation for behavior changes.
- Do not submit secrets, personal/confidential data, real copyrighted scores,
  restricted datasets, or proprietary model weights.
- Identify every copied or generated third-party component, its exact source,
  version/revision, license, notice obligations, and modification status.
- Do not add an unpinned dependency or download. Update
  `third_party/dependency-licenses.json` in the same pull request.
- AGPL/GPL, source-available, noncommercial, custom, or unclear-license
  components require explicit maintainer approval and must remain blocked from
  production until the policy inventory approves that exact use.
- Preserve `NOTICE`, license files, attribution, and third-party notices.

Run the license checks with:

```bash
python scripts/validate_license_policy.py
python -m unittest discover -s tests -p 'test_license_policy.py' -v
```
