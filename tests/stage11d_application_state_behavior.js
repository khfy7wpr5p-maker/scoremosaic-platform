const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const context = vm.createContext({window: {}, console});
vm.runInContext(fs.readFileSync(path.join(root, 'prototypes/stage11-ui-application-contracts/application-state.js'), 'utf8'), context);

const reducer = context.window.ScoreMosaicApplicationState;
assert.ok(reducer);
assert.equal(reducer.authoritative, false);
assert.equal(reducer.networkCapable, false);
assert.equal(reducer.persistent, false);

const request = {
  requestId: 'read-001',
  kind: 'review.read',
  documentId: 'fixture-score-001',
  revision: 'fixture-r3',
};

const idle = reducer.idle();
assert.equal(idle.phase, 'idle');
assert.equal(idle.authority.authoritative, false);
assert.equal(idle.authority.canWrite, false);
assert.equal(idle.authority.canApprove, false);
assert.equal(idle.authority.canPublish, false);
assert.equal(idle.authority.canPlayback, false);

const loading = reducer.begin(request);
assert.equal(loading.phase, 'loading');
assert.equal(loading.requestId, request.requestId);

const success = reducer.settle(loading, {
  schemaVersion: 'scoremosaic-stage11-read-response-v1',
  requestId: request.requestId,
  kind: request.kind,
  state: 'success',
  documentId: request.documentId,
  revision: request.revision,
  data: {label: 'fixture'},
  error: null,
});
assert.equal(success.phase, 'ready');
assert.equal(success.data.label, 'fixture');

const empty = reducer.settle(loading, {
  schemaVersion: 'scoremosaic-stage11-read-response-v1',
  requestId: request.requestId,
  kind: request.kind,
  state: 'empty',
  documentId: request.documentId,
  revision: request.revision,
  data: null,
  error: null,
});
assert.equal(empty.phase, 'empty');

const stale = reducer.settle(loading, {
  schemaVersion: 'scoremosaic-stage11-read-response-v1',
  requestId: request.requestId,
  kind: request.kind,
  state: 'rejected',
  documentId: request.documentId,
  revision: request.revision,
  data: null,
  error: {code: 'REVISION_MISMATCH', message: 'stale', retryable: false},
});
assert.equal(stale.phase, 'rejected');
assert.equal(stale.error.category, 'stale_context');

const unavailable = reducer.settle(loading, {
  schemaVersion: 'scoremosaic-stage11-read-response-v1',
  requestId: request.requestId,
  kind: request.kind,
  state: 'unavailable',
  documentId: request.documentId,
  revision: request.revision,
  data: null,
  error: {code: 'ADAPTER_UNAVAILABLE', message: 'unavailable', retryable: true},
});
assert.equal(unavailable.phase, 'unavailable');
assert.equal(unavailable.error.category, 'unavailable');
assert.equal(unavailable.error.retryable, true);

const mismatch = reducer.settle(loading, {
  schemaVersion: 'scoremosaic-stage11-read-response-v1',
  requestId: 'other-request',
  kind: request.kind,
  state: 'success',
  documentId: request.documentId,
  revision: request.revision,
  data: {label: 'wrong'},
  error: null,
});
assert.equal(mismatch.phase, 'rejected');
assert.equal(mismatch.error.category, 'protocol');
assert.equal(mismatch.error.code, 'RESPONSE_REQUEST_ID_MISMATCH');

const badSuccess = reducer.settle(loading, {
  schemaVersion: 'scoremosaic-stage11-read-response-v1',
  requestId: request.requestId,
  kind: request.kind,
  state: 'success',
  documentId: request.documentId,
  revision: request.revision,
  data: null,
  error: null,
});
assert.equal(badSuccess.phase, 'rejected');
assert.equal(badSuccess.error.code, 'RESPONSE_SUCCESS_INVALID');

const editLoading = reducer.begin({...request, requestId: 'edit-001', kind: 'editIntent.prepare'});
const illegalEmpty = reducer.settle(editLoading, {
  schemaVersion: 'scoremosaic-stage11-edit-intent-response-v1',
  requestId: 'edit-001',
  kind: 'editIntent.prepare',
  state: 'empty',
  documentId: request.documentId,
  revision: request.revision,
  data: null,
  error: null,
});
assert.equal(illegalEmpty.phase, 'rejected');
assert.equal(illegalEmpty.error.code, 'RESPONSE_STATE_INVALID');

console.log('Stage 11-D application state behavior PASS');
