(() => {
  'use strict';

  const freezeDeep = (value) => {
    if (value && typeof value === 'object' && !Object.isFrozen(value)) {
      Object.freeze(value);
      Object.keys(value).forEach((key) => freezeDeep(value[key]));
    }
    return value;
  };

  const fixture = {
    fixtureVersion: 'scoremosaic-stage10-review-fixture-v1',
    authoritativeTruth: false,
    productionArtifact: false,
    document: {
      id: 'fixture-score-001',
      label: 'Bach Study — local fixture',
      revision: 'fixture-r3',
      sourceSha256: 'fixture-source-sha256-6f6f0c2a',
      canonicalSha256: 'fixture-canonical-sha256-71a0bb19',
      reviewState: 'needs-review'
    },
    validation: {
      status: 'needs-review',
      blocking: 1,
      warnings: 1,
      info: 1,
      approvalEligible: false,
      publicationEligible: false
    },
    issues: [
      {
        id: 'issue-duration-001',
        severity: 'blocking',
        title: 'Duration evidence disagrees',
        summary: 'Beam evidence and deterministic duration validation disagree for the selected event.',
        location: { page: 1, measure: 3, staff: 1, voice: 1, event: 'event-003-04' },
        event: { pitch: 'E4', duration: '1/8', voice: '1' },
        evidence: { sourceRegion: 'page-1/measure-3', candidate: 'fixture-st-omr-a', canonical: 'fixture-canonical-a' }
      },
      {
        id: 'issue-accidental-002',
        severity: 'warning',
        title: 'Accidental needs review',
        summary: 'Visual accidental evidence is present but the deterministic pitch context is ambiguous.',
        location: { page: 1, measure: 5, staff: 1, voice: 1, event: 'event-005-02' },
        event: { pitch: 'F4?', duration: '1/4', voice: '1' },
        evidence: { sourceRegion: 'page-1/measure-5', candidate: 'fixture-st-omr-a', canonical: 'fixture-canonical-a' }
      },
      {
        id: 'issue-source-003',
        severity: 'info',
        title: 'Low source contrast',
        summary: 'The source crop is usable but visual confidence evidence is intentionally marked limited.',
        location: { page: 1, measure: 7, staff: 1, voice: 1, event: 'event-007-01' },
        event: { pitch: 'A4', duration: '1/2', voice: '1' },
        evidence: { sourceRegion: 'page-1/measure-7', candidate: 'fixture-st-omr-a', canonical: 'fixture-canonical-a' }
      }
    ]
  };

  window.ScoreMosaicFixture = freezeDeep(fixture);
})();
