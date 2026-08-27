'use strict';

const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const http = require('node:http');
const os = require('node:os');
const path = require('node:path');
const {spawnSync} = require('node:child_process');
const test = require('node:test');
const vm = require('node:vm');
const {
  StagingPreviewAdapterError,
  readContract,
  validateEndpoint,
  buildSignedRequest,
  validateResult,
  requestStagingPreview,
  toBrowserPreviewData,
} = require('../tools/st-orchestration-staging-preview-adapter.cjs');

const ROOT = path.resolve(__dirname, '..');
const INPUT = path.join(ROOT, 'fixtures', 'h7c', 'st-orchestration-local-preview-input-v1.json');
const LOCAL_DATA = path.join(ROOT, 'prototypes', 'stage10-ui-application-experience', 'orchestration-preview-data.js');
const BROWSER_ADAPTER = path.join(ROOT, 'prototypes', 'stage11-ui-application-contracts', 'orchestration-preview-adapter.js');
const UI = path.join(ROOT, 'prototypes', 'stage10-ui-application-experience', 'orchestration-preview-ui.js');
const SYNTHETIC_TEST_KEY = 'scoremosaic-h7d-ci-noncredential-key-material-32-bytes-minimum';
const liveEndpoint = process.env.ST_ORCHESTRATION_STAGING_ENDPOINT;
const liveSecret = process.env.ST_ORCHESTRATION_STAGING_HMAC_SECRET;
const liveAllowedOrigin = process.env.ST_ORCHESTRATION_STAGING_ALLOWED_ORIGIN;
const allowLoopback = process.env.ST_ORCHESTRATION_ALLOW_LOOPBACK_HTTP_TEST === '1';

const input = () => JSON.parse(fs.readFileSync(INPUT, 'utf8'));
const localPreviewData = () => {
  const sandbox = {window: {}, Object, JSON};
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(LOCAL_DATA, 'utf8'), sandbox, {filename: LOCAL_DATA});
  return JSON.parse(JSON.stringify(sandbox.window.ScoreMosaicOrchestrationPreviewData));
};
const validWrapper = () => {
  const local = localPreviewData();
  return {
    schema_version: 'st-orchestration.h7d-authenticated-staging-result/v0',
    staging_transport: true,
    authenticated: true,
    preview_input_sha256: local.previewInputSha256,
    result: local.result,
  };
};

class FakeNode {
  constructor(tag) {
    this.tag = tag;
    this.className = '';
    this.id = '';
    this.textContent = '';
    this.children = [];
    this.attributes = {};
    this.inserted = null;
  }
  append(...children) { this.children.push(...children); }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  insertAdjacentElement(_position, node) { this.inserted = node; }
}
const nodeText = (node) => [node.textContent, ...node.children.map((child) => nodeText(child))].filter(Boolean).join(' ');

const withHttpServer = async (handler, fn) => {
  const server = http.createServer(handler);
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  try {
    await fn(`http://127.0.0.1:${server.address().port}/`);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
};

test('H7-D ScoreMosaic contract pins exact ST main and keeps production/mutation closed', () => {
  const contract = readContract();
  assert.equal(contract.target.mainCommit, '80b1e925804616d36c2b46c8074e6a608aa7bff4');
  assert.equal(contract.target.h7dContractGitBlobSha, '4f519d5ec978b305db4b670ea64c333460aa4a79');
  assert.equal(contract.target.stagingRuntimeGitBlobSha, '27204251ccd37b96a004e3eba1602959b94caaf6');
  assert.equal(contract.target.stagingCliGitBlobSha, '083936a44136d5edc8b5c07931af0606bfc2bf29');
  assert.equal(contract.target.parentH7cRuntimeGitBlobSha, 'e51c5ed970afcafa2318a2da6177595120a04203');
  assert.equal(contract.target.modelFingerprint, '15cd94722a0ba2724ceea6f450f16a87ef455fa8bc21d4b619f0bda6d880ca14');
  assert.equal(contract.target.abstentionThreshold, 0.55);
  assert.equal(contract.transportBoundary.authenticationScheme, 'hmac-sha256-v1');
  assert.equal(contract.transportBoundary.httpsRequiredForNonLoopback, true);
  assert.equal(contract.transportBoundary.nonLoopbackAllowedOriginPinRequired, true);
  assert.equal(contract.browserBoundary.browserDirectEngineCallAllowed, false);
  assert.equal(contract.browserBoundary.browserReceivesAuthenticationSecret, false);
  assert.equal(contract.browserBoundary.applyActionExists, false);
  for (const key of ['productionCredentialsActivated', 'productionInferenceActivated', 'canonicalMutationActivated', 'teacherRevisionMutationActivated', 'approvalActivated', 'publicationActivated', 'stOmrIntegrationActivated', 'postH4RetuningAuthorized', 'h4RerunAuthorized', 'automaticLearningActivated']) {
    assert.equal(contract.activationLocks[key], false, key);
  }
});

test('endpoint policy requires exact HTTPS origin pin except explicit loopback test harness', () => {
  assert.throws(() => validateEndpoint('https://staging.example.invalid/'), /requires an exact allowed origin pin/);
  assert.equal(
    validateEndpoint('https://staging.example.invalid/', {allowedOrigin: 'https://staging.example.invalid/'}).origin,
    'https://staging.example.invalid'
  );
  assert.throws(
    () => validateEndpoint('https://staging.example.invalid/', {allowedOrigin: 'https://other.example.invalid/'}),
    /does not match the allowed origin pin/
  );
  assert.throws(
    () => validateEndpoint('https://staging.example.invalid/', {allowedOrigin: 'http://staging.example.invalid/'}),
    /allowed staging origin must use HTTPS/
  );
  assert.throws(() => validateEndpoint('http://staging.example.invalid/'), /plain HTTP/);
  assert.throws(() => validateEndpoint('http://127.0.0.1:8081/'), /plain HTTP/);
  assert.equal(validateEndpoint('http://127.0.0.1:8081/', {allowLoopbackHttpForTest: true}).hostname, '127.0.0.1');
  assert.throws(() => validateEndpoint('https://user:pass@staging.example.invalid/'), /credentials/);
  assert.throws(() => validateEndpoint('https://staging.example.invalid/path'), /origin URL/);
  assert.throws(() => validateEndpoint('https://staging.example.invalid/?x=1'), /query\/fragment/);
  assert.throws(() => validateEndpoint('ftp://staging.example.invalid/'), /requires HTTPS/);
});

test('non-loopback request fails closed before network without exact origin pin', () => {
  assert.throws(
    () => requestStagingPreview({endpoint: 'https://staging.example.invalid/', secret: SYNTHETIC_TEST_KEY, input: input()}),
    /requires an exact allowed origin pin/
  );
  assert.throws(
    () => requestStagingPreview({
      endpoint: 'https://staging.example.invalid/',
      allowedOrigin: 'https://other.example.invalid/',
      secret: SYNTHETIC_TEST_KEY,
      input: input(),
    }),
    /does not match the allowed origin pin/
  );
});

test('signed request binds method path timestamp nonce and exact body digest', () => {
  const payload = input();
  const timestamp = 1800000000;
  const nonce = 'ab'.repeat(16);
  const signed = buildSignedRequest(payload, SYNTHETIC_TEST_KEY, {timestamp, nonce});
  const bodyHash = crypto.createHash('sha256').update(signed.body).digest('hex');
  const material = `POST\n/v1/staging/orchestration/preview\n${timestamp}\n${nonce}\n${bodyHash}`;
  const expected = crypto.createHmac('sha256', Buffer.from(SYNTHETIC_TEST_KEY)).update(material).digest('hex');
  assert.equal(signed.headers['X-ScoreMosaic-Key-Id'], 'scoremosaic-staging-v1');
  assert.equal(signed.headers['X-ScoreMosaic-Content-SHA256'], bodyHash);
  assert.equal(signed.headers['X-ScoreMosaic-Signature'], `v1=${expected}`);
  assert.equal(signed.headers['Content-Length'], String(signed.body.length));
  assert.throws(() => buildSignedRequest(payload, 'short', {timestamp, nonce}), /at least 32 bytes/);
  assert.throws(() => buildSignedRequest(payload, SYNTHETIC_TEST_KEY, {timestamp, nonce: 'not-a-nonce'}), /nonce/);
});

test('H7-D result validator preserves request/model/source/deterministic/hash boundaries', () => {
  const payload = input();
  const wrapper = validWrapper();
  const validated = validateResult(wrapper, payload);
  assert.equal(validated.result.status, 'proposal');
  assert.equal(validated.result.alternatives[0].instrument, 'violin-1');
  assert.equal(validated.result.alternatives[0].confidence, 0.9271937969980509);
  assert.equal(validated.result.result_sha256, '2ee992b14ce19a0a4d326b05b6ad7c737dcf69a973626e207f1ca8fb33f109af');

  const wrongSource = validWrapper();
  wrongSource.result.corrected_musicxml_sha256 = '2'.repeat(64);
  assert.throws(() => validateResult(wrongSource, payload), /source hash mismatch/);

  const vetoedProposal = validWrapper();
  vetoedProposal.result.deterministic_validation.passed = false;
  vetoedProposal.result.deterministic_validation.violations = ['synthetic-veto'];
  assert.throws(() => validateResult(vetoedProposal, payload), /invalid proposal/);

  const hashDrift = validWrapper();
  hashDrift.result.result_sha256 = '0'.repeat(64);
  assert.throws(() => validateResult(hashDrift, payload), /result SHA-256 mismatch/);
});

test('validated H7-D staging result becomes browser-safe evidence without endpoint or secret', () => {
  const payload = toBrowserPreviewData(validWrapper(), input());
  assert.equal(payload.schemaVersion, 'scoremosaic-st-orchestration-staging-preview-data-v1');
  assert.equal(payload.transportMode, 'authenticated-staging');
  assert.equal(payload.target.mainCommit, '80b1e925804616d36c2b46c8074e6a608aa7bff4');
  assert.equal(payload.productionArtifact, false);
  assert.equal(payload.authoritative, false);
  assert.equal(payload.networkCapable, false);
  assert.equal(payload.sourceMutationAllowed, false);
  assert.equal(payload.teacherRevisionMutationAllowed, false);
  const serialized = JSON.stringify(payload);
  assert.doesNotMatch(serialized, /ST_ORCHESTRATION_STAGING_HMAC_SECRET|ST_ORCHESTRATION_STAGING_ALLOWED_ORIGIN/);
  assert.doesNotMatch(serialized, /https?:\/\//);
  assert.doesNotMatch(serialized, /scoremosaic-h7d-ci-noncredential/);
});

test('browser presentation adapter accepts exact H7-D evidence but remains network/mutation incapable', () => {
  const data = toBrowserPreviewData(validWrapper(), input());
  const sandbox = {
    window: {
      ScoreMosaicFixture: {document: {id: 'fixture-score-001', revision: 'fixture-r3'}},
      ScoreMosaicOrchestrationPreviewData: data,
    },
    Object,
    JSON,
    Number,
  };
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(BROWSER_ADAPTER, 'utf8'), sandbox, {filename: BROWSER_ADAPTER});
  const adapter = sandbox.window.ScoreMosaicOrchestrationPreviewAdapter;
  assert.equal(adapter.networkCapable, false);
  assert.equal(adapter.mutationCapable, false);
  const state = adapter.read();
  assert.equal(state.state, 'ready');
  assert.equal(state.data.transportMode, 'authenticated-staging');
  assert.equal(state.data.target.mainCommit, '80b1e925804616d36c2b46c8074e6a608aa7bff4');
});

test('browser presentation adapter still accepts immutable H7-C evidence', () => {
  const sandbox = {
    window: {ScoreMosaicFixture: {document: {id: 'fixture-score-001', revision: 'fixture-r3'}}},
    Object,
    JSON,
    Number,
  };
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(LOCAL_DATA, 'utf8'), sandbox, {filename: LOCAL_DATA});
  vm.runInContext(fs.readFileSync(BROWSER_ADAPTER, 'utf8'), sandbox, {filename: BROWSER_ADAPTER});
  const state = sandbox.window.ScoreMosaicOrchestrationPreviewAdapter.read();
  assert.equal(state.state, 'ready');
  assert.equal(state.data.schemaVersion, 'scoremosaic-st-orchestration-local-preview-data-v1');
  assert.equal(state.data.target.mainCommit, 'f5ee0e605e62c41af86255712941305b2a8c7afb');
});

test('Teacher Review labels H7-D evidence as authenticated staging and exposes no apply path', () => {
  const data = toBrowserPreviewData(validWrapper(), input());
  const scorePanel = new FakeNode('section');
  const workspace = new FakeNode('main');
  const document = {
    createElement(tag) { return new FakeNode(tag); },
    querySelector(selector) {
      if (selector === '.score-panel') return scorePanel;
      if (selector === '#view-teacher-review .workspace') return workspace;
      return null;
    },
  };
  const sandbox = {
    window: {
      ScoreMosaicOrchestrationPreviewAdapter: Object.freeze({
        productionAdapter: false,
        authoritative: false,
        networkCapable: false,
        mutationCapable: false,
        read: () => ({state: 'ready', data, error: null}),
      }),
    },
    document,
    Object,
    JSON,
  };
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(UI, 'utf8'), sandbox, {filename: UI});
  const text = nodeText(scorePanel.inserted);
  assert.match(text, /Authenticated staging preview · non-authoritative/);
  assert.match(text, /H7-D has no Apply action/);
  assert.match(text, /Transport authenticated staging/);
  assert.match(text, /browser receives neither the staging endpoint nor its authentication secret/);
  assert.doesNotMatch(text, /Apply orchestration|Apply suggestion/);
});

test('browser H7-D presentation files still contain no network or persistence API', () => {
  const source = [BROWSER_ADAPTER, UI].map((file) => fs.readFileSync(file, 'utf8')).join('\n');
  for (const pattern of [/\bfetch\s*\(/, /XMLHttpRequest/, /WebSocket/, /EventSource/, /localStorage/, /sessionStorage/, /indexedDB/, /document\.cookie/, /\bwindow\.location\b/, /\beval\s*\(/, /new\s+Function/]) {
    assert.equal(pattern.test(source), false, pattern.toString());
  }
});

test('server-side adapter rejects redirects instead of following them', async () => {
  await withHttpServer((request, response) => {
    response.statusCode = 302;
    response.setHeader('Location', 'http://127.0.0.1/elsewhere');
    response.end();
  }, async (endpoint) => {
    await assert.rejects(
      requestStagingPreview({endpoint, secret: SYNTHETIC_TEST_KEY, input: input(), allowLoopbackHttpForTest: true}),
      /rejected request \(302\)/
    );
  });
});

test('server-side adapter rejects oversized staging responses', async () => {
  await withHttpServer((request, response) => {
    request.resume();
    response.statusCode = 200;
    response.setHeader('Content-Type', 'application/json');
    response.write('x'.repeat(262145));
    response.end();
  }, async (endpoint) => {
    await assert.rejects(
      requestStagingPreview({endpoint, secret: SYNTHETIC_TEST_KEY, input: input(), allowLoopbackHttpForTest: true}),
      /response exceeds bounded contract/
    );
  });
});

test('real ST H7-D loopback transport returns exact bounded proposal', {skip: !(liveEndpoint && liveSecret)}, async () => {
  const wrapper = await requestStagingPreview({
    endpoint: liveEndpoint,
    secret: liveSecret,
    input: input(),
    allowLoopbackHttpForTest: allowLoopback,
    allowedOrigin: liveAllowedOrigin,
  });
  assert.equal(wrapper.authenticated, true);
  assert.equal(wrapper.staging_transport, true);
  assert.equal(wrapper.result.status, 'proposal');
  assert.equal(wrapper.result.alternatives[0].instrument, 'violin-1');
  assert.equal(wrapper.result.alternatives[0].confidence, 0.9271937969980509);
  assert.equal(wrapper.result.deterministic_validation.passed, true);
  assert.equal(wrapper.result.result_sha256, '2ee992b14ce19a0a4d326b05b6ad7c737dcf69a973626e207f1ca8fb33f109af');
});

test('real ST H7-D endpoint rejects a wrong staging secret', {skip: !(liveEndpoint && liveSecret)}, async () => {
  await assert.rejects(
    requestStagingPreview({
      endpoint: liveEndpoint,
      secret: 'wrong-scoremosaic-h7d-test-key-material-at-least-32-bytes',
      input: input(),
      allowLoopbackHttpForTest: allowLoopback,
      allowedOrigin: liveAllowedOrigin,
    }),
    /rejected request \(401\)/
  );
});

test('staging generator produces H7-D browser evidence through server-side transport', {skip: !(liveEndpoint && liveSecret)}, () => {
  const tmp = path.join(os.tmpdir(), `scoremosaic-h7d-${process.pid}.js`);
  const result = spawnSync(process.execPath, [path.join(ROOT, 'tools', 'generate-st-orchestration-staging-preview-data.cjs'), tmp], {
    cwd: ROOT,
    encoding: 'utf8',
    shell: false,
    timeout: 20000,
    env: {
      ...process.env,
      ST_ORCHESTRATION_STAGING_ENDPOINT: liveEndpoint,
      ST_ORCHESTRATION_STAGING_HMAC_SECRET: liveSecret,
      ST_ORCHESTRATION_STAGING_ALLOWED_ORIGIN: liveAllowedOrigin || '',
      ST_ORCHESTRATION_ALLOW_LOOPBACK_HTTP_TEST: allowLoopback ? '1' : '0',
    },
  });
  try {
    assert.equal(result.status, 0, result.stderr);
    const sandbox = {window: {}, Object, JSON};
    vm.createContext(sandbox);
    vm.runInContext(fs.readFileSync(tmp, 'utf8'), sandbox, {filename: tmp});
    const data = sandbox.window.ScoreMosaicOrchestrationPreviewData;
    assert.equal(data.schemaVersion, 'scoremosaic-st-orchestration-staging-preview-data-v1');
    assert.equal(data.transportMode, 'authenticated-staging');
    assert.equal(data.networkCapable, false);
    assert.equal(data.target.mainCommit, '80b1e925804616d36c2b46c8074e6a608aa7bff4');
    assert.equal(data.result.alternatives[0].instrument, 'violin-1');
    assert.doesNotMatch(fs.readFileSync(tmp, 'utf8'), /ST_ORCHESTRATION_STAGING_HMAC_SECRET|ST_ORCHESTRATION_STAGING_ALLOWED_ORIGIN|scoremosaic-h7d-ci-noncredential/);
  } finally {
    if (fs.existsSync(tmp)) fs.unlinkSync(tmp);
  }
});
