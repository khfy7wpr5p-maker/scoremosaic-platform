# Third-party notice: Audiveris

This container installs the official Audiveris Linux release package.

- Project: Audiveris
- Version: `5.11.0`
- Upstream source: `https://github.com/Audiveris/audiveris`
- Release asset: `Audiveris-5.11.0-ubuntu24.04-x86_64.deb`
- SHA-256: `f20113aaa33b3149ec8d6a09b2a7963360e65fafd92d69389987a85bbc3ec7a3`
- License: GNU Affero General Public License version 3
- Release date: 2026-07-11

The Docker build verifies the release asset checksum before installation. The image does not download an unpinned `latest` asset.

Audiveris includes a bundled Java runtime in its official installer. The adapter invokes the fixed `audiveris` command without accepting client-controlled command-line options.

Before public or user-facing network access is enabled, the project must complete a license-compliance review, preserve the corresponding source and notices, and define how source availability obligations will be satisfied. This runtime stage remains private and exposes no upload or conversion endpoint.
