FROM python:3.12-slim@sha256:9f9f5d24f6f8d4dd7cc8e9c5b2f76cb0d70fb0eb8f7e1b95c73ff6fd183a21b8

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ST_OMR_PORT=8080

RUN groupadd --system --gid 10001 scoremosaic \
    && useradd --system --uid 10001 --gid scoremosaic --home-dir /nonexistent --shell /usr/sbin/nologin scoremosaic

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN python -m pip install --no-cache-dir --no-deps .

USER 10001:10001
EXPOSE 8080

CMD ["scoremosaic-st-omr"]
