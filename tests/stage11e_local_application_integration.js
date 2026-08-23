const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const context = vm.createContext({window: {}, console});
const load = (relative) => vm.runInContext(fs.readFileSync(path.join(root, relative), 'utf8'), context);

load('prototypes/stage10-ui-application-experience/fixture.js');
load('prototypes/stage11-ui-application-contracts/read-adapter.js');
load('prototypes/stage11-ui-application-contracts/edit-intent-adapter.js');
load('prototypes/stage11-ui-application-contracts/application-state.js');
load('prototypes/stage11-ui-application-contracts/local-application.js');

const fixture = context.window.ScoreMosaicFixture;
const application = context.window.ScoreMosaicLocalApplication;
assert.ok(application);
assert.equal(application.productionApplication, false);
assert.equal(application.authoritative, false);
assert.equal(application.networkCapable, false);
assert.equal(application.persistent, false);
assert.equal(application.context.documentId, fixture.document.id);
assert.equal(application.context.revision, fixture.document.revision);

const review = application.read('review.read');
const issues = application.read('issues.read');
const evidence = application.read('sourceEvidence.read');
const validation = application.read('validation.read');
for (const state of [review, issues, evidence, validation]) {
  assert.equal(state.phase, 'ready');
  assert.equal(state.authority.authoritative, false);
  assert.equal(state.authority.canWrite, false);
  assert.ok(Object.isFrozen(state));
  assert.ok(Object.isFrozen(state.data));
}
assert.equal(review.data.label, fixture.document.label);
assert.equal(issues.data.items.length, fixture.issues.length);
assert.equal(evidence.data.regions.length, fixture.issues.length);
assert.equal(validation.data.authoritative, false);
assert.equal(validation.data.approvalEligible, false);
assert.equal(validation.data.publicationEligible, false);

const unknown = application.read('unknown.read');
assert.equal(unknown.phase, 'rejected');
assert.equal(unknown.error.code, 'REQUEST_KIND_INVALID');
assert.equal(unknown.authority.authoritative, false);

const issue = issues.data.items[0];
const edit = application.prepareEditIntent({
  issueId: issue.id,
  target: {...issue.location},
  operation: {type: 'set_dots', value: 1},
  reason: 'local integration fixture',
});
assert.equal(edit.phase, 'ready');
assert.equal(edit.authority.authoritative, false);
assert.equal(edit.data.intentVersion, 'scoremosaic-stage11-local-edit-intent-v1');
assert.equal(edit.data.authority.authoritativeCapability, false);
assert.equal(edit.data.authority.serverAuthorizationIncluded, false);
assert.equal(edit.data.authority.oldValuePreconditionIncluded, false);
assert.equal(edit.data.authority.commandIdentityIncluded, false);
assert.equal(edit.data.authority.networkSubmissionAllowed, false);
assert.equal(edit.data.authority.canCreateScoreEditCommand, false);
assert.equal(edit.data.authority.canCreateRevision, false);
assert.equal(edit.data.authority.canApprove, false);
assert.equal(edit.data.authority.canPublish, false);

const badTarget = application.prepareEditIntent({
  issueId: issue.id,
  target: {...issue.location, measure: issue.location.measure + 1},
  operation: {type: 'set_dots', value: 1},
  reason: null,
});
assert.equal(badTarget.phase, 'rejected');
assert.equal(badTarget.error.code, 'TARGET_MISMATCH');
assert.equal(badTarget.authority.canWrite, false);

console.log('Stage 11-E local application integration PASS');
