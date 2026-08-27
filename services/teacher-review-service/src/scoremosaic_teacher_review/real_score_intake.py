from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re
from typing import Any, Mapping


REAL_SCORE_INTAKE_VERSION = "scoremosaic-real-score-intake-v1"
REAL_SCORE_INTAKE_BINDING_TYPE = "scoremosaic.real-score-intake-binding"
MAX_MUSICXML_BYTES = 64 * 1024 * 1024
MAX_REVIEW_BINDINGS = 1000

_ENGINE_NAMES = frozenset({"homr", "clarity", "audiveris"})
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_GENERIC_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")
_ARTIFACT_ID_RE = re.compile(r"^artifact_[0-9a-f]{24}$")
_CANDIDATE_ID_RE = re.compile(r"^candidate_[0-9a-f]{24}$")
_SAFE_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")
_SAFE_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+:-]{0,127}$")

_TOP_KEYS = frozenset({
    "schemaVersion",
    "bindingType",
    "document",
    "source",
    "candidate",
    "canonical",
    "mappingPolicy",
    "reviewBindings",
    "authority",
})
_DOCUMENT_KEYS = frozenset({"documentId", "revision"})
_SOURCE_KEYS = frozenset({"sourceArtifactId", "sourceSha256"})
_CANDIDATE_KEYS = frozenset({
    "engine",
    "candidateId",
    "candidateNamespace",
    "candidateSha256",
    "sourceArtifactId",
    "sourceSha256",
    "musicxmlArtifactId",
    "musicxmlSha256",
    "engineVersion",
    "modelVersion",
})
_CANONICAL_KEYS = frozenset({
    "canonicalSha256",
    "sourceEngine",
    "sourceArtifactRef",
    "sourceArtifactSha256",
})
_MAPPING_POLICY = {
    "scoreSource": "canonical",
    "eventIdentity": "preserve-canonical-event-id",
    "musicXmlRole": "immutable-candidate-evidence",
    "syntheticScoreAllowed": False,
    "rendererAuthority": False,
}
_REVIEW_BINDING_KEYS = frozenset({
    "issueId",
    "sourceRegion",
    "candidateId",
    "candidateSha256",
    "canonicalSha256",
    "canonicalEventId",
    "coreEventId",
    "provenance",
})
_PROVENANCE_KEYS = frozenset({"xmlPath", "sourceEventIndex"})
_AUTHORITY = {
    "bindingOnly": True,
    "networkCapable": False,
    "persistent": False,
    "finalTruthAuthority": False,
    "writeAuthority": False,
    "approvalAuthority": False,
    "publicationAuthority": False,
    "automaticCorrectionAuthority": False,
}


class RealScoreIntakeError(ValueError):
    """Stable fail-closed Real Score Intake validation category."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> None:
    raise RealScoreIntakeError(code)


def _require_closed_dict(value: Any, keys: frozenset[str], code: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != set(keys):
        _fail(code)
    return value


def _require_match(value: Any, pattern: re.Pattern[str], code: str) -> str:
    if type(value) is not str or pattern.fullmatch(value) is None:
        _fail(code)
    return value


def _require_hash(value: Any, code: str) -> str:
    return _require_match(value, _HASH_RE, code)


def _require_version(value: Any, code: str) -> str | None:
    if value is None:
        return None
    return _require_match(value, _SAFE_VERSION_RE, code)


def _require_bounded_text(value: Any, *, maximum: int, code: str) -> str:
    if type(value) is not str or not value or len(value) > maximum:
        _fail(code)
    return value


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeError):
        _fail("INTAKE_PAYLOAD_INVALID")


@dataclass(frozen=True, slots=True)
class RealScoreIntakeBinding:
    document_id: str
    revision: str
    source_artifact_id: str
    source_sha256: str
    engine: str
    candidate_id: str
    candidate_sha256: str
    musicxml_artifact_id: str
    musicxml_sha256: str
    canonical_sha256: str
    review_binding_count: int
    binding_sha256: str

    def as_safe_dict(self) -> dict[str, Any]:
        return {
            "version": REAL_SCORE_INTAKE_VERSION,
            "documentId": self.document_id,
            "revision": self.revision,
            "sourceArtifactId": self.source_artifact_id,
            "sourceSha256": self.source_sha256,
            "engine": self.engine,
            "candidateId": self.candidate_id,
            "candidateSha256": self.candidate_sha256,
            "musicxmlArtifactId": self.musicxml_artifact_id,
            "musicxmlSha256": self.musicxml_sha256,
            "canonicalSha256": self.canonical_sha256,
            "reviewBindingCount": self.review_binding_count,
            "bindingSha256": self.binding_sha256,
            "bindingOnly": True,
            "authoritative": False,
            "persistent": False,
            "networkCapable": False,
        }


def _validate_review_binding(
    value: Any,
    *,
    candidate_id: str,
    candidate_sha256: str,
    canonical_sha256: str,
) -> dict[str, Any]:
    item = _require_closed_dict(
        value,
        _REVIEW_BINDING_KEYS,
        "INTAKE_REVIEW_BINDING_INVALID",
    )
    issue_id = _require_match(
        item.get("issueId"),
        _GENERIC_ID_RE,
        "INTAKE_REVIEW_BINDING_INVALID",
    )
    source_region = _require_bounded_text(
        item.get("sourceRegion"),
        maximum=240,
        code="INTAKE_REVIEW_BINDING_INVALID",
    )
    bound_candidate_id = _require_match(
        item.get("candidateId"),
        _CANDIDATE_ID_RE,
        "INTAKE_REVIEW_BINDING_INVALID",
    )
    bound_candidate_sha = _require_hash(
        item.get("candidateSha256"),
        "INTAKE_REVIEW_BINDING_INVALID",
    )
    bound_canonical_sha = _require_hash(
        item.get("canonicalSha256"),
        "INTAKE_REVIEW_BINDING_INVALID",
    )
    if (
        bound_candidate_id != candidate_id
        or bound_candidate_sha != candidate_sha256
        or bound_canonical_sha != canonical_sha256
    ):
        _fail("INTAKE_ISSUE_BINDING_MISMATCH")

    canonical_event_id = _require_match(
        item.get("canonicalEventId"),
        _GENERIC_ID_RE,
        "INTAKE_REVIEW_BINDING_INVALID",
    )
    core_event_id = _require_match(
        item.get("coreEventId"),
        _GENERIC_ID_RE,
        "INTAKE_REVIEW_BINDING_INVALID",
    )
    if canonical_event_id != core_event_id:
        _fail("INTAKE_EVENT_BINDING_MISMATCH")

    provenance = _require_closed_dict(
        item.get("provenance"),
        _PROVENANCE_KEYS,
        "INTAKE_REVIEW_BINDING_INVALID",
    )
    xml_path = _require_bounded_text(
        provenance.get("xmlPath"),
        maximum=1000,
        code="INTAKE_REVIEW_BINDING_INVALID",
    )
    source_event_index = provenance.get("sourceEventIndex")
    if type(source_event_index) is not int or source_event_index < 0:
        _fail("INTAKE_REVIEW_BINDING_INVALID")

    return {
        "issueId": issue_id,
        "sourceRegion": source_region,
        "candidateId": bound_candidate_id,
        "candidateSha256": bound_candidate_sha,
        "canonicalSha256": bound_canonical_sha,
        "canonicalEventId": canonical_event_id,
        "coreEventId": core_event_id,
        "provenance": {
            "xmlPath": xml_path,
            "sourceEventIndex": source_event_index,
        },
    }


def validate_real_score_intake(
    payload: Mapping[str, Any],
    *,
    musicxml: bytes,
) -> RealScoreIntakeBinding:
    """Validate immutable candidate/canonical/review identity bindings only.

    The function performs no file, network, persistence, approval, publication,
    correction, rendering, or source mutation operation. ``musicxml`` is used
    only to prove that the bound MusicXML hash matches the exact bytes supplied
    to the caller by an already-authenticated candidate boundary.
    """

    body = _require_closed_dict(payload, _TOP_KEYS, "INTAKE_SCHEMA_CLOSED")
    if body.get("schemaVersion") != REAL_SCORE_INTAKE_VERSION:
        _fail("INTAKE_VERSION_INVALID")
    if body.get("bindingType") != REAL_SCORE_INTAKE_BINDING_TYPE:
        _fail("INTAKE_BINDING_TYPE_INVALID")
    if type(musicxml) is not bytes or not musicxml or len(musicxml) > MAX_MUSICXML_BYTES:
        _fail("INTAKE_MUSICXML_INVALID")

    document = _require_closed_dict(
        body.get("document"),
        _DOCUMENT_KEYS,
        "INTAKE_DOCUMENT_INVALID",
    )
    document_id = _require_match(
        document.get("documentId"),
        _GENERIC_ID_RE,
        "INTAKE_DOCUMENT_INVALID",
    )
    revision = _require_match(
        document.get("revision"),
        _GENERIC_ID_RE,
        "INTAKE_DOCUMENT_INVALID",
    )

    source = _require_closed_dict(
        body.get("source"),
        _SOURCE_KEYS,
        "INTAKE_SOURCE_INVALID",
    )
    source_artifact_id = _require_match(
        source.get("sourceArtifactId"),
        _ARTIFACT_ID_RE,
        "INTAKE_SOURCE_INVALID",
    )
    source_sha = _require_hash(source.get("sourceSha256"), "INTAKE_SOURCE_INVALID")

    candidate = _require_closed_dict(
        body.get("candidate"),
        _CANDIDATE_KEYS,
        "INTAKE_CANDIDATE_INVALID",
    )
    engine = candidate.get("engine")
    if type(engine) is not str or engine not in _ENGINE_NAMES:
        _fail("INTAKE_CANDIDATE_INVALID")
    candidate_id = _require_match(
        candidate.get("candidateId"),
        _CANDIDATE_ID_RE,
        "INTAKE_CANDIDATE_INVALID",
    )
    _require_match(
        candidate.get("candidateNamespace"),
        _SAFE_REF_RE,
        "INTAKE_CANDIDATE_INVALID",
    )
    candidate_sha = _require_hash(
        candidate.get("candidateSha256"),
        "INTAKE_CANDIDATE_INVALID",
    )
    candidate_source_artifact_id = _require_match(
        candidate.get("sourceArtifactId"),
        _ARTIFACT_ID_RE,
        "INTAKE_CANDIDATE_INVALID",
    )
    candidate_source_sha = _require_hash(
        candidate.get("sourceSha256"),
        "INTAKE_CANDIDATE_INVALID",
    )
    musicxml_artifact_id = _require_match(
        candidate.get("musicxmlArtifactId"),
        _ARTIFACT_ID_RE,
        "INTAKE_CANDIDATE_INVALID",
    )
    musicxml_sha = _require_hash(
        candidate.get("musicxmlSha256"),
        "INTAKE_CANDIDATE_INVALID",
    )
    _require_version(candidate.get("engineVersion"), "INTAKE_CANDIDATE_INVALID")
    _require_version(candidate.get("modelVersion"), "INTAKE_CANDIDATE_INVALID")

    if (
        candidate_source_artifact_id != source_artifact_id
        or candidate_source_sha != source_sha
    ):
        _fail("INTAKE_SOURCE_BINDING_MISMATCH")
    if sha256(musicxml).hexdigest() != musicxml_sha:
        _fail("INTAKE_MUSICXML_HASH_MISMATCH")

    canonical = _require_closed_dict(
        body.get("canonical"),
        _CANONICAL_KEYS,
        "INTAKE_CANONICAL_INVALID",
    )
    canonical_sha = _require_hash(
        canonical.get("canonicalSha256"),
        "INTAKE_CANONICAL_INVALID",
    )
    canonical_source_engine = canonical.get("sourceEngine")
    if type(canonical_source_engine) is not str or canonical_source_engine not in _ENGINE_NAMES:
        _fail("INTAKE_CANONICAL_INVALID")
    canonical_source_ref = _require_match(
        canonical.get("sourceArtifactRef"),
        _SAFE_REF_RE,
        "INTAKE_CANONICAL_INVALID",
    )
    canonical_source_sha = _require_hash(
        canonical.get("sourceArtifactSha256"),
        "INTAKE_CANONICAL_INVALID",
    )
    if (
        canonical_source_engine != engine
        or canonical_source_ref != musicxml_artifact_id
        or canonical_source_sha != musicxml_sha
    ):
        _fail("INTAKE_CANONICAL_BINDING_MISMATCH")

    mapping_policy = body.get("mappingPolicy")
    if type(mapping_policy) is not dict or mapping_policy != _MAPPING_POLICY:
        _fail("INTAKE_MAPPING_POLICY_INVALID")

    authority = body.get("authority")
    if type(authority) is not dict or authority != _AUTHORITY:
        _fail("INTAKE_AUTHORITY_INVALID")

    raw_bindings = body.get("reviewBindings")
    if type(raw_bindings) is not list or len(raw_bindings) > MAX_REVIEW_BINDINGS:
        _fail("INTAKE_REVIEW_BINDING_INVALID")
    normalized_bindings: list[dict[str, Any]] = []
    seen_issue_ids: set[str] = set()
    for raw_binding in raw_bindings:
        normalized = _validate_review_binding(
            raw_binding,
            candidate_id=candidate_id,
            candidate_sha256=candidate_sha,
            canonical_sha256=canonical_sha,
        )
        issue_id = normalized["issueId"]
        if issue_id in seen_issue_ids:
            _fail("INTAKE_DUPLICATE_ISSUE_BINDING")
        seen_issue_ids.add(issue_id)
        normalized_bindings.append(normalized)

    normalized_payload = {
        "schemaVersion": REAL_SCORE_INTAKE_VERSION,
        "bindingType": REAL_SCORE_INTAKE_BINDING_TYPE,
        "document": {"documentId": document_id, "revision": revision},
        "source": {"sourceArtifactId": source_artifact_id, "sourceSha256": source_sha},
        "candidate": {
            "engine": engine,
            "candidateId": candidate_id,
            "candidateNamespace": candidate["candidateNamespace"],
            "candidateSha256": candidate_sha,
            "sourceArtifactId": candidate_source_artifact_id,
            "sourceSha256": candidate_source_sha,
            "musicxmlArtifactId": musicxml_artifact_id,
            "musicxmlSha256": musicxml_sha,
            "engineVersion": candidate["engineVersion"],
            "modelVersion": candidate["modelVersion"],
        },
        "canonical": {
            "canonicalSha256": canonical_sha,
            "sourceEngine": canonical_source_engine,
            "sourceArtifactRef": canonical_source_ref,
            "sourceArtifactSha256": canonical_source_sha,
        },
        "mappingPolicy": dict(_MAPPING_POLICY),
        "reviewBindings": normalized_bindings,
        "authority": dict(_AUTHORITY),
    }
    binding_sha = sha256(_canonical_json(normalized_payload)).hexdigest()

    return RealScoreIntakeBinding(
        document_id=document_id,
        revision=revision,
        source_artifact_id=source_artifact_id,
        source_sha256=source_sha,
        engine=engine,
        candidate_id=candidate_id,
        candidate_sha256=candidate_sha,
        musicxml_artifact_id=musicxml_artifact_id,
        musicxml_sha256=musicxml_sha,
        canonical_sha256=canonical_sha,
        review_binding_count=len(normalized_bindings),
        binding_sha256=binding_sha,
    )
