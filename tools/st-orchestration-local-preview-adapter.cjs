'use strict';

const fs = require('node:fs');
const path = require('node:path');
const {spawnSync} = require('node:child_process');

const ROOT = path.resolve(__dirname, '..');
const CONTRACT_PATH = path.join(ROOT, 'contracts', 'st-orchestration-local-preview-v1.json');
const MAX_INPUT_BYTES = 131072;
const MAX_STDOUT_BYTES = 262144;
const TIMEOUT_MS = 15000;

class LocalPreviewAdapterError extends Error {}

const readContract = () => {
  const contract = JSON.parse(fs.readFileSync(CONTRACT_PATH, 'utf8'));
  if (contract.version !== 'scoremosaic-st-orchestration-local-preview-v1') throw new LocalPreviewAdapterError('contract version drift');
  if (contract.status !== 'H7C_LOCAL_PREVIEW_ACTIVE_PRODUCTION_DISABLED') throw new LocalPreviewAdapterError('H7-C status drift');
  if (contract.target.repository !== 'khfy7wpr5p-maker/ST-Orchestration') throw new LocalPreviewAdapterError('target repository drift');
  if (contract.target.capability !== 'string-seat-ranking-v0') throw new LocalPreviewAdapterError('capability drift');
  if (contract.target.modelFingerprint !== '15cd94722a0ba2724ceea6f450f16a87ef455fa8bc21d4b619f0bda6d880ca14') throw new LocalPreviewAdapterError('model fingerprint drift');
  if (contract.target.abstentionThreshold !== 0.55) throw new LocalPreviewAdapterError('threshold drift');
  const locks = contract.activationLocks;
  for (const key of ['localProcessAdapterActivated', 'localModelInferenceActivated', 'teacherReviewPreviewActivated']) {
    if (locks[key] !== true) throw new LocalPreviewAdapterError(`required local authority closed: ${key}`);
  }
  for (const key of [
    'networkTransportActivated', 'productionCredentialsActivated', 'productionInferenceActivated',
    'canonicalMutationActivated', 'teacherRevisionMutationActivated', 'approvalActivated',
    'publicationActivated', 'stOmrIntegrationActivated', 'postH4RetuningAuthorized',
    'h4RerunAuthorized', 'automaticLearningActivated'
  ]) {
    if (locks[key] !== false) throw new LocalPreviewAdapterError(`forbidden authority opened: ${key}`);
  }
  return contract;
};

const run = (command, args, options = {}) => {
  const result = spawnSync(command, args, {
    cwd: options.cwd,
    encoding: 'utf8',
    shell: false,
    timeout: options.timeout ?? TIMEOUT_MS,
    maxBuffer: options.maxBuffer ?? MAX_STDOUT_BYTES,
    env: options.env ?? process.env,
  });
  if (result.error) throw new LocalPreviewAdapterError(`${command} failed: ${result.error.message}`);
  if (result.status !== 0) {
    const stderr = String(result.stderr || '').slice(0, 2000).trim();
    throw new LocalPreviewAdapterError(`${command} rejected local preview (${result.status}): ${stderr}`);
  }
  return String(result.stdout || '').trim();
};

const assertExactTarget = (stRoot, contract) => {
  if (!stRoot || !path.isAbsolute(stRoot)) throw new LocalPreviewAdapterError('ST_ORCHESTRATION_ROOT must be an absolute path');
  const actual = run('git', ['-C', stRoot, 'rev-parse', 'HEAD'], {timeout: 5000, maxBuffer: 4096});
  if (actual !== contract.target.mainCommit) throw new LocalPreviewAdapterError(`ST-Orchestration HEAD mismatch: ${actual}`);
  const dirty = run('git', ['-C', stRoot, 'status', '--porcelain'], {timeout: 5000, maxBuffer: 16384});
  if (dirty) throw new LocalPreviewAdapterError('ST-Orchestration working tree must be clean for H7-C preview');
  for (const relativePath of [contract.target.contractPath, contract.target.runtimePath, contract.target.cliPath]) {
    const resolved = path.join(stRoot, relativePath);
    if (!fs.existsSync(resolved)) throw new LocalPreviewAdapterError(`required ST-Orchestration path missing: ${relativePath}`);
  }
};

const validateInput = (inputPath, contract) => {
  const stat = fs.statSync(inputPath);
  if (!stat.isFile() || stat.size <= 0 || stat.size > Math.min(MAX_INPUT_BYTES, contract.localProcessBoundary.inputSizeLimitBytes)) {
    throw new LocalPreviewAdapterError('preview input size outside bounded contract');
  }
  const payload = JSON.parse(fs.readFileSync(inputPath, 'utf8'));
  const request = payload.request || {};
  if (request.source_state !== 'validated-preview') throw new LocalPreviewAdapterError('H7-C requires validated-preview source state');
  if (request.capability !== contract.target.capability) throw new LocalPreviewAdapterError('unsupported preview capability');
  if (payload.preview_input_sha256 !== contract.fixtureEvidence.previewInputSha256 && inputPath.endsWith('st-orchestration-local-preview-input-v1.json')) {
    throw new LocalPreviewAdapterError('fixture input fingerprint drift');
  }
  return payload;
};

const validateOutput = (wrapper, input, contract) => {
  if (!wrapper || wrapper.schema_version !== 'st-orchestration.h7c-local-preview-result/v0' || wrapper.local_preview !== true) {
    throw new LocalPreviewAdapterError('ST-Orchestration preview wrapper identity drift');
  }
  if (wrapper.preview_input_sha256 !== input.preview_input_sha256) throw new LocalPreviewAdapterError('preview input binding mismatch');
  const result = wrapper.result || {};
  if (result.integration_request_id !== input.request.integration_request_id) throw new LocalPreviewAdapterError('request identity mismatch');
  if (result.corrected_musicxml_sha256 !== input.request.corrected_musicxml_sha256) throw new LocalPreviewAdapterError('source hash mismatch');
  if (result.capability !== contract.target.capability) throw new LocalPreviewAdapterError('result capability mismatch');
  if (result.candidate_id !== contract.target.modelId || result.model_fingerprint !== contract.target.modelFingerprint) throw new LocalPreviewAdapterError('model identity mismatch');
  if (result.abstention_threshold !== contract.target.abstentionThreshold) throw new LocalPreviewAdapterError('threshold mismatch');
  if (!['proposal', 'abstain', 'unsupported'].includes(result.status)) throw new LocalPreviewAdapterError('unsupported result status');
  if (!Array.isArray(result.alternatives)) throw new LocalPreviewAdapterError('alternatives must be an array');
  if (!result.deterministic_validation || typeof result.deterministic_validation.passed !== 'boolean' || !Array.isArray(result.deterministic_validation.violations)) {
    throw new LocalPreviewAdapterError('deterministic validation missing');
  }
  if (result.status === 'proposal' && result.deterministic_validation.passed !== true) throw new LocalPreviewAdapterError('proposal survived deterministic veto');
  if (!/^[0-9a-f]{64}$/.test(result.result_sha256 || '')) throw new LocalPreviewAdapterError('result SHA-256 invalid');
  return wrapper;
};

const runLocalPreview = ({stRoot, inputPath, pythonBin = process.env.PYTHON_BIN || 'python3'}) => {
  const contract = readContract();
  assertExactTarget(stRoot, contract);
  const resolvedInput = path.resolve(inputPath);
  const input = validateInput(resolvedInput, contract);
  const stdout = run(pythonBin, ['-P', '-m', 'tools.run_h7c_local_preview', '--input', resolvedInput], {
    cwd: stRoot,
    timeout: contract.localProcessBoundary.timeoutMs,
    maxBuffer: contract.localProcessBoundary.stdoutLimitBytes,
    env: {PATH: process.env.PATH || '', PYTHONPATH: stRoot, PYTHONNOUSERSITE: '1'},
  });
  let wrapper;
  try { wrapper = JSON.parse(stdout); } catch (error) { throw new LocalPreviewAdapterError(`invalid JSON from ST-Orchestration: ${error.message}`); }
  return validateOutput(wrapper, input, contract);
};

module.exports = {LocalPreviewAdapterError, readContract, runLocalPreview, validateOutput};
