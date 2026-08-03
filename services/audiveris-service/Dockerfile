FROM ubuntu:24.04

ARG AUDIVERIS_VERSION=5.11.0
ARG AUDIVERIS_DEB_SHA256=f20113aaa33b3149ec8d6a09b2a7963360e65fafd92d69389987a85bbc3ec7a3
ARG AUDIVERIS_DEB_NAME=Audiveris-5.11.0-ubuntu24.04-x86_64.deb

LABEL org.opencontainers.image.title="ScoreMosaic Audiveris adapter" \
      org.opencontainers.image.source="https://github.com/khfy7wpr5p-maker/scoremosaic-platform" \
      org.opencontainers.image.version="0.2.0" \
      org.opencontainers.image.licenses="AGPL-3.0-only"

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    SCOREMOSAIC_AUDIVERIS_HOST=0.0.0.0 \
    SCOREMOSAIC_AUDIVERIS_PORT=8082 \
    SCOREMOSAIC_AUDIVERIS_RUNTIME_MODE=audiveris \
    SCOREMOSAIC_AUDIVERIS_COMMAND=/usr/bin/audiveris \
    SCOREMOSAIC_AUDIVERIS_VERSION=5.11.0 \
    SCOREMOSAIC_AUDIVERIS_PROBE_TIMEOUT_SECONDS=20 \
    SCOREMOSAIC_AUDIVERIS_WORKSPACE_ROOT=/tmp/scoremosaic-audiveris \
    HOME=/tmp/scoremosaic-audiveris/home \
    XDG_CACHE_HOME=/tmp/scoremosaic-audiveris/home/.cache \
    XDG_CONFIG_HOME=/tmp/scoremosaic-audiveris/home/.config \
    XDG_DATA_HOME=/tmp/scoremosaic-audiveris/home/.local/share \
    TMPDIR=/tmp/scoremosaic-audiveris/tmp \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

RUN set -eux; \
    test "$(dpkg --print-architecture)" = "amd64"; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl python3-minimal python-is-python3; \
    curl --fail --location --proto '=https' --tlsv1.2 --retry 4 --retry-all-errors \
      --output "/tmp/${AUDIVERIS_DEB_NAME}" \
      "https://github.com/Audiveris/audiveris/releases/download/${AUDIVERIS_VERSION}/${AUDIVERIS_DEB_NAME}"; \
    echo "${AUDIVERIS_DEB_SHA256}  /tmp/${AUDIVERIS_DEB_NAME}" | sha256sum --check --strict; \
    apt-get install -y --no-install-recommends "/tmp/${AUDIVERIS_DEB_NAME}"; \
    rm -f "/tmp/${AUDIVERIS_DEB_NAME}"; \
    command -v audiveris; \
    audiveris -version 2>&1 | grep -F "${AUDIVERIS_VERSION}"; \
    apt-get purge -y --auto-remove curl; \
    rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    groupadd --system --gid 65532 scoremosaic; \
    useradd --system --uid 65532 --gid 65532 --home-dir /nonexistent --shell /usr/sbin/nologin scoremosaic

WORKDIR /app
COPY src/ ./src/

USER 65532:65532
EXPOSE 8082

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8082/health', timeout=3).read()"]

CMD ["python", "-m", "scoremosaic_audiveris.app"]
