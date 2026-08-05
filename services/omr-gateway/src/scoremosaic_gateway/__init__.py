"""ScoreMosaic OMR Gateway foundation and disabled orchestration contract."""

from .orchestration import (
    ACCEPTED_SOURCE_MEDIA_TYPES,
    ENGINE_NAMES,
    ORCHESTRATION_CONTRACT_TYPE,
    ORCHESTRATION_SCHEMA_VERSION,
    EngineRunPlan,
    ExpectedArtifactPlan,
    GatewayOrchestrationPlan,
    OrchestrationContractError,
    SourceArtifactPlan,
    build_orchestration_plan,
    verify_orchestration_plan,
)

__all__ = [
    "ACCEPTED_SOURCE_MEDIA_TYPES",
    "ENGINE_NAMES",
    "ORCHESTRATION_CONTRACT_TYPE",
    "ORCHESTRATION_SCHEMA_VERSION",
    "EngineRunPlan",
    "ExpectedArtifactPlan",
    "GatewayOrchestrationPlan",
    "OrchestrationContractError",
    "SourceArtifactPlan",
    "build_orchestration_plan",
    "verify_orchestration_plan",
    "__version__",
]

__version__ = "0.2.0"
