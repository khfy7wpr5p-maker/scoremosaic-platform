(() => {
  'use strict';

  const fixture = window.ScoreMosaicFixture;
  const application = window.ScoreMosaicLocalApplication;
  const coreBridge = window.ScoreMosaicScoreEditorCoreBridge;
  if (
    !fixture
    || fixture.productionArtifact !== false
    || fixture.authoritativeTruth !== false
    || !application
    || application.productionApplication !== false
    || application.authoritative !== false
    || application.networkCapable !== false
    || application.persistent !== false
  ) {
    return;
  }

  const coreAvailable = coreBridge?.available === true
    && coreBridge.authoritative === false
    && coreBridge.networkCapable === false
    && coreBridge.persistent === false
    && coreBridge.serverRevisionAuthority === false
    && coreBridge.approvalAuthority === false
    && coreBridge.publicationAuthority === false;

  const issuesState = application.read('issues.read');
  const issues = issuesState?.phase === 'ready' && issuesState.authority?.authoritative === false
    ? issuesState.data.items
    : [];

  const ALLOWED_OPERATIONS = new Set([
    'set_pitch',
    'set_effective_duration',
    'set_dots',
    'remove_event'
  ]);
  const PITCH_RE = /^([A-G])([#b]?)(-?[0-9]{1,2})$/;
  const DURATION_RE = /^([1-9][0-9]{0,8})\/([1-9][0-9]{0,6})$/;
  const REQUEST_AUTHORITY = Object.freeze({
    authoritativeCapability: false,
    serverAuthorizationIncluded: false,
    oldValuePreconditionIncluded: false,
    commandIdentityIncluded: false,
    networkSubmissionAllowed: false
  });
  const EXPECTED_LOCAL_AUTHORITY = Object.freeze({
    authoritativeCapability: false,
    serverAuthorizationIncluded: false,
    oldValuePreconditionIncluded: false,
    commandIdentityIncluded: false,
    networkSubmissionAllowed: false,
    canCreateScoreEditCommand: false,
    canCreateRevision: false,
    canApprove: false,
    canPublish: false
  });

  const byId = (id) => document.getElementById(id);
  const operation = byId('edit-operation');
  const proposedValue = byId('edit-value');
  const reason = byId('edit-reason');
  const prepareButton = byId('prepare-intent');
  const clearButton = byId('clear-intent');
  const status = byId('intent-status');
  const preview = byId('intent-preview');
  const issueList = byId('issue-list');

  if (!operation || !proposedValue || !reason || !prepareButton || !clearButton || !status || !preview || !issueList) {
    return;
  }

  const selectedIssue = () => {
    const selected = issueList.querySelector('[data-issue-id][aria-pressed="true"]');
    const issueId = selected?.dataset.issueId;
    return issues.find((issue) => issue.id === issueId) ?? null;
  };

  const setStatus = (message, kind = 'neutral') => {
    status.textContent = message;
    status.dataset.kind = kind;
  };

  const clearIntent = (message = 'No local intent prepared.') => {
    preview.textContent = message;
    clearButton.disabled = true;
  };

  const configureValueField = () => {
    const type = operation.value;
    if (!ALLOWED_OPERATIONS.has(type)) {
      proposedValue.value = '';
      proposedValue.disabled = true;
      prepareButton.disabled = true;
      setStatus('Operation unavailable', 'locked');
      return;
    }
    const remove = type === 'remove_event';
    proposedValue.disabled = remove;
    proposedValue.value = '';
    if (type === 'set_pitch') {
      proposedValue.placeholder = 'Example: F#4 or Bb3';
      proposedValue.maxLength = 5;
    } else if (type === 'set_effective_duration') {
      proposedValue.placeholder = 'Example: 1/8';
      proposedValue.maxLength = 16;
    } else if (type === 'set_dots') {
      proposedValue.placeholder = coreAvailable ? '0–3' : '0–8';
      proposedValue.maxLength = 1;
    } else {
      proposedValue.placeholder = coreAvailable ? 'Not mapped in editor core' : 'No value for remove_event';
    }
    prepareButton.disabled = selectedIssue() === null;
    prepareButton.textContent = coreAvailable ? 'Apply local core edit' : 'Prepare local intent';
    setStatus(coreAvailable ? 'Core-backed local session · not submitted' : 'Local draft only', coreAvailable ? 'safe' : 'neutral');
    clearIntent(coreAvailable ? 'Operation changed. Apply a new local core edit.' : 'Operation changed. Prepare a new local intent.');
  };

  const parsePitch = (value) => {
    const match = PITCH_RE.exec(value.trim());
    if (!match) throw new Error('PITCH_INVALID');
    const accidental = match[2];
    const octave = Number(match[3]);
    if (!Number.isSafeInteger(octave) || octave < -2 || octave > 12) throw new Error('PITCH_OCTAVE_INVALID');
    const alter = accidental === '#' ? 1 : accidental === 'b' ? -1 : 0;
    return {
      step: match[1],
      alter: {numerator: alter, denominator: 1},
      octave
    };
  };

  const parseDuration = (value) => {
    const match = DURATION_RE.exec(value.trim());
    if (!match) throw new Error('DURATION_INVALID');
    const numerator = Number(match[1]);
    const denominator = Number(match[2]);
    if (!Number.isSafeInteger(numerator) || !Number.isSafeInteger(denominator)) throw new Error('DURATION_INVALID');
    return {numerator, denominator};
  };

  const operationPayload = () => {
    const type = operation.value;
    if (!ALLOWED_OPERATIONS.has(type)) throw new Error('OPERATION_INVALID');
    if (type === 'set_pitch') return {type, value: parsePitch(proposedValue.value)};
    if (type === 'set_effective_duration') return {type, value: parseDuration(proposedValue.value)};
    if (type === 'set_dots') {
      const dots = Number(proposedValue.value.trim());
      if (!Number.isSafeInteger(dots) || dots < 0 || dots > 8) throw new Error('DOTS_INVALID');
      if (coreAvailable && dots > 3) throw new Error('DOTS_INVALID');
      return {type, value: dots};
    }
    return {type, value: null};
  };

  const authorityMatches = (authority) => Object.entries(EXPECTED_LOCAL_AUTHORITY)
    .every(([key, expected]) => authority?.[key] === expected);

  const prepareFixtureIntent = (issue, payload, note) => {
    const result = application.prepareEditIntent({
      issueId: issue.id,
      target: Object.freeze({
        page: issue.location.page,
        measure: issue.location.measure,
        staff: issue.location.staff,
        voice: issue.location.voice,
        event: issue.location.event
      }),
      operation: Object.freeze(payload),
      reason: note.length === 0 ? null : note,
      authority: REQUEST_AUTHORITY
    });

    if (result?.phase !== 'ready' || result.authority?.authoritative !== false || !result.data || !authorityMatches(result.data.authority)) {
      const code = result?.error?.code ?? 'INTENT_APPLICATION_REJECTED';
      throw new Error(code);
    }
    return result.data;
  };

  const prepareIntent = () => {
    const issue = selectedIssue();
    if (!issue) throw new Error('TARGET_INVALID');
    const note = reason.value.trim();
    if (note.length > 300) throw new Error('REASON_TOO_LONG');
    const payload = operationPayload();

    if (coreAvailable) {
      const snapshot = coreBridge.commitOperation(issue.id, Object.freeze(payload));
      preview.textContent = JSON.stringify({
        mode: 'st-score-editor-core-local-session',
        coreCommit: coreBridge.coreCommit,
        revisionId: snapshot.revisionId,
        rendererFamily: snapshot.rendererFamily,
        authoritative: false,
        persistent: false,
        reviewerNote: note.length === 0 ? null : note
      }, null, 2);
      clearButton.disabled = false;
      setStatus('Core-backed local revision · not submitted', 'safe');
      return;
    }

    const intent = prepareFixtureIntent(issue, payload, note);
    preview.textContent = JSON.stringify(intent, null, 2);
    clearButton.disabled = false;
    setStatus('Prepared locally · typed contract · not submitted', 'safe');
  };

  const syncSelection = () => {
    const issue = selectedIssue();
    prepareButton.disabled = issue === null;
    clearIntent(issue
      ? (coreAvailable ? 'Selected fixture target changed. Apply a new local core edit.' : 'Selected fixture target changed. Prepare a new local intent.')
      : 'No local target selected.');
    setStatus(
      issue ? (coreAvailable ? 'Core-backed local session · not submitted' : 'Local draft only') : 'No target',
      issue ? (coreAvailable ? 'safe' : 'neutral') : 'locked'
    );
  };

  operation.addEventListener('change', configureValueField);
  prepareButton.addEventListener('click', () => {
    try {
      prepareIntent();
    } catch (error) {
      const code = error instanceof Error ? error.message : 'INTENT_INVALID';
      preview.textContent = `Intent rejected locally: ${code}`;
      clearButton.disabled = false;
      setStatus('Rejected locally', 'locked');
    }
  });
  clearButton.addEventListener('click', () => {
    reason.value = '';
    clearIntent();
    setStatus(coreAvailable ? 'Core-backed local session · not submitted' : 'Local draft only', coreAvailable ? 'safe' : 'neutral');
  });
  issueList.addEventListener('click', syncSelection);

  configureValueField();
  syncSelection();
})();
