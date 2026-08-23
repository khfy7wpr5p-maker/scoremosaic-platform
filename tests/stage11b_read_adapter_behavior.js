const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const context = vm.createContext({window: {}, console});

vm.runInContext(fs.readFileSync(path.join(root, 'prototypes/stage10-ui-application-experience/fixture.js'), 'utf8'), context);
vm.runInContext(fs.readFileSync(path.join(root, 'prototypes/stage11-ui-application-contracts/read-adapter.js'), 'utf8'), context);

const fixture = context.window.ScoreMosaicFixture;
const adapter = context.window.ScoreMosaicLocalReadAdapter;
assert.ok(fixture);
assert.ok(adapter);
assert.equal(adapter.productionAdapter, false);
assert.equal(adapter.authoritative, false);
assert.equal(adapter.networkCapable, false);
assert.equal(adapter.persistent, false);

const request = (kind, overrides = {}) => ({
  schemaVersion: 'scoremosaic-stage11-read-request-v1',
  requestId: `req-${kind}`,
  kind,
  documentId: fixture.document.id,
  revision: fixture.document.revision,
  ...overrides,
});

for (const kind of ['review.read', 'issues.read', 'sourceEvidence.read', 'validation.read']) {
  const response = adapter.read(request(kind));
  assert.equal(response.state, 'success');
  assert.equal(response.kind, kind);
  assert.equal(response.documentId, fixture.document.id);
  assert.equal(response.revision, fixture.document.revision);
  assert.equal(response.error, null);
  assert.ok(Object.isFrozen(response));
  assert.ok(Object.isFrozen(response.data));
}

const issues = adapter.read(request('issues.read'));
assert.equal(issues.data.items.length, fixture.issues.length);
assert.deepEqual(JSON.parse(JSON.stringify(issues.data.counts)), {blocking: 1, warning: 1, info: 1});

const validation = adapter.read(request('validation.read'));
assert.equal(validation.data.authoritative, false);
assert.equal(validation.data.approvalEligible, false);
assert.equal(validation.data.publicationEligible, false);

const unknown = adapter.read(request('dangerous.unknown'));
assert.equal(unknown.state, 'rejected');
assert.equal(unknown.kind, 'unknown');
assert.equal(unknown.data, null);
assert.equal(unknown.error.code, 'REQUEST_KIND_INVALID');

const stale = adapter.read(request('review.read', {revision: 'stale-revision'}));
assert.equal(stale.state, 'rejected');
assert.equal(stale.error.code, 'REVISION_MISMATCH');

const wrongDocument = adapter.read(request('review.read', {documentId: 'other-document'}));
assert.equal(wrongDocument.state, 'rejected');
assert.equal(wrongDocument.error.code, 'DOCUMENT_MISMATCH');

const extraField = adapter.read({...request('review.read'), unexpected: true});
assert.equal(extraField.state, 'rejected');
assert.equal(extraField.error.code, 'REQUEST_SHAPE_INVALID');

console.log('Stage 11-B local read adapter behavior PASS');
