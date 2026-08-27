(() => {
  'use strict';

  const HOST_VERSION = 'scoremosaic-osmd-host-v1';
  const VIEW_MODES = Object.freeze(['fit-width', '100']);
  const FIT_WIDTH_POLICY = Object.freeze({
    minZoom: 1.45,
    maxZoom: 1.9,
    referenceWidth: 380,
    rerenderWidthDelta: 32
  });
  const bridge = window.ScoreMosaicScoreEditorCoreBridge;
  const profile = window.ScoreMosaicRendererProfile;
  const Osmd = window.opensheetmusicdisplay?.OpenSheetMusicDisplay;
  const host = document.getElementById('score-render-host');
  const fallback = document.getElementById('score-fixture-fallback');
  const scorePanel = document.querySelector?.('.score-panel') ?? null;
  const presentationButtons = Array.from(scorePanel?.querySelectorAll?.('.panel-actions button') ?? []);
  const fitWidthButton = presentationButtons.find((button) => button.textContent?.trim() === 'Fit width') ?? null;
  const zoom100Button = presentationButtons.find((button) => button.textContent?.trim() === '100%') ?? null;
  let renderer = null;
  let lastRenderedRevision = null;
  let lastRenderError = null;
  let renderQueue = Promise.resolve();
  let viewMode = 'fit-width';
  let presentationZoom = 1.0;
  let lastFitWidthWidth = null;
  let resizeObserver = null;

  const freeze = (value) => Object.freeze(value);
  const clamp = (value, minimum, maximum) => Math.min(maximum, Math.max(minimum, value));
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

  const knownRenderError = (error) => {
    const message = error instanceof Error ? error.message : '';
    if (['RENDERER_FAMILY_MISMATCH', 'REVISION_INVALID', 'MUSICXML_INVALID'].includes(message)) return message;
    return 'OSMD_RENDER_FAILED';
  };

  const presentFailure = (code) => {
    lastRenderError = code;
    lastRenderedRevision = null;
    if (host) {
      host.hidden = false;
      host.dataset.renderState = 'error';
      host.dataset.renderError = code;
      host.removeAttribute('data-rendered-revision');
      host.textContent = `Score renderer unavailable (${code}). Fixture fallback remains visible.`;
    }
    if (fallback) fallback.hidden = false;
  };

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
    presentFailure('CORE_BRIDGE_UNAVAILABLE');
    window.ScoreMosaicScoreEditorOsmdHost = unavailable('CORE_BRIDGE_UNAVAILABLE');
    return;
  }
  if (!safeProfile) {
    presentFailure('RENDERER_PROFILE_MISMATCH');
    window.ScoreMosaicScoreEditorOsmdHost = unavailable('RENDERER_PROFILE_MISMATCH');
    return;
  }
  if (typeof Osmd !== 'function' || !host || !fallback) {
    presentFailure('OSMD_HOST_UNAVAILABLE');
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

  const measuredWidth = () => {
    const candidates = [Number(host.clientWidth), Number(scorePanel?.clientWidth)];
    const width = candidates.find((candidate) => Number.isFinite(candidate) && candidate > 0);
    return width ?? FIT_WIDTH_POLICY.referenceWidth;
  };

  const computeFitWidthZoom = (width = measuredWidth()) => {
    const raw = width / FIT_WIDTH_POLICY.referenceWidth;
    return clamp(raw, FIT_WIDTH_POLICY.minZoom, FIT_WIDTH_POLICY.maxZoom);
  };

  const rendererOptions = () => freeze({
    // ScoreMosaic owns responsive rerendering through the single ResizeObserver
    // below. OSMD autoResize is intentionally disabled to prevent a second,
    // competing render lifecycle from appending another presentation surface.
    autoResize: false,
    drawTitle: false,
    followCursor: false,
    stretchLastSystemLine: viewMode === 'fit-width'
  });

  const updatePresentationControls = () => {
    if (!fitWidthButton || !zoom100Button) return;
    fitWidthButton.id = 'score-fit-width';
    zoom100Button.id = 'score-zoom-100';
    fitWidthButton.disabled = false;
    zoom100Button.disabled = false;
    fitWidthButton.setAttribute('aria-pressed', String(viewMode === 'fit-width'));
    zoom100Button.setAttribute('aria-pressed', String(viewMode === '100'));
    fitWidthButton.setAttribute('aria-label', `Fit rendered score to the available score-view width with bounded automatic zoom; current scale ${Math.round(presentationZoom * 100)} percent`);
    zoom100Button.setAttribute('aria-label', 'Show rendered score at normal 100 percent engraving scale');
  };

  const resetRenderer = () => {
    try {
      renderer?.clear?.();
    } catch {
      // Renderer cleanup is presentation-only. A fresh instance is still used below.
    }
    renderer = null;
    host.textContent = '';
  };

  const renderOnce = async () => {
    const snapshot = bridge.getSessionSnapshot();
    const musicXml = assertMusicXml(snapshot);

    // OSMD must receive a measurable container. Rendering into `hidden`
    // can produce a zero-width/blank SVG while still calling render().
    host.hidden = false;
    host.dataset.renderState = 'loading';
    host.dataset.viewMode = viewMode;
    delete host.dataset.renderError;
    if (renderer === null) {
      host.textContent = '';
      renderer = new Osmd(host, rendererOptions());
    }

    await renderer.load(musicXml);
    presentationZoom = viewMode === 'fit-width' ? computeFitWidthZoom() : 1.0;
    renderer.zoom = presentationZoom;
    renderer.render();

    const svg = host.querySelector?.('svg') ?? null;
    if (!svg) throw new Error('OSMD_RENDER_EMPTY');

    fallback.hidden = true;
    lastRenderError = null;
    lastRenderedRevision = snapshot.revisionId;
    if (viewMode === 'fit-width') lastFitWidthWidth = measuredWidth();
    host.dataset.renderState = 'rendered';
    host.dataset.renderedRevision = snapshot.revisionId;
    host.dataset.viewMode = viewMode;
    host.dataset.presentationZoom = presentationZoom.toFixed(2);
    updatePresentationControls();
    return freeze({
      revisionId: snapshot.revisionId,
      rendererFamily: 'osmd',
      viewMode,
      presentationZoom,
      authoritative: false,
      presentationOnly: true
    });
  };

  const enqueueRender = (operation) => {
    const task = renderQueue.then(operation, operation);
    renderQueue = task.catch(() => undefined);
    return task.catch((error) => {
      resetRenderer();
      presentFailure(knownRenderError(error));
      throw error;
    });
  };

  const renderCurrentSession = () => enqueueRender(async () => {
    // Every real session rerender gets a fresh OSMD surface. This prevents
    // edit-driven rerenders from retaining an older SVG alongside the new one.
    resetRenderer();
    return renderOnce();
  });

  const setViewMode = (nextMode) => {
    if (!VIEW_MODES.includes(nextMode)) return Promise.reject(new Error('VIEW_MODE_INVALID'));
    return enqueueRender(async () => {
      viewMode = nextMode;
      presentationZoom = nextMode === '100' ? 1.0 : presentationZoom;
      updatePresentationControls();
      resetRenderer();
      return renderOnce();
    });
  };

  const refreshResponsiveLayout = () => {
    if (viewMode !== 'fit-width' || lastRenderedRevision === null) {
      return Promise.resolve(freeze({rerendered: false, viewMode, presentationZoom}));
    }
    const width = measuredWidth();
    if (lastFitWidthWidth !== null && Math.abs(width - lastFitWidthWidth) < FIT_WIDTH_POLICY.rerenderWidthDelta) {
      return Promise.resolve(freeze({rerendered: false, viewMode, presentationZoom}));
    }
    return enqueueRender(async () => {
      resetRenderer();
      const rendered = await renderOnce();
      return freeze({...rendered, rerendered: true});
    });
  };

  updatePresentationControls();
  fitWidthButton?.addEventListener?.('click', () => {
    setViewMode('fit-width').catch(() => {
      // Presentation failure is already visible through the host fallback state.
    });
  });
  zoom100Button?.addEventListener?.('click', () => {
    setViewMode('100').catch(() => {
      // Presentation failure is already visible through the host fallback state.
    });
  });

  if (typeof window.ResizeObserver === 'function' && scorePanel) {
    resizeObserver = new window.ResizeObserver(() => {
      refreshResponsiveLayout().catch(() => {
        // Resize failures remain bounded to presentation and preserve the fallback.
      });
    });
    resizeObserver.observe(scorePanel);
  }

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
    presentationControls: true,
    fitWidthPolicy: FIT_WIDTH_POLICY,
    getViewMode: () => viewMode,
    getPresentationZoom: () => presentationZoom,
    setViewMode,
    refreshResponsiveLayout,
    getLastRenderedRevision: () => lastRenderedRevision,
    getLastRenderError: () => lastRenderError,
    renderCurrentSession
  });

  renderCurrentSession().catch(() => {
    // Failure remains presentation-only and visibly falls back to fixture evidence.
  });
})();
