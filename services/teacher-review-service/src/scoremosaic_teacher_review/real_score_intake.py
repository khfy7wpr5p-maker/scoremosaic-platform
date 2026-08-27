from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re
from typing import Any, Mapping


REAL_SCORE_INTAKE_VERSION = "scoremosaic-real-score-intake-v1"
REAL_SCORE_INTAKE_BINDING_TYPE = "scoremosaic.real-score-intake-binding"
VERIFIED_CANDIDATE_HANDOFF_VERSION = "scoremosaic-candidate-convergence-handoff-v1"
MAX_MUSICXML_BYTES = 16 * 1024 * 1024
MAX_REVIEW_BINDINGS = 1000

_ENGINE_NAMES = frozenset({"homr", "clarity", "audiveris"})
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_GENERIC_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")
_JOB_ID_RE = re.compile(r"^job_[A-Za-z0-9_-]{8,80}$")
_PLAN_ID_RE = re.compile(r"^plan_[0-9a-f]{24}$")
_RUN_ID_RE = re.compile(r"^run_[0-9a-f]{24}$")
_ARTIFACT_ID_RE = re.compile(r"^artifact_[0-9a-f]{24}$")
_CANDIDATE_ID_RE = re.compile(r"^candidate_[0-9a-f]{24}$")
_SAFE_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,499}$")
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
    "version",
    "jobId",
    "planId",
    "planSha256",
    "sourceArtifactId",
    "sourceSha256",
    "engine",
    "runId",
    "candidateId",
    "candidateSha256",
    "persistenceRecordSha256",
    "musicxmlArtifactId",
    "musicxmlArtifactRef",
    "musicxmlSha256",
    "musicxmlBytes",
    "handoffSha256",
    "engineVersion",
    "modelVersion",
    "provenanceAuthenticated",
    "persistedArtifactVerified",
    "candidateOnly",
    "authoritativeScore",
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


def _require_safe_ref(value: Any, code: str) -> str:
    ref = _require_match(value, _SAFE_REF_RE, code)
    if ref.startswith("/") or "\\" in ref or "//" in ref:
        _fail(code)
    if any(part in {"", ".", ".."} for part in ref.split("/")):
        _fail(code)
    return ref


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


def _candidate_handoff_core(candidate: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "version": candidate["version"],
        "jobId": candidate["jobId"],
        "planId": candidate["planId"],
        "planSha256": candidate["planSha256"],
        "sourceArtifactId": candidate["sourceArtifactId"],
        "sourceSha256": candidate["sourceSha256"],
        "engine": candidate["engine"],
        "runId": candidate["runId"],
        "candidateId": candidate["candidateId"],
        "candidateSha256": candidate["candidateSha256"],
        "persistenceRecordSha256": candidate["persistenceRecordSha256"],
        "musicxmlArtifactId": candidate["musicxmlArtifactId"],
        "musicxmlArtifactRef": candidate["musicxmlArtifactRef"],
        "musicxmlSha256": candidate["musicxmlSha256"],
        "musicxmlBytes": candidate["musicxmlBytes"],
        "engineVersion": candidate["engineVersion"],
        "modelVersion": candidate["modelVersion"],
        "provenanceAuthenticated": candidate["provenanceAuthenticated"],
        "persistedArtifactVerified": candidate["persistedArtifactVerified"],
        "candidateOnly": candidate["candidateOnly"],
        "authoritativeScore": candidate["authoritativeScore"],
    }


@dataclass(frozen=True, slots=True)
class RealScoreIntakeBinding:
    document_id: str
    revision: str
    source_artifact_id: str
    source_sha256: str
    engine: str
    candidate_id: str
    candidate_sha256: str
    handoff_sha256: str
    musicxml_artifact_id: str
    musicxml_artifact_ref: str
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
            "handoffSha256": self.handoff_sha256,
            "musicxmlArtifactId": self.musicxml_artifact_id,
            "musicxmlArtifactRef": self.musicxml_artifact_ref,
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
    """Validate an already-verified Stage 7 candidate/canonical/review binding.

    This validator deliberately performs no external authentication, file I/O,
    network access, persistence, correction, rendering, approval, publication,
    or source mutation. The caller must supply metadata from the existing trusted
    Stage 7 handoff boundary. This function independently rechecks its closed
    shape, deterministic handoff hash, exact MusicXML byte/hash identity,
    Canonical source identity, and Teacher Review -> Core event identity.
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
    if candidate.get("version") != VERIFIED_CANDIDATE_HANDOFF_VERSION:
        _fail("INTAKE_CANDIDATE_INVALID")
    job_id = _require_match(candidate.get("jobId"), _JOB_ID_RE, "INTAKE_CANDIDATE_INVALID")
    plan_id = _require_match(candidate.get("planId"), _PLAN_ID_RE, "INTAKE_CANDIDATE_INVALID")
    plan_sha = _require_hash(candidate.get("planSha256"), "INTAKE_CANDIDATE_INVALID")
    candidate_source_artifact_id = _require_match(
        candidate.get("sourceArtifactId"),
        _ARTIFACT_ID_RE,
        "INTAKE_CANDIDATE_INVALID",
    )
    candidate_source_sha = _require_hash(
        candidate.get("sourceSha256"),
        "INTAKE_CANDIDATE_INVALID",
    )
    engine = candidate.get("engine")
    if type(engine) is not str or engine not in _ENGINE_NAMES:
        _fail("INTAKE_CANDIDATE_INVALID")
    run_id = _require_match(candidate.get("runId"), _RUN_ID_RE, "INTAKE_CANDIDATE_INVALID")
    candidate_id = _require_match(
        candidate.get("candidateId"),
        _CANDIDATE_ID_RE,
        "INTAKE_CANDIDATE_INVALID",
    )
    candidate_sha = _require_hash(
        candidate.get("candidateSha256"),
        "INTAKE_CANDIDATE_INVALID",
    )
    persistence_record_sha = _require_hash(
        candidate.get("persistenceRecordSha256"),
        "INTAKE_CANDIDATE_INVALID",
    )
    musicxml_artifact_id = _require_match(
        candidate.get("musicxmlArtifactId"),
        _ARTIFACT_ID_RE,
        "INTAKE_CANDIDATE_INVALID",
    )
    musicxml_artifact_ref = _require_safe_ref(
        candidate.get("musicxmlArtifactRef"),
        "INTAKE_CANDIDATE_INVALID",
    )
    musicxml_sha = _require_hash(
        candidate.get("musicxmlSha256"),
        "INTAKE_CANDIDATE_INVALID",
    )
    musicxml_bytes = candidate.get("musicxmlBytes")
    if type(musicxml_bytes) is not int or musicxml_bytes != len(musicxml):
        _fail("INTAKE_MUSICXML_SIZE_MISMATCH")
    handoff_sha = _require_hash(candidate.get("handoffSha256"), "INTAKE_CANDIDATE_INVALID")
    engine_version = _require_version(candidate.get("engineVersion"), "INTAKE_CANDIDATE_INVALID")
    model_version = _require_version(candidate.get("modelVersion"), "INTAKE_CANDIDATE_INVALID")
    if (
        candidate.get("provenanceAuthenticated") is not True
        or candidate.get("persistedArtifactVerified") is not True
        or candidate.get("candidateOnly") is not True
        or candidate.get("authoritativeScore") is not False
    ):
        _fail("INTAKE_CANDIDATE_TRUST_STATE_INVALID")

    if (
        candidate_source_artifact_id != source_artifact_id
        or candidate_source_sha != source_sha
    ):
        _fail("INTAKE_SOURCE_BINDING_MISMATCH")
    if sha256(musicxml).hexdigest() != musicxml_sha:
        _fail("INTAKE_MUSICXML_HASH_MISMATCH")
    expected_handoff_sha = sha256(_canonical_json(_candidate_handoff_core(candidate))).hexdigest()
    if handoff_sha != expected_handoff_sha:
        _fail("INTAKE_CANDIDATE_HANDOFF_MISMATCH")

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
    canonical_source_ref = _require_safe_ref(
        canonical.get("sourceArtifactRef"),
        "INTAKE_CANONICAL_INVALID",
    )
    canonical_source_sha = _require_hash(
        canonical.get("sourceArtifactSha256"),
        "INTAKE_CANONICAL_INVALID",
    )
    if (
        canonical_source_engine != engine
        or canonical_source_ref != musicxml_artifact_ref
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

    normalized_candidate = {
        "version": VERIFIED_CANDIDATE_HANDOFF_VERSION,
        "jobId": job_id,
        "planId": plan_id,
        "planSha256": plan_sha,
        "sourceArtifactId": candidate_source_artifact_id,
        "sourceSha256": candidate_source_sha,
        "engine": engine,
        "runId": run_id,
        "candidateId": candidate_id,
        "candidateSha256": candidate_sha,
        "persistenceRecordSha256": persistence_record_sha,
        "musicxmlArtifactId": musicxml_artifact_id,
        "musicxmlArtifactRef": musicxml_artifact_ref,
        "musicxmlSha256": musicxml_sha,
        "musicxmlBytes": musicxml_bytes,
        "handoffSha256": handoff_sha,
        "engineVersion": engine_version,
        "modelVersion": model_version,
        "provenanceAuthenticated": True,
        "persistedArtifactVerified": True,
        "candidateOnly": True,
        "authoritativeScore": False,
    }
    normalized_payload = {
        "schemaVersion": REAL_SCORE_INTAKE_VERSION,
        "bindingType": REAL_SCORE_INTAKE_BINDING_TYPE,
        "document": {"documentId": document_id, "revision": revision},
        "source": {"sourceArtifactId": source_artifact_id, "sourceSha256": source_sha},
        "candidate": normalized_candidate,
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
        handoff_sha256=handoff_sha,
        musicxml_artifact_id=musicxml_artifact_id,
        musicxml_artifact_ref=musicxml_artifact_ref,
        musicxml_sha256=musicxml_sha,
        canonical_sha256=canonical_sha,
        review_binding_count=len(normalized_bindings),
        binding_sha256=binding_sha,
    )
