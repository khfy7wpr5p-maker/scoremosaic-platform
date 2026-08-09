FROM python:3.12.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    SCOREMOSAIC_GATEWAY_HOST=0.0.0.0 \
    SCOREMOSAIC_GATEWAY_PORT=8090 \
    SCOREMOSAIC_GATEWAY_ORCHESTRATION_MODE=disabled \
    SCOREMOSAIC_GATEWAY_WORKSPACE_ROOT=/tmp/scoremosaic-gateway

WORKDIR /app

RUN python -m pip install --no-cache-dir --disable-pip-version-check pypdf==6.14.2

COPY src/ ./src/

USER 65532:65532

EXPOSE 8090

HEALTHCHECK --interval=10s --timeout=3s --start-period=3s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8090/health', timeout=2).read()"]

CMD ["python", "-m", "scoremosaic_gateway.app"]
