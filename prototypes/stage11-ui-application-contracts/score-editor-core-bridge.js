(() => {
  'use strict';

  const fixture = window.ScoreMosaicFixture;
  const runtime = window.STScoreEditorCoreRuntime;
  const CORE_COMMIT = 'b317abef915d1e16b37572221a38feb3e504450d';
  const INTEGRATION_VERSION = 'scoremosaic-st-score-editor-core-bridge-v1';
  const SCORE_MEASURE_COUNT = 12;
  const FILLER_PITCHES = Object.freeze([
    Object.freeze({step: 'E', alter: 0, octave: 4}),
    Object.freeze({step: 'G', alter: 0, octave: 4}),
    Object.freeze({step: 'B', alter: 0, octave: 4}),
    Object.freeze({step: 'D', alter: 0, octave: 5}),
    Object.freeze({step: 'F', alter: 0, octave: 4}),
    Object.freeze({step: 'A', alter: 0, octave: 4}),
    Object.freeze({step: 'C', alter: 0, octave: 5}),
    Object.freeze({step: 'E', alter: 0, octave: 5})
  ]);
  let sequence = 0;
  let session = null;

  const freezeDeep = (value) => {
    if (value && typeof value === 'object' && !Object.isFrozen(value)) {
      Object.freeze(value);
      Object.keys(value).forEach((key) => freezeDeep(value[key]));
    }
    return value;
  };

  const unavailable = (reason) => freezeDeep({
    integrationVersion: INTEGRATION_VERSION,
    available: false,
    reason,
    authoritative: false,
    networkCapable: false,
    persistent: false,
    serverRevisionAuthority: false,
    approvalAuthority: false,
    publicationAuthority: false,
    coreCommit: CORE_COMMIT
  });

  const expectedRuntime = (candidate) => {
    if (!candidate || candidate.runtimeVersion !== '1.0.0') return false;
    const profile = candidate.profile;
    if (
      !profile
      || profile.version !== '1.0.0'
      || profile.productionRuntime !== false
      || profile.networkCapable !== false
      || profile.persistenceCapable !== false
      || profile.rendererAuthority !== false
      || profile.browserMutationAuthority !== false
      || profile.serverRevisionAuthority !== false
      || profile.approvalAuthority !== false
      || profile.publicationAuthority !== false
    ) return false;
    return [
      'createScoreDocument',
      'emptyNotationDocument',
      'createEditorSession',
      'selectSessionRenderToken',
      'commitSessionScoreIntent',
      'commitSessionNotationIntent',
      'navigateSessionHistory'
    ].every((name) => typeof candidate[name] === 'function');
  };

  if (!fixture || fixture.productionArtifact !== false || fixture.authoritativeTruth !== false) {
    window.ScoreMosaicScoreEditorCoreBridge = unavailable('FIXTURE_UNAVAILABLE');
    return;
  }
  if (!runtime) {
    window.ScoreMosaicScoreEditorCoreBridge = unavailable('RUNTIME_UNAVAILABLE');
    return;
  }
  if (!expectedRuntime(runtime)) {
    window.ScoreMosaicScoreEditorCoreBridge = unavailable('RUNTIME_PROFILE_MISMATCH');
    return;
  }

  const parsePitchText = (text) => {
    const match = /^([A-G])([#b]?)(-?[0-9]{1,2})\??$/.exec(String(text).trim());
    if (!match) throw new Error('FIXTURE_PITCH_INVALID');
    const octave = Number(match[3]);
    if (!Number.isSafeInteger(octave) || octave < -1 || octave > 9) throw new Error('FIXTURE_PITCH_INVALID');
    return freezeDeep({step: match[1], alter: match[2] === '#' ? 1 : match[2] === 'b' ? -1 : 0, octave});
  };

  const parseDurationText = (text) => {
    const match = /^([1-9][0-9]{0,8})\/([1-9][0-9]{0,8})$/.exec(String(text).trim());
    if (!match) throw new Error('FIXTURE_DURATION_INVALID');
    const numerator = Number(match[1]);
    const denominator = Number(match[2]);
    if (!Number.isSafeInteger(numerator) || !Number.isSafeInteger(denominator)) throw new Error('FIXTURE_DURATION_INVALID');
    return freezeDeep({numerator, denominator});
  };

  const fillerEvent = (measureOrdinal, eventOrdinal, onset, pitch) => {
    const suffix = `${String(measureOrdinal).padStart(3, '0')}-${String(eventOrdinal).padStart(2, '0')}`;
    const eventId = `fixture-event-${suffix}`;
    return {
      id: eventId,
      kind: 'note',
      onset,
      duration: {numerator: 1, denominator: 4},
      note: {
        id: `note-${eventId}`,
        pitch
      }
    };
  };

  const coherentMeasureEvents = (ordinal) => {
    const issue = fixture.issues.find((candidate) => candidate.location.measure === ordinal) ?? null;
    if (issue) {
      const issueEvent = {
        id: issue.location.event,
        kind: 'note',
        onset: {numerator: 0, denominator: 1},
        duration: parseDurationText(issue.event.duration),
        note: {
          id: `note-${issue.location.event}`,
          pitch: parsePitchText(issue.event.pitch)
        }
      };
      const closingPitch = FILLER_PITCHES[(ordinal + 2) % FILLER_PITCHES.length];
      return [
        issueEvent,
        fillerEvent(ordinal, 4, {numerator: 3, denominator: 4}, closingPitch)
      ];
    }

    const onsets = [
      {numerator: 0, denominator: 1},
      {numerator: 1, denominator: 4},
      {numerator: 1, denominator: 2},
      {numerator: 3, denominator: 4}
    ];
    return onsets.map((onset, index) => fillerEvent(
      ordinal,
      index + 1,
      onset,
      FILLER_PITCHES[(ordinal + index - 1) % FILLER_PITCHES.length]
    ));
  };

  const scoreInput = () => {
    const measures = Array.from({length: SCORE_MEASURE_COUNT}, (_, index) => {
      const ordinal = index + 1;
      return {
        id: `measure-${ordinal}`,
        ordinal,
        displayNumber: String(ordinal),
        voices: [{
          id: `voice-${ordinal}-1`,
          ordinal: 1,
          events: coherentMeasureEvents(ordinal)
        }]
      };
    });

    return freezeDeep({
      schemaVersion: '1.0.0',
      id: fixture.document.id,
      revision: {id: fixture.document.revision, parentId: null},
      source: {sha256: 'f'.repeat(64), format: 'synthetic', byteLength: null},
      parts: [{
        id: 'part-fixture-1',
        name: 'Teacher Review score',
        staves: [{id: 'staff-fixture-1', ordinal: 1, measures}]
      }]
    });
  };

  const score = runtime.createScoreDocument(scoreInput());
  const notation = runtime.emptyNotationDocument(score);
  session = runtime.createEditorSession(score, notation, 'osmd');

  const issueById = (issueId) => fixture.issues.find((issue) => issue.id === issueId) ?? null;
  const noteTokenForIssue = (issue) => session.renderRequest.manifest.entries.find((entry) =>
    entry.address.kind === 'note' && entry.address.eventId === issue.location.event
  )?.token ?? null;

  const selectIssue = (issueId) => {
    const issue = issueById(issueId);
    if (!issue) throw new Error('ISSUE_NOT_FOUND');
    const token = noteTokenForIssue(issue);
    if (!token) throw new Error('SEMANTIC_TARGET_NOT_FOUND');
    session = runtime.selectSessionRenderToken(session, token);
    return session;
  };

  const corePitch = (value) => {
    if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('PITCH_INVALID');
    const keys = Object.keys(value).sort();
    if (JSON.stringify(keys) !== JSON.stringify(['alter','octave','step'])) throw new Error('PITCH_INVALID');
    if (!value.alter || typeof value.alter !== 'object' || Array.isArray(value.alter)) throw new Error('PITCH_INVALID');
    if (value.alter.denominator !== 1 || !Number.isInteger(value.alter.numerator) || value.alter.numerator < -2 || value.alter.numerator > 2) throw new Error('PITCH_INVALID');
    if (!['A','B','C','D','E','F','G'].includes(value.step) || !Number.isInteger(value.octave) || value.octave < -1 || value.octave > 9) throw new Error('PITCH_INVALID');
    return freezeDeep({step: value.step, alter: value.alter.numerator, octave: value.octave});
  };

  const coreDuration = (value) => {
    if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('DURATION_INVALID');
    if (JSON.stringify(Object.keys(value).sort()) !== JSON.stringify(['denominator','numerator'])) throw new Error('DURATION_INVALID');
    if (!Number.isSafeInteger(value.numerator) || value.numerator <= 0 || !Number.isSafeInteger(value.denominator) || value.denominator <= 0) throw new Error('DURATION_INVALID');
    return freezeDeep({numerator: value.numerator, denominator: value.denominator});
  };

  const nextIdentity = () => {
    sequence += 1;
    const suffix = String(sequence).padStart(4, '0');
    return freezeDeep({
      transactionId: `e7h-tx-${suffix}`,
      commandId: `e7h-cmd-${suffix}`,
      nextRevisionId: `fixture-e7h-r${suffix}`
    });
  };

  const commitOperation = (issueId, operation) => {
    if (!operation || typeof operation !== 'object' || Array.isArray(operation)) throw new Error('OPERATION_INVALID');
    if (JSON.stringify(Object.keys(operation).sort()) !== JSON.stringify(['type','value'])) throw new Error('OPERATION_INVALID');
    selectIssue(issueId);
    const identity = nextIdentity();
    if (operation.type === 'set_pitch') {
      session = runtime.commitSessionScoreIntent(session, freezeDeep({version:'1.0.0', type:'SET_PITCH', pitch:corePitch(operation.value)}), identity);
    } else if (operation.type === 'set_effective_duration') {
      session = runtime.commitSessionScoreIntent(session, freezeDeep({version:'1.0.0', type:'SET_DURATION', duration:coreDuration(operation.value)}), identity);
    } else if (operation.type === 'set_dots') {
      if (!Number.isSafeInteger(operation.value) || operation.value < 0 || operation.value > 3) throw new Error('DOTS_INVALID');
      session = runtime.commitSessionNotationIntent(session, freezeDeep({version:'1.0.0', type:'SET_DOTS', value:operation.value}), identity);
    } else if (operation.type === 'remove_event') {
      throw new Error('OPERATION_NOT_MAPPED');
    } else {
      throw new Error('OPERATION_INVALID');
    }

    // Core edits invalidate selection by design. Re-select the same semantic
    // issue target on the new revision so Structured Edit shows current values.
    selectIssue(issueId);
    return getSessionSnapshot();
  };

  const getSessionSnapshot = () => freezeDeep({
    documentId: session.history.present.score.id,
    revisionId: session.history.present.score.revision.id,
    rendererFamily: session.rendererFamily,
    musicXml: session.renderRequest.musicXml,
    selectedKind: session.selection?.primary?.kind ?? null,
    inspector: session.inspector,
    scoreFixtureMeasureCount: SCORE_MEASURE_COUNT,
    authoritative: false,
    persistent: false
  });

  const navigate = (action) => {
    session = runtime.navigateSessionHistory(session, action);
    return getSessionSnapshot();
  };

  window.ScoreMosaicScoreEditorCoreBridge = freezeDeep({
    integrationVersion: INTEGRATION_VERSION,
    available: true,
    reason: null,
    authoritative: false,
    networkCapable: false,
    persistent: false,
    serverRevisionAuthority: false,
    approvalAuthority: false,
    publicationAuthority: false,
    syntheticFixtureMapping: true,
    scoreFixtureMeasureCount: SCORE_MEASURE_COUNT,
    coreCommit: CORE_COMMIT,
    getSessionSnapshot,
    selectIssue: (issueId) => {
      selectIssue(issueId);
      return getSessionSnapshot();
    },
    commitOperation,
    undo: () => navigate('UNDO'),
    redo: () => navigate('REDO')
  });
})();
