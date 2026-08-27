'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync('prototypes/stage11-ui-application-contracts/score-editor-osmd-host.js', 'utf8');

const exactProfile = Object.freeze({
  contract:'SCOREMOSAIC_LOCAL_RENDERER_PROFILE',
  version:'1.0.0',
  family:'osmd',
  packageName:'opensheetmusicdisplay',
  packageVersion:'2.1.1',
  license:'BSD-3-Clause',
  presentationOnly:true,
  coordinatesAuthoritative:false,
  domIdsAuthoritative:false,
  rendererObjectsAuthoritative:false,
  networkUseAllowed:false,
  persistent:false
});

const makeBridge = (snapshotRef) => Object.freeze({
  available:true,
  authoritative:false,
  networkCapable:false,
  persistent:false,
  serverRevisionAuthority:false,
  approvalAuthority:false,
  publicationAuthority:false,
  getSessionSnapshot:() => snapshotRef.current
});

const run = ({bridge, profile=exactProfile, failLoad=false, emptyRender=false}={}) => {
  let hasSvg = false;
  const host = {
    hidden:true,
    dataset:{},
    textContent:'',
    removeAttribute(name){if(name==='data-rendered-revision')delete this.dataset.renderedRevision;},
    querySelector(selector){return selector==='svg' && hasSvg ? {} : null;}
  };
  const fallback = {hidden:false};
  const calls = [];
  class FakeOsmd {
    constructor(target, options) {
      calls.push(['constructor',target,options,target.hidden]);
    }
    async load(xml) {
      calls.push(['load',xml,host.hidden]);
      if(failLoad)throw new Error('load failed');
    }
    render() {
      calls.push(['render',host.hidden]);
      if(!emptyRender)hasSvg=true;
    }
  }
  const window = {
    ScoreMosaicScoreEditorCoreBridge:bridge,
    ScoreMosaicRendererProfile:profile,
    opensheetmusicdisplay:{OpenSheetMusicDisplay:FakeOsmd}
  };
  const document = {getElementById(id){return id==='score-render-host'?host:id==='score-fixture-fallback'?fallback:null;}};
  const context = vm.createContext({window,document,Object,Promise,Error,RegExp});
  vm.runInContext(source, context, {filename:'score-editor-osmd-host.js'});
  return {window,host,fallback,calls};
};

(async () => {
  const snapshotRef = {current:{revisionId:'fixture-r1',rendererFamily:'osmd',musicXml:'<score-partwise version="4.0"></score-partwise>'}};
  const result = run({bridge:makeBridge(snapshotRef)});
  const api = result.window.ScoreMosaicScoreEditorOsmdHost;
  assert.equal(api.available,true);
  assert.equal(api.authoritative,false);
  assert.equal(api.presentationOnly,true);
  assert.equal(api.coordinatesAuthoritative,false);
  assert.equal(api.domIdsAuthoritative,false);
  assert.equal(api.rendererObjectsAuthoritative,false);
  assert.equal(api.networkCapable,false);
  assert.equal(api.serverRevisionAuthority,false);

  await api.renderCurrentSession();
  assert.equal(result.host.hidden,false);
  assert.equal(result.fallback.hidden,true);
  assert.equal(result.host.dataset.renderState,'rendered');
  assert.equal(result.host.dataset.renderedRevision,'fixture-r1');
  assert.equal(api.getLastRenderError(),null);
  assert.ok(result.calls.some((call)=>call[0]==='load' && call[1].includes('<score-partwise')));
  assert.ok(result.calls.some((call)=>call[0]==='render'));
  assert.ok(result.calls.filter((call)=>['constructor','load','render'].includes(call[0])).every((call)=>call.at(-1)===false), 'OSMD must never layout inside a hidden host');

  snapshotRef.current={revisionId:'fixture-e7h-r0001',rendererFamily:'osmd',musicXml:'<score-partwise version="4.0"><part-list/></score-partwise>'};
  await api.renderCurrentSession();
  assert.equal(api.getLastRenderedRevision(),'fixture-e7h-r0001');
  assert.equal(result.host.dataset.renderedRevision,'fixture-e7h-r0001');

  const badProfile = run({bridge:makeBridge(snapshotRef),profile:{...exactProfile,networkUseAllowed:true}});
  assert.equal(badProfile.window.ScoreMosaicScoreEditorOsmdHost.available,false);
  assert.equal(badProfile.window.ScoreMosaicScoreEditorOsmdHost.reason,'RENDERER_PROFILE_MISMATCH');
  assert.equal(badProfile.fallback.hidden,false);
  assert.equal(badProfile.host.hidden,false);
  assert.equal(badProfile.host.dataset.renderError,'RENDERER_PROFILE_MISMATCH');

  const noBridge = run({bridge:null});
  assert.equal(noBridge.window.ScoreMosaicScoreEditorOsmdHost.available,false);
  assert.equal(noBridge.window.ScoreMosaicScoreEditorOsmdHost.reason,'CORE_BRIDGE_UNAVAILABLE');
  assert.equal(noBridge.host.dataset.renderError,'CORE_BRIDGE_UNAVAILABLE');

  const failing = run({bridge:makeBridge(snapshotRef),failLoad:true});
  await failing.window.ScoreMosaicScoreEditorOsmdHost.renderCurrentSession().catch(()=>{});
  assert.equal(failing.host.hidden,false);
  assert.equal(failing.fallback.hidden,false);
  assert.equal(failing.host.dataset.renderState,'error');
  assert.equal(failing.host.dataset.renderError,'OSMD_RENDER_FAILED');
  assert.match(failing.host.textContent,/Score renderer unavailable/);

  const empty = run({bridge:makeBridge(snapshotRef),emptyRender:true});
  await empty.window.ScoreMosaicScoreEditorOsmdHost.renderCurrentSession().catch(()=>{});
  assert.equal(empty.fallback.hidden,false);
  assert.equal(empty.host.dataset.renderError,'OSMD_RENDER_FAILED');

  const urlSnapshot={current:{revisionId:'x',rendererFamily:'osmd',musicXml:'https://example.invalid/score.musicxml'}};
  const urlCase=run({bridge:makeBridge(urlSnapshot)});
  await urlCase.window.ScoreMosaicScoreEditorOsmdHost.renderCurrentSession().catch(()=>{});
  assert.equal(urlCase.host.hidden,false);
  assert.equal(urlCase.fallback.hidden,false);
  assert.equal(urlCase.host.dataset.renderError,'MUSICXML_INVALID');

  console.log('E7-H OSMD host behavior: PASS');
})().catch((error)=>{console.error(error);process.exitCode=1;});
