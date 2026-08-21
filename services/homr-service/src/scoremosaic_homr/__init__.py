"""ScoreMosaic private HOMR adapter."""

from .source_delivery_hardening import activate as _activate_source_delivery_hardening

_activate_source_delivery_hardening()
del _activate_source_delivery_hardening

__all__ = ["__version__"]

__version__ = "0.2.0"
