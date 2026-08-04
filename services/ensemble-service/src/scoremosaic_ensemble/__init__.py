"""ScoreMosaic Ensemble canonical model and neutral comparator foundation."""

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

__all__ = [
    "COMPARISON_FORMAT_VERSION",
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
    "ComparisonResult",
    "DivisionsChange",
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
    "compare_candidates",
    "normalize_musicxml",
]

__version__ = "0.2.0"
