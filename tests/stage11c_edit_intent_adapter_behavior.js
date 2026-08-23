const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const context = vm.createContext({window: {}, console});
vm.runInContext(fs.readFileSync(path.join(root, 'prototypes/stage10-ui-application-experience/fixture.js'), 'utf8'), context);
vm.runInContext(fs.readFileSync(path.join(root, 'prototypes/stage11-ui-application-contracts/edit-intent-adapter.js'), 'utf8'), context);

const fixture = context.window.ScoreMosaicFixture;
const adapter = context.window.ScoreMosaicLocalEditIntentAdapter;
assert.ok(adapter);
assert.equal(adapter.productionAdapter, false);
assert.equal(adapter.authoritative, false);
assert.equal(adapter.networkCapable, false);
assert.equal(adapter.persistent, false);

const issue = fixture.issues[0];
const authority = {
  authoritativeCapability: false,
  serverAuthorizationIncluded: false,
  oldValuePreconditionIncluded: false,
  commandIdentityIncluded: false,
  networkSubmissionAllowed: false,
};
const request = (overrides = {}) => ({
  schemaVersion: 'scoremosaic-stage11-edit-intent-request-v1',
  requestId: 'intent-req-001',
  kind: 'editIntent.prepare',
  documentId: fixture.document.id,
  revision: fixture.document.revision,
  issueId: issue.id,
  target: {...issue.location},
  operation: {type: 'set_dots', value: 1},
  reason: 'fixture correction',
  authority: {...authority},
  ...overrides,
});

const success = adapter.prepare(request());
assert.equal(success.state, 'success');
assert.equal(success.error, null);
assert.equal(success.data.intentVersion, 'scoremosaic-stage11-local-edit-intent-v1');
assert.equal(success.data.authority.authoritativeCapability, false);
assert.equal(success.data.authority.serverAuthorizationIncluded, false);
assert.equal(success.data.authority.oldValuePreconditionIncluded, false);
assert.equal(success.data.authority.commandIdentityIncluded, false);
assert.equal(success.data.authority.networkSubmissionAllowed, false);
assert.equal(success.data.authority.canCreateScoreEditCommand, false);
assert.equal(success.data.authority.canCreateRevision, false);
assert.equal(success.data.authority.canApprove, false);
assert.equal(success.data.authority.canPublish, false);
assert.ok(Object.isFrozen(success));
assert.ok(Object.isFrozen(success.data));

const stale = adapter.prepare(request({revision: 'stale'}));
assert.equal(stale.state, 'rejected');
assert.equal(stale.error.code, 'REVISION_MISMATCH');

const wrongTarget = adapter.prepare(request({target: {...issue.location, measure: issue.location.measure + 1}}));
assert.equal(wrongTarget.state, 'rejected');
assert.equal(wrongTarget.error.code, 'TARGET_MISMATCH');

const badOperation = adapter.prepare(request({operation: {type: 'raw_musicxml', value: '<score/>'}}));
assert.equal(badOperation.state, 'rejected');
assert.equal(badOperation.error.code, 'OPERATION_INVALID');

const authorityClaim = adapter.prepare(request({authority: {...authority, serverAuthorizationIncluded: true}}));
assert.equal(authorityClaim.state, 'rejected');
assert.equal(authorityClaim.error.code, 'AUTHORITY_INVALID');

const extraField = adapter.prepare({...request(), commandId: 'forbidden'});
assert.equal(extraField.state, 'rejected');
assert.equal(extraField.error.code, 'REQUEST_SHAPE_INVALID');

console.log('Stage 11-C local edit-intent adapter behavior PASS');
