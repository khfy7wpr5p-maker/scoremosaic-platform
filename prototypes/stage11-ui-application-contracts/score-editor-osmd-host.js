(() => {
  'use strict';

  const HOST_VERSION = 'scoremosaic-osmd-host-v1';
  const bridge = window.ScoreMosaicScoreEditorCoreBridge;
  const profile = window.ScoreMosaicRendererProfile;
  const Osmd = window.opensheetmusicdisplay?.OpenSheetMusicDisplay;
  const host = document.getElementById('score-render-host');
  const fallback = document.getElementById('score-fixture-fallback');
  let renderer = null;
  let lastRenderedRevision = null;
  let renderQueue = Promise.resolve();

  const freeze = (value) => Object.freeze(value);
  const unavailable = (reason) => freeze({
    hostVersion: HOST_VERSION,
    available: false,
    reason,
    authoritative: false,
    presentationOnly: true,
    coordinatesAuthoritative: false,
    domIdsAuthoritative: false,
    rendererObjectsAuthoritative: false,
    networkCapable: false,
    persistent: false,
    serverRevisionAuthority: false,
    approvalAuthority: false,
    publicationAuthority: false
  });

  const safeBridge = bridge?.available === true
    && bridge.authoritative === false
    && bridge.networkCapable === false
    && bridge.persistent === false
    && bridge.serverRevisionAuthority === false
    && bridge.approvalAuthority === false
    && bridge.publicationAuthority === false
    && typeof bridge.getSessionSnapshot === 'function';

  const safeProfile = profile?.contract === 'SCOREMOSAIC_LOCAL_RENDERER_PROFILE'
    && profile.version === '1.0.0'
    && profile.family === 'osmd'
    && profile.packageName === 'opensheetmusicdisplay'
    && profile.packageVersion === '2.1.1'
    && profile.license === 'BSD-3-Clause'
    && profile.presentationOnly === true
    && profile.coordinatesAuthoritative === false
    && profile.domIdsAuthoritative === false
    && profile.rendererObjectsAuthoritative === false
    && profile.networkUseAllowed === false
    && profile.persistent === false;

  if (!safeBridge) {
    window.ScoreMosaicScoreEditorOsmdHost = unavailable('CORE_BRIDGE_UNAVAILABLE');
    return;
  }
  if (!safeProfile) {
    window.ScoreMosaicScoreEditorOsmdHost = unavailable('RENDERER_PROFILE_MISMATCH');
    return;
  }
  if (typeof Osmd !== 'function' || !host || !fallback) {
    window.ScoreMosaicScoreEditorOsmdHost = unavailable('OSMD_HOST_UNAVAILABLE');
    return;
  }

  const assertMusicXml = (snapshot) => {
    if (!snapshot || snapshot.rendererFamily !== 'osmd') throw new Error('RENDERER_FAMILY_MISMATCH');
    if (typeof snapshot.revisionId !== 'string' || snapshot.revisionId.length === 0) throw new Error('REVISION_INVALID');
    if (typeof snapshot.musicXml !== 'string') throw new Error('MUSICXML_INVALID');
    const xml = snapshot.musicXml.trim();
    if (xml.length === 0 || !xml.includes('<score-partwise') || /^https?:/i.test(xml)) throw new Error('MUSICXML_INVALID');
    return xml;
  };

  const renderOnce = async () => {
    const snapshot = bridge.getSessionSnapshot();
    const musicXml = assertMusicXml(snapshot);
    if (renderer === null) {
      renderer = new Osmd(host, {
        autoResize: true,
        drawTitle: false,
        followCursor: false
      });
    }
    await renderer.load(musicXml);
    renderer.render();
    host.hidden = false;
    fallback.hidden = true;
    lastRenderedRevision = snapshot.revisionId;
    host.dataset.renderedRevision = snapshot.revisionId;
    return freeze({
      revisionId: snapshot.revisionId,
      rendererFamily: 'osmd',
      authoritative: false,
      presentationOnly: true
    });
  };

  const renderCurrentSession = () => {
    renderQueue = renderQueue.then(renderOnce, renderOnce).catch((error) => {
      host.hidden = true;
      fallback.hidden = false;
      host.removeAttribute('data-rendered-revision');
      throw error;
    });
    return renderQueue;
  };

  window.ScoreMosaicScoreEditorOsmdHost = freeze({
    hostVersion: HOST_VERSION,
    available: true,
    reason: null,
    authoritative: false,
    presentationOnly: true,
    coordinatesAuthoritative: false,
    domIdsAuthoritative: false,
    rendererObjectsAuthoritative: false,
    networkCapable: false,
    persistent: false,
    serverRevisionAuthority: false,
    approvalAuthority: false,
    publicationAuthority: false,
    rendererPackage: 'opensheetmusicdisplay',
    rendererVersion: '2.1.1',
    getLastRenderedRevision: () => lastRenderedRevision,
    renderCurrentSession
  });

  renderCurrentSession().catch(() => {
    // The fixture fallback remains visible. Rendering never creates authority.
  });
})();
