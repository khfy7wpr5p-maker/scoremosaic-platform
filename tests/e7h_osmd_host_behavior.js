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

const makeButton = (label) => {
  const listeners = new Map();
  const attributes = new Map();
  return {
    id:'',
    disabled:true,
    textContent:label,
    setAttribute(name,value){attributes.set(name,String(value));},
    getAttribute(name){return attributes.get(name) ?? null;},
    addEventListener(type,listener){listeners.set(type,listener);},
    click(){listeners.get('click')?.();}
  };
};

const run = ({bridge, profile=exactProfile, failLoad=false, emptyRender=false, hostWidth=640}={}) => {
  let hasSvg = false;
  let currentHostWidth = hostWidth;
  const host = {
    hidden:true,
    dataset:{},
    textContent:'',
    get clientWidth(){return currentHostWidth;},
    getBoundingClientRect(){return {width:currentHostWidth};},
    removeAttribute(name){if(name==='data-rendered-revision')delete this.dataset.renderedRevision;},
    querySelector(selector){return selector==='svg' && hasSvg ? {} : null;}
  };
  const fallback = {hidden:false};
  const fitWidthButton = makeButton('Fit width');
  const zoom100Button = makeButton('100%');
  const scorePanel = {
    get clientWidth(){return currentHostWidth;},
    getBoundingClientRect(){return {width:currentHostWidth};},
    querySelectorAll(selector){return selector==='.panel-actions button' ? [fitWidthButton,zoom100Button] : [];}
  };
  const calls = [];
  class FakeOsmd {
    constructor(target, options) {
      this.options = options;
      this.zoom = 1.0;
      calls.push(['constructor',target,options,target.hidden]);
    }
    async load(xml) {
      calls.push(['load',xml,host.hidden]);
      if(failLoad)throw new Error('load failed');
    }
    render() {
      calls.push(['render',host.hidden,this.zoom]);
      if(!emptyRender)hasSvg=true;
    }
    clear() {
      calls.push(['clear']);
      hasSvg=false;
    }
  }
  const window = {
    ScoreMosaicScoreEditorCoreBridge:bridge,
    ScoreMosaicRendererProfile:profile,
    opensheetmusicdisplay:{OpenSheetMusicDisplay:FakeOsmd}
  };
  const document = {
    getElementById(id){return id==='score-render-host'?host:id==='score-fixture-fallback'?fallback:null;},
    querySelector(selector){return selector==='.score-panel'?scorePanel:null;}
  };
  const context = vm.createContext({window,document,Object,Promise,Error,RegExp,Array,Number,Math});
  vm.runInContext(source, context, {filename:'score-editor-osmd-host.js'});
  return {
    window,host,fallback,calls,fitWidthButton,zoom100Button,
    setHostWidth(width){currentHostWidth=width;}
  };
};

(async () => {
  const snapshotRef = {current:{revisionId:'fixture-r1',rendererFamily:'osmd',musicXml:'<score-partwise version="4.0"></score-partwise>'}};
  const result = run({bridge:makeBridge(snapshotRef),hostWidth:640});
  const api = result.window.ScoreMosaicScoreEditorOsmdHost;
  assert.equal(api.available,true);
  assert.equal(api.authoritative,false);
  assert.equal(api.presentationOnly,true);
  assert.equal(api.coordinatesAuthoritative,false);
  assert.equal(api.domIdsAuthoritative,false);
  assert.equal(api.rendererObjectsAuthoritative,false);
  assert.equal(api.networkCapable,false);
  assert.equal(api.serverRevisionAuthority,false);
  assert.equal(api.presentationControls,true);
  assert.deepEqual(JSON.parse(JSON.stringify(api.fitWidthPolicy)),{minZoom:1.45,maxZoom:1.9,referenceWidth:380,rerenderWidthDelta:32});
  assert.equal(api.getViewMode(),'fit-width');
  assert.equal(result.fitWidthButton.disabled,false);
  assert.equal(result.zoom100Button.disabled,false);
  assert.equal(result.fitWidthButton.getAttribute('aria-pressed'),'true');
  assert.equal(result.zoom100Button.getAttribute('aria-pressed'),'false');

  await api.renderCurrentSession();
  assert.equal(result.host.hidden,false);
  assert.equal(result.fallback.hidden,true);
  assert.equal(result.host.dataset.renderState,'rendered');
  assert.equal(result.host.dataset.renderedRevision,'fixture-r1');
  assert.equal(result.host.dataset.viewMode,'fit-width');
  assert.equal(api.getLastRenderError(),null);
  const initialZoom = api.getPresentationZoom();
  assert.ok(initialZoom >= 1.45 && initialZoom <= 1.9);
  assert.ok(initialZoom > 1.0);
  assert.equal(Number(result.host.dataset.presentationZoom),Number(initialZoom.toFixed(2)));
  assert.match(result.fitWidthButton.getAttribute('aria-label'),/current scale 168 percent|current scale 169 percent/);
  assert.ok(result.calls.some((call)=>call[0]==='load' && call[1].includes('<score-partwise')));
  assert.ok(result.calls.some((call)=>call[0]==='render' && call[2]===initialZoom));
  assert.ok(result.calls.filter((call)=>call[0]==='constructor').every((call)=>call[3]===false), 'OSMD constructor must never receive a hidden host');
  assert.ok(result.calls.filter((call)=>call[0]==='load').every((call)=>call[2]===false), 'OSMD load must never receive a hidden host');
  assert.ok(result.calls.filter((call)=>call[0]==='render').every((call)=>call[1]===false), 'OSMD render must never receive a hidden host');
  const fitConstructor = result.calls.find((call)=>call[0]==='constructor');
  assert.equal(fitConstructor[2].autoResize,false);
  assert.equal(fitConstructor[2].stretchLastSystemLine,true);

  await api.setViewMode('100');
  assert.equal(api.getViewMode(),'100');
  assert.equal(api.getPresentationZoom(),1.0);
  assert.equal(Number(result.host.dataset.presentationZoom),1.0);
  assert.equal(result.host.dataset.viewMode,'100');
  assert.equal(result.fitWidthButton.getAttribute('aria-pressed'),'false');
  assert.equal(result.zoom100Button.getAttribute('aria-pressed'),'true');
  const constructorsAfter100 = result.calls.filter((call)=>call[0]==='constructor');
  const nativeConstructor = constructorsAfter100.at(-1);
  assert.equal(nativeConstructor[2].autoResize,false);
  assert.equal(nativeConstructor[2].stretchLastSystemLine,false);
  assert.equal(result.calls.filter((call)=>call[0]==='render').at(-1)[2],1.0);

  await api.setViewMode('fit-width');
  assert.equal(api.getViewMode(),'fit-width');
  assert.ok(api.getPresentationZoom() > 1.0);
  const constructorsAfterFit = result.calls.filter((call)=>call[0]==='constructor');
  const finalFitConstructor = constructorsAfterFit.at(-1);
  assert.equal(finalFitConstructor[2].autoResize,false);
  assert.equal(finalFitConstructor[2].stretchLastSystemLine,true);
  await assert.rejects(api.setViewMode('150'), /VIEW_MODE_INVALID/);

  const beforeResponsiveZoom = api.getPresentationZoom();
  result.setHostWidth(800);
  const responsive = await api.refreshResponsiveLayout();
  assert.equal(responsive.rerendered,true);
  assert.equal(api.getPresentationZoom(),1.9);
  assert.ok(api.getPresentationZoom() > beforeResponsiveZoom);
  const stable = await api.refreshResponsiveLayout();
  assert.equal(stable.rerendered,false);

  snapshotRef.current={revisionId:'fixture-e7h-r0001',rendererFamily:'osmd',musicXml:'<score-partwise version="4.0"><part-list/></score-partwise>'};
  const clearsBeforeSessionRerender = result.calls.filter((call)=>call[0]==='clear').length;
  const constructorsBeforeSessionRerender = result.calls.filter((call)=>call[0]==='constructor').length;
  await api.renderCurrentSession();
  assert.equal(api.getLastRenderedRevision(),'fixture-e7h-r0001');
  assert.equal(result.host.dataset.renderedRevision,'fixture-e7h-r0001');
  assert.equal(result.calls.filter((call)=>call[0]==='clear').length,clearsBeforeSessionRerender+1);
  assert.equal(result.calls.filter((call)=>call[0]==='constructor').length,constructorsBeforeSessionRerender+1);

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
