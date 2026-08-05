"""ScoreMosaic Ensemble canonical model, comparator, and report contract."""

from .canonical import (
    CanonicalEvent,
    CanonicalMeasure,
    CanonicalModelError,
    CanonicalPart,
    CanonicalScore,
    DivisionsChange,
    EventProvenance,
    NormalizationDiagnostic,
    Pitch,
    SourceIdentity,
    TabPosition,
    TimeSignature,
    TimeSignatureChange,
    TimingMovement,
    TupletRatio,
)
from .comparator import (
    COMPARISON_FORMAT_VERSION,
    CandidateObservation,
    CandidateSummary,
    ComparisonDifference,
    ComparisonError,
    ComparisonLocation,
    ComparisonResult,
    compare_candidates,
)
from .musicxml import MusicXmlNormalizationError, normalize_musicxml
from .report import (
    REPORT_SCHEMA_VERSION,
    REPORT_TYPE,
    ComparisonReportError,
    EnsembleComparisonReport,
    build_comparison_report,
    validate_comparison_report_payload,
)

__all__ = [
    "COMPARISON_FORMAT_VERSION",
    "REPORT_SCHEMA_VERSION",
    "REPORT_TYPE",
    "CandidateObservation",
    "CandidateSummary",
    "CanonicalEvent",
    "CanonicalMeasure",
    "CanonicalModelError",
    "CanonicalPart",
    "CanonicalScore",
    "ComparisonDifference",
    "ComparisonError",
    "ComparisonLocation",
    "ComparisonReportError",
    "ComparisonResult",
    "DivisionsChange",
    "EnsembleComparisonReport",
    "EventProvenance",
    "MusicXmlNormalizationError",
    "NormalizationDiagnostic",
    "Pitch",
    "SourceIdentity",
    "TabPosition",
    "TimeSignature",
    "TimeSignatureChange",
    "TimingMovement",
    "TupletRatio",
    "build_comparison_report",
    "compare_candidates",
    "normalize_musicxml",
    "validate_comparison_report_payload",
]

__version__ = "0.2.0"
