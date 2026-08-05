from __future__ import annotations

import os
import platform
import sys
from dataclasses import asdict, dataclass
from typing import Final

DEVICE_POLICY: Final = "cpu_only"
MODEL_LOADING_ENABLED: Final = False
INFERENCE_ENABLED: Final = False
GPU_ENABLED: Final = False
OUTBOUND_NETWORK_ENABLED: Final = False


@dataclass(frozen=True, slots=True)
class RuntimeLimits:
    max_workers: int
    max_memory_mb: int
    max_temp_mb: int
    operation_timeout_seconds: int


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def load_runtime_limits() -> RuntimeLimits:
    return RuntimeLimits(
        max_workers=_bounded_int("ST_OMR_MAX_WORKERS", 1, 1, 4),
        max_memory_mb=_bounded_int("ST_OMR_MAX_MEMORY_MB", 512, 128, 4096),
        max_temp_mb=_bounded_int("ST_OMR_MAX_TEMP_MB", 256, 32, 2048),
        operation_timeout_seconds=_bounded_int(
            "ST_OMR_OPERATION_TIMEOUT_SECONDS", 30, 1, 300
        ),
    )


def runtime_evidence() -> dict[str, object]:
    limits = load_runtime_limits()
    return {
        "pythonImplementation": platform.python_implementation(),
        "pythonVersion": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "devicePolicy": DEVICE_POLICY,
        "gpuEnabled": GPU_ENABLED,
        "modelLoadingEnabled": MODEL_LOADING_ENABLED,
        "inferenceEnabled": INFERENCE_ENABLED,
        "outboundNetworkEnabled": OUTBOUND_NETWORK_ENABLED,
        "limits": asdict(limits),
    }
