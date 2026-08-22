(() => {
  'use strict';

  const fixture = window.ScoreMosaicFixture;
  if (!fixture || fixture.productionArtifact !== false || fixture.authoritativeTruth !== false) {
    return;
  }

  const state = {
    filter: 'all',
    selectedIssueId: fixture.issues[0]?.id ?? null
  };

  const byId = (id) => document.getElementById(id);
  const text = (id, value) => {
    const node = byId(id);
    if (node) node.textContent = String(value);
  };

  const countSeverity = (severity) => fixture.issues.filter((issue) => issue.severity === severity).length;

  const filteredIssues = () => {
    if (state.filter === 'all') return fixture.issues;
    return fixture.issues.filter((issue) => issue.severity === state.filter);
  };

  const focusRenderedIssue = (issueId) => {
    const list = byId('issue-list');
    if (!list) return;
    const button = Array.from(list.querySelectorAll('[data-issue-id]'))
      .find((candidate) => candidate.dataset.issueId === issueId);
    button?.focus();
  };

  const selectIssue = (issueId, focusMode = 'score') => {
    const exists = fixture.issues.some((issue) => issue.id === issueId);
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
    text('blocking-count', countSeverity('blocking'));
    text('warning-count', countSeverity('warning'));
    text('info-count', countSeverity('info'));

    document.querySelectorAll('[data-filter]').forEach((button) => {
      button.setAttribute('aria-pressed', button.dataset.filter === state.filter ? 'true' : 'false');
    });
  };

  const renderSelectedIssue = () => {
    const issue = fixture.issues.find((candidate) => candidate.id === state.selectedIssueId);
    if (!issue) return;

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
    text('source-region', issue.evidence.sourceRegion);
    text('candidate-id', issue.evidence.candidate);
    text('canonical-id', issue.evidence.canonical);
    text('score-focus-label', `Measure ${issue.location.measure} · ${issue.title}`);
  };

  const renderDocument = () => {
    text('document-label', fixture.document.label);
    text('revision-label', fixture.document.revision);
    text('source-sha', fixture.document.sourceSha256);
    text('canonical-sha', fixture.document.canonicalSha256);
    text('validation-label', fixture.validation.status);
    text('status-blocking', fixture.validation.blocking);
    text('status-revision', fixture.document.revision);
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
