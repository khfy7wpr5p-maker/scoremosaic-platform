(() => {
  'use strict';

  const fixture = window.ScoreMosaicFixture;
  if (!fixture || fixture.productionArtifact !== false || fixture.authoritativeTruth !== false) {
    return;
  }

  const REQUEST_SCHEMA = 'scoremosaic-stage11-read-request-v1';
  const RESPONSE_SCHEMA = 'scoremosaic-stage11-read-response-v1';
  const ALLOWED_KINDS = new Set(['review.read', 'issues.read', 'sourceEvidence.read', 'validation.read']);
  const REQUIRED_KEYS = new Set(['schemaVersion', 'requestId', 'kind', 'documentId', 'revision']);

  const freezeDeep = (value) => {
    if (value && typeof value === 'object' && !Object.isFrozen(value)) {
      Object.freeze(value);
      Object.keys(value).forEach((key) => freezeDeep(value[key]));
    }
    return value;
  };

  const cloneJson = (value) => JSON.parse(JSON.stringify(value));

  const envelope = (request, state, data, error) => freezeDeep({
    schemaVersion: RESPONSE_SCHEMA,
    requestId: typeof request?.requestId === 'string' ? request.requestId : 'invalid-request',
    kind: typeof request?.kind === 'string' ? request.kind : 'review.read',
    state,
    documentId: fixture.document.id,
    revision: fixture.document.revision,
    data,
    error,
  });

  const reject = (request, code, message) => envelope(
    request,
    'rejected',
    null,
    freezeDeep({code, message, retryable: false}),
  );

  const validateRequest = (request) => {
    if (!request || typeof request !== 'object' || Array.isArray(request)) return 'REQUEST_INVALID';
    const keys = Object.keys(request);
    if (keys.length !== REQUIRED_KEYS.size || keys.some((key) => !REQUIRED_KEYS.has(key))) return 'REQUEST_SHAPE_INVALID';
    if (request.schemaVersion !== REQUEST_SCHEMA) return 'SCHEMA_VERSION_INVALID';
    if (typeof request.requestId !== 'string' || request.requestId.length < 1 || request.requestId.length > 128) return 'REQUEST_ID_INVALID';
    if (!ALLOWED_KINDS.has(request.kind)) return 'REQUEST_KIND_INVALID';
    if (request.documentId !== fixture.document.id) return 'DOCUMENT_MISMATCH';
    if (request.revision !== fixture.document.revision) return 'REVISION_MISMATCH';
    return null;
  };

  const count = (severity) => fixture.issues.filter((issue) => issue.severity === severity).length;

  const readData = (kind) => {
    if (kind === 'review.read') {
      return {
        label: fixture.document.label,
        reviewState: fixture.document.reviewState,
        sourceSha256: fixture.document.sourceSha256,
        canonicalSha256: fixture.document.canonicalSha256,
      };
    }
    if (kind === 'issues.read') {
      return {
        items: cloneJson(fixture.issues),
        counts: {blocking: count('blocking'), warning: count('warning'), info: count('info')},
      };
    }
    if (kind === 'sourceEvidence.read') {
      return {
        sourceSha256: fixture.document.sourceSha256,
        canonicalSha256: fixture.document.canonicalSha256,
        regions: fixture.issues.map((issue) => ({
          issueId: issue.id,
          sourceRegion: issue.evidence.sourceRegion,
          candidate: issue.evidence.candidate,
          canonical: issue.evidence.canonical,
        })),
      };
    }
    return {
      status: fixture.validation.status,
      blocking: fixture.validation.blocking,
      warnings: fixture.validation.warnings,
      info: fixture.validation.info,
      approvalEligible: fixture.validation.approvalEligible,
      publicationEligible: fixture.validation.publicationEligible,
      authoritative: false,
    };
  };

  const read = (request) => {
    const invalid = validateRequest(request);
    if (invalid) return reject(request, invalid, 'Local read request rejected by Stage 11 contract.');
    return envelope(request, 'success', freezeDeep(readData(request.kind)), null);
  };

  window.ScoreMosaicLocalReadAdapter = freezeDeep({
    adapterVersion: 'scoremosaic-stage11-local-read-adapter-v1',
    productionAdapter: false,
    authoritative: false,
    networkCapable: false,
    persistent: false,
    requestSchemaVersion: REQUEST_SCHEMA,
    responseSchemaVersion: RESPONSE_SCHEMA,
    read,
  });
})();
