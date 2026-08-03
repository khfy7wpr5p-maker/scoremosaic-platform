FROM python:3.12.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    SCOREMOSAIC_AUDIVERIS_HOST=0.0.0.0 \
    SCOREMOSAIC_AUDIVERIS_PORT=8082 \
    SCOREMOSAIC_AUDIVERIS_RUNTIME_MODE=disabled \
    SCOREMOSAIC_AUDIVERIS_WORKSPACE_ROOT=/tmp/scoremosaic-audiveris

WORKDIR /app

COPY src/ ./src/

USER 65532:65532

EXPOSE 8082

HEALTHCHECK --interval=10s --timeout=3s --start-period=3s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8082/health', timeout=2).read()"]

CMD ["python", "-m", "scoremosaic_audiveris.app"]
