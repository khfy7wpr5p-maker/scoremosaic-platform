(() => {
  'use strict';

  const byId = (id) => document.getElementById(id);
  const text = (id, value) => {
    const node = byId(id);
    if (node) node.textContent = String(value);
  };

  const productNavButtons = Array.from(document.querySelectorAll('[data-product-nav]'));
  const productViews = Array.from(document.querySelectorAll('[data-product-view]'));

  const activateProductView = (viewName, focusView = true) => {
    const target = productViews.find((view) => view.dataset.productView === viewName);
    if (!target) return;

    productViews.forEach((view) => {
      view.hidden = view !== target;
    });
    productNavButtons.forEach((button) => {
      if (button.dataset.productNav === viewName) {
        button.setAttribute('aria-current', 'page');
      } else {
        button.removeAttribute('aria-current');
      }
    });

    if (focusView) target.focus();
  };

  productNavButtons.forEach((button) => {
    button.addEventListener('click', () => activateProductView(button.dataset.productNav || 'teacher-review'));
  });
  document.querySelectorAll('[data-open-product-view]').forEach((button) => {
    button.addEventListener('click', () => activateProductView(button.dataset.openProductView || 'teacher-review'));
  });
  activateProductView('teacher-review', false);

  const fixture = window.ScoreMosaicFixture;
  const application = window.ScoreMosaicLocalApplication;
  if (
    !fixture
    || fixture.productionArtifact !== false
    || fixture.authoritativeTruth !== false
    || !application
    || application.productionApplication !== false
    || application.authoritative !== false
    || application.networkCapable !== false
    || application.persistent !== false
  ) {
    return;
  }

  const reviewState = application.read('review.read');
  const issuesState = application.read('issues.read');
  const evidenceState = application.read('sourceEvidence.read');
  const validationState = application.read('validation.read');
  const statesReady = [reviewState, issuesState, evidenceState, validationState]
    .every((entry) => entry?.phase === 'ready' && entry.authority?.authoritative === false);

  const review = statesReady ? reviewState.data : null;
  const issuesModel = statesReady ? issuesState.data : {items: [], counts: {blocking: 0, warning: 0, info: 0}};
  const evidence = statesReady ? evidenceState.data : null;
  const validation = statesReady ? validationState.data : null;

  const state = {
    filter: 'all',
    selectedIssueId: issuesModel.items[0]?.id ?? null,
  };

  const countSeverity = (severity) => issuesModel.items.filter((issue) => issue.severity === severity).length;

  const filteredIssues = () => {
    if (state.filter === 'all') return issuesModel.items;
    return issuesModel.items.filter((issue) => issue.severity === state.filter);
  };

  const focusRenderedIssue = (issueId) => {
    const list = byId('issue-list');
    if (!list) return;
    const button = Array.from(list.querySelectorAll('[data-issue-id]'))
      .find((candidate) => candidate.dataset.issueId === issueId);
    button?.focus();
  };

  const selectIssue = (issueId, focusMode = 'score') => {
    const exists = issuesModel.items.some((issue) => issue.id === issueId);
    if (!exists) return;
    state.selectedIssueId = issueId;
    render();
    if (focusMode === 'issue') {
      focusRenderedIssue(issueId);
    } else if (focusMode === 'score') {
      byId('score-view')?.focus();
    }
  };

  const createIssueButton = (issue) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `issue-button issue-button--${issue.severity}`;
    button.dataset.issueId = issue.id;
    button.setAttribute('aria-pressed', issue.id === state.selectedIssueId ? 'true' : 'false');
    button.setAttribute('aria-label', `${issue.severity}: ${issue.title}. Page ${issue.location.page}, measure ${issue.location.measure}.`);

    const severity = document.createElement('span');
    severity.className = 'issue-severity';
    severity.textContent = issue.severity;

    const title = document.createElement('strong');
    title.textContent = issue.title;

    const locationLabel = document.createElement('span');
    locationLabel.className = 'issue-location';
    locationLabel.textContent = `Page ${issue.location.page} · Measure ${issue.location.measure} · Event ${issue.location.event}`;

    button.append(severity, title, locationLabel);
    button.addEventListener('click', () => selectIssue(issue.id, 'score'));
    return button;
  };

  const renderIssues = () => {
    const list = byId('issue-list');
    if (!list) return;
    list.replaceChildren();
    const issues = filteredIssues();
    issues.forEach((issue) => list.append(createIssueButton(issue)));
    text('issue-count', `${issues.length} shown`);
    text('blocking-count', issuesModel.counts.blocking ?? countSeverity('blocking'));
    text('warning-count', issuesModel.counts.warning ?? countSeverity('warning'));
    text('info-count', issuesModel.counts.info ?? countSeverity('info'));

    document.querySelectorAll('[data-filter]').forEach((button) => {
      button.setAttribute('aria-pressed', button.dataset.filter === state.filter ? 'true' : 'false');
    });
  };

  const renderSelectedIssue = () => {
    const issue = issuesModel.items.find((candidate) => candidate.id === state.selectedIssueId);
    if (!issue) return;

    const evidenceRegion = evidence?.regions.find((candidate) => candidate.issueId === issue.id) ?? issue.evidence;
    text('focused-page', issue.location.page);
    text('focused-measure', issue.location.measure);
    text('focused-staff', issue.location.staff);
    text('focused-voice', issue.location.voice);
    text('focused-event', issue.location.event);
    text('selected-pitch', issue.event.pitch);
    text('selected-duration', issue.event.duration);
    text('selected-voice', issue.event.voice);
    text('selected-issue-title', issue.title);
    text('selected-issue-summary', issue.summary);
    text('source-region', evidenceRegion.sourceRegion);
    text('candidate-id', evidenceRegion.candidate);
    text('canonical-id', evidenceRegion.canonical);
    text('score-focus-label', `Measure ${issue.location.measure} · ${issue.title}`);
  };

  const renderUnavailable = () => {
    text('document-label', 'Local contract unavailable');
    text('revision-label', application.context.revision);
    text('source-sha', '—');
    text('canonical-sha', '—');
    text('validation-label', 'unavailable');
    text('status-blocking', '—');
    text('status-revision', application.context.revision);
    text('selected-issue-summary', 'Local typed application data failed closed. No production fallback is available.');
  };

  const renderDocument = () => {
    if (!statesReady || !review || !validation || !evidence) {
      renderUnavailable();
      return;
    }
    text('document-label', review.label);
    text('revision-label', application.context.revision);
    text('source-sha', evidence.sourceSha256);
    text('canonical-sha', evidence.canonicalSha256);
    text('validation-label', validation.status);
    text('status-blocking', validation.blocking);
    text('status-revision', application.context.revision);
  };

  const render = () => {
    renderDocument();
    renderIssues();
    renderSelectedIssue();
  };

  document.querySelectorAll('[data-filter]').forEach((button) => {
    button.addEventListener('click', () => {
      state.filter = button.dataset.filter || 'all';
      const visible = filteredIssues();
      if (!visible.some((issue) => issue.id === state.selectedIssueId)) {
        state.selectedIssueId = visible[0]?.id ?? null;
      }
      render();
    });
  });

  const issueList = byId('issue-list');
  issueList?.addEventListener('keydown', (event) => {
    if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;
    const visible = filteredIssues();
    if (visible.length === 0) return;
    const currentIndex = Math.max(0, visible.findIndex((issue) => issue.id === state.selectedIssueId));
    let nextIndex = currentIndex;
    if (event.key === 'ArrowDown') nextIndex = Math.min(currentIndex + 1, visible.length - 1);
    if (event.key === 'ArrowUp') nextIndex = Math.max(currentIndex - 1, 0);
    if (event.key === 'Home') nextIndex = 0;
    if (event.key === 'End') nextIndex = visible.length - 1;
    event.preventDefault();
    selectIssue(visible[nextIndex].id, 'issue');
  });

  render();
})();
