'use strict';

const fs = require('node:fs');
const path = require('node:path');
const {runLocalPreview, readContract} = require('./st-orchestration-local-preview-adapter.cjs');

const ROOT = path.resolve(__dirname, '..');
if (!process.env.ST_ORCHESTRATION_ROOT) throw new Error('ST_ORCHESTRATION_ROOT is required');
const stRoot = path.resolve(process.env.ST_ORCHESTRATION_ROOT);
const inputPath = path.join(ROOT, 'fixtures', 'h7c', 'st-orchestration-local-preview-input-v1.json');
const contract = readContract();
const input = JSON.parse(fs.readFileSync(inputPath, 'utf8'));
const wrapper = runLocalPreview({stRoot, inputPath});

const payload = {
  schemaVersion: 'scoremosaic-st-orchestration-local-preview-data-v1',
  productionArtifact: false,
  authoritative: false,
  networkCapable: false,
  persistent: false,
  sourceMutationAllowed: false,
  teacherRevisionMutationAllowed: false,
  approvalCapable: false,
  publicationCapable: false,
  automaticLearningCapable: false,
  target: {
    repository: contract.target.repository,
    mainCommit: contract.target.mainCommit,
    modelId: contract.target.modelId,
    modelFingerprint: contract.target.modelFingerprint,
    abstentionThreshold: contract.target.abstentionThreshold,
    capability: contract.target.capability,
  },
  request: input.request,
  previewInputSha256: wrapper.preview_input_sha256,
  result: wrapper.result,
};

const source = `(() => {\n  'use strict';\n  const freezeDeep = (value) => {\n    if (value && typeof value === 'object' && !Object.isFrozen(value)) {\n      Object.freeze(value);\n      Object.keys(value).forEach((key) => freezeDeep(value[key]));\n    }\n    return value;\n  };\n  window.ScoreMosaicOrchestrationPreviewData = freezeDeep(${JSON.stringify(payload, null, 2)});\n})();\n`;

const output = process.argv[2];
if (output) fs.writeFileSync(path.resolve(output), source, 'utf8');
else process.stdout.write(source);
