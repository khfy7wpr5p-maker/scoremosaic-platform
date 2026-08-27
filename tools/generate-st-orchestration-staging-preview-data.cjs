'use strict';

const fs = require('node:fs');
const path = require('node:path');
const {
  requestStagingPreview,
  toBrowserPreviewData,
} = require('./st-orchestration-staging-preview-adapter.cjs');

const ROOT = path.resolve(__dirname, '..');
const inputPath = path.join(ROOT, 'fixtures', 'h7c', 'st-orchestration-local-preview-input-v1.json');

const sourceFor = (payload) => `(() => {\n  'use strict';\n  const freezeDeep = (value) => {\n    if (value && typeof value === 'object' && !Object.isFrozen(value)) {\n      Object.freeze(value);\n      Object.keys(value).forEach((key) => freezeDeep(value[key]));\n    }\n    return value;\n  };\n  window.ScoreMosaicOrchestrationPreviewData = freezeDeep(${JSON.stringify(payload, null, 2)});\n})();\n`;

const main = async () => {
  const endpoint = process.env.ST_ORCHESTRATION_STAGING_ENDPOINT;
  const secret = process.env.ST_ORCHESTRATION_STAGING_HMAC_SECRET;
  if (!endpoint) throw new Error('ST_ORCHESTRATION_STAGING_ENDPOINT is required');
  if (!secret) throw new Error('ST_ORCHESTRATION_STAGING_HMAC_SECRET is required');
  const allowLoopbackHttpForTest = process.env.ST_ORCHESTRATION_ALLOW_LOOPBACK_HTTP_TEST === '1';
  const input = JSON.parse(fs.readFileSync(inputPath, 'utf8'));
  const wrapper = await requestStagingPreview({endpoint, secret, input, allowLoopbackHttpForTest});
  const payload = toBrowserPreviewData(wrapper, input);
  const source = sourceFor(payload);
  const output = process.argv[2];
  if (output) fs.writeFileSync(path.resolve(output), source, 'utf8');
  else process.stdout.write(source);
};

main().catch((error) => {
  process.stderr.write(`H7-D staging preview generation failed: ${error.message}\n`);
  process.exitCode = 1;
});
