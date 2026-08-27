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

  const waitFor = async (predicate, code, attempts = 80) => {
    for (let index = 0; index < attempts; index += 1) {
      if (predicate()) return;
      await new Promise((resolve) => setTimeout(resolve, 50));
    }
    fail(code);
  };

  const graphicsSpanRatio = (svg) => {
    const graphics = [...svg.querySelectorAll('path,use,line,polyline,polygon,ellipse,circle')];
    let minX = Number.POSITIVE_INFINITY;
    let maxX = Number.NEGATIVE_INFINITY;
    for (const graphic of graphics) {
      try {
        const box = graphic.getBBox();
        if (!Number.isFinite(box.x) || !Number.isFinite(box.width)) continue;
        minX = Math.min(minX, box.x);
        maxX = Math.max(maxX, box.x + box.width);
      } catch {
        // Some SVG nodes can refuse getBBox in headless mode; other graphics still count.
      }
    }
    const viewBoxWidth = svg.viewBox?.baseVal?.width || svg.getBBox?.().width || 0;
    if (!Number.isFinite(minX) || !Number.isFinite(maxX) || !(viewBoxWidth > 0)) return 0;
    return (maxX - minX) / viewBoxWidth;
  };

  const maxGraphicPixelHeight = (svg) => {
    let maximum = 0;
    for (const graphic of svg.querySelectorAll('path,use,line,polyline,polygon,ellipse,circle')) {
      try {
        const rect = graphic.getBoundingClientRect();
        if (Number.isFinite(rect.height)) maximum = Math.max(maximum, rect.height);
      } catch {
        // Ignore individual browser geometry failures; other graphics remain measurable.
      }
    }
    return maximum;
  };

  const renderedSystemGeometry = (svg) => {
    const svgRect = svg.getBoundingClientRect();
    const minimumSegmentWidth = Math.max(24, svgRect.width * 0.08);
    const rawLineYs = [];

    for (const graphic of svg.querySelectorAll('path,line,polyline')) {
      try {
        const rect = graphic.getBoundingClientRect();
        if (!Number.isFinite(rect.width) || !Number.isFinite(rect.height)) continue;
        if (rect.width < minimumSegmentWidth || rect.height > 3.5) continue;
        rawLineYs.push(rect.top + (rect.height / 2));
      } catch {
        // Geometry probing is test-only; other staff-line segments still count.
      }
    }

    rawLineYs.sort((left, right) => left - right);
    const clusters = [];
    for (const y of rawLineYs) {
      const current = clusters.at(-1);
      if (current && Math.abs(current.y - y) <= 2.5) {
        current.y = ((current.y * current.count) + y) / (current.count + 1);
        current.count += 1;
      } else {
        clusters.push({y, count: 1});
      }
    }

    const lineYs = clusters.map((cluster) => cluster.y);
    let systems = 0;
    let index = 0;
    while (index <= lineYs.length - 5) {
      const five = lineYs.slice(index, index + 5);
      const gaps = five.slice(1).map((value, gapIndex) => value - five[gapIndex]);
      const looksLikeFiveLineStaff = gaps.every((gap) => gap >= 3 && gap <= 18)
        && (five[4] - five[0]) <= 70;
      if (looksLikeFiveLineStaff) {
        systems += 1;
        index += 5;
      } else {
        index += 1;
      }
    }

    return {systems, staffLineClusters: lineYs.length, rawSegments: rawLineYs.length};
  };

  const assertRendered = (expectedRevision, {fitWidth = false, minimumSystems = 0} = {}) => {
    const host = document.getElementById('score-render-host');
    const fallback = document.getElementById('score-fixture-fallback');
    if (!host || !fallback) fail('SURFACE_MISSING');
    if (host.hidden) fail('HOST_HIDDEN');
    if (fallback.hidden !== true) fail('FALLBACK_NOT_HIDDEN');
    if (host.dataset.renderState !== 'rendered') fail('RENDER_STATE_INVALID', host.dataset.renderState ?? 'missing');
    if (host.dataset.renderedRevision !== expectedRevision) fail('REVISION_MISMATCH', host.dataset.renderedRevision ?? 'missing');
    const svgs = host.querySelectorAll('svg');
    if (svgs.length !== 1) fail('SVG_SURFACE_COUNT_INVALID', String(svgs.length));
    const svg = svgs[0];
    const graphics = svg.querySelectorAll('path,use,line,polyline,polygon,ellipse,circle').length;
    if (graphics === 0) fail('SVG_GRAPHICS_EMPTY');
    const rect = svg.getBoundingClientRect();
    if (!(rect.width > 0) || !(rect.height > 0)) fail('SVG_ZERO_SIZE', `${rect.width}x${rect.height}`);
    const graphicHeight = maxGraphicPixelHeight(svg);
    if (!(graphicHeight > 0)) fail('SVG_GRAPHICS_ZERO_HEIGHT');
    if (svg.textContent.includes('Teacher Review score') || svg.textContent.includes('Bach Study')) {
      fail('FIXTURE_CREDIT_CONSUMES_SCORE_VIEW');
    }
    if (fitWidth) {
      const ratio = graphicsSpanRatio(svg);
      if (!(ratio >= 0.6)) fail('FIT_WIDTH_SPAN_TOO_SMALL', ratio.toFixed(3));
    }
    const geometry = renderedSystemGeometry(svg);
    if (minimumSystems > 0 && geometry.systems < minimumSystems) {
      fail('SCORE_SYSTEM_COUNT_TOO_SMALL', `${geometry.systems}/staff-lines=${geometry.staffLineClusters}/segments=${geometry.rawSegments}`);
    }
    return {svg, rect, graphicHeight, systems: geometry.systems, staffLineClusters: geometry.staffLineClusters};
  };

  window.addEventListener('load', async () => {
    try {
      const bridge = window.ScoreMosaicScoreEditorCoreBridge;
      const renderer = window.ScoreMosaicScoreEditorOsmdHost;
      if (!bridge || bridge.available !== true) fail('BRIDGE_UNAVAILABLE', bridge?.reason ?? 'missing');
      if (!renderer || renderer.available !== true) fail('RENDERER_UNAVAILABLE', renderer?.reason ?? 'missing');
      if (renderer.presentationControls !== true) fail('PRESENTATION_CONTROLS_UNAVAILABLE');
      if (typeof renderer.getPresentationZoom !== 'function') fail('PRESENTATION_ZOOM_UNAVAILABLE');
      if (typeof renderer.refreshResponsiveLayout !== 'function') fail('RESPONSIVE_REFRESH_UNAVAILABLE');
      if (renderer.getViewMode() !== 'fit-width') fail('DEFAULT_VIEW_MODE_INVALID', renderer.getViewMode());
      if (bridge.scoreFixtureMeasureCount !== 12) fail('FIXTURE_MEASURE_COUNT_CONTRACT_INVALID', String(bridge.scoreFixtureMeasureCount));

      const fitWidthButton = document.getElementById('score-fit-width');
      const zoom100Button = document.getElementById('score-zoom-100');
      const host = document.getElementById('score-render-host');
      if (!fitWidthButton || !zoom100Button || !host) fail('VIEW_CONTROLS_MISSING');
      if (fitWidthButton.disabled || zoom100Button.disabled) fail('VIEW_CONTROLS_DISABLED');
      if (fitWidthButton.getAttribute('aria-pressed') !== 'true') fail('FIT_WIDTH_NOT_ACTIVE');

      let snapshot = bridge.getSessionSnapshot();
      const measureCount = (snapshot.musicXml.match(/<measure number=/g) || []).length;
      if (measureCount !== 12) fail('MUSICXML_MEASURE_COUNT_INVALID', String(measureCount));
      await renderer.renderCurrentSession();
      const initialFit = assertRendered(snapshot.revisionId, {fitWidth: true, minimumSystems: 4});
      if (!(initialFit.rect.height >= 300)) fail('SCORE_VIEW_TOO_SHORT', String(initialFit.rect.height));
      const initialFitZoom = renderer.getPresentationZoom();
      if (!(initialFitZoom >= renderer.fitWidthPolicy.minZoom && initialFitZoom <= renderer.fitWidthPolicy.maxZoom)) {
        fail('FIT_WIDTH_ZOOM_OUT_OF_BOUNDS', String(initialFitZoom));
      }
      if (Number(host.dataset.presentationZoom) !== Number(initialFitZoom.toFixed(2))) fail('FIT_WIDTH_ZOOM_DATASET_MISMATCH');

      await renderer.setViewMode('100');
      if (renderer.getViewMode() !== '100') fail('ZOOM_100_MODE_NOT_APPLIED');
      if (renderer.getPresentationZoom() !== 1.0) fail('ZOOM_100_SCALE_INVALID', String(renderer.getPresentationZoom()));
      if (zoom100Button.getAttribute('aria-pressed') !== 'true') fail('ZOOM_100_NOT_ACTIVE');
      assertRendered(snapshot.revisionId);

      await renderer.setViewMode('fit-width');
      if (renderer.getViewMode() !== 'fit-width') fail('FIT_WIDTH_MODE_NOT_RESTORED');
      if (fitWidthButton.getAttribute('aria-pressed') !== 'true') fail('FIT_WIDTH_NOT_RESTORED');
      assertRendered(snapshot.revisionId, {fitWidth: true, minimumSystems: 4});

      const originalInlineWidth = host.style.width;
      const originalWidth = host.getBoundingClientRect().width;
      const narrowedWidth = Math.max(360, Math.floor(originalWidth - 140));
      host.style.width = `${narrowedWidth}px`;
      const responsiveResult = await renderer.refreshResponsiveLayout();
      if (responsiveResult.rerendered !== true) fail('RESPONSIVE_RERENDER_NOT_TRIGGERED');
      const narrowedZoom = renderer.getPresentationZoom();
      if (!(narrowedZoom >= renderer.fitWidthPolicy.minZoom && narrowedZoom <= renderer.fitWidthPolicy.maxZoom)) {
        fail('RESPONSIVE_ZOOM_OUT_OF_BOUNDS', String(narrowedZoom));
      }
      assertRendered(snapshot.revisionId, {fitWidth: true, minimumSystems: 4});
      host.style.width = originalInlineWidth;
      await renderer.refreshResponsiveLayout();
      assertRendered(snapshot.revisionId, {fitWidth: true, minimumSystems: 4});

      const accidentalButton = [...document.querySelectorAll('[data-issue-id]')]
        .find((button) => button.dataset.issueId === 'issue-accidental-002');
      const operation = document.getElementById('edit-operation');
      const proposedValue = document.getElementById('edit-value');
      const applyButton = document.getElementById('prepare-intent');
      const selectedPitch = document.getElementById('selected-pitch');
      if (!accidentalButton || !operation || !proposedValue || !applyButton || !selectedPitch) fail('STRUCTURED_EDIT_CONTROLS_MISSING');
      accidentalButton.click();
      await waitFor(() => selectedPitch.textContent === 'F4', 'STRUCTURED_EDIT_SELECTION_NOT_SYNCED');
      const beforePitchSvg = host.querySelector('svg').innerHTML;
      operation.value = 'set_pitch';
      operation.dispatchEvent(new Event('change', {bubbles: true}));
      proposedValue.value = 'G4';
      applyButton.click();
      await waitFor(() => selectedPitch.textContent === 'G4', 'STRUCTURED_EDIT_VALUE_NOT_UPDATED');
      snapshot = bridge.getSessionSnapshot();
      await waitFor(() => host.dataset.renderedRevision === snapshot.revisionId, 'STRUCTURED_EDIT_RENDER_NOT_UPDATED');
      const afterPitch = assertRendered(snapshot.revisionId, {fitWidth: true, minimumSystems: 4});
      if (afterPitch.svg.innerHTML === beforePitchSvg) fail('STRUCTURED_EDIT_SVG_UNCHANGED');
      const pitchField = snapshot.inspector?.fields?.find((field) => field.key === 'pitch')?.value;
      if (pitchField !== 'G4') fail('STRUCTURED_EDIT_INSPECTOR_NOT_CURRENT', String(pitchField));

      snapshot = bridge.commitOperation('issue-duration-001', {
        type: 'set_effective_duration',
        value: {numerator: 1, denominator: 4}
      });
      await renderer.renderCurrentSession();
      assertRendered(snapshot.revisionId, {fitWidth: true, minimumSystems: 4});

      snapshot = bridge.commitOperation('issue-source-003', {
        type: 'set_dots',
        value: 1
      });
      await renderer.renderCurrentSession();
      assertRendered(snapshot.revisionId, {fitWidth: true, minimumSystems: 4});

      if (renderer.getLastRenderError() !== null) fail('UNEXPECTED_RENDER_ERROR', renderer.getLastRenderError());
      document.documentElement.dataset.e7hRealOsmdSmoke = 'pass';
      result.hidden = false;
      result.textContent = `E7H_REAL_OSMD_BROWSER_SMOKE_PASS:${snapshot.revisionId}:systems>=4:measures=12:structured-edit=visible`;
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
