(() => {
  'use strict';
  const freezeDeep = (value) => {
    if (value && typeof value === 'object' && !Object.isFrozen(value)) {
      Object.freeze(value);
      Object.keys(value).forEach((key) => freezeDeep(value[key]));
    }
    return value;
  };
  window.ScoreMosaicOrchestrationPreviewData = freezeDeep({
  "schemaVersion": "scoremosaic-st-orchestration-local-preview-data-v1",
  "productionArtifact": false,
  "authoritative": false,
  "networkCapable": false,
  "persistent": false,
  "sourceMutationAllowed": false,
  "teacherRevisionMutationAllowed": false,
  "approvalCapable": false,
  "publicationCapable": false,
  "automaticLearningCapable": false,
  "target": {
    "repository": "khfy7wpr5p-maker/ST-Orchestration",
    "mainCommit": "f5ee0e605e62c41af86255712941305b2a8c7afb",
    "modelId": "o5c-ossq-anonymous-context-v0",
    "modelFingerprint": "15cd94722a0ba2724ceea6f450f16a87ef455fa8bc21d4b619f0bda6d880ca14",
    "abstentionThreshold": 0.55,
    "capability": "string-seat-ranking-v0"
  },
  "request": {
    "integration_request_id": "scoremosaic-h7c-local-001",
    "document_id": "fixture-score-001",
    "canonical_score_id": "fixture-canonical-001",
    "teacher_revision_id": "fixture-r3",
    "corrected_musicxml_sha256": "1111111111111111111111111111111111111111111111111111111111111111",
    "source_state": "validated-preview",
    "capability": "string-seat-ranking-v0"
  },
  "previewInputSha256": "232896f7af0b1fde5261c6a8a2359ff2e4082574b9b4559d97050d2359c63fdf",
  "result": {
    "abstention_threshold": 0.55,
    "alternatives": [
      {
        "confidence": 0.9271937969980509,
        "instrument": "violin-1"
      },
      {
        "confidence": 0.0724528864781487,
        "instrument": "violin-2"
      },
      {
        "confidence": 0.00022699501083995596,
        "instrument": "cello"
      },
      {
        "confidence": 0.0001263215129604685,
        "instrument": "viola"
      }
    ],
    "candidate_id": "o5c-ossq-anonymous-context-v0",
    "capability": "string-seat-ranking-v0",
    "corrected_musicxml_sha256": "1111111111111111111111111111111111111111111111111111111111111111",
    "deterministic_validation": {
      "passed": true,
      "violations": []
    },
    "integration_request_id": "scoremosaic-h7c-local-001",
    "model_fingerprint": "15cd94722a0ba2724ceea6f450f16a87ef455fa8bc21d4b619f0bda6d880ca14",
    "result_sha256": "2ee992b14ce19a0a4d326b05b6ad7c737dcf69a973626e207f1ca8fb33f109af",
    "status": "proposal"
  }
});
})();
