'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync('prototypes/stage11-ui-application-contracts/score-editor-core-bridge.js', 'utf8');

const fixture = Object.freeze({
  fixtureVersion: 'test-fixture-v1',
  authoritativeTruth: false,
  productionArtifact: false,
  document: Object.freeze({id:'fixture-score-001',label:'Fixture',revision:'fixture-r3'}),
  issues: Object.freeze([
    Object.freeze({
      id:'issue-1',
      location:Object.freeze({measure:3,event:'event-003-04'}),
      event:Object.freeze({pitch:'E4',duration:'1/8',voice:'1'})
    })
  ])
});

const run = (runtime) => {
  const window = {ScoreMosaicFixture: fixture};
  if (runtime !== undefined) window.STScoreEditorCoreRuntime = runtime;
  const context = vm.createContext({window, Object, Array, JSON, String, Number, RegExp, Set, Error});
  vm.runInContext(source, context, {filename:'score-editor-core-bridge.js'});
  return window.ScoreMosaicScoreEditorCoreBridge;
};

const calls = [];
let currentPitch = 'E4';
let currentDuration = '1/8';
const inspector = () => ({
  version:'1.0.0',documentId:'fixture-score-001',revisionId:'fixture-r3',targetKind:'note',targetId:'note-event-003-04',
  fields:[
    {key:'pitch',value:currentPitch},
    {key:'eventKind',value:'note'},
    {key:'duration',value:currentDuration},
    {key:'onset',value:'0/1'}
  ]
});

const runtime = {
  runtimeVersion:'1.0.0',
  profile:Object.freeze({
    version:'1.0.0',productionRuntime:false,networkCapable:false,persistenceCapable:false,
    rendererAuthority:false,browserMutationAuthority:false,serverRevisionAuthority:false,
    approvalAuthority:false,publicationAuthority:false
  }),
  createScoreDocument(input) { calls.push(['createScoreDocument', input]); return input; },
  emptyNotationDocument(score) { return {contractVersion:'1.0.0',documentId:score.id,revisionId:score.revision.id,measures:[],events:[],notes:[]}; },
  createEditorSession(score, notation) {
    return {
      rendererFamily:'osmd',
      history:{present:{score,notation}},
      renderRequest:{musicXml:'<score-partwise/>',manifest:{entries:[{token:'stse-r1-note',address:{kind:'note',eventId:'event-003-04',noteId:'note-event-003-04'}}]}},
      selection:null,
      inspector:null
    };
  },
  selectSessionRenderToken(session, token) {
    calls.push(['select', token]);
    return {...session,selection:{primary:{kind:'note',eventId:'event-003-04',noteId:'note-event-003-04'}},inspector:inspector()};
  },
  commitSessionScoreIntent(session, intent, identity) {
    calls.push(['score', intent, identity]);
    if (intent.type === 'SET_PITCH') {
      const accidental = intent.pitch.alter === 0 ? '' : intent.pitch.alter > 0 ? `+${intent.pitch.alter}` : String(intent.pitch.alter);
      currentPitch = `${intent.pitch.step}${accidental}${intent.pitch.octave}`;
    }
    if (intent.type === 'SET_DURATION') currentDuration = `${intent.duration.numerator}/${intent.duration.denominator}`;
    return {...session,history:{present:{score:{...session.history.present.score,revision:{id:identity.nextRevisionId,parentId:session.history.present.score.revision.id}},notation:{...session.history.present.notation,revisionId:identity.nextRevisionId}}},selection:null,inspector:null,renderRequest:{...session.renderRequest,musicXml:'<score-partwise><edited/></score-partwise>'}};
  },
  commitSessionNotationIntent(session, intent, identity) {
    calls.push(['notation', intent, identity]);
    return {...session,history:{present:{score:{...session.history.present.score,revision:{id:identity.nextRevisionId,parentId:session.history.present.score.revision.id}},notation:{...session.history.present.notation,revisionId:identity.nextRevisionId}}},selection:null,inspector:null,renderRequest:{...session.renderRequest,musicXml:'<score-partwise><dot/></score-partwise>'}};
  },
  navigateSessionHistory(session, action) { calls.push(['history', action]); return session; }
};

const missing = run(undefined);
assert.equal(missing.available, false);
assert.equal(missing.reason, 'RUNTIME_UNAVAILABLE');
assert.equal(missing.networkCapable, false);
assert.equal(missing.serverRevisionAuthority, false);

const bad = run({...runtime, profile:{...runtime.profile, networkCapable:true}});
assert.equal(bad.available, false);
assert.equal(bad.reason, 'RUNTIME_PROFILE_MISMATCH');

calls.length = 0;
currentPitch = 'E4';
currentDuration = '1/8';
const bridge = run(runtime);
assert.equal(bridge.available, true);
assert.equal(bridge.authoritative, false);
assert.equal(bridge.persistent, false);
assert.equal(bridge.coreCommit, 'b317abef915d1e16b37572221a38feb3e504450d');
assert.equal(bridge.scoreFixtureMeasureCount, 12);
assert.equal(bridge.getSessionSnapshot().scoreFixtureMeasureCount, 12);
assert.equal(bridge.getSessionSnapshot().revisionId, 'fixture-r3');

const createdScore = calls.find((call) => call[0] === 'createScoreDocument')[1];
const measures = createdScore.parts[0].staves[0].measures;
assert.equal(measures.length, 12);
assert.deepEqual(measures.map((measure) => measure.ordinal), Array.from({length:12}, (_, index) => index + 1));
assert.equal(measures[0].voices[0].events.length, 4, 'normal fixture measures must contain enough musical context');
assert.ok(measures[0].voices[0].events.every((event) => event.note.pitch.octave >= 4 && event.note.pitch.octave <= 5));
assert.equal(measures[2].voices[0].events[0].id, 'event-003-04', 'issue event must live in its real fixture measure');
assert.equal(measures[2].voices[0].events[0].note.pitch.step, 'E');

const selected = bridge.selectIssue('issue-1');
assert.deepEqual(calls.find((call) => call[0] === 'select'), ['select','stse-r1-note']);
assert.equal(selected.inspector.targetKind, 'note');
assert.equal(selected.inspector.fields.find((field) => field.key === 'pitch').value, 'E4');

const edited = bridge.commitOperation('issue-1', {type:'set_pitch',value:{step:'F',alter:{numerator:1,denominator:1},octave:4}});
const scoreCall = calls.find((call) => call[0] === 'score');
assert.equal(JSON.stringify(scoreCall[1]), JSON.stringify({version:'1.0.0',type:'SET_PITCH',pitch:{step:'F',alter:1,octave:4}}));
assert.match(scoreCall[2].nextRevisionId, /^fixture-e7h-r\d{4}$/);
assert.equal(edited.selectedKind, 'note', 'edited semantic target must be reselected on the new revision');
assert.equal(edited.inspector.fields.find((field) => field.key === 'pitch').value, 'F+14');
assert.ok(calls.filter((call) => call[0] === 'select').length >= 3, 'commit must reselect the semantic target after selection invalidation');

bridge.commitOperation('issue-1', {type:'set_dots',value:2});
const notationCall = calls.find((call) => call[0] === 'notation');
assert.equal(JSON.stringify(notationCall[1]), JSON.stringify({version:'1.0.0',type:'SET_DOTS',value:2}));

assert.throws(() => bridge.commitOperation('issue-1', {type:'set_dots',value:4}), /DOTS_INVALID/);
assert.throws(() => bridge.commitOperation('issue-1', {type:'remove_event',value:null}), /OPERATION_NOT_MAPPED/);
assert.throws(() => bridge.commitOperation('missing', {type:'set_dots',value:1}), /ISSUE_NOT_FOUND/);

bridge.undo();
assert.ok(calls.some((call) => call[0] === 'history' && call[1] === 'UNDO'));

console.log('E7-H Score Editor Core bridge behavior: PASS');
