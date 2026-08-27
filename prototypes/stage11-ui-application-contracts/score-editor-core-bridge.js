(() => {
  'use strict';

  const fixture = window.ScoreMosaicFixture;
  const runtime = window.STScoreEditorCoreRuntime;
  const HAS_REAL_INPUT = Object.prototype.hasOwnProperty.call(window, 'ScoreMosaicRealScoreRuntimeInput');
  const realInput = HAS_REAL_INPUT ? window.ScoreMosaicRealScoreRuntimeInput : null;
  const CORE_COMMIT = 'b317abef915d1e16b37572221a38feb3e504450d';
  const INTEGRATION_VERSION = 'scoremosaic-st-score-editor-core-bridge-v1';
  const REAL_RUNTIME_VERSION = 'scoremosaic-real-score-runtime-v1';
  const SCORE_MEASURE_COUNT = 12;
  const CORE_ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
  const SHA256 = /^[a-f0-9]{64}$/;
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
  let realMode = false;
  let issueTargets = null;

  const freezeDeep = (value) => {
    if (value && typeof value === 'object' && !Object.isFrozen(value)) {
      Object.freeze(value);
      Object.keys(value).forEach((key) => freezeDeep(value[key]));
    }
    return value;
  };

  const exactKeys = (value, expected) => {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
    return JSON.stringify(Object.keys(value).sort()) === JSON.stringify([...expected].sort());
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
    automaticCorrectionAuthority: false,
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

  const validCoreTarget = (target) => {
    if (!target || typeof target !== 'object' || Array.isArray(target)) return false;
    if (target.kind === 'event') {
      return exactKeys(target, ['kind','eventId']) && CORE_ID.test(target.eventId);
    }
    if (target.kind === 'note') {
      return exactKeys(target, ['kind','eventId','noteId']) && CORE_ID.test(target.eventId) && CORE_ID.test(target.noteId);
    }
    return false;
  };

  const validateRealInput = (input) => {
    if (!exactKeys(input, [
      'version','coreCommit','scoreSource','synthetic','documentId','revisionId','canonicalSha256',
      'score','notation','issueTargets','authority'
    ])) return false;
    if (
      input.version !== REAL_RUNTIME_VERSION
      || input.coreCommit !== CORE_COMMIT
      || input.scoreSource !== 'canonical'
      || input.synthetic !== false
      || !CORE_ID.test(input.documentId)
      || !CORE_ID.test(input.revisionId)
      || !SHA256.test(input.canonicalSha256)
      || !input.score || typeof input.score !== 'object' || Array.isArray(input.score)
      || !input.notation || typeof input.notation !== 'object' || Array.isArray(input.notation)
      || !Array.isArray(input.issueTargets)
    ) return false;
    if (!exactKeys(input.authority, [
      'authoritative','networkCapable','persistent','serverRevisionAuthority',
      'approvalAuthority','publicationAuthority','automaticCorrectionAuthority'
    ])) return false;
    if (Object.values(input.authority).some((value) => value !== false)) return false;
    if (
      input.score.id !== input.documentId
      || input.score.revision?.id !== input.revisionId
      || input.score.source?.format !== 'canonical'
      || input.score.source?.sha256 !== input.canonicalSha256
      || input.notation.documentId !== input.documentId
      || input.notation.revisionId !== input.revisionId
    ) return false;
    const seenIssues = new Set();
    for (const item of input.issueTargets) {
      if (!exactKeys(item, ['issueId','canonicalEventId','coreTarget'])) return false;
      if (typeof item.issueId !== 'string' || item.issueId.length < 1 || item.issueId.length > 200) return false;
      if (typeof item.canonicalEventId !== 'string' || item.canonicalEventId.length < 1 || item.canonicalEventId.length > 200) return false;
      if (!validCoreTarget(item.coreTarget) || seenIssues.has(item.issueId)) return false;
      seenIssues.add(item.issueId);
    }
    return true;
  };

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
      note: {id: `note-${eventId}`, pitch}
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
        note: {id: `note-${issue.location.event}`, pitch: parsePitchText(issue.event.pitch)}
      };
      const closingPitch = FILLER_PITCHES[(ordinal + 2) % FILLER_PITCHES.length];
      return [issueEvent, fillerEvent(ordinal, 4, {numerator: 3, denominator: 4}, closingPitch)];
    }
    const onsets = [
      {numerator: 0, denominator: 1},
      {numerator: 1, denominator: 4},
      {numerator: 1, denominator: 2},
      {numerator: 3, denominator: 4}
    ];
    return onsets.map((onset, index) => fillerEvent(
      ordinal, index + 1, onset, FILLER_PITCHES[(ordinal + index - 1) % FILLER_PITCHES.length]
    ));
  };

  const fixtureScoreInput = () => {
    const measures = Array.from({length: SCORE_MEASURE_COUNT}, (_, index) => {
      const ordinal = index + 1;
      return {
        id: `measure-${ordinal}`,
        ordinal,
        displayNumber: String(ordinal),
        voices: [{id: `voice-${ordinal}-1`, ordinal: 1, events: coherentMeasureEvents(ordinal)}]
      };
    });
    return freezeDeep({
      schemaVersion: '1.0.0',
      id: fixture.document.id,
      revision: {id: fixture.document.revision, parentId: null},
      source: {sha256: 'f'.repeat(64), format: 'synthetic', byteLength: null},
      parts: [{id: 'part-fixture-1', name: 'Teacher Review score', staves: [{id: 'staff-fixture-1', ordinal: 1, measures}]}]
    });
  };

  const addressMatches = (address, target) => {
    if (!address || address.kind !== target.kind || address.eventId !== target.eventId) return false;
    return target.kind === 'event' || address.noteId === target.noteId;
  };

  const tokenForTarget = (target) => session.renderRequest.manifest.entries.find((entry) =>
    addressMatches(entry.address, target)
  )?.token ?? null;

  const initialize = () => {
    if (HAS_REAL_INPUT) {
      if (!validateRealInput(realInput)) return 'REAL_SCORE_INPUT_INVALID';
      try {
        const score = runtime.createScoreDocument(realInput.score);
        session = runtime.createEditorSession(score, realInput.notation, 'osmd');
      } catch (_) {
        return 'REAL_SCORE_RUNTIME_REJECTED';
      }
      if (
        session.history.present.score.id !== realInput.documentId
        || session.history.present.score.revision.id !== realInput.revisionId
        || session.renderRequest.documentId !== realInput.documentId
        || session.renderRequest.revisionId !== realInput.revisionId
      ) return 'REAL_SCORE_RUNTIME_MISMATCH';
      issueTargets = realInput.issueTargets;
      if (issueTargets.some((item) => tokenForTarget(item.coreTarget) === null)) return 'REAL_SCORE_TARGET_MISMATCH';
      realMode = true;
      return null;
    }
    if (!fixture || fixture.productionArtifact !== false || fixture.authoritativeTruth !== false) return 'FIXTURE_UNAVAILABLE';
    try {
      const score = runtime.createScoreDocument(fixtureScoreInput());
      const notation = runtime.emptyNotationDocument(score);
      session = runtime.createEditorSession(score, notation, 'osmd');
    } catch (_) {
      return 'FIXTURE_RUNTIME_REJECTED';
    }
    return null;
  };

  const initializationError = initialize();
  if (initializationError !== null) {
    window.ScoreMosaicScoreEditorCoreBridge = unavailable(initializationError);
    return;
  }

  const issueTargetById = (issueId) => {
    if (realMode) {
      return issueTargets.find((item) => item.issueId === issueId)?.coreTarget ?? null;
    }
    const issue = fixture.issues.find((candidate) => candidate.id === issueId) ?? null;
    if (!issue) return null;
    return {kind: 'note', eventId: issue.location.event, noteId: `note-${issue.location.event}`};
  };

  const selectIssue = (issueId) => {
    const target = issueTargetById(issueId);
    if (!target) throw new Error('ISSUE_NOT_FOUND');
    const token = tokenForTarget(target);
    if (!token) throw new Error('SEMANTIC_TARGET_NOT_FOUND');
    session = runtime.selectSessionRenderToken(session, token);
    return session;
  };

  const corePitch = (value) => {
    if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('PITCH_INVALID');
    if (JSON.stringify(Object.keys(value).sort()) !== JSON.stringify(['alter','octave','step'])) throw new Error('PITCH_INVALID');
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

  const allScoreIds = () => {
    const ids = new Set([session.history.present.score.id, session.history.present.score.revision.id]);
    for (const part of session.history.present.score.parts) {
      ids.add(part.id);
      for (const staff of part.staves) {
        ids.add(staff.id);
        for (const measure of staff.measures) {
          ids.add(measure.id);
          for (const voice of measure.voices) {
            ids.add(voice.id);
            for (const event of voice.events) {
              ids.add(event.id);
              if (event.kind === 'note') ids.add(event.note.id);
              if (event.kind === 'chord') event.notes.forEach((note) => ids.add(note.id));
            }
          }
        }
      }
    }
    return ids;
  };

  const nextIdentity = () => {
    sequence += 1;
    const suffix = String(sequence).padStart(4, '0');
    if (!realMode) return freezeDeep({
      transactionId: `e7h-tx-${suffix}`,
      commandId: `e7h-cmd-${suffix}`,
      nextRevisionId: `fixture-e7h-r${suffix}`
    });
    const occupied = allScoreIds();
    let candidate = `stse-local-r${suffix}`;
    let attempt = 0;
    while (occupied.has(candidate) && attempt < 100) {
      attempt += 1;
      candidate = `stse-local-r${suffix}-${attempt}`;
    }
    if (occupied.has(candidate)) throw new Error('LOCAL_REVISION_ID_EXHAUSTED');
    return freezeDeep({
      transactionId: `e7k-tx-${suffix}`,
      commandId: `e7k-cmd-${suffix}`,
      nextRevisionId: candidate
    });
  };

  const scoreMeasureCount = () => {
    let maximum = 0;
    for (const part of session.history.present.score.parts) {
      for (const staff of part.staves) maximum = Math.max(maximum, staff.measures.length);
    }
    return maximum;
  };

  const getSessionSnapshot = () => freezeDeep({
    documentId: session.history.present.score.id,
    revisionId: session.history.present.score.revision.id,
    rendererFamily: session.rendererFamily,
    musicXml: session.renderRequest.musicXml,
    selectedKind: session.selection?.primary?.kind ?? null,
    inspector: session.inspector,
    scoreFixtureMeasureCount: realMode ? null : SCORE_MEASURE_COUNT,
    scoreMeasureCount: scoreMeasureCount(),
    scoreSource: realMode ? 'canonical' : 'synthetic',
    syntheticFixtureMapping: !realMode,
    authoritative: false,
    persistent: false
  });

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
    selectIssue(issueId);
    return getSessionSnapshot();
  };

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
    automaticCorrectionAuthority: false,
    syntheticFixtureMapping: !realMode,
    scoreFixtureMeasureCount: realMode ? null : SCORE_MEASURE_COUNT,
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