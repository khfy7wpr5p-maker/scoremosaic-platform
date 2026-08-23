(() => {
  'use strict';

  const fixture = window.ScoreMosaicFixture;
  if (!fixture || fixture.productionArtifact !== false || fixture.authoritativeTruth !== false) return;

  const REQUEST_SCHEMA = 'scoremosaic-stage11-edit-intent-request-v1';
  const RESPONSE_SCHEMA = 'scoremosaic-stage11-edit-intent-response-v1';
  const REQUEST_KEYS = new Set(['schemaVersion', 'requestId', 'kind', 'documentId', 'revision', 'issueId', 'target', 'operation', 'reason', 'authority']);
  const TARGET_KEYS = new Set(['page', 'measure', 'staff', 'voice', 'event']);
  const AUTHORITY_KEYS = new Set(['authoritativeCapability', 'serverAuthorizationIncluded', 'oldValuePreconditionIncluded', 'commandIdentityIncluded', 'networkSubmissionAllowed']);
  const OPERATION_TYPES = new Set(['set_pitch', 'set_effective_duration', 'set_dots', 'remove_event']);

  const freezeDeep = (value) => {
    if (value && typeof value === 'object' && !Object.isFrozen(value)) {
      Object.freeze(value);
      Object.keys(value).forEach((key) => freezeDeep(value[key]));
    }
    return value;
  };

  const cloneJson = (value) => JSON.parse(JSON.stringify(value));
  const hasExactKeys = (value, expected) => value && typeof value === 'object' && !Array.isArray(value) && Object.keys(value).length === expected.size && Object.keys(value).every((key) => expected.has(key));
  const safeId = (value, max = 160) => typeof value === 'string' && value.length >= 1 && value.length <= max;
  const safeInt = (value, min, max) => Number.isSafeInteger(value) && value >= min && value <= max;

  const authorityIsFalse = (authority) => {
    if (!hasExactKeys(authority, AUTHORITY_KEYS)) return false;
    return [...AUTHORITY_KEYS].every((key) => authority[key] === false);
  };

  const validTarget = (target) => hasExactKeys(target, TARGET_KEYS)
    && safeInt(target.page, 1, 1000000)
    && safeInt(target.measure, 1, 1000000)
    && safeInt(target.staff, 1, 128)
    && safeInt(target.voice, 1, 1000000)
    && safeId(target.event);

  const rational = (value, numeratorMin = -1000000) => value
    && typeof value === 'object'
    && !Array.isArray(value)
    && Object.keys(value).length === 2
    && Object.prototype.hasOwnProperty.call(value, 'numerator')
    && Object.prototype.hasOwnProperty.call(value, 'denominator')
    && safeInt(value.numerator, numeratorMin, 1000000000)
    && safeInt(value.denominator, 1, 1000000);

  const validOperation = (operation) => {
    if (!operation || typeof operation !== 'object' || Array.isArray(operation)) return false;
    if (Object.keys(operation).length !== 2 || !Object.prototype.hasOwnProperty.call(operation, 'type') || !Object.prototype.hasOwnProperty.call(operation, 'value')) return false;
    if (!OPERATION_TYPES.has(operation.type)) return false;
    if (operation.type === 'remove_event') return operation.value === null;
    if (operation.type === 'set_dots') return safeInt(operation.value, 0, 8);
    if (operation.type === 'set_effective_duration') return rational(operation.value, 0);
    const pitch = operation.value;
    return pitch
      && typeof pitch === 'object'
      && !Array.isArray(pitch)
      && Object.keys(pitch).length === 3
      && ['A', 'B', 'C', 'D', 'E', 'F', 'G'].includes(pitch.step)
      && rational(pitch.alter)
      && safeInt(pitch.octave, -2, 12);
  };

  const sameTarget = (left, right) => [...TARGET_KEYS].every((key) => left[key] === right[key]);

  const responseKind = (request) => request?.kind === 'editIntent.prepare' ? 'editIntent.prepare' : 'unknown';
  const response = (request, state, data, error) => freezeDeep({
    schemaVersion: RESPONSE_SCHEMA,
    requestId: safeId(request?.requestId, 128) ? request.requestId : 'invalid-request',
    kind: responseKind(request),
    state,
    documentId: fixture.document.id,
    revision: fixture.document.revision,
    data,
    error,
  });

  const reject = (request, code) => response(request, 'rejected', null, freezeDeep({
    code,
    message: 'Local edit-intent request rejected by Stage 11 contract.',
    retryable: false,
  }));

  const validate = (request) => {
    if (!hasExactKeys(request, REQUEST_KEYS)) return 'REQUEST_SHAPE_INVALID';
    if (request.schemaVersion !== REQUEST_SCHEMA) return 'SCHEMA_VERSION_INVALID';
    if (!safeId(request.requestId, 128)) return 'REQUEST_ID_INVALID';
    if (request.kind !== 'editIntent.prepare') return 'REQUEST_KIND_INVALID';
    if (request.documentId !== fixture.document.id) return 'DOCUMENT_MISMATCH';
    if (request.revision !== fixture.document.revision) return 'REVISION_MISMATCH';
    if (!safeId(request.issueId)) return 'ISSUE_ID_INVALID';
    const issue = fixture.issues.find((candidate) => candidate.id === request.issueId);
    if (!issue) return 'ISSUE_NOT_FOUND';
    if (!validTarget(request.target)) return 'TARGET_INVALID';
    if (!sameTarget(request.target, issue.location)) return 'TARGET_MISMATCH';
    if (!validOperation(request.operation)) return 'OPERATION_INVALID';
    if (!(request.reason === null || (typeof request.reason === 'string' && request.reason.length >= 1 && request.reason.length <= 300))) return 'REASON_INVALID';
    if (!authorityIsFalse(request.authority)) return 'AUTHORITY_INVALID';
    return null;
  };

  const prepare = (request) => {
    const invalid = validate(request);
    if (invalid) return reject(request, invalid);
    const intent = freezeDeep({
      intentVersion: 'scoremosaic-stage11-local-edit-intent-v1',
      issueId: request.issueId,
      target: freezeDeep(cloneJson(request.target)),
      operation: freezeDeep(cloneJson(request.operation)),
      reason: request.reason,
      authority: freezeDeep({
        authoritativeCapability: false,
        serverAuthorizationIncluded: false,
        oldValuePreconditionIncluded: false,
        commandIdentityIncluded: false,
        networkSubmissionAllowed: false,
        canCreateScoreEditCommand: false,
        canCreateRevision: false,
        canApprove: false,
        canPublish: false,
      }),
    });
    return response(request, 'success', intent, null);
  };

  window.ScoreMosaicLocalEditIntentAdapter = freezeDeep({
    adapterVersion: 'scoremosaic-stage11-local-edit-intent-adapter-v1',
    productionAdapter: false,
    authoritative: false,
    networkCapable: false,
    persistent: false,
    requestSchemaVersion: REQUEST_SCHEMA,
    responseSchemaVersion: RESPONSE_SCHEMA,
    prepare,
  });
})();
