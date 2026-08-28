'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  buildClassicalDiscoveryRequest,
  sanitizeGatewayResponse,
  buildServerIntakeHandoff,
} = require('../tools/score-discovery-consumer-v1.cjs');

test('classical request is bounded and cannot select a gateway/provider origin', () => {
  const request = buildClassicalDiscoveryRequest({
    query: 'Beethoven String Quartet',
    gatewayUrl: 'https://attacker.invalid',
    providerUrl: 'https://attacker.invalid',
    filters: {
      repertoireFamily: 'contemporary',
      catalogScope: 'international',
      requiredInstruments: ['violin', 'viola', 'cello', 'unknown-instrument'],
      ensembleType: 'string-quartet',
      scoreRole: 'full-score',
      requiredFeatures: ['notation', 'attacker-feature'],
    },
    limit: 999,
  });

  assert.deepEqual(request, {
    query: 'Beethoven String Quartet',
    filters: {
      repertoireFamily: 'classical',
      catalogScope: 'international',
      requiredInstruments: ['violin', 'viola', 'cello'],
      ensembleType: 'string-quartet',
      scoreRole: 'full-score',
      requiredFeatures: ['notation'],
    },
    limit: 50,
  });
  assert.equal(Object.hasOwn(request, 'gatewayUrl'), false);
  assert.equal(Object.hasOwn(request, 'providerUrl'), false);
});

test('malformed or oversized query fails closed', () => {
  assert.throws(() => buildClassicalDiscoveryRequest({ query: '' }), /query/);
  assert.throws(() => buildClassicalDiscoveryRequest({ query: 'x'.repeat(257) }), /query/);
  assert.throws(() => buildClassicalDiscoveryRequest([]), /object/);
});

test('browser-facing response strips asset URLs and keeps discovery non-authoritative', () => {
  const response = sanitizeGatewayResponse({
    results: [{
      id: 'openscore:1:musicxml',
      title: 'Quartet No. 1',
      artist: 'Example Composer',
      source: 'OpenScore',
      format: 'musicxml',
      repertoireFamily: 'classical',
      catalogScope: 'international',
      instrumentation: ['violin', 'viola', 'cello'],
      ensembleType: 'string-quartet',
      scoreRole: 'full-score',
      contentFeatures: ['notation'],
      sourcePageUrl: 'https://example.test/score',
      assetUrl: 'https://assets.example.test/score.musicxml',
      rightsStatus: 'open-license',
      accessPolicy: 'public',
      handoffMode: 'direct-import',
      workGroupKey: 'work::example::quartet',
      versionGroupKey: 'version::example',
      maliciousField: 'must-not-cross',
    }],
    sourceLocators: [],
    totalResults: 1,
  });

  assert.equal(response.results.length, 1);
  assert.equal(response.results[0].canRequestIntake, true);
  assert.equal(response.results[0].canOpenSource, true);
  assert.equal(Object.hasOwn(response.results[0], 'assetUrl'), false);
  assert.equal(Object.hasOwn(response.results[0], 'maliciousField'), false);
  assert.equal(Object.hasOwn(response.results[0], 'canonicalScore'), false);
  assert.equal(Object.hasOwn(response.results[0], 'teacherApproval'), false);
});

test('web/external results can never request intake', () => {
  const response = sanitizeGatewayResponse({
    results: [{
      id: 'imslp:1:web',
      title: 'Work page',
      source: 'IMSLP',
      format: 'web',
      repertoireFamily: 'classical',
      sourcePageUrl: 'https://imslp.org/wiki/Example',
      assetUrl: 'https://attacker.invalid/file.pdf',
      rightsStatus: 'external-link-only',
      accessPolicy: 'public',
      handoffMode: 'external-open',
    }],
  });

  assert.equal(response.results[0].canOpenSource, true);
  assert.equal(response.results[0].canRequestIntake, false);
});

test('unsafe source URLs and unverified locator shapes fail closed', () => {
  const response = sanitizeGatewayResponse({
    results: [{
      id: 'unsafe:1',
      title: 'Unsafe',
      format: 'pdf',
      repertoireFamily: 'classical',
      sourcePageUrl: 'http://example.test/score',
      assetUrl: 'http://example.test/score.pdf',
      accessPolicy: 'public',
      handoffMode: 'direct-import',
    }],
    sourceLocators: [
      {
        id: 'bad',
        source: 'Bad',
        label: 'Bad',
        sourcePageUrl: 'http://example.test',
        availability: 'search-unverified',
      },
      {
        id: 'not-proven',
        source: 'Source',
        label: 'Source',
        sourcePageUrl: 'https://example.test',
        availability: 'verified-score',
      },
    ],
  });

  assert.equal(response.results[0].sourcePageUrl, null);
  assert.equal(response.results[0].canOpenSource, false);
  assert.equal(response.results[0].canRequestIntake, false);
  assert.equal(response.sourceLocators.length, 0);
});

test('server intake handoff requires exact direct-import/public/file evidence', () => {
  const eligible = {
    id: 'provider:score',
    format: 'pdf',
    assetUrl: 'https://assets.example.test/score.pdf',
    sourcePageUrl: 'https://example.test/score',
    rightsStatus: 'open-license',
    accessPolicy: 'public',
    handoffMode: 'direct-import',
    workGroupKey: 'work::x',
    versionGroupKey: 'version::x',
  };

  assert.deepEqual(buildServerIntakeHandoff(eligible), {
    discoveryResultId: 'provider:score',
    format: 'pdf',
    assetUrl: 'https://assets.example.test/score.pdf',
    sourcePageUrl: 'https://example.test/score',
    rightsStatus: 'open-license',
    accessPolicy: 'public',
    workGroupKey: 'work::x',
    versionGroupKey: 'version::x',
    authority: 'discovery-handoff-only',
  });

  assert.equal(buildServerIntakeHandoff({ ...eligible, handoffMode: 'external-open' }), null);
  assert.equal(buildServerIntakeHandoff({ ...eligible, accessPolicy: 'entitlement-required' }), null);
  assert.equal(buildServerIntakeHandoff({ ...eligible, format: 'web' }), null);
  assert.equal(buildServerIntakeHandoff({ ...eligible, assetUrl: 'http://example.test/file.pdf' }), null);
});

test('response collections remain independently bounded', () => {
  const results = Array.from({ length: 80 }, (_, index) => ({
    id: `r:${index}`,
    title: `Result ${index}`,
    format: 'web',
    repertoireFamily: 'classical',
    sourcePageUrl: `https://example.test/${index}`,
    accessPolicy: 'public',
    handoffMode: 'external-open',
  }));
  const sourceLocators = Array.from({ length: 20 }, (_, index) => ({
    id: `l:${index}`,
    source: 'Example',
    label: `Search ${index}`,
    sourcePageUrl: `https://example.test/search/${index}`,
    availability: 'search-unverified',
    capabilities: ['notation'],
  }));

  const response = sanitizeGatewayResponse({ results, sourceLocators, totalResults: 80 });
  assert.equal(response.results.length, 50);
  assert.equal(response.sourceLocators.length, 10);
  assert.equal(response.totalResults, 80);
});
