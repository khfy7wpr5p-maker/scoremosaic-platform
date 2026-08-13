"""Compatibility import surface for the canonical Gate E.4A session contract.

All upload-session authority lives in :mod:`scoremosaic_gateway.safe_upload_session`.
This module intentionally defines no second policy, decision, reservation algorithm,
or construction seal. It may be removed in a separately approved cleanup once no
callers depend on the historical module path.
"""

from .safe_upload_session import (
    MAX_SAFE_UPLOAD_SESSION_PDF_PAGES as MAX_UPLOAD_SESSION_PDF_PAGES,
    MAX_SAFE_UPLOAD_SESSION_TTL_SECONDS as MAX_UPLOAD_SESSION_TTL_SECONDS,
    MIN_SAFE_UPLOAD_SESSION_TTL_SECONDS as MIN_UPLOAD_SESSION_TTL_SECONDS,
    SAFE_UPLOAD_SESSION_CONTRACT_VERSION as EXTERNAL_UPLOAD_SESSION_CONTRACT_VERSION,
    SafeUploadSessionDecision as ExternalUploadSessionDecision,
    SafeUploadSessionError as ExternalUploadSessionError,
    SafeUploadSessionPolicy as ExternalUploadSessionPolicy,
    SafeUploadSessionReservationReceipt as ExternalUploadSessionReservationReceipt,
    SafeUploadSessionReservationRequest as ExternalUploadSessionReservationRequest,
    SafeUploadSessionReserver as ExternalUploadSessionReserver,
    reserve_safe_upload_session as reserve_external_upload_session,
)

__all__ = (
    "EXTERNAL_UPLOAD_SESSION_CONTRACT_VERSION",
    "MIN_UPLOAD_SESSION_TTL_SECONDS",
    "MAX_UPLOAD_SESSION_TTL_SECONDS",
    "MAX_UPLOAD_SESSION_PDF_PAGES",
    "ExternalUploadSessionError",
    "ExternalUploadSessionPolicy",
    "ExternalUploadSessionReservationRequest",
    "ExternalUploadSessionReservationReceipt",
    "ExternalUploadSessionReserver",
    "ExternalUploadSessionDecision",
    "reserve_external_upload_session",
)
