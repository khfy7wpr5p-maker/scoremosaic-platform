FROM python:3.12.11-slim-bookworm

ARG HOMR_VERSION=0.7.0
ARG HOMR_WHEEL_SHA256=84c6028df06e60b1aff158c9049d1876b22137144e319b61bacc41518842c4a9

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    SCOREMOSAIC_HOMR_HOST=0.0.0.0 \
    SCOREMOSAIC_HOMR_PORT=8080 \
    SCOREMOSAIC_HOMR_RUNTIME_MODE=homr \
    SCOREMOSAIC_HOMR_COMMAND=/usr/local/bin/homr \
    SCOREMOSAIC_HOMR_VERSION=0.7.0 \
    SCOREMOSAIC_HOMR_PROBE_TIMEOUT_SECONDS=30 \
    SCOREMOSAIC_HOMR_REQUEST_TIMEOUT_SECONDS=900 \
    SCOREMOSAIC_HOMR_WORKSPACE_ROOT=/tmp/scoremosaic-homr

WORKDIR /app

COPY requirements-runtime.txt /tmp/requirements-runtime.txt

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      libgl1 \
      libglib2.0-0 \
      libgomp1 \
      unzip; \
    python -m pip download \
      --disable-pip-version-check \
      --no-deps \
      --dest /tmp \
      "homr==${HOMR_VERSION}"; \
    echo "${HOMR_WHEEL_SHA256}  /tmp/homr-${HOMR_VERSION}-py3-none-any.whl" \
      | sha256sum --check --strict; \
    python -m pip install \
      --disable-pip-version-check \
      --no-cache-dir \
      --requirement /tmp/requirements-runtime.txt \
      "/tmp/homr-${HOMR_VERSION}-py3-none-any.whl"; \
    homr_root="$(python -c 'import homr, pathlib; print(pathlib.Path(homr.__file__).resolve().parent)')"; \
    download_model() { \
      archive="$1"; \
      archive_sha="$2"; \
      destination="$3"; \
      output_sha="$4"; \
      output_name="$5"; \
      url="https://github.com/liebharc/homr/releases/download/onnx_checkpoints/${archive}"; \
      curl --fail --location --proto '=https' --tlsv1.2 \
        --retry 4 --retry-all-errors \
        --output "/tmp/${archive}" "${url}"; \
      echo "${archive_sha}  /tmp/${archive}" | sha256sum --check --strict; \
      mkdir -p "${destination}"; \
      unzip -j -q "/tmp/${archive}" -d "${destination}"; \
      echo "${output_sha}  ${destination}/${output_name}" \
        | sha256sum --check --strict; \
      rm -f "/tmp/${archive}"; \
    }; \
    download_model \
      "segnet_308-3296ccd40960f90ca6ab9c035cca945675d30a0f.zip" \
      "1d4277354a8397a6830ef1279232e6d989c2d254b7451525e53ff3d3754b1f70" \
      "${homr_root}/segmentation" \
      "6ed36640db4ef5d223098b6d5efe4eda97c66b24a2c72faab8a018c749003a8d" \
      "segnet_308-3296ccd40960f90ca6ab9c035cca945675d30a0f.onnx"; \
    download_model \
      "encoder_pytorch_model_426-b6fd20809a8dcaf10dfd39a4ca4f64c6f056e644.zip" \
      "10128de32aad243cb8b85e7b6bc059b9e376f33d85a6d442974b86c2b7f2b847" \
      "${homr_root}/transformer" \
      "1513e83ae281ef06cdb8f08451b59f06c56536f13bd3418b4fd13227543dc4ff" \
      "encoder_pytorch_model_426-b6fd20809a8dcaf10dfd39a4ca4f64c6f056e644.onnx"; \
    download_model \
      "decoder_pytorch_model_426-b6fd20809a8dcaf10dfd39a4ca4f64c6f056e644.zip" \
      "c28801d95ff062190b00d84d73e73cbca13df2fdeb01886ba82363e20ebe83da" \
      "${homr_root}/transformer" \
      "8652b5c2e3129775ca9109eb180c16c3615413ce38005adc8ce5966c3c76737c" \
      "decoder_pytorch_model_426-b6fd20809a8dcaf10dfd39a4ca4f64c6f056e644.onnx"; \
    test "$(python -c 'from importlib.metadata import version; print(version("homr"))')" = "${HOMR_VERSION}"; \
    homr --help > /tmp/homr-help.txt; \
    grep -F "optical music recognition" /tmp/homr-help.txt; \
    rm -f \
      "/tmp/homr-${HOMR_VERSION}-py3-none-any.whl" \
      /tmp/homr-help.txt \
      /tmp/requirements-runtime.txt; \
    apt-get purge -y --auto-remove curl unzip; \
    rm -rf /var/lib/apt/lists/* /root/.cache

COPY src/ ./src/
COPY THIRD_PARTY_NOTICES.md /usr/share/doc/scoremosaic-homr/THIRD_PARTY_NOTICES.md

USER 65532:65532

EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3).read()"]

CMD ["python", "-m", "scoremosaic_homr.app"]
