"""ScoreMosaic private Clarity-OMR adapter."""

from .source_delivery_hardening import activate as _activate_source_delivery_hardening

_activate_source_delivery_hardening()
del _activate_source_delivery_hardening

from .authenticated_execution_trigger_hardening import activate as _activate_execution_trigger_hardening

_activate_execution_trigger_hardening()
del _activate_execution_trigger_hardening

__all__ = ["__version__"]

__version__ = "0.2.0"
