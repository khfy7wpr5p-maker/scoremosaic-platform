'use strict';

const MAX_QUERY_LENGTH = 256;
const DEFAULT_LIMIT = 25;
const MAX_LIMIT = 50;
const MAX_RESULTS = 50;
const MAX_SOURCE_LOCATORS = 10;

const ALLOWED_FORMATS = new Set(['pdf', 'musicxml', 'mxl', 'mei', 'web']);
const INTAKE_FORMATS = new Set(['pdf', 'musicxml', 'mxl']);
const ALLOWED_HANDOFF_MODES = new Set(['direct-import', 'external-open', 'blocked']);
const ALLOWED_INSTRUMENTS = new Set([
  'voice', 'piano', 'guitar', 'violin', 'viola', 'cello', 'strings',
  'flute', 'oboe', 'clarinet', 'bassoon', 'horn', 'trumpet', 'trombone',
  'tuba', 'percussion', 'orchestra',
]);
const ALLOWED_ENSEMBLES = new Set([
  'solo', 'voice-piano', 'duo', 'trio', 'string-quartet', 'chamber-ensemble',
  'string-orchestra', 'chamber-orchestra', 'symphony-orchestra',
]);
const ALLOWED_SCORE_ROLES = new Set([
  'full-score', 'part', 'vocal-score', 'lead-sheet', 'guitar-vocal-score', 'tablature',
]);
const ALLOWED_FEATURES = new Set(['notation', 'chords', 'lyrics', 'tablature']);
const ALLOWED_LOCATOR_CAPABILITIES = new Set(['notation', 'chords', 'lyrics', 'tablature', 'audio', 'metadata']);

function boundedText(value, max = 256) {
  if (typeof value !== 'string') return null;
  const text = value.trim();
  if (!text || text.length > max) return null;
  return text;
}

function safeHttpsUrl(value) {
  if (typeof value !== 'string' || value.length > 2048) return null;
  try {
    const url = new URL(value);
    if (url.protocol !== 'https:' || url.username || url.password) return null;
    return url.toString();
  } catch {
    return null;
  }
}

function boundedEnumList(value, allowed, maxItems = 16) {
  if (!Array.isArray(value)) return [];
  return [...new Set(value.filter((item) => typeof item === 'string' && allowed.has(item)))].slice(0, maxItems);
}

function buildClassicalDiscoveryRequest(input = {}) {
  if (!input || typeof input !== 'object' || Array.isArray(input)) {
    throw new TypeError('discovery input must be an object');
  }

  const query = boundedText(input.query, MAX_QUERY_LENGTH);
  if (!query) throw new TypeError('query must be a non-empty string up to 256 characters');

  const sourceFilters = input.filters && typeof input.filters === 'object' && !Array.isArray(input.filters)
    ? input.filters
    : {};

  const filters = { repertoireFamily: 'classical' };

  const catalogScope = boundedText(sourceFilters.catalogScope, 32);
  if (catalogScope === 'international') filters.catalogScope = catalogScope;

  const format = boundedText(sourceFilters.format, 32);
  if (format && ALLOWED_FORMATS.has(format)) filters.format = format;

  const requiredInstruments = boundedEnumList(sourceFilters.requiredInstruments, ALLOWED_INSTRUMENTS, 12);
  if (requiredInstruments.length) filters.requiredInstruments = requiredInstruments;

  const ensembleType = boundedText(sourceFilters.ensembleType, 64);
  if (ensembleType && ALLOWED_ENSEMBLES.has(ensembleType)) filters.ensembleType = ensembleType;

  const scoreRole = boundedText(sourceFilters.scoreRole, 64);
  if (scoreRole && ALLOWED_SCORE_ROLES.has(scoreRole)) filters.scoreRole = scoreRole;

  const requiredFeatures = boundedEnumList(sourceFilters.requiredFeatures, ALLOWED_FEATURES, 4);
  if (requiredFeatures.length) filters.requiredFeatures = requiredFeatures;

  const requestedLimit = Number.isInteger(input.limit) ? input.limit : DEFAULT_LIMIT;
  const limit = Math.max(1, Math.min(MAX_LIMIT, requestedLimit));

  return { query, filters, limit };
}

function sanitizeResult(result) {
  if (!result || typeof result !== 'object' || Array.isArray(result)) return null;
  const id = boundedText(result.id, 256);
  const title = boundedText(result.title, 512);
  const format = boundedText(result.format, 32);
  const handoffMode = boundedText(result.handoffMode, 32);
  if (!id || !title || !format || !ALLOWED_FORMATS.has(format) || !ALLOWED_HANDOFF_MODES.has(handoffMode)) {
    return null;
  }

  const sourcePageUrl = safeHttpsUrl(result.sourcePageUrl);
  const assetUrl = safeHttpsUrl(result.assetUrl);
  const canOpenSource = Boolean(sourcePageUrl && handoffMode !== 'blocked');
  const canRequestIntake = Boolean(
    handoffMode === 'direct-import' &&
    INTAKE_FORMATS.has(format) &&
    assetUrl &&
    result.accessPolicy === 'public'
  );

  return {
    id,
    title,
    artist: boundedText(result.artist, 512),
    source: boundedText(result.source, 256),
    format,
    repertoireFamily: result.repertoireFamily === 'classical' ? 'classical' : 'unknown',
    catalogScope: result.catalogScope === 'international' ? 'international' : 'unknown',
    instrumentation: boundedEnumList(result.instrumentation, ALLOWED_INSTRUMENTS, 16),
    ensembleType: ALLOWED_ENSEMBLES.has(result.ensembleType) ? result.ensembleType : 'unknown',
    scoreRole: ALLOWED_SCORE_ROLES.has(result.scoreRole) ? result.scoreRole : 'unknown',
    contentFeatures: boundedEnumList(result.contentFeatures, ALLOWED_FEATURES, 4),
    rightsStatus: boundedText(result.rightsStatus, 64),
    accessPolicy: boundedText(result.accessPolicy, 64),
    handoffMode,
    sourcePageUrl,
    workGroupKey: boundedText(result.workGroupKey, 512),
    versionGroupKey: boundedText(result.versionGroupKey, 1024),
    canOpenSource,
    canRequestIntake,
  };
}

function sanitizeLocator(locator) {
  if (!locator || typeof locator !== 'object' || Array.isArray(locator)) return null;
  const sourcePageUrl = safeHttpsUrl(locator.sourcePageUrl);
  if (!sourcePageUrl || locator.availability !== 'search-unverified') return null;
  const source = boundedText(locator.source, 128);
  const label = boundedText(locator.label, 256);
  if (!source || !label) return null;
  return {
    id: boundedText(locator.id, 256),
    source,
    label,
    sourcePageUrl,
    capabilities: boundedEnumList(locator.capabilities, ALLOWED_LOCATOR_CAPABILITIES, 8),
    queryApplied: locator.queryApplied === true,
    availability: 'search-unverified',
    note: boundedText(locator.note, 512),
  };
}

function sanitizeGatewayResponse(payload = {}) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    return { results: [], sourceLocators: [], totalResults: 0, partial: true };
  }

  const results = (Array.isArray(payload.results) ? payload.results : [])
    .slice(0, MAX_RESULTS)
    .map(sanitizeResult)
    .filter(Boolean);
  const sourceLocators = (Array.isArray(payload.sourceLocators) ? payload.sourceLocators : [])
    .slice(0, MAX_SOURCE_LOCATORS)
    .map(sanitizeLocator)
    .filter(Boolean);

  const totalResults = Number.isSafeInteger(payload.totalResults) && payload.totalResults >= 0
    ? payload.totalResults
    : results.length;

  return {
    results,
    sourceLocators,
    totalResults,
    partial: Array.isArray(payload.providerErrors) && payload.providerErrors.length > 0,
  };
}

function buildServerIntakeHandoff(result) {
  if (!result || typeof result !== 'object' || Array.isArray(result)) {
    throw new TypeError('result must be an object');
  }
  const format = boundedText(result.format, 32);
  const assetUrl = safeHttpsUrl(result.assetUrl);
  if (
    result.handoffMode !== 'direct-import' ||
    result.accessPolicy !== 'public' ||
    !INTAKE_FORMATS.has(format) ||
    !assetUrl
  ) {
    return null;
  }

  return {
    discoveryResultId: boundedText(result.id, 256),
    format,
    assetUrl,
    sourcePageUrl: safeHttpsUrl(result.sourcePageUrl),
    rightsStatus: boundedText(result.rightsStatus, 64),
    accessPolicy: 'public',
    workGroupKey: boundedText(result.workGroupKey, 512),
    versionGroupKey: boundedText(result.versionGroupKey, 1024),
    authority: 'discovery-handoff-only',
  };
}

module.exports = {
  buildClassicalDiscoveryRequest,
  sanitizeGatewayResponse,
  buildServerIntakeHandoff,
};
