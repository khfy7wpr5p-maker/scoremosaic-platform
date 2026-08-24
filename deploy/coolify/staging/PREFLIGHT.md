# Coolify connection preflight

The authoritative repository-only preflight is defined by:

- `../../../contracts/coolify-connection-preflight-v1.json`
- `../../../docs/coolify-connection-preflight-v1.md`
- `../../../scripts/validate_coolify_connection_preflight.py`

Before any external Coolify connection, use the validated `main` branch with base directory `/` and Compose path `/deploy/coolify/staging/compose.yaml`.

This directory remains private-staging only: no public domains, no published host ports, no persistent score volumes, no Gateway orchestration, no real user uploads and no production activation. The repository preflight artifact is evidence of configuration validation only; it is not deployment evidence and contains no provider credentials.
