FROM python:3.12.11-slim-bookworm

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
