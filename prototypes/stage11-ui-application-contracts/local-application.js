(() => {
  'use strict';

  const fixture = window.ScoreMosaicFixture;
  const readAdapter = window.ScoreMosaicLocalReadAdapter;
  const editAdapter = window.ScoreMosaicLocalEditIntentAdapter;
  const reducer = window.ScoreMosaicApplicationState;

  if (
    !fixture
    || fixture.productionArtifact !== false
    || fixture.authoritativeTruth !== false
    || !readAdapter
    || readAdapter.productionAdapter !== false
    || readAdapter.authoritative !== false
    || readAdapter.networkCapable !== false
    || !editAdapter
    || editAdapter.productionAdapter !== false
    || editAdapter.authoritative !== false
    || editAdapter.networkCapable !== false
    || !reducer
    || reducer.authoritative !== false
    || reducer.networkCapable !== false
  ) {
    return;
  }

  const READ_KINDS = new Set(['review.read', 'issues.read', 'sourceEvidence.read', 'validation.read']);
  let requestSequence = 0;

  const freezeDeep = (value) => {
    if (value && typeof value === 'object' && !Object.isFrozen(value)) {
      Object.freeze(value);
      Object.keys(value).forEach((key) => freezeDeep(value[key]));
    }
    return value;
  };

  const nextRequestId = (prefix) => {
    requestSequence += 1;
    return `local-${prefix}-${String(requestSequence).padStart(4, '0')}`;
  };

  const baseRequest = (kind, requestId) => ({
    requestId,
    kind,
    documentId: fixture.document.id,
    revision: fixture.document.revision,
  });

  const failClosedState = (kind) => reducer.begin({
    requestId: nextRequestId('invalid'),
    kind: READ_KINDS.has(kind) ? kind : 'review.read',
    documentId: fixture.document.id,
    revision: fixture.document.revision,
  });

  const read = (kind) => {
    if (!READ_KINDS.has(kind)) {
      const loading = failClosedState(kind);
      return reducer.settle(loading, {
        schemaVersion: 'scoremosaic-stage11-read-response-v1',
        requestId: loading.requestId,
        kind: loading.kind,
        state: 'rejected',
        documentId: loading.documentId,
        revision: loading.revision,
        data: null,
        error: {code: 'REQUEST_KIND_INVALID', message: 'Unknown local read kind.', retryable: false},
      });
    }

    const request = freezeDeep({
      schemaVersion: 'scoremosaic-stage11-read-request-v1',
      ...baseRequest(kind, nextRequestId('read')),
    });
    const loading = reducer.begin(request);
    return reducer.settle(loading, readAdapter.read(request));
  };

  const prepareEditIntent = ({issueId, target, operation, reason}) => {
    const request = freezeDeep({
      schemaVersion: 'scoremosaic-stage11-edit-intent-request-v1',
      ...baseRequest('editIntent.prepare', nextRequestId('intent')),
      issueId,
      target,
      operation,
      reason,
      authority: freezeDeep({
        authoritativeCapability: false,
        serverAuthorizationIncluded: false,
        oldValuePreconditionIncluded: false,
        commandIdentityIncluded: false,
        networkSubmissionAllowed: false,
      }),
    });
    const loading = reducer.begin(request);
    return reducer.settle(loading, editAdapter.prepare(request));
  };

  const context = freezeDeep({
    documentId: fixture.document.id,
    revision: fixture.document.revision,
    fixtureVersion: fixture.fixtureVersion,
    productionArtifact: false,
    authoritativeTruth: false,
  });

  window.ScoreMosaicLocalApplication = freezeDeep({
    applicationVersion: 'scoremosaic-stage11-local-application-v1',
    productionApplication: false,
    authoritative: false,
    networkCapable: false,
    persistent: false,
    context,
    read,
    prepareEditIntent,
  });
})();
