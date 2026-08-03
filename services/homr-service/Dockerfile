FROM python:3.12.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    SCOREMOSAIC_HOMR_HOST=0.0.0.0 \
    SCOREMOSAIC_HOMR_PORT=8080 \
    SCOREMOSAIC_HOMR_WORKSPACE_ROOT=/tmp/scoremosaic-homr

WORKDIR /app

COPY src/ ./src/

USER 65532:65532

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=3s --start-period=3s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=2).read()"]

CMD ["python", "-m", "scoremosaic_homr.app"]
