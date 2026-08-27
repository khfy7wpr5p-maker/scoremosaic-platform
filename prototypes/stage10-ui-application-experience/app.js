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

  const normalizeLocalSearch = (value) => String(value ?? '').trim().toLowerCase();
  const documentRows = Array.from(document.querySelectorAll('[data-document-row]'));

  const renderDashboardSummary = () => {
    const localReviewState = fixture.document?.reviewState ?? '';
    text('dashboard-needs-review-count', localReviewState === 'needs-review' ? 1 : 0);
    text('dashboard-processing-count', localReviewState === 'processing' ? 1 : 0);
  };

  const renderDocumentList = () => {
    const search = normalizeLocalSearch(byId('document-search')?.value);
    const status = byId('document-status-filter')?.value || 'all';
    let visibleCount = 0;

    documentRows.forEach((row) => {
      const rowSearch = normalizeLocalSearch(row.dataset.documentSearch);
      const rowStatus = row.dataset.documentStatus || '';
      const matchesSearch = search.length === 0 || rowSearch.includes(search);
      const matchesStatus = status === 'all' || rowStatus === status;
      const visible = matchesSearch && matchesStatus;
      row.hidden = !visible;
      if (visible) visibleCount += 1;
    });

    text('document-result-count', `${visibleCount} shown`);
    const emptyState = byId('document-empty-filter');
    if (emptyState) emptyState.hidden = visibleCount !== 0;
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
    renderDashboardSummary();
    renderDocumentList();
    renderDocument();
    renderIssues();
    renderSelectedIssue();
  };

  byId('document-search')?.addEventListener('input', renderDocumentList);
  byId('document-status-filter')?.addEventListener('change', renderDocumentList);

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

(() => {
  'use strict';

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

  const issuesState = application.read('issues.read');
  const issues = issuesState?.phase === 'ready' && issuesState.authority?.authoritative === false
    ? issuesState.data.items
    : [];
  const issueList = document.getElementById('issue-list');
  const editPanel = document.querySelector('.edit-panel');
  const statusbar = document.querySelector('.statusbar');
  if (!issueList || !editPanel || !statusbar) return;

  const workflowState = {
    reviewedIssueIds: new Set(),
    validation: 'not-run',
    approval: 'locked',
  };

  const selectedIssue = () => {
    const selected = issueList.querySelector('[data-issue-id][aria-pressed="true"]');
    const issueId = selected?.dataset.issueId;
    return issues.find((issue) => issue.id === issueId) ?? null;
  };

  const unresolvedBlocking = () => issues.filter(
    (issue) => issue.severity === 'blocking' && !workflowState.reviewedIssueIds.has(issue.id)
  ).length;

  const makeNode = (tag, options = {}) => {
    const node = document.createElement(tag);
    if (options.id) node.id = options.id;
    if (options.className) node.className = options.className;
    if (options.textContent !== undefined) node.textContent = options.textContent;
    if (options.type) node.type = options.type;
    return node;
  };

  const workflow = makeNode('section', {className: 'edit-section'});
  workflow.dataset.reviewWorkflow = 'local';
  workflow.setAttribute('aria-labelledby', 'review-workflow-title');

  const heading = makeNode('div', {className: 'intent-heading'});
  const title = makeNode('h3', {id: 'review-workflow-title', textContent: 'Validation & approval'});
  const status = makeNode('span', {id: 'review-workflow-status', className: 'intent-status', textContent: 'Review required'});
  status.dataset.kind = 'neutral';
  status.setAttribute('role', 'status');
  status.setAttribute('aria-live', 'polite');
  status.setAttribute('aria-atomic', 'true');
  heading.append(title, status);

  const help = makeNode('p', {
    className: 'security-note',
    textContent: 'Local workflow only. It can mark fixture issues reviewed, run a bounded readiness check, and prepare the approval UI state. It cannot create TeacherScoreRevision, approve, publish, persist, or call a backend.'
  });
  help.id = 'review-workflow-help';

  const details = makeNode('dl', {className: 'detail-list'});
  const detailRow = (label, id) => {
    const row = makeNode('div');
    const dt = makeNode('dt', {textContent: label});
    const dd = makeNode('dd', {id, textContent: '—'});
    row.append(dt, dd);
    return row;
  };
  details.append(
    detailRow('Reviewed issues', 'reviewed-issue-count'),
    detailRow('Unresolved blocking', 'workflow-blocking-count'),
    detailRow('Validation', 'workflow-validation-label'),
    detailRow('Approval', 'workflow-approval-label')
  );

  const actions = makeNode('div', {className: 'intent-actions'});
  const markReviewed = makeNode('button', {id: 'mark-reviewed', type: 'button', textContent: 'Mark selected reviewed'});
  const runValidation = makeNode('button', {id: 'run-local-validation', type: 'button', textContent: 'Run validation'});
  const prepareApproval = makeNode('button', {id: 'prepare-local-approval', className: 'primary-button', type: 'button', textContent: 'Prepare approval'});
  const approveScore = makeNode('button', {id: 'approve-score', type: 'button', textContent: 'Approve score'});
  approveScore.disabled = true;
  approveScore.setAttribute('aria-describedby', 'review-workflow-help');
  approveScore.title = 'Production approval authority is not activated in this fixture preview.';
  const reset = makeNode('button', {id: 'reset-review-workflow', type: 'button', textContent: 'Reset local review'});
  actions.append(markReviewed, runValidation, prepareApproval, approveScore, reset);

  const output = makeNode('pre', {id: 'review-workflow-output', className: 'intent-preview', textContent: 'Select an issue, review the score/evidence, apply any local structured edit, then mark the issue reviewed.'});
  output.setAttribute('role', 'status');
  output.setAttribute('aria-live', 'polite');
  output.setAttribute('aria-atomic', 'true');

  workflow.append(heading, details, actions, output, help);
  const existingSecurityNote = editPanel.querySelector(':scope > .security-note');
  if (existingSecurityNote) editPanel.insertBefore(workflow, existingSecurityNote);
  else editPanel.append(workflow);

  const approvalStatusSpan = Array.from(statusbar.querySelectorAll('span')).find((candidate) => {
    const strong = candidate.querySelector('strong');
    return strong?.textContent === 'Approval';
  });
  let approvalStatusValue = null;
  if (approvalStatusSpan) {
    const strong = approvalStatusSpan.querySelector('strong');
    approvalStatusValue = makeNode('span', {id: 'status-approval', textContent: ' unavailable'});
    approvalStatusSpan.replaceChildren(strong, approvalStatusValue);
  }

  const text = (id, value) => {
    const node = document.getElementById(id);
    if (node) node.textContent = String(value);
  };

  const updateIssueAnnotations = () => {
    issueList.querySelectorAll('[data-issue-id]').forEach((button) => {
      const reviewed = workflowState.reviewedIssueIds.has(button.dataset.issueId);
      button.dataset.localReviewed = reviewed ? 'true' : 'false';
      const base = button.getAttribute('aria-label')?.replace(/ Locally reviewed\.$/, '') ?? '';
      button.setAttribute('aria-label', reviewed ? `${base} Locally reviewed.` : base);
    });
  };

  const renderWorkflow = () => {
    const selected = selectedIssue();
    const blocking = unresolvedBlocking();
    const reviewedCount = workflowState.reviewedIssueIds.size;
    text('reviewed-issue-count', `${reviewedCount} / ${issues.length}`);
    text('workflow-blocking-count', blocking);
    text('workflow-validation-label', workflowState.validation === 'pass' ? 'PASS · local readiness' : 'Not run');
    text('workflow-approval-label', workflowState.approval === 'ready-preview' ? 'Ready · production action locked' : 'Locked');

    markReviewed.disabled = !selected || workflowState.reviewedIssueIds.has(selected.id);
    runValidation.disabled = issues.length === 0 || blocking !== 0;
    prepareApproval.disabled = workflowState.validation !== 'pass';

    if (workflowState.approval === 'ready-preview') {
      status.textContent = 'Ready for teacher approval · production locked';
      status.dataset.kind = 'safe';
      if (approvalStatusValue) approvalStatusValue.textContent = ' ready preview · production locked';
    } else if (workflowState.validation === 'pass') {
      status.textContent = 'Validation passed · prepare approval';
      status.dataset.kind = 'safe';
      if (approvalStatusValue) approvalStatusValue.textContent = ' locked pending local preparation';
    } else if (blocking === 0) {
      status.textContent = 'Ready to validate';
      status.dataset.kind = 'neutral';
      if (approvalStatusValue) approvalStatusValue.textContent = ' locked pending validation';
    } else {
      status.textContent = `${blocking} blocking issue${blocking === 1 ? '' : 's'} remaining`;
      status.dataset.kind = 'locked';
      if (approvalStatusValue) approvalStatusValue.textContent = ` locked · ${blocking} blocking remaining`;
    }
    updateIssueAnnotations();
  };

  const invalidateReadiness = () => {
    workflowState.validation = 'not-run';
    workflowState.approval = 'locked';
  };

  markReviewed.addEventListener('click', () => {
    const issue = selectedIssue();
    if (!issue) return;
    workflowState.reviewedIssueIds.add(issue.id);
    invalidateReadiness();
    output.textContent = `Marked locally reviewed: ${issue.title}. This browser-only marker is non-authoritative and will disappear on reload.`;
    renderWorkflow();
  });

  runValidation.addEventListener('click', () => {
    const blocking = unresolvedBlocking();
    if (blocking !== 0 || issues.length === 0) {
      workflowState.validation = 'not-run';
      workflowState.approval = 'locked';
      output.textContent = `Validation blocked locally: ${blocking} unresolved blocking issue${blocking === 1 ? '' : 's'}.`;
      renderWorkflow();
      return;
    }
    workflowState.validation = 'pass';
    workflowState.approval = 'locked';
    output.textContent = 'Local readiness validation PASS. This is UI workflow evidence only; no authoritative server validation or revision was created.';
    renderWorkflow();
  });

  prepareApproval.addEventListener('click', () => {
    if (workflowState.validation !== 'pass' || unresolvedBlocking() !== 0) return;
    workflowState.approval = 'ready-preview';
    output.textContent = 'Approval UI is prepared and locally ready. The final Approve score action stays fail-closed until authenticated server revision, validation evidence, RBAC, persistence, and approval authority are separately activated.';
    renderWorkflow();
  });

  reset.addEventListener('click', () => {
    workflowState.reviewedIssueIds.clear();
    invalidateReadiness();
    output.textContent = 'Local review state reset. No server state existed or was changed.';
    renderWorkflow();
  });

  document.addEventListener('click', (event) => {
    const target = event.target instanceof Element ? event.target : null;
    if (target?.closest('[data-issue-id], [data-filter]')) queueMicrotask(renderWorkflow);
  });
  issueList.addEventListener('keydown', () => queueMicrotask(renderWorkflow));

  renderWorkflow();
})();
