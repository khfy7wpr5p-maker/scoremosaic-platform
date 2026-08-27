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

  append(...children) {
    this.children.push(...children);
  }

  setAttribute(name, value) {
    this.attributes[name] = String(value);
  }

  insertAdjacentElement(_position, node) {
    this.inserted = node;
  }
}

const nodeText = (node) => [node.textContent, ...node.children.map((child) => nodeText(child))].filter(Boolean).join(' ');

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

test('ignored Python overlays are rejected before pinned runtime execution', {skip: !stRoot}, () => {
  const root = path.resolve(stRoot);
  const excludePath = path.join(root, '.git', 'info', 'exclude');
  const overlayPath = path.join(root, 'sitecustomize.py');
  const originalExclude = fs.readFileSync(excludePath, 'utf8');
  try {
    fs.writeFileSync(excludePath, `${originalExclude}\n/sitecustomize.py\n`);
    fs.writeFileSync(overlayPath, "raise RuntimeError('ignored overlay executed')\n");
    assert.throws(
      () => runLocalPreview({stRoot: root, inputPath: INPUT}),
      /ignored Python files that could overlay the pinned H7-C runtime/
    );
  } finally {
    if (fs.existsSync(overlayPath)) fs.unlinkSync(overlayPath);
    fs.writeFileSync(excludePath, originalExclude);
  }
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

test('browser adapter fails closed when generated preview evidence is absent', () => {
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
  vm.runInContext(fs.readFileSync(BROWSER_ADAPTER, 'utf8'), sandbox, {filename: BROWSER_ADAPTER});
  const state = sandbox.window.ScoreMosaicOrchestrationPreviewAdapter.read();
  assert.equal(state.state, 'rejected');
  assert.equal(state.data, null);
  assert.equal(state.error.code, 'ORCHESTRATION_PREVIEW_INVALID');
});

test('fixture remains safe in non-DOM VM harnesses', () => {
  const sandbox = {window: {}, Object, JSON};
  vm.createContext(sandbox);
  assert.doesNotThrow(() => vm.runInContext(fs.readFileSync(FIXTURE, 'utf8'), sandbox, {filename: FIXTURE}));
  assert.equal(sandbox.window.ScoreMosaicFixture.productionArtifact, false);
  assert.equal(sandbox.window.ScoreMosaicFixture.authoritativeTruth, false);
});

test('preview bootstrap continues to adapter and UI when generated data is missing', () => {
  const requested = [];
  const document = {
    createElement(tag) {
      return new FakeNode(tag);
    },
    head: {
      append(node) {
        if (!node.src) return;
        requested.push(node.src);
        if (node.src === 'orchestration-preview-data.js') node.onerror();
        else node.onload();
      },
    },
  };
  const sandbox = {window: {}, document, Object, JSON};
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(FIXTURE, 'utf8'), sandbox, {filename: FIXTURE});
  assert.deepEqual(requested, [
    'orchestration-preview-data.js',
    '../stage11-ui-application-contracts/orchestration-preview-adapter.js',
    'orchestration-preview-ui.js',
  ]);
});

test('abstention alternatives remain evidence and are not presented as a recommendation', () => {
  const scorePanel = new FakeNode('section');
  const workspace = new FakeNode('main');
  const document = {
    createElement(tag) {
      return new FakeNode(tag);
    },
    querySelector(selector) {
      if (selector === '.score-panel') return scorePanel;
      if (selector === '#view-teacher-review .workspace') return workspace;
      return null;
    },
  };
  const data = {
    target: {
      capability: 'string-seat-ranking-v0',
      modelId: 'o5c-ossq-anonymous-context-v0',
      modelFingerprint: '15cd94722a0ba2724ceea6f450f16a87ef455fa8bc21d4b619f0bda6d880ca14',
      mainCommit: 'f5ee0e605e62c41af86255712941305b2a8c7afb',
    },
    previewInputSha256: 'a'.repeat(64),
    result: {
      status: 'abstain',
      alternatives: [{instrument: 'violin-1', confidence: 0.91}],
      deterministic_validation: {passed: true, violations: []},
      result_sha256: 'b'.repeat(64),
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
  assert.ok(scorePanel.inserted);
  const text = nodeText(scorePanel.inserted);
  assert.match(text, /Recommendation No proposal/);
  assert.match(text, /Ranked alternatives · evidence only/);
  assert.doesNotMatch(text, /Top suggestion/);
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
