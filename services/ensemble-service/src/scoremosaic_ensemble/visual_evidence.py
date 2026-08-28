"""Research-only visual localization evidence sidecar for polyphonic OMR.

This module does not modify Stage 6/7 candidate contracts. It validates a
separate, immutable sidecar that can bind a Canonical event to bounded page
geometry when such evidence actually exists. Missing localization remains
explicitly unavailable; no bbox, confidence, source-quality, crop, or authority
is invented.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import re
from typing import Any, Mapping

SCHEMA_VERSION = "scoremosaic-polyphonic-visual-evidence-sidecar-v1"
CURRENT_ENGINES = ("audiveris", "homr", "clarity")
MAX_PAGE_DIMENSION_PX = 50_000
MAX_PAGE_PIXELS = 200_000_000
MAX_SYMBOL_REGIONS = 64

_SHA_RE = re.compile(r"[0-9a-f]{64}\Z")
_EVIDENCE_RE = re.compile(r"visual_evidence_[0-9a-f]{24}\Z")
_CANDIDATE_RE = re.compile(r"candidate_[0-9a-f]{24}\Z")
_RUN_RE = re.compile(r"run_[0-9a-f]{24}\Z")
_ARTIFACT_RE = re.compile(r"artifact_[0-9a-f]{24}\Z")
_SAFE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,199}\Z")
_SAFE_REF_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,499}\Z")
_SAFE_VERSION_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+:-]{0,127}\Z")

_LOCALIZATION_SOURCES = frozenset(
    {
        "ENGINE_NATIVE_BBOX",
        "ENGINE_AUXILIARY_VISUAL_OUTPUT",
        "DETERMINISTIC_GEOMETRY",
        "TEACHER_ANNOTATION",
        "IMPORTED_DATASET_ANNOTATION",
    }
)
_SYMBOL_KINDS = frozenset(
    {
        "NOTEHEAD",
        "REST",
        "ACCIDENTAL",
        "STEM",
        "BEAM",
        "FLAG",
        "DOT",
        "TUPLET",
        "ORNAMENT",
        "CLEF",
        "OTHER",
    }
)
_BOUNDARIES = {
    "researchOnly": True,
    "readOnly": True,
    "sourceMutation": False,
    "productionDecisionAuthority": False,
    "engineRanking": False,
    "winnerSelection": False,
    "automaticMerge": False,
    "automaticCorrection": False,
    "teacherAuthorityOverride": False,
    "stage7EvidenceMutation": False,
    "stOmrQuorumChange": False,
}
_CORE_KEYS = {
    "schemaVersion",
    "evidenceId",
    "candidate",
    "sourcePage",
    "canonicalIdentity",
    "localization",
    "engineConfidence",
    "visualConfidence",
    "sourceQuality",
    "boundaries",
}


class VisualEvidenceError(ValueError):
    """Stable fail-closed visual evidence category."""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    except (TypeError, ValueError, OverflowError, UnicodeEncodeError):
        raise VisualEvidenceError("visual_evidence_state_invalid") from None


def _matches(pattern: re.Pattern[str], value: object) -> bool:
    return type(value) is str and pattern.fullmatch(value) is not None


def _safe_text(value: object, *, maximum: int) -> bool:
    return (
        type(value) is str
        and 1 <= len(value) <= maximum
        and all(ord(character) >= 32 for character in value)
    )


def _safe_ref(value: object) -> bool:
    if not _matches(_SAFE_REF_RE, value):
        return False
    assert isinstance(value, str)
    if value.startswith("/") or "\\" in value or "//" in value:
        return False
    return all(part not in {"", ".", ".."} for part in value.split("/"))


def _require_exact_keys(value: object, expected: set[str], category: str) -> Mapping[str, Any]:
    if type(value) is not dict or set(value) != expected:
        raise VisualEvidenceError(category)
    return value


def _validate_bbox(value: object, page_width: int, page_height: int, category: str) -> tuple[int, int, int, int]:
    bbox = _require_exact_keys(value, {"x", "y", "width", "height"}, category)
    x = bbox["x"]
    y = bbox["y"]
    width = bbox["width"]
    height = bbox["height"]
    if (
        type(x) is not int
        or type(y) is not int
        or type(width) is not int
        or type(height) is not int
        or x < 0
        or y < 0
        or width <= 0
        or height <= 0
        or x + width > page_width
        or y + height > page_height
    ):
        raise VisualEvidenceError(category)
    return x, y, width, height


def _bbox_contains(outer: tuple[int, int, int, int], inner: tuple[int, int, int, int]) -> bool:
    ox, oy, ow, oh = outer
    ix, iy, iw, ih = inner
    return (
        ix >= ox
        and iy >= oy
        and ix + iw <= ox + ow
        and iy + ih <= oy + oh
    )


def _validate_confidence(value: object, category: str) -> None:
    confidence = _require_exact_keys(
        value,
        {"available", "rawValue", "scale", "calibratedProbability"},
        category,
    )
    if type(confidence["available"]) is not bool or confidence["calibratedProbability"] is not None:
        raise VisualEvidenceError(category)
    if confidence["available"]:
        if not _safe_text(confidence["rawValue"], maximum=80) or not _safe_text(
            confidence["scale"], maximum=80
        ):
            raise VisualEvidenceError(category)
    elif confidence["rawValue"] is not None or confidence["scale"] is not None:
        raise VisualEvidenceError(category)


def _validate_source_quality(value: object) -> None:
    quality = _require_exact_keys(
        value,
        {"available", "profileRef", "profileSha256", "authoritative"},
        "source_quality_link_invalid",
    )
    if type(quality["available"]) is not bool or quality["authoritative"] is not False:
        raise VisualEvidenceError("source_quality_link_invalid")
    if quality["available"]:
        if not _safe_ref(quality["profileRef"]) or not _matches(_SHA_RE, quality["profileSha256"]):
            raise VisualEvidenceError("source_quality_link_invalid")
    elif quality["profileRef"] is not None or quality["profileSha256"] is not None:
        raise VisualEvidenceError("source_quality_link_invalid")


def validate_visual_evidence_core(payload: Mapping[str, Any]) -> None:
    """Validate the unhashed v1 sidecar payload without changing any source state."""

    core = _require_exact_keys(payload, _CORE_KEYS, "visual_evidence_schema_invalid")
    if (
        core["schemaVersion"] != SCHEMA_VERSION
        or not _matches(_EVIDENCE_RE, core["evidenceId"])
        or type(core["boundaries"]) is not dict
    ):
        raise VisualEvidenceError("visual_evidence_schema_invalid")
    boundaries = _require_exact_keys(core["boundaries"], set(_BOUNDARIES), "authority_boundary_invalid")
    if any(boundaries[key] is not expected for key, expected in _BOUNDARIES.items()):
        raise VisualEvidenceError("authority_boundary_invalid")

    candidate = _require_exact_keys(
        core["candidate"],
        {
            "engine",
            "runId",
            "candidateId",
            "candidateSha256",
            "musicxmlSha256",
            "canonicalScoreSha256",
        },
        "candidate_identity_invalid",
    )
    if (
        candidate["engine"] not in CURRENT_ENGINES
        or not _matches(_RUN_RE, candidate["runId"])
        or not _matches(_CANDIDATE_RE, candidate["candidateId"])
        or not _matches(_SHA_RE, candidate["candidateSha256"])
        or not _matches(_SHA_RE, candidate["musicxmlSha256"])
        or not _matches(_SHA_RE, candidate["canonicalScoreSha256"])
    ):
        raise VisualEvidenceError("candidate_identity_invalid")

    page = _require_exact_keys(
        core["sourcePage"],
        {
            "sourceArtifactId",
            "sourceSha256",
            "pageArtifactRef",
            "pageSha256",
            "pageIndex",
            "widthPx",
            "heightPx",
        },
        "source_page_invalid",
    )
    if (
        not _matches(_ARTIFACT_RE, page["sourceArtifactId"])
        or not _matches(_SHA_RE, page["sourceSha256"])
        or not _safe_ref(page["pageArtifactRef"])
        or not _matches(_SHA_RE, page["pageSha256"])
        or type(page["pageIndex"]) is not int
        or not 0 <= page["pageIndex"] <= 9_999
        or type(page["widthPx"]) is not int
        or type(page["heightPx"]) is not int
        or not 1 <= page["widthPx"] <= MAX_PAGE_DIMENSION_PX
        or not 1 <= page["heightPx"] <= MAX_PAGE_DIMENSION_PX
        or page["widthPx"] * page["heightPx"] > MAX_PAGE_PIXELS
    ):
        raise VisualEvidenceError("source_page_invalid")

    canonical = _require_exact_keys(
        core["canonicalIdentity"],
        {"partId", "measureId", "eventId", "sourceEventIndex", "xmlPath"},
        "canonical_identity_invalid",
    )
    if (
        not _matches(_SAFE_ID_RE, canonical["partId"])
        or not _matches(_SAFE_ID_RE, canonical["measureId"])
        or not _matches(_SAFE_ID_RE, canonical["eventId"])
        or type(canonical["sourceEventIndex"]) is not int
        or canonical["sourceEventIndex"] < 0
        or not _safe_text(canonical["xmlPath"], maximum=1_000)
    ):
        raise VisualEvidenceError("canonical_identity_invalid")

    _validate_confidence(core["engineConfidence"], "engine_confidence_invalid")
    _validate_confidence(core["visualConfidence"], "visual_confidence_invalid")
    _validate_source_quality(core["sourceQuality"])

    localization = _require_exact_keys(
        core["localization"],
        {
            "available",
            "evidenceSource",
            "methodVersion",
            "systemId",
            "measureRegionId",
            "staffId",
            "bbox",
            "symbolRegions",
            "crop",
        },
        "localization_invalid",
    )
    if type(localization["available"]) is not bool or type(localization["symbolRegions"]) is not list:
        raise VisualEvidenceError("localization_invalid")

    crop = _require_exact_keys(
        localization["crop"],
        {"available", "artifactRef", "sha256"},
        "crop_evidence_invalid",
    )
    if type(crop["available"]) is not bool:
        raise VisualEvidenceError("crop_evidence_invalid")
    if crop["available"]:
        if not _safe_ref(crop["artifactRef"]) or not _matches(_SHA_RE, crop["sha256"]):
            raise VisualEvidenceError("crop_evidence_invalid")
    elif crop["artifactRef"] is not None or crop["sha256"] is not None:
        raise VisualEvidenceError("crop_evidence_invalid")

    if not localization["available"]:
        if (
            localization["evidenceSource"] != "UNAVAILABLE"
            or localization["methodVersion"] is not None
            or localization["systemId"] is not None
            or localization["measureRegionId"] is not None
            or localization["staffId"] is not None
            or localization["bbox"] is not None
            or localization["symbolRegions"] != []
            or crop["available"]
        ):
            raise VisualEvidenceError("unavailable_localization_contains_evidence")
        return

    if (
        localization["evidenceSource"] not in _LOCALIZATION_SOURCES
        or not _matches(_SAFE_VERSION_RE, localization["methodVersion"])
        or (
            localization["systemId"] is not None
            and not _matches(_SAFE_ID_RE, localization["systemId"])
        )
        or (
            localization["measureRegionId"] is not None
            and not _matches(_SAFE_ID_RE, localization["measureRegionId"])
        )
        or type(localization["staffId"]) is not int
        or not 1 <= localization["staffId"] <= 128
        or not 0 <= len(localization["symbolRegions"]) <= MAX_SYMBOL_REGIONS
    ):
        raise VisualEvidenceError("localization_invalid")

    primary_bbox = _validate_bbox(
        localization["bbox"], page["widthPx"], page["heightPx"], "bbox_invalid"
    )
    region_ids: set[str] = set()
    for item in localization["symbolRegions"]:
        region = _require_exact_keys(
            item,
            {"regionId", "kind", "bbox"},
            "symbol_region_invalid",
        )
        if (
            not _matches(_SAFE_ID_RE, region["regionId"])
            or region["regionId"] in region_ids
            or region["kind"] not in _SYMBOL_KINDS
        ):
            raise VisualEvidenceError("symbol_region_invalid")
        region_ids.add(region["regionId"])
        symbol_bbox = _validate_bbox(
            region["bbox"], page["widthPx"], page["heightPx"], "symbol_region_invalid"
        )
        if not _bbox_contains(primary_bbox, symbol_bbox):
            raise VisualEvidenceError("symbol_region_outside_event_bbox")


def build_visual_evidence_sidecar(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return a detached, deterministic, SHA-pinned sidecar."""

    validate_visual_evidence_core(payload)
    detached = json.loads(_canonical_json(payload).decode("ascii"))
    detached["sidecarSha256"] = sha256(_canonical_json(detached)).hexdigest()
    return detached


def validate_visual_evidence_sidecar(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a complete sidecar including its deterministic SHA-256."""

    if type(payload) is not dict or set(payload) != _CORE_KEYS | {"sidecarSha256"}:
        raise VisualEvidenceError("visual_evidence_schema_invalid")
    if not _matches(_SHA_RE, payload["sidecarSha256"]):
        raise VisualEvidenceError("visual_evidence_hash_invalid")
    core = {key: deepcopy(payload[key]) for key in _CORE_KEYS}
    validate_visual_evidence_core(core)
    expected = build_visual_evidence_sidecar(core)["sidecarSha256"]
    if payload["sidecarSha256"] != expected:
        raise VisualEvidenceError("visual_evidence_hash_invalid")
    return deepcopy(dict(payload))
