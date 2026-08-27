'use strict';

const crypto = require('node:crypto');
const fs = require('node:fs');
const http = require('node:http');
const https = require('node:https');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');
const CONTRACT_PATH = path.join(ROOT, 'contracts', 'st-orchestration-staging-preview-v1.json');
const ROUTE = '/v1/staging/orchestration/preview';
const KEY_ID = 'scoremosaic-staging-v1';
const MAX_REQUEST_BYTES = 131072;
const MAX_RESPONSE_BYTES = 262144;
const TIMEOUT_MS = 15000;
const SHA256_RE = /^[0-9a-f]{64}$/;
const NONCE_RE = /^[0-9a-f]{32}$/;
const ALLOWED_INSTRUMENTS = new Set(['violin-1', 'violin-2', 'viola', 'cello']);

class StagingPreviewAdapterError extends Error {}

const deepCopy = (value) => JSON.parse(JSON.stringify(value));
const freezeDeep = (value) => {
  if (value && typeof value === 'object' && !Object.isFrozen(value)) {
    Object.freeze(value);
    Object.keys(value).forEach((key) => freezeDeep(value[key]));
  }
  return value;
};

const canonicalize = (value) => {
  if (Array.isArray(value)) return value.map(canonicalize);
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonicalize(value[key])]));
  }
  return value;
};

const sha256 = (bytes) => crypto.createHash('sha256').update(bytes).digest('hex');
const canonicalSha256 = (value) => sha256(Buffer.from(JSON.stringify(canonicalize(value)), 'utf8'));

const readContract = () => {
  const contract = JSON.parse(fs.readFileSync(CONTRACT_PATH, 'utf8'));
  if (contract.version !== 'scoremosaic-st-orchestration-staging-preview-v1') throw new StagingPreviewAdapterError('contract version drift');
  if (contract.status !== 'H7D_AUTHENTICATED_STAGING_ACTIVE_PRODUCTION_DISABLED') throw new StagingPreviewAdapterError('H7-D status drift');
  const target = contract.target || {};
  if (target.repository !== 'khfy7wpr5p-maker/ST-Orchestration') throw new StagingPreviewAdapterError('target repository drift');
  if (target.mainCommit !== '80b1e925804616d36c2b46c8074e6a608aa7bff4') throw new StagingPreviewAdapterError('target ST main drift');
  if (target.h7dContractGitBlobSha !== '4f519d5ec978b305db4b670ea64c333460aa4a79') throw new StagingPreviewAdapterError('H7-D contract blob drift');
  if (target.stagingRuntimeGitBlobSha !== '27204251ccd37b96a004e3eba1602959b94caaf6') throw new StagingPreviewAdapterError('H7-D runtime blob drift');
  if (target.stagingCliGitBlobSha !== '083936a44136d5edc8b5c07931af0606bfc2bf29') throw new StagingPreviewAdapterError('H7-D CLI blob drift');
  if (target.parentH7cContractGitBlobSha !== '1392bb3cb929620dc8645af4b2a808e99c338e91') throw new StagingPreviewAdapterError('parent H7-C contract blob drift');
  if (target.parentH7cRuntimeGitBlobSha !== 'e51c5ed970afcafa2318a2da6177595120a04203') throw new StagingPreviewAdapterError('parent H7-C runtime blob drift');
  if (target.modelId !== 'o5c-ossq-anonymous-context-v0') throw new StagingPreviewAdapterError('model id drift');
  if (target.modelFingerprint !== '15cd94722a0ba2724ceea6f450f16a87ef455fa8bc21d4b619f0bda6d880ca14') throw new StagingPreviewAdapterError('model fingerprint drift');
  if (target.abstentionThreshold !== 0.55 || target.capability !== 'string-seat-ranking-v0') throw new StagingPreviewAdapterError('model contract drift');
  const transport = contract.transportBoundary || {};
  if (transport.route !== ROUTE || transport.authenticationScheme !== 'hmac-sha256-v1' || transport.keyId !== KEY_ID) throw new StagingPreviewAdapterError('transport identity drift');
  if (transport.minimumSecretBytes !== 32 || transport.maximumClockSkewSeconds !== 300) throw new StagingPreviewAdapterError('authentication limits drift');
  if (transport.requestSizeLimitBytes !== MAX_REQUEST_BYTES || transport.responseSizeLimitBytes !== MAX_RESPONSE_BYTES || transport.timeoutMs !== TIMEOUT_MS) throw new StagingPreviewAdapterError('transport bounds drift');
  if (
    transport.httpsRequiredForNonLoopback !== true
    || transport.nonLoopbackAllowedOriginPinRequired !== true
    || transport.loopbackHttpAllowedForExplicitTestHarnessOnly !== true
    || transport.redirectsAllowed !== false
    || transport.endpointCredentialsInUrlAllowed !== false
    || transport.endpointQueryOrFragmentAllowed !== false
    || transport.realCredentialMayBeCommitted !== false
    || transport.externalStagingDeploymentProvisionedByRepository !== false
  ) {
    throw new StagingPreviewAdapterError('transport safety boundary drift');
  }
  const browser = contract.browserBoundary || {};
  for (const key of ['browserDirectEngineCallAllowed', 'browserNetworkTransportAllowed', 'browserReceivesAuthenticationSecret', 'browserReceivesStagingEndpoint', 'previewIsAuthoritativeMusicalTruth', 'previewMayMutateCanonicalScore', 'previewMayCreateOrOverwriteTeacherRevision', 'previewMayApprove', 'previewMayPublish', 'previewMayAutomaticallyTrain', 'applyActionExists']) {
    if (browser[key] !== false) throw new StagingPreviewAdapterError(`browser authority opened: ${key}`);
  }
  const locks = contract.activationLocks || {};
  for (const key of ['serverSideStagingAdapterActivated', 'authenticatedStagingTransportActivated', 'stagingModelInferenceActivated', 'teacherReviewPreviewActivated']) {
    if (locks[key] !== true) throw new StagingPreviewAdapterError(`required staging authority closed: ${key}`);
  }
  for (const key of ['browserDirectEngineCallActivated', 'browserNetworkTransportActivated', 'productionCredentialsActivated', 'productionInferenceActivated', 'canonicalMutationActivated', 'teacherRevisionMutationActivated', 'approvalActivated', 'publicationActivated', 'stOmrIntegrationActivated', 'postH4RetuningAuthorized', 'h4RerunAuthorized', 'automaticLearningActivated']) {
    if (locks[key] !== false) throw new StagingPreviewAdapterError(`forbidden staging authority opened: ${key}`);
  }
  return contract;
};

const normalizeSecret = (secret) => {
  let bytes;
  if (Buffer.isBuffer(secret)) bytes = Buffer.from(secret);
  else if (typeof secret === 'string') bytes = Buffer.from(secret, 'utf8');
  else throw new StagingPreviewAdapterError('staging HMAC secret must be a string or Buffer');
  if (bytes.length < 32) throw new StagingPreviewAdapterError('staging HMAC secret must contain at least 32 bytes');
  return bytes;
};

const isLoopback = (hostname) => ['127.0.0.1', '::1', '[::1]', 'localhost'].includes(hostname);

const parseAllowedOrigin = (allowedOrigin) => {
  if (typeof allowedOrigin !== 'string' || allowedOrigin.trim() === '') {
    throw new StagingPreviewAdapterError('non-loopback staging endpoint requires an exact allowed origin pin');
  }
  let pinned;
  try { pinned = new URL(allowedOrigin); }
  catch (error) { throw new StagingPreviewAdapterError(`invalid allowed staging origin: ${error.message}`); }
  if (pinned.username || pinned.password) throw new StagingPreviewAdapterError('allowed staging origin credentials are forbidden');
  if (pinned.search || pinned.hash) throw new StagingPreviewAdapterError('allowed staging origin query/fragment is forbidden');
  if (pinned.pathname !== '/') throw new StagingPreviewAdapterError('allowed staging origin must not contain a path');
  if (pinned.protocol !== 'https:') throw new StagingPreviewAdapterError('allowed staging origin must use HTTPS');
  return pinned;
};

const validateEndpoint = (endpoint, {allowLoopbackHttpForTest = false, allowedOrigin} = {}) => {
  let url;
  try { url = new URL(endpoint); } catch (error) { throw new StagingPreviewAdapterError(`invalid staging endpoint: ${error.message}`); }
  if (url.username || url.password) throw new StagingPreviewAdapterError('staging endpoint credentials in URL are forbidden');
  if (url.search || url.hash) throw new StagingPreviewAdapterError('staging endpoint query/fragment is forbidden');
  if (url.pathname !== '/') throw new StagingPreviewAdapterError('staging endpoint must be an origin URL without a path');
  if (url.protocol === 'http:') {
    if (!allowLoopbackHttpForTest || !isLoopback(url.hostname)) throw new StagingPreviewAdapterError('plain HTTP is allowed only for an explicit loopback test harness');
  } else if (url.protocol === 'https:') {
    if (!isLoopback(url.hostname)) {
      const pinned = parseAllowedOrigin(allowedOrigin);
      if (pinned.origin !== url.origin) throw new StagingPreviewAdapterError('staging endpoint origin does not match the allowed origin pin');
    }
  } else {
    throw new StagingPreviewAdapterError('non-loopback staging transport requires HTTPS');
  }
  return url;
};

const validateInput = (input, contract = readContract()) => {
  if (!input || typeof input !== 'object' || Array.isArray(input)) throw new StagingPreviewAdapterError('preview input must be an object');
  const encoded = Buffer.from(JSON.stringify(input), 'utf8');
  if (encoded.length <= 0 || encoded.length > Math.min(MAX_REQUEST_BYTES, contract.transportBoundary.requestSizeLimitBytes)) throw new StagingPreviewAdapterError('preview input size outside bounded contract');
  const request = input.request || {};
  for (const key of ['integration_request_id', 'document_id', 'canonical_score_id', 'teacher_revision_id', 'corrected_musicxml_sha256', 'source_state', 'capability']) {
    if (typeof request[key] !== 'string' || request[key].length === 0) throw new StagingPreviewAdapterError(`missing request identity: ${key}`);
  }
  if (request.source_state !== 'validated-preview') throw new StagingPreviewAdapterError('H7-D admits validated-preview source state only');
  if (request.capability !== contract.target.capability) throw new StagingPreviewAdapterError('unsupported staging capability');
  if (!SHA256_RE.test(request.corrected_musicxml_sha256)) throw new StagingPreviewAdapterError('corrected MusicXML SHA-256 invalid');
  if (!SHA256_RE.test(input.preview_input_sha256 || '')) throw new StagingPreviewAdapterError('preview input SHA-256 invalid');
  if (!Array.isArray(input.line_events) || !Array.isArray(input.context_lines) || input.context_lines.length !== 3) throw new StagingPreviewAdapterError('bounded symbolic preview material missing');
  return deepCopy(input);
};

const buildSignedRequest = (input, secret, {timestamp = Math.floor(Date.now() / 1000), nonce = crypto.randomBytes(16).toString('hex')} = {}) => {
  const body = Buffer.from(JSON.stringify(input), 'utf8');
  const secretBytes = normalizeSecret(secret);
  if (!Number.isSafeInteger(timestamp) || timestamp < 0) throw new StagingPreviewAdapterError('invalid staging timestamp');
  if (!NONCE_RE.test(nonce)) throw new StagingPreviewAdapterError('nonce must be 16 random bytes encoded as lowercase hex');
  const bodySha256 = sha256(body);
  const material = Buffer.from(`POST\n${ROUTE}\n${timestamp}\n${nonce}\n${bodySha256}`, 'utf8');
  const signature = crypto.createHmac('sha256', secretBytes).update(material).digest('hex');
  return {
    body,
    headers: {
      'Content-Type': 'application/json',
      'Content-Length': String(body.length),
      'X-ScoreMosaic-Key-Id': KEY_ID,
      'X-ScoreMosaic-Timestamp': String(timestamp),
      'X-ScoreMosaic-Nonce': nonce,
      'X-ScoreMosaic-Content-SHA256': bodySha256,
      'X-ScoreMosaic-Signature': `v1=${signature}`,
      'Accept': 'application/json',
    },
  };
};

const validateResult = (wrapper, input, contract = readContract()) => {
  if (!wrapper || typeof wrapper !== 'object' || Array.isArray(wrapper)) throw new StagingPreviewAdapterError('staging result wrapper missing');
  const wrapperKeys = Object.keys(wrapper).sort();
  const expectedWrapperKeys = ['authenticated', 'preview_input_sha256', 'result', 'schema_version', 'staging_transport'];
  if (JSON.stringify(wrapperKeys) !== JSON.stringify(expectedWrapperKeys)) throw new StagingPreviewAdapterError('staging result wrapper schema mismatch');
  if (wrapper.schema_version !== 'st-orchestration.h7d-authenticated-staging-result/v0' || wrapper.staging_transport !== true || wrapper.authenticated !== true) throw new StagingPreviewAdapterError('staging result wrapper identity drift');
  if (wrapper.preview_input_sha256 !== input.preview_input_sha256) throw new StagingPreviewAdapterError('preview input binding mismatch');
  const result = wrapper.result;
  if (!result || typeof result !== 'object' || Array.isArray(result)) throw new StagingPreviewAdapterError('staging result missing');
  const request = input.request;
  if (result.integration_request_id !== request.integration_request_id) throw new StagingPreviewAdapterError('request identity mismatch');
  if (result.corrected_musicxml_sha256 !== request.corrected_musicxml_sha256) throw new StagingPreviewAdapterError('source hash mismatch');
  if (result.capability !== contract.target.capability) throw new StagingPreviewAdapterError('result capability mismatch');
  if (result.candidate_id !== contract.target.modelId || result.model_fingerprint !== contract.target.modelFingerprint) throw new StagingPreviewAdapterError('model identity mismatch');
  if (result.abstention_threshold !== contract.target.abstentionThreshold) throw new StagingPreviewAdapterError('abstention threshold mismatch');
  if (!['proposal', 'abstain', 'unsupported'].includes(result.status)) throw new StagingPreviewAdapterError('unsupported result status');
  if (!Array.isArray(result.alternatives)) throw new StagingPreviewAdapterError('alternatives must be an array');
  for (const item of result.alternatives) {
    if (!item || typeof item !== 'object' || !ALLOWED_INSTRUMENTS.has(item.instrument) || !Number.isFinite(item.confidence) || item.confidence < 0 || item.confidence > 1) throw new StagingPreviewAdapterError('invalid ranked alternative');
  }
  if (!result.deterministic_validation || typeof result.deterministic_validation.passed !== 'boolean' || !Array.isArray(result.deterministic_validation.violations) || !result.deterministic_validation.violations.every((value) => typeof value === 'string')) {
    throw new StagingPreviewAdapterError('deterministic validation missing');
  }
  if (result.status === 'proposal') {
    if (result.deterministic_validation.passed !== true || result.alternatives.length === 0 || result.alternatives[0].confidence < contract.target.abstentionThreshold) throw new StagingPreviewAdapterError('invalid proposal survived staging validation');
  }
  if (result.status === 'abstain' && result.alternatives.length > 0 && result.alternatives[0].confidence >= contract.target.abstentionThreshold) throw new StagingPreviewAdapterError('abstention contradicts frozen threshold');
  if (result.status === 'unsupported' && (result.alternatives.length !== 0 || result.deterministic_validation.passed !== false)) throw new StagingPreviewAdapterError('unsupported result contradicts deterministic boundary');
  if (!SHA256_RE.test(result.result_sha256 || '')) throw new StagingPreviewAdapterError('result SHA-256 invalid');
  const material = deepCopy(result);
  delete material.result_sha256;
  if (canonicalSha256(material) !== result.result_sha256) throw new StagingPreviewAdapterError('result SHA-256 mismatch');
  return freezeDeep(deepCopy(wrapper));
};

const requestStagingPreview = ({endpoint, secret, input, allowLoopbackHttpForTest = false, allowedOrigin, timestamp, nonce, timeoutMs = TIMEOUT_MS}) => {
  const contract = readContract();
  const validatedInput = validateInput(input, contract);
  const endpointUrl = validateEndpoint(endpoint, {allowLoopbackHttpForTest, allowedOrigin});
  if (!Number.isInteger(timeoutMs) || timeoutMs <= 0 || timeoutMs > contract.transportBoundary.timeoutMs) throw new StagingPreviewAdapterError('timeout exceeds staging contract');
  const signed = buildSignedRequest(validatedInput, secret, {timestamp, nonce});
  if (signed.body.length > contract.transportBoundary.requestSizeLimitBytes) throw new StagingPreviewAdapterError('signed request exceeds staging contract');
  const transport = endpointUrl.protocol === 'https:' ? https : http;
  const options = {
    protocol: endpointUrl.protocol,
    hostname: endpointUrl.hostname,
    port: endpointUrl.port || undefined,
    method: 'POST',
    path: ROUTE,
    headers: signed.headers,
    timeout: timeoutMs,
    agent: false,
  };

  return new Promise((resolve, reject) => {
    let settled = false;
    const fail = (error) => {
      if (settled) return;
      settled = true;
      reject(error instanceof StagingPreviewAdapterError ? error : new StagingPreviewAdapterError(error.message || String(error)));
    };
    const request = transport.request(options, (response) => {
      if (response.statusCode !== 200) {
        response.resume();
        fail(new StagingPreviewAdapterError(`staging endpoint rejected request (${response.statusCode})`));
        return;
      }
      const contentType = String(response.headers['content-type'] || '').split(';', 1)[0].trim().toLowerCase();
      if (contentType !== 'application/json') {
        response.resume();
        fail(new StagingPreviewAdapterError('staging response must be application/json'));
        return;
      }
      const contentEncoding = String(response.headers['content-encoding'] || '').trim().toLowerCase();
      if (contentEncoding && contentEncoding !== 'identity') {
        response.resume();
        fail(new StagingPreviewAdapterError('compressed staging responses are outside the bounded contract'));
        return;
      }
      const chunks = [];
      let size = 0;
      response.on('data', (chunk) => {
        if (settled) return;
        size += chunk.length;
        if (size > contract.transportBoundary.responseSizeLimitBytes) {
          response.destroy();
          fail(new StagingPreviewAdapterError('staging response exceeds bounded contract'));
          return;
        }
        chunks.push(chunk);
      });
      response.on('error', fail);
      response.on('end', () => {
        if (settled) return;
        let wrapper;
        try { wrapper = JSON.parse(Buffer.concat(chunks).toString('utf8')); }
        catch (error) { fail(new StagingPreviewAdapterError(`invalid JSON from staging endpoint: ${error.message}`)); return; }
        try {
          const validated = validateResult(wrapper, validatedInput, contract);
          settled = true;
          resolve(validated);
        } catch (error) { fail(error); }
      });
    });
    request.on('timeout', () => request.destroy(new StagingPreviewAdapterError('staging request timed out')));
    request.on('error', fail);
    request.end(signed.body);
  });
};

const toBrowserPreviewData = (wrapper, input, contract = readContract()) => {
  const validatedInput = validateInput(input, contract);
  const validated = validateResult(wrapper, validatedInput, contract);
  return freezeDeep({
    schemaVersion: 'scoremosaic-st-orchestration-staging-preview-data-v1',
    transportMode: 'authenticated-staging',
    productionArtifact: false,
    authoritative: false,
    networkCapable: false,
    persistent: false,
    sourceMutationAllowed: false,
    teacherRevisionMutationAllowed: false,
    approvalCapable: false,
    publicationCapable: false,
    automaticLearningCapable: false,
    target: {
      repository: contract.target.repository,
      mainCommit: contract.target.mainCommit,
      modelId: contract.target.modelId,
      modelFingerprint: contract.target.modelFingerprint,
      abstentionThreshold: contract.target.abstentionThreshold,
      capability: contract.target.capability,
    },
    request: deepCopy(validatedInput.request),
    previewInputSha256: validated.preview_input_sha256,
    result: deepCopy(validated.result),
  });
};

module.exports = {
  StagingPreviewAdapterError,
  readContract,
  validateEndpoint,
  validateInput,
  buildSignedRequest,
  validateResult,
  requestStagingPreview,
  toBrowserPreviewData,
};
