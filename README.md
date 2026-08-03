# ScoreMosaic Platform

ScoreMosaic is an independent, multi-engine optical music recognition (OMR) platform for comparing OMR candidates, detecting musical inconsistencies, and preparing structured findings for teacher review.

## Current status

**Phase 0 — foundation only.**

This repository does not yet contain production OMR services, model files, or a live deployment. The first phase defines architecture, security boundaries, data contracts, and the teacher-review workflow before any engine integration begins.

## Planned platform services

- `homr-service` — isolated HOMR adapter and runtime
- `clarity-service` — isolated Clarity-OMR adapter and runtime
- `ensemble-service` — candidate comparison, confidence evidence, and issue reporting
- Future: Audiveris adapter and a teacher-review API

## Core principles

1. OMR output is never treated as automatically correct.
2. Original PDF and engine outputs remain immutable.
3. Measure, pitch, rhythm, rest, chord, voice, staff, and TAB differences are reported with evidence.
4. Automatic merging of raw MusicXML is outside the first Ensemble release.
5. Teacher approval is required before a result can be published to a learner-facing application.
6. Untrusted PDF and MusicXML data must pass strict validation and resource limits.
7. Development happens through feature branches and pull requests; staging is validated before production.

## Repository boundaries

ScoreMosaic is not the learner-facing music application. External applications will connect to it through a versioned, authenticated API after the platform contracts and security controls are established.

## Development workflow

- Source control: GitHub
- Development environment: GitHub Codespaces
- Automated checks: GitHub Actions (planned)
- Deployment target: Coolify staging, then production

See `docs/` and `contracts/` for the Phase 0 specification.
