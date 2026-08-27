(() => {
  'use strict';

  const adapter = window.ScoreMosaicOrchestrationPreviewAdapter;
  const scorePanel = document.querySelector('.score-panel');
  const workspace = document.querySelector('#view-teacher-review .workspace');
  if (!adapter || adapter.productionAdapter !== false || adapter.authoritative !== false || adapter.networkCapable !== false || adapter.mutationCapable !== false || !scorePanel || !workspace) return;

  const make = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = String(text);
    return node;
  };

  const state = adapter.read();
  const isStaging = state.state === 'ready' && state.data?.transportMode === 'authenticated-staging';

  const panel = make('section', 'panel orchestration-preview-panel');
  panel.id = 'orchestration-preview';
  panel.setAttribute('aria-labelledby', 'orchestration-preview-title');
  panel.setAttribute('aria-describedby', 'orchestration-preview-authority');

  const header = make('div', 'panel-header panel-header--wide');
  const heading = make('div');
  heading.append(make('p', 'eyebrow', 'AI-assisted downstream evidence'));
  const title = make('h2', '', 'Orchestration Preview');
  title.id = 'orchestration-preview-title';
  heading.append(title);
  const badge = make('span', 'badge badge--neutral', isStaging ? 'Authenticated staging preview · non-authoritative' : 'Local model preview · non-authoritative');
  header.append(heading, badge);
  panel.append(header);

  const authority = make('p', 'security-note', `Suggestion only · score unchanged. ${isStaging ? 'H7-D' : 'H7-C'} has no Apply action and cannot create or overwrite Canonical Score, TeacherScoreRevision, approval, or publication state.`);
  authority.id = 'orchestration-preview-authority';
  panel.append(authority);

  if (state.state !== 'ready' || !state.data) {
    const unavailable = make('div', 'orchestration-preview-unavailable');
    unavailable.setAttribute('role', 'status');
    unavailable.setAttribute('aria-live', 'polite');
    unavailable.append(make('strong', '', 'Preview unavailable'), make('p', '', state.error?.message || 'Orchestration evidence failed closed.'));
    panel.append(unavailable);
    scorePanel.insertAdjacentElement('afterend', panel);
    return;
  }

  const data = state.data;
  const result = data.result;
  const primary = result.status === 'proposal' ? (result.alternatives[0] || null) : null;
  const summary = make('div', 'orchestration-preview-summary');
  const statusCard = make('div', 'orchestration-preview-card');
  statusCard.append(make('span', 'eyebrow', 'Result status'), make('strong', '', result.status));
  const suggestionCard = make('div', 'orchestration-preview-card');
  suggestionCard.append(make('span', 'eyebrow', 'Recommendation'));
  if (primary) {
    suggestionCard.append(make('strong', '', primary.instrument), make('span', 'orchestration-confidence', `${(primary.confidence * 100).toFixed(1)}% confidence`));
  } else {
    suggestionCard.append(make('strong', '', 'No proposal'));
  }
  const validationCard = make('div', 'orchestration-preview-card');
  validationCard.append(make('span', 'eyebrow', 'Deterministic validation'), make('strong', '', result.deterministic_validation.passed ? 'PASS' : 'VETO'));
  summary.append(statusCard, suggestionCard, validationCard);
  panel.append(summary);

  const alternativesSection = make('section', 'orchestration-alternatives');
  alternativesSection.append(make('h3', '', result.status === 'proposal' ? 'Ranked alternatives' : 'Ranked alternatives · evidence only'));
  const list = make('ol', 'orchestration-alternative-list');
  result.alternatives.forEach((item) => {
    const row = make('li', 'orchestration-alternative');
    row.append(make('strong', '', item.instrument), make('span', '', `${(item.confidence * 100).toFixed(1)}%`));
    list.append(row);
  });
  alternativesSection.append(list);
  panel.append(alternativesSection);

  const lineage = make('dl', 'detail-list orchestration-lineage');
  const add = (label, value) => {
    const row = make('div');
    row.append(make('dt', '', label), make('dd', '', value));
    lineage.append(row);
  };
  add('Transport', isStaging ? 'authenticated staging' : 'local process');
  add('Capability', data.target.capability);
  add('Model', data.target.modelId);
  add('Model fingerprint', data.target.modelFingerprint);
  add('ST main', data.target.mainCommit);
  add('Input SHA-256', data.previewInputSha256);
  add('Result SHA-256', result.result_sha256);
  panel.append(lineage);

  panel.append(make('p', 'orchestration-preview-footnote', isStaging
    ? 'Authenticated staging model inference was executed server-side against the pinned ST-Orchestration commit. The browser receives neither the staging endpoint nor its authentication secret and only presents validated preview evidence.'
    : 'Real local-process model inference was executed outside the browser against the pinned ST-Orchestration commit. The browser only presents the generated, validated preview evidence.'));
  scorePanel.insertAdjacentElement('afterend', panel);
})();
