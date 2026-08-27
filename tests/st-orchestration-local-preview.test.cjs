'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const {runLocalPreview, readContract} = require('../tools/st-orchestration-local-preview-adapter.cjs');

const ROOT = path.resolve(__dirname, '..');
const INPUT = path.join(ROOT, 'fixtures', 'h7c', 'st-orchestration-local-preview-input-v1.json');
const GENERATED = path.join(ROOT, 'prototypes', 'stage10-ui-application-experience', 'orchestration-preview-data.js');
const BROWSER_ADAPTER = path.join(ROOT, 'prototypes', 'stage11-ui-application-contracts', 'orchestration-preview-adapter.js');
const UI = path.join(ROOT, 'prototypes', 'stage10-ui-application-experience', 'orchestration-preview-ui.js');
const CSS = path.join(ROOT, 'prototypes', 'stage10-ui-application-experience', 'orchestration-preview.css');
const FIXTURE = path.join(ROOT, 'prototypes', 'stage10-ui-application-experience', 'fixture.js');
const HTML = path.join(ROOT, 'prototypes', 'stage10-ui-application-experience', 'index.html');
const stRoot = process.env.ST_ORCHESTRATION_ROOT;

test('H7-C contract opens local preview only', () => {
  const contract = readContract();
  assert.equal(contract.target.mainCommit, 'f5ee0e605e62c41af86255712941305b2a8c7afb');
  assert.equal(contract.target.modelFingerprint, '15cd94722a0ba2724ceea6f450f16a87ef455fa8bc21d4b619f0bda6d880ca14');
  assert.equal(contract.target.abstentionThreshold, 0.55);
  assert.equal(contract.target.capability, 'string-seat-ranking-v0');
  assert.equal(contract.localProcessBoundary.shellExecutionAllowed, false);
  assert.equal(contract.browserBoundary.browserDirectEngineCallAllowed, false);
  assert.equal(contract.browserBoundary.applyActionExists, false);
  for (const key of ['networkTransportActivated', 'productionCredentialsActivated', 'productionInferenceActivated', 'canonicalMutationActivated', 'teacherRevisionMutationActivated', 'approvalActivated', 'publicationActivated', 'stOmrIntegrationActivated', 'postH4RetuningAuthorized', 'h4RerunAuthorized', 'automaticLearningActivated']) {
    assert.equal(contract.activationLocks[key], false, key);
  }
});

test('real pinned ST-Orchestration local process returns expected bounded proposal', {skip: !stRoot}, () => {
  const wrapper = runLocalPreview({stRoot: path.resolve(stRoot), inputPath: INPUT});
  assert.equal(wrapper.preview_input_sha256, '232896f7af0b1fde5261c6a8a2359ff2e4082574b9b4559d97050d2359c63fdf');
  assert.equal(wrapper.result.status, 'proposal');
  assert.equal(wrapper.result.alternatives[0].instrument, 'violin-1');
  assert.equal(wrapper.result.alternatives[0].confidence, 0.9271937969980509);
  assert.equal(wrapper.result.deterministic_validation.passed, true);
  assert.equal(wrapper.result.result_sha256, '2ee992b14ce19a0a4d326b05b6ad7c737dcf69a973626e207f1ca8fb33f109af');
});

test('committed browser preview data is non-authoritative exact-runtime evidence', () => {
  const source = fs.readFileSync(GENERATED, 'utf8');
  const sandbox = {window: {}, Object, JSON};
  vm.createContext(sandbox);
  vm.runInContext(source, sandbox, {filename: GENERATED});
  const data = sandbox.window.ScoreMosaicOrchestrationPreviewData;
  assert.equal(data.productionArtifact, false);
  assert.equal(data.authoritative, false);
  assert.equal(data.networkCapable, false);
  assert.equal(data.sourceMutationAllowed, false);
  assert.equal(data.teacherRevisionMutationAllowed, false);
  assert.equal(data.target.mainCommit, 'f5ee0e605e62c41af86255712941305b2a8c7afb');
  assert.equal(data.result.result_sha256, '2ee992b14ce19a0a4d326b05b6ad7c737dcf69a973626e207f1ca8fb33f109af');
  assert.equal(data.result.alternatives[0].instrument, 'violin-1');
});

test('browser adapter accepts exact generated evidence as read-only preview', () => {
  const sandbox = {
    window: {
      ScoreMosaicFixture: {
        document: {id: 'fixture-score-001', revision: 'fixture-r3'},
      },
    },
    Object,
    JSON,
    Number,
  };
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(GENERATED, 'utf8'), sandbox, {filename: GENERATED});
  vm.runInContext(fs.readFileSync(BROWSER_ADAPTER, 'utf8'), sandbox, {filename: BROWSER_ADAPTER});
  const adapter = sandbox.window.ScoreMosaicOrchestrationPreviewAdapter;
  assert.equal(adapter.productionAdapter, false);
  assert.equal(adapter.authoritative, false);
  assert.equal(adapter.networkCapable, false);
  assert.equal(adapter.mutationCapable, false);
  assert.equal(adapter.persistent, false);
  const state = adapter.read();
  assert.equal(state.state, 'ready');
  assert.equal(state.error, null);
  assert.equal(state.data.authoritative, false);
  assert.equal(state.data.sourceMutationAllowed, false);
  assert.equal(state.data.teacherRevisionMutationAllowed, false);
  assert.equal(state.data.result.status, 'proposal');
  assert.equal(state.data.result.alternatives[0].instrument, 'violin-1');
});

test('browser preview boundary contains no network, persistence or apply mutation path', () => {
  const source = [BROWSER_ADAPTER, UI, FIXTURE].map((file) => fs.readFileSync(file, 'utf8')).join('\n');
  for (const pattern of [/\bfetch\s*\(/, /XMLHttpRequest/, /WebSocket/, /EventSource/, /localStorage/, /sessionStorage/, /indexedDB/, /document\.cookie/, /\bwindow\.location\b/, /\binnerHTML\b/, /insertAdjacentHTML/, /\beval\s*\(/, /new\s+Function/]) {
    assert.equal(pattern.test(source), false, pattern.toString());
  }
  assert.equal(/apply orchestration|apply suggestion|data-.*apply/i.test(source), false);
  assert.match(source, /sourceMutationAllowed/);
  assert.match(source, /mutationCapable: false/);
});

test('Teacher Review fixture bootstraps only self-hosted preview resources and CSP still blocks connections', () => {
  const fixture = fs.readFileSync(FIXTURE, 'utf8');
  const html = fs.readFileSync(HTML, 'utf8');
  assert.match(fixture, /orchestration-preview-data\.js/);
  assert.match(fixture, /orchestration-preview-adapter\.js/);
  assert.match(fixture, /orchestration-preview-ui\.js/);
  assert.match(fixture, /orchestration-preview\.css/);
  assert.match(html, /connect-src 'none'/);
  assert.match(html, /script-src 'self'/);
  assert.equal(/https?:\/\//.test(fixture), false);
  assert.equal(fs.existsSync(CSS), true);
});

test('generated preview is byte-for-byte reproducible from pinned runtime', {skip: !stRoot}, () => {
  const tmp = path.join(os.tmpdir(), `scoremosaic-h7c-${process.pid}.js`);
  const {spawnSync} = require('node:child_process');
  const result = spawnSync(process.execPath, [path.join(ROOT, 'tools', 'generate-st-orchestration-preview-data.cjs'), tmp], {
    cwd: ROOT,
    encoding: 'utf8',
    shell: false,
    timeout: 20000,
    env: {...process.env, ST_ORCHESTRATION_ROOT: path.resolve(stRoot)},
  });
  try {
    assert.equal(result.status, 0, result.stderr);
    assert.equal(fs.readFileSync(tmp, 'utf8'), fs.readFileSync(GENERATED, 'utf8'));
  } finally {
    if (fs.existsSync(tmp)) fs.unlinkSync(tmp);
  }
});
