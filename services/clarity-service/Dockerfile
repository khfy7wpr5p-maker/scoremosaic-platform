FROM python:3.12.11-slim-bookworm

ARG CLARITY_SOURCE_COMMIT=c6bb8a4d2a5b52842a9c41bd0f761f58d02f6f82
ARG CLARITY_SOURCE_SHA256=feee5f0f9bfe0211d3385736371e6e6bff05c496e000c9166777bd7db89c5748
ARG CLARITY_MODEL_REVISION=ee14c1e41ab371fe27bf8a2707ea588560077e73
ARG CLARITY_YOLO_SHA256=94610a2749022edd6938146505812544fece2983740fe8523907d2c855e4da73
ARG CLARITY_STAGE_B_SHA256=5138f11acd1b89d780e65fbb363dae992e8c6d3e514f0e2a01062b0ea99edb43

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    SCOREMOSAIC_CLARITY_HOST=0.0.0.0 \
    SCOREMOSAIC_CLARITY_PORT=8081 \
    SCOREMOSAIC_CLARITY_COMPUTE_MODE=cpu \
    SCOREMOSAIC_CLARITY_PYTHON_COMMAND=/usr/local/bin/python \
    SCOREMOSAIC_CLARITY_SOURCE_ROOT=/opt/clarity \
    SCOREMOSAIC_CLARITY_SOURCE_REVISION=c6bb8a4d2a5b52842a9c41bd0f761f58d02f6f82 \
    SCOREMOSAIC_CLARITY_MODEL_REVISION=ee14c1e41ab371fe27bf8a2707ea588560077e73 \
    SCOREMOSAIC_CLARITY_PROBE_TIMEOUT_SECONDS=90 \
    SCOREMOSAIC_CLARITY_REQUEST_TIMEOUT_SECONDS=1200 \
    SCOREMOSAIC_CLARITY_WORKSPACE_ROOT=/tmp/scoremosaic-clarity

WORKDIR /app

COPY requirements-runtime.txt /tmp/requirements-runtime.txt

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      libgl1 \
      libglib2.0-0 \
      libgomp1; \
    curl --fail --location --proto '=https' --tlsv1.2 \
      --retry 4 --retry-all-errors \
      --output /tmp/clarity-source.tar.gz \
      "https://codeload.github.com/clquwu/Clarity-OMR/tar.gz/${CLARITY_SOURCE_COMMIT}"; \
    echo "${CLARITY_SOURCE_SHA256}  /tmp/clarity-source.tar.gz" \
      | sha256sum --check --strict; \
    mkdir -p /opt/clarity; \
    tar -xzf /tmp/clarity-source.tar.gz --strip-components=1 -C /opt/clarity; \
    printf '%s\n' "${CLARITY_SOURCE_COMMIT}" > /opt/clarity/.scoremosaic-source-revision; \
    python -m pip install \
      --disable-pip-version-check \
      --no-cache-dir \
      --index-url https://download.pytorch.org/whl/cpu \
      "torch==2.13.0+cpu" \
      "torchvision==0.28.0+cpu"; \
    python -m pip install \
      --disable-pip-version-check \
      --no-cache-dir \
      --requirement /tmp/requirements-runtime.txt; \
    mkdir -p /opt/clarity/info; \
    curl --fail --location --proto '=https' --tlsv1.2 \
      --retry 4 --retry-all-errors \
      --output /opt/clarity/info/yolo.pt \
      "https://huggingface.co/clquwu/Clarity-OMR/resolve/${CLARITY_MODEL_REVISION}/yolo.pt?download=true"; \
    echo "${CLARITY_YOLO_SHA256}  /opt/clarity/info/yolo.pt" \
      | sha256sum --check --strict; \
    curl --fail --location --proto '=https' --tlsv1.2 \
      --retry 4 --retry-all-errors \
      --output /opt/clarity/info/model.safetensors \
      "https://huggingface.co/clquwu/Clarity-OMR/resolve/${CLARITY_MODEL_REVISION}/model.safetensors?download=true"; \
    echo "${CLARITY_STAGE_B_SHA256}  /opt/clarity/info/model.safetensors" \
      | sha256sum --check --strict; \
    test "$(python -c 'import torch; print(torch.__version__)')" = "2.13.0+cpu"; \
    test "$(python -c 'import torchvision; print(torchvision.__version__)')" = "0.28.0+cpu"; \
    test "$(python -c 'import torch; print(torch.cuda.is_available())')" = "False"; \
    python /opt/clarity/omr.py --help > /tmp/clarity-help.txt; \
    grep -F "Clarity OMR" /tmp/clarity-help.txt; \
    rm -f \
      /tmp/clarity-source.tar.gz \
      /tmp/clarity-help.txt \
      /tmp/requirements-runtime.txt; \
    apt-get purge -y --auto-remove curl; \
    rm -rf /var/lib/apt/lists/* /root/.cache

COPY src/ ./src/
COPY THIRD_PARTY_NOTICES.md /usr/share/doc/scoremosaic-clarity/THIRD_PARTY_NOTICES.md

USER 65532:65532

EXPOSE 8081

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8081/health', timeout=3).read()"]

CMD ["python", "-m", "scoremosaic_clarity.app"]
