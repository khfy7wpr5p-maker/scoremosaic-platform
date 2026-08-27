(() => {
  'use strict';

  const RESULT_ID = 'e7h-real-osmd-browser-smoke-result';
  const result = document.createElement('pre');
  result.id = RESULT_ID;
  result.hidden = true;
  document.body.appendChild(result);

  const fail = (code, detail = '') => {
    document.documentElement.dataset.e7hRealOsmdSmoke = 'fail';
    result.hidden = false;
    result.textContent = `E7H_REAL_OSMD_BROWSER_SMOKE_FAIL:${code}${detail ? `:${detail}` : ''}`;
    throw new Error(code);
  };

  const assertRendered = (expectedRevision) => {
    const host = document.getElementById('score-render-host');
    const fallback = document.getElementById('score-fixture-fallback');
    if (!host || !fallback) fail('SURFACE_MISSING');
    if (host.hidden) fail('HOST_HIDDEN');
    if (fallback.hidden !== true) fail('FALLBACK_NOT_HIDDEN');
    if (host.dataset.renderState !== 'rendered') fail('RENDER_STATE_INVALID', host.dataset.renderState ?? 'missing');
    if (host.dataset.renderedRevision !== expectedRevision) fail('REVISION_MISMATCH', host.dataset.renderedRevision ?? 'missing');
    const svg = host.querySelector('svg');
    if (!svg) fail('SVG_MISSING');
    const graphics = svg.querySelectorAll('path,use,line,polyline,polygon,ellipse,circle').length;
    if (graphics === 0) fail('SVG_GRAPHICS_EMPTY');
    const rect = svg.getBoundingClientRect();
    if (!(rect.width > 0) || !(rect.height > 0)) fail('SVG_ZERO_SIZE', `${rect.width}x${rect.height}`);
  };

  window.addEventListener('load', async () => {
    try {
      const bridge = window.ScoreMosaicScoreEditorCoreBridge;
      const renderer = window.ScoreMosaicScoreEditorOsmdHost;
      if (!bridge || bridge.available !== true) fail('BRIDGE_UNAVAILABLE', bridge?.reason ?? 'missing');
      if (!renderer || renderer.available !== true) fail('RENDERER_UNAVAILABLE', renderer?.reason ?? 'missing');

      let snapshot = bridge.getSessionSnapshot();
      await renderer.renderCurrentSession();
      assertRendered(snapshot.revisionId);

      snapshot = bridge.commitOperation('issue-accidental-002', {
        type: 'set_pitch',
        value: {step: 'G', alter: {numerator: 0, denominator: 1}, octave: 4}
      });
      await renderer.renderCurrentSession();
      assertRendered(snapshot.revisionId);

      snapshot = bridge.commitOperation('issue-duration-001', {
        type: 'set_effective_duration',
        value: {numerator: 1, denominator: 4}
      });
      await renderer.renderCurrentSession();
      assertRendered(snapshot.revisionId);

      snapshot = bridge.commitOperation('issue-source-003', {
        type: 'set_dots',
        value: 1
      });
      await renderer.renderCurrentSession();
      assertRendered(snapshot.revisionId);

      if (renderer.getLastRenderError() !== null) fail('UNEXPECTED_RENDER_ERROR', renderer.getLastRenderError());
      document.documentElement.dataset.e7hRealOsmdSmoke = 'pass';
      result.hidden = false;
      result.textContent = `E7H_REAL_OSMD_BROWSER_SMOKE_PASS:${snapshot.revisionId}`;
    } catch (error) {
      if (document.documentElement.dataset.e7hRealOsmdSmoke !== 'fail') {
        const detail = error instanceof Error ? error.message : String(error);
        document.documentElement.dataset.e7hRealOsmdSmoke = 'fail';
        result.hidden = false;
        result.textContent = `E7H_REAL_OSMD_BROWSER_SMOKE_FAIL:UNCAUGHT:${detail}`;
      }
    }
  }, {once: true});
})();
