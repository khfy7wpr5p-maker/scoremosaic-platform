(() => {
  'use strict';

  const data = window.ScoreMosaicOrchestrationPreviewData;
  const fixture = window.ScoreMosaicFixture;
  const LOCAL_SCHEMA = 'scoremosaic-st-orchestration-local-preview-data-v1';
  const STAGING_SCHEMA = 'scoremosaic-st-orchestration-staging-preview-data-v1';
  const LOCAL_COMMIT = 'f5ee0e605e62c41af86255712941305b2a8c7afb';
  const STAGING_COMMIT = '80b1e925804616d36c2b46c8074e6a608aa7bff4';
  const EXPECTED_MODEL_FINGERPRINT = '15cd94722a0ba2724ceea6f450f16a87ef455fa8bc21d4b619f0bda6d880ca14';
  const EXPECTED_CAPABILITY = 'string-seat-ranking-v0';
  const EXPECTED_THRESHOLD = 0.55;

  const deepCopy = (value) => JSON.parse(JSON.stringify(value));
  const isSha256 = (value) => typeof value === 'string' && /^[0-9a-f]{64}$/.test(value);
  const expectedCommit = () => {
    if (data?.schemaVersion === LOCAL_SCHEMA && (data.transportMode === undefined || data.transportMode === 'local-process')) return LOCAL_COMMIT;
    if (data?.schemaVersion === STAGING_SCHEMA && data.transportMode === 'authenticated-staging') return STAGING_COMMIT;
    return null;
  };
  const valid = () => {
    if (!data || !fixture) return false;
    const commit = expectedCommit();
    if (!commit) return false;
    for (const key of ['productionArtifact', 'authoritative', 'networkCapable', 'persistent', 'sourceMutationAllowed', 'teacherRevisionMutationAllowed', 'approvalCapable', 'publicationCapable', 'automaticLearningCapable']) {
      if (data[key] !== false) return false;
    }
    if (data.target?.repository !== 'khfy7wpr5p-maker/ST-Orchestration') return false;
    if (data.target?.mainCommit !== commit) return false;
    if (data.target?.modelId !== 'o5c-ossq-anonymous-context-v0') return false;
    if (data.target?.modelFingerprint !== EXPECTED_MODEL_FINGERPRINT) return false;
    if (data.target?.abstentionThreshold !== EXPECTED_THRESHOLD) return false;
    if (data.target?.capability !== EXPECTED_CAPABILITY) return false;
    if (data.request?.document_id !== fixture.document?.id) return false;
    if (data.request?.teacher_revision_id !== fixture.document?.revision) return false;
    if (data.request?.source_state !== 'validated-preview') return false;
    if (data.request?.capability !== EXPECTED_CAPABILITY) return false;
    if (!isSha256(data.request?.corrected_musicxml_sha256) || !isSha256(data.previewInputSha256)) return false;
    const result = data.result;
    if (!result || result.integration_request_id !== data.request.integration_request_id) return false;
    if (result.corrected_musicxml_sha256 !== data.request.corrected_musicxml_sha256) return false;
    if (result.capability !== EXPECTED_CAPABILITY || result.candidate_id !== data.target.modelId) return false;
    if (result.model_fingerprint !== EXPECTED_MODEL_FINGERPRINT || result.abstention_threshold !== EXPECTED_THRESHOLD) return false;
    if (!['proposal', 'abstain', 'unsupported'].includes(result.status)) return false;
    if (!Array.isArray(result.alternatives) || !isSha256(result.result_sha256)) return false;
    if (!result.deterministic_validation || typeof result.deterministic_validation.passed !== 'boolean' || !Array.isArray(result.deterministic_validation.violations)) return false;
    if (result.status === 'proposal' && result.deterministic_validation.passed !== true) return false;
    return result.alternatives.every((item) =>
      item && ['violin-1', 'violin-2', 'viola', 'cello'].includes(item.instrument)
      && Number.isFinite(item.confidence) && item.confidence >= 0 && item.confidence <= 1
    );
  };

  window.ScoreMosaicOrchestrationPreviewAdapter = Object.freeze({
    adapterVersion: 'scoremosaic-st-orchestration-preview-adapter-v1',
    productionAdapter: false,
    authoritative: false,
    networkCapable: false,
    mutationCapable: false,
    persistent: false,
    approvalCapable: false,
    publicationCapable: false,
    read() {
      if (!valid()) {
        return Object.freeze({state: 'rejected', data: null, error: Object.freeze({code: 'ORCHESTRATION_PREVIEW_INVALID', message: 'Orchestration preview evidence failed closed.'})});
      }
      return Object.freeze({state: 'ready', data: deepCopy(data), error: null});
    },
  });
})();
