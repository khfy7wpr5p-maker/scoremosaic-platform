'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const coreBundlePath = process.argv[2];
const bridgePath = process.argv[3] || 'prototypes/stage11-ui-application-contracts/score-editor-core-bridge.js';
if (!coreBundlePath) throw new Error('CORE_BUNDLE_PATH_REQUIRED');
const coreBundle = fs.readFileSync(coreBundlePath, 'utf8');
const bridgeSource = fs.readFileSync(bridgePath, 'utf8');

const HASH = 'a'.repeat(64);
const authority = () => ({
  authoritative: false,
  networkCapable: false,
  persistent: false,
  serverRevisionAuthority: false,
  approvalAuthority: false,
  publicationAuthority: false,
  automaticCorrectionAuthority: false
});

const runtimeInput = () => ({
  version: 'scoremosaic-real-score-runtime-v1',
  coreCommit: 'b317abef915d1e16b37572221a38feb3e504450d',
  scoreSource: 'canonical',
  synthetic: false,
  documentId: 'real-score-001',
  revisionId: 'real-rev-001',
  canonicalSha256: HASH,
  score: {
    schemaVersion: '1.0.0',
    id: 'real-score-001',
    revision: {id: 'real-rev-001', parentId: null},
    source: {sha256: HASH, format: 'canonical', byteLength: null},
    parts: [{
      id: 'real-part-001',
      name: 'Piano',
      staves: [{
        id: 'real-staff-001',
        ordinal: 1,
        measures: [{
          id: 'real-measure-001',
          ordinal: 1,
          displayNumber: '1',
          voices: [{
            id: 'real-voice-001',
            ordinal: 1,
            events: [
              {
                id: 'core-chord-001',
                kind: 'chord',
                onset: {numerator: 0, denominator: 1},
                duration: {numerator: 1, denominator: 4},
                notes: [
                  {id: 'core-note-c', pitch: {step: 'C', alter: 0, octave: 4}},
                  {id: 'core-note-e', pitch: {step: 'E', alter: 0, octave: 4}}
                ]
              },
              {
                id: 'core-rest-001',
                kind: 'rest',
                onset: {numerator: 1, denominator: 4},
                duration: {numerator: 3, denominator: 4}
              }
            ]
          }]
        }]
      }]
    }]
  },
  notation: {
    contractVersion: '1.0.0',
    documentId: 'real-score-001',
    revisionId: 'real-rev-001',
    measures: [{
      target: {kind: 'measure', documentId: 'real-score-001', revisionId: 'real-rev-001', partId: 'real-part-001', staffId: 'real-staff-001', measureId: 'real-measure-001', contractVersion: '1.0.0'},
      notation: {timeSignature: {beats: 4, beatType: 4}, keySignature: null, clef: null, barlines: []}
    }],
    events: [{
      target: {kind: 'event', documentId: 'real-score-001', revisionId: 'real-rev-001', partId: 'real-part-001', staffId: 'real-staff-001', measureId: 'real-measure-001', voiceId: 'real-voice-001', eventId: 'core-rest-001', contractVersion: '1.0.0'},
      notation: {dots: 1, beams: [], tuplet: null}
    }],
    notes: []
  },
  issueTargets: [
    {issueId: 'issue-c', canonicalEventId: 'canonical-note-c', coreTarget: {kind: 'note', eventId: 'core-chord-001', noteId: 'core-note-c'}},
    {issueId: 'issue-e', canonicalEventId: 'canonical-note-e', coreTarget: {kind: 'note', eventId: 'core-chord-001', noteId: 'core-note-e'}},
    {issueId: 'issue-rest', canonicalEventId: 'canonical-rest', coreTarget: {kind: 'event', eventId: 'core-rest-001'}}
  ],
  authority: authority()
});

const boot = (input, fixture) => {
  const window = {};
  if (input !== undefined) window.ScoreMosaicRealScoreRuntimeInput = input;
  if (fixture !== undefined) window.ScoreMosaicFixture = fixture;
  const context = vm.createContext({window, console});
  vm.runInContext(coreBundle, context, {filename: 'st-score-editor-core.runtime.js'});
  window.STScoreEditorCoreRuntime = context.STScoreEditorCoreRuntime;
  vm.runInContext(bridgeSource, context, {filename: 'score-editor-core-bridge.js'});
  return window.ScoreMosaicScoreEditorCoreBridge;
};

const inspectorField = (inspector, key) => inspector?.fields?.find((field) => field.key === key)?.value ?? null;

const bridge = boot(runtimeInput());
assert.equal(bridge.available, true);
assert.equal(bridge.syntheticFixtureMapping, false);
assert.equal(bridge.scoreFixtureMeasureCount, null);
assert.equal(bridge.networkCapable, false);
assert.equal(bridge.persistent, false);
assert.equal(bridge.serverRevisionAuthority, false);
assert.equal(bridge.approvalAuthority, false);
assert.equal(bridge.publicationAuthority, false);
assert.equal(bridge.automaticCorrectionAuthority, false);

const initial = bridge.getSessionSnapshot();
assert.equal(initial.scoreSource, 'canonical');
assert.equal(initial.scoreMeasureCount, 1);
assert.equal(initial.scoreFixtureMeasureCount, null);
assert.equal(initial.syntheticFixtureMapping, false);
assert.match(initial.musicXml, /<chord\/>/);
assert.match(initial.musicXml, /<step>E<\/step>/);

const selected = bridge.selectIssue('issue-e');
assert.equal(selected.selectedKind, 'note');
assert.equal(selected.inspector.targetKind, 'note');
assert.equal(selected.inspector.targetId, 'core-note-e');
assert.equal(inspectorField(selected.inspector, 'pitch'), 'E4');
assert.equal(inspectorField(selected.inspector, 'eventKind'), 'chord');
assert.equal(inspectorField(selected.inspector, 'duration'), '1/4');

const edited = bridge.commitOperation('issue-e', {
  type: 'set_pitch',
  value: {step: 'F', alter: {numerator: 1, denominator: 1}, octave: 4}
});
assert.match(edited.revisionId, /^stse-local-r0001/);
assert.equal(edited.selectedKind, 'note');
assert.equal(edited.inspector.targetKind, 'note');
assert.equal(edited.inspector.targetId, 'core-note-e');
assert.equal(inspectorField(edited.inspector, 'pitch'), 'F+14');
assert.match(edited.musicXml, /<step>F<\/step>/);
assert.match(edited.musicXml, /<alter>1<\/alter>/);

const rest = bridge.selectIssue('issue-rest');
assert.equal(rest.selectedKind, 'event');
assert.equal(rest.inspector.targetKind, 'event');
assert.equal(rest.inspector.targetId, 'core-rest-001');
assert.equal(inspectorField(rest.inspector, 'eventKind'), 'rest');
assert.equal(inspectorField(rest.inspector, 'duration'), '3/4');
const durationEdited = bridge.commitOperation('issue-rest', {
  type: 'set_effective_duration',
  value: {numerator: 1, denominator: 2}
});
assert.equal(durationEdited.selectedKind, 'event');
assert.equal(durationEdited.inspector.targetKind, 'event');
assert.equal(durationEdited.inspector.targetId, 'core-rest-001');
assert.equal(inspectorField(durationEdited.inspector, 'duration'), '1/2');

const fixtureThatMustNotBeUsed = {productionArtifact: false, authoritativeTruth: false, document: {}, issues: []};
const malformed = runtimeInput();
malformed.authority.networkCapable = true;
const rejected = boot(malformed, fixtureThatMustNotBeUsed);
assert.equal(rejected.available, false);
assert.equal(rejected.reason, 'REAL_SCORE_INPUT_INVALID');

const targetMismatch = runtimeInput();
targetMismatch.issueTargets[0].coreTarget.noteId = 'missing-note';
const mismatch = boot(targetMismatch, fixtureThatMustNotBeUsed);
assert.equal(mismatch.available, false);
assert.equal(mismatch.reason, 'REAL_SCORE_TARGET_MISMATCH');

console.log('E7-K real-score Core bridge exact-runtime behavior: PASS');
