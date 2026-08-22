# Stage 8-L — Human Approval Handoff Foundation

## Status

Repository/server-only contract foundation. No live route, production identity provider, approval decision, approval record, publication, or score mutation is activated.

## Purpose

Stage 8-L is the last non-authoritative repository slice before a real human teacher approval decision. It converts one exact, freshly revalidated Stage 8-K approval-eligible revision/artifact pair into a purpose-separated handoff packet that may be presented to one exact human approver.

The handoff packet is not an approval. It cannot record approval and cannot publish.

## Trust chain

```text
exact current durable TeacherScoreRevision
  -> exact Stage 8-F corrected MusicXML rebuild
  -> Stage 8-K fresh approval-eligibility recomputation
  -> candidateEligible=true with zero blocking/unresolved issues
  -> purpose-separated approval-handoff authorization
  -> exact approver + revision + artifact + eligibility hash binding
  -> immutable deterministic HumanApprovalHandoffRequest
  -> state=awaiting_human_decision
  -> canPresentForHumanApproval=true
  -> canRecordApproval=false
  -> canPublish=false
  -> [HUMAN AUTHORITY BOUNDARY]
  -> [LOCKED] actual approval decision
  -> [LOCKED] approval record
  -> [LOCKED] publication
```

## Exact bindings

The authorization grant binds:

- one request ID;
- one approver ID;
- exact tenant and job;
- exact review report identity and SHA-256;
- exact base Canonical SHA-256;
- exact current revision ID and SHA-256;
- exact corrected artifact ID and artifact-record SHA-256;
- exact MusicXML SHA-256;
- exact Stage 8-K eligibility-evidence SHA-256;
- the single action `present_for_human_approval`.

The grant is HMAC-SHA256 sealed with a purpose-separated Stage 8-L domain. Its signature is never exposed by `safe_dict()`.

## Freshness and substitution safety

The public handoff builder does not trust caller-supplied eligibility as current authority. It first reruns Stage 8-K from exact scope/store/revision/state/artifact inputs. Therefore:

- a historical revision fails once a newer durable head exists;
- substituted MusicXML bytes fail;
- substituted artifact records fail;
- validation-count changes fail;
- an ineligible candidate cannot receive a handoff grant;
- a grant for another approver or another exact evidence identity fails;
- a wrong signing key fails.

Exact repeated construction from unchanged evidence converges deterministically to one handoff request SHA-256.

## Human boundary

Every Stage 8-L handoff request fixes:

```text
humanDecisionRequired=true
approvalDecision=null
approvalRecordId=null
publicationRecordId=null
canRecordApproval=false
canPublish=false
canMutate=false
canWrite=false
authoritativeTruth=false
```

The only positive capability is `canPresentForHumanApproval=true`.

This is intentional. Stage 8-L prepares evidence for a human decision but does not make, infer, simulate, or persist that decision.

## Explicit non-activation

Stage 8-L does not add:

- an Approve button with server authority;
- a Teacher Review HTTP endpoint;
- production RBAC/session wiring;
- approval persistence;
- an approval signature/record;
- publication eligibility or publication;
- database/object-store providers;
- score mutation;
- audio/MIDI/playback execution.

The existing repository flags remain authoritative:

```text
approval-handoff-foundation-enabled=true
approval-enabled=false
publication-enabled=false
write-api-enabled=false
public-api-enabled=false
production-durable-store-enabled=false
```

## Verification gate

Stage 8-L CI reruns Foundation and Stage 8-A through Stage 8-K regressions before Stage 8-L tests. Stage 8-L adds evidence for:

- deterministic exact-current handoff construction;
- purpose-separated HMAC authorization;
- signature redaction;
- ineligible-candidate rejection;
- wrong-approver rejection;
- wrong-key rejection;
- tampered-grant rejection;
- stale-head rejection;
- corrected-artifact substitution rejection;
- sealed handoff construction;
- activation locks;
- closed JSON schema validation;
- repository diff formatting.

## Stop condition

If Stage 8-L passes and merges, the safe autonomous Teacher Review path has reached the human authority boundary. The next semantic transition is an actual teacher approval decision. That decision must not be generated autonomously on behalf of the teacher.
