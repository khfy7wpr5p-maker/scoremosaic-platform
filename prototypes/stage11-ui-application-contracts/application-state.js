(() => {
  'use strict';

  const STATE_SCHEMA = 'scoremosaic-stage11-ui-application-state-v1';
  const READ_RESPONSE_SCHEMA = 'scoremosaic-stage11-read-response-v1';
  const EDIT_RESPONSE_SCHEMA = 'scoremosaic-stage11-edit-intent-response-v1';
  const READ_KINDS = new Set(['review.read', 'issues.read', 'sourceEvidence.read', 'validation.read']);
  const ALL_KINDS = new Set([...READ_KINDS, 'editIntent.prepare']);
  const RESPONSE_STATES = new Set(['success', 'empty', 'rejected', 'unavailable']);

  const freezeDeep = (value) => {
    if (value && typeof value === 'object' && !Object.isFrozen(value)) {
      Object.freeze(value);
      Object.keys(value).forEach((key) => freezeDeep(value[key]));
    }
    return value;
  };

  const authority = () => freezeDeep({
    authoritative: false,
    canWrite: false,
    canApprove: false,
    canPublish: false,
    canPlayback: false,
  });

  const state = (phase, request, data = null, error = null) => freezeDeep({
    schemaVersion: STATE_SCHEMA,
    phase,
    requestId: request?.requestId ?? null,
    kind: ALL_KINDS.has(request?.kind) ? request.kind : null,
    documentId: request?.documentId ?? null,
    revision: request?.revision ?? null,
    data,
    error,
    authority: authority(),
  });

  const errorCategory = (code) => {
    if (['DOCUMENT_MISMATCH', 'REVISION_MISMATCH', 'TARGET_MISMATCH'].includes(code)) return 'stale_context';
    if (['ISSUE_NOT_FOUND'].includes(code)) return 'not_found';
    if (['ADAPTER_UNAVAILABLE'].includes(code)) return 'unavailable';
    if (typeof code === 'string' && (
      code.startsWith('REQUEST_')
      || code.startsWith('SCHEMA_')
      || ['ISSUE_ID_INVALID', 'TARGET_INVALID', 'OPERATION_INVALID', 'REASON_INVALID', 'AUTHORITY_INVALID'].includes(code)
    )) return 'invalid_request';
    if (typeof code === 'string' && code.startsWith('RESPONSE_')) return 'protocol';
    return 'unknown';
  };

  const normalizedError = (code, message, retryable = false) => freezeDeep({
    category: errorCategory(code),
    code: typeof code === 'string' && code.length > 0 ? code.slice(0, 80) : 'UNKNOWN_ERROR',
    message: typeof message === 'string' && message.length > 0 ? message.slice(0, 500) : 'Application request failed.',
    retryable: retryable === true,
  });

  const validRequest = (request) => request
    && typeof request === 'object'
    && typeof request.requestId === 'string'
    && request.requestId.length > 0
    && request.requestId.length <= 128
    && ALL_KINDS.has(request.kind)
    && typeof request.documentId === 'string'
    && request.documentId.length > 0
    && typeof request.revision === 'string'
    && request.revision.length > 0;

  const begin = (request) => {
    if (!validRequest(request)) {
      return state('rejected', null, null, normalizedError('REQUEST_STATE_INVALID', 'Application request cannot enter loading state.'));
    }
    return state('loading', request);
  };

  const expectedResponseSchema = (kind) => READ_KINDS.has(kind) ? READ_RESPONSE_SCHEMA : EDIT_RESPONSE_SCHEMA;

  const correlationError = (loading, response) => {
    if (!loading || loading.schemaVersion !== STATE_SCHEMA || loading.phase !== 'loading') return 'RESPONSE_LOADING_STATE_REQUIRED';
    if (!response || typeof response !== 'object') return 'RESPONSE_INVALID';
    if (response.schemaVersion !== expectedResponseSchema(loading.kind)) return 'RESPONSE_SCHEMA_MISMATCH';
    if (response.requestId !== loading.requestId) return 'RESPONSE_REQUEST_ID_MISMATCH';
    if (response.kind !== loading.kind) return 'RESPONSE_KIND_MISMATCH';
    if (response.documentId !== loading.documentId) return 'RESPONSE_DOCUMENT_MISMATCH';
    if (response.revision !== loading.revision) return 'RESPONSE_REVISION_MISMATCH';
    if (!RESPONSE_STATES.has(response.state)) return 'RESPONSE_STATE_INVALID';
    if (loading.kind === 'editIntent.prepare' && response.state === 'empty') return 'RESPONSE_STATE_INVALID';
    return null;
  };

  const settle = (loading, response) => {
    const correlation = correlationError(loading, response);
    if (correlation) {
      const request = loading?.phase === 'loading' ? loading : null;
      return state('rejected', request, null, normalizedError(correlation, 'Application response failed correlation checks.'));
    }

    if (response.state === 'success') {
      if (response.error !== null || response.data === null || typeof response.data !== 'object') {
        return state('rejected', loading, null, normalizedError('RESPONSE_SUCCESS_INVALID', 'Success response violated envelope invariants.'));
      }
      return state('ready', loading, freezeDeep(response.data), null);
    }

    if (response.state === 'empty') {
      if (response.error !== null || response.data !== null) {
        return state('rejected', loading, null, normalizedError('RESPONSE_EMPTY_INVALID', 'Empty response violated envelope invariants.'));
      }
      return state('empty', loading);
    }

    const remoteError = response.error;
    if (!remoteError || typeof remoteError !== 'object') {
      return state('rejected', loading, null, normalizedError('RESPONSE_ERROR_INVALID', 'Non-success response omitted a bounded error.'));
    }
    const normalized = normalizedError(remoteError.code, remoteError.message, response.state === 'unavailable' && remoteError.retryable === true);
    return state(response.state, loading, null, normalized);
  };

  const idle = () => state('idle', null);

  window.ScoreMosaicApplicationState = freezeDeep({
    reducerVersion: 'scoremosaic-stage11-application-state-v1',
    authoritative: false,
    networkCapable: false,
    persistent: false,
    idle,
    begin,
    settle,
  });
})();
