"""Real Score Intake v1.1 semantic target binding.

v1.1 keeps the verified v1 candidate/source/canonical trust boundary intact while
separating Canonical event identity from ST Score Editor Core event/note identity.
That separation is required for chords because Canonical Score stores chord notes
as separate events while Core stores one chord event with multiple note atoms.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
import re
from typing import Any, Mapping

from .real_score_intake import (
    REAL_SCORE_INTAKE_BINDING_TYPE,
    REAL_SCORE_INTAKE_VERSION,
    RealScoreIntakeError,
    validate_real_score_intake,
)


REAL_SCORE_INTAKE_VERSION_V1_1 = "scoremosaic-real-score-intake-v1.1"

_MAPPING_POLICY_V1 = {
    "scoreSource": "canonical",
    "eventIdentity": "preserve-canonical-event-id",
    "musicXmlRole": "immutable-candidate-evidence",
    "syntheticScoreAllowed": False,
    "rendererAuthority": False,
}

MAPPING_POLICY_V1_1 = {
    "scoreSource": "canonical",
    "eventIdentity": "preserve-canonical-event-id",
    "coreTargetIdentity": "explicit-semantic-target",
    "chordMapping": "canonical-note-to-core-chord-note",
    "musicXmlRole": "immutable-candidate-evidence",
    "syntheticScoreAllowed": False,
    "rendererAuthority": False,
}

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
_REVIEW_KEYS = frozenset({
    "issueId",
    "sourceRegion",
    "candidateId",
    "candidateSha256",
    "canonicalSha256",
    "canonicalEventId",
    "coreTarget",
    "provenance",
})
_CANONICAL_TOP_KEYS = frozenset({
    "schemaVersion",
    "source",
    "rootType",
    "movementTitle",
    "parts",
    "diagnostics",
    "canonicalSha256",
})
_CANONICAL_SOURCE_KEYS = frozenset({
    "engine",
    "engineVersion",
    "modelVersion",
    "artifactRef",
    "artifactSha256",
})
_PROVENANCE_KEYS = frozenset({"xmlPath", "sourceEventIndex"})
_GENERIC_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")
_CORE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


def _fail(code: str) -> None:
    raise RealScoreIntakeError(code)


def _closed_dict(value: Any, keys: frozenset[str], code: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != set(keys):
        _fail(code)
    return value


def _id(value: Any, pattern: re.Pattern[str], code: str) -> str:
    if type(value) is not str or pattern.fullmatch(value) is None:
        _fail(code)
    return value


def _canonical_json_ascii(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeError):
        _fail("INTAKE_V1_1_PAYLOAD_INVALID")


def _canonical_score_digest(score: dict[str, Any]) -> str:
    payload = {key: value for key, value in score.items() if key != "canonicalSha256"}
    try:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError):
        _fail("INTAKE_V1_1_CANONICAL_SCORE_INVALID")
    return sha256(encoded).hexdigest()


def _validate_core_target(value: Any) -> dict[str, str]:
    if type(value) is not dict:
        _fail("INTAKE_V1_1_CORE_TARGET_INVALID")
    kind = value.get("kind")
    if kind == "note":
        if set(value) != {"kind", "eventId", "noteId"}:
            _fail("INTAKE_V1_1_CORE_TARGET_INVALID")
        event_id = _id(value.get("eventId"), _CORE_ID_RE, "INTAKE_V1_1_CORE_TARGET_INVALID")
        note_id = _id(value.get("noteId"), _CORE_ID_RE, "INTAKE_V1_1_CORE_TARGET_INVALID")
        return {"kind": "note", "eventId": event_id, "noteId": note_id}
    if kind == "event":
        if set(value) != {"kind", "eventId"}:
            _fail("INTAKE_V1_1_CORE_TARGET_INVALID")
        event_id = _id(value.get("eventId"), _CORE_ID_RE, "INTAKE_V1_1_CORE_TARGET_INVALID")
        return {"kind": "event", "eventId": event_id}
    _fail("INTAKE_V1_1_CORE_TARGET_INVALID")


def _canonical_event_index(canonical_score: Mapping[str, Any]) -> tuple[dict[str, dict[str, Any]], str]:
    score = _closed_dict(canonical_score, _CANONICAL_TOP_KEYS, "INTAKE_V1_1_CANONICAL_SCORE_INVALID")
    if score.get("schemaVersion") != "1.0" or score.get("rootType") != "score-partwise":
        _fail("INTAKE_V1_1_CANONICAL_SCORE_INVALID")
    if type(score.get("diagnostics")) is not list:
        _fail("INTAKE_V1_1_CANONICAL_SCORE_INVALID")
    movement_title = score.get("movementTitle")
    if movement_title is not None and type(movement_title) is not str:
        _fail("INTAKE_V1_1_CANONICAL_SCORE_INVALID")

    source = _closed_dict(
        score.get("source"),
        _CANONICAL_SOURCE_KEYS,
        "INTAKE_V1_1_CANONICAL_SCORE_INVALID",
    )
    source_engine = source.get("engine")
    source_ref = source.get("artifactRef")
    source_sha = source.get("artifactSha256")
    if type(source_engine) is not str or type(source_ref) is not str:
        _fail("INTAKE_V1_1_CANONICAL_SCORE_INVALID")
    if type(source_sha) is not str or _HASH_RE.fullmatch(source_sha) is None:
        _fail("INTAKE_V1_1_CANONICAL_SCORE_INVALID")

    canonical_sha = score.get("canonicalSha256")
    if type(canonical_sha) is not str or _HASH_RE.fullmatch(canonical_sha) is None:
        _fail("INTAKE_V1_1_CANONICAL_SCORE_INVALID")
    if _canonical_score_digest(score) != canonical_sha:
        _fail("INTAKE_V1_1_CANONICAL_HASH_MISMATCH")

    parts = score.get("parts")
    if type(parts) is not list or not parts:
        _fail("INTAKE_V1_1_CANONICAL_SCORE_INVALID")

    events: dict[str, dict[str, Any]] = {}
    for part in parts:
        if type(part) is not dict or type(part.get("measures")) is not list:
            _fail("INTAKE_V1_1_CANONICAL_SCORE_INVALID")
        for measure in part["measures"]:
            if type(measure) is not dict or type(measure.get("events")) is not list:
                _fail("INTAKE_V1_1_CANONICAL_SCORE_INVALID")
            for event in measure["events"]:
                if type(event) is not dict:
                    _fail("INTAKE_V1_1_CANONICAL_SCORE_INVALID")
                event_id = _id(
                    event.get("eventId"),
                    _GENERIC_ID_RE,
                    "INTAKE_V1_1_CANONICAL_SCORE_INVALID",
                )
                if event_id in events:
                    _fail("INTAKE_V1_1_DUPLICATE_CANONICAL_EVENT_ID")
                kind = event.get("kind")
                if kind not in {"note", "rest", "unpitched"}:
                    _fail("INTAKE_V1_1_CANONICAL_SCORE_INVALID")
                provenance = _closed_dict(
                    event.get("provenance"),
                    _PROVENANCE_KEYS,
                    "INTAKE_V1_1_CANONICAL_SCORE_INVALID",
                )
                if type(provenance.get("xmlPath")) is not str or not provenance["xmlPath"]:
                    _fail("INTAKE_V1_1_CANONICAL_SCORE_INVALID")
                source_event_index = provenance.get("sourceEventIndex")
                if type(source_event_index) is not int or source_event_index < 0:
                    _fail("INTAKE_V1_1_CANONICAL_SCORE_INVALID")
                chord_group = event.get("chordGroup")
                if chord_group is not None:
                    _id(chord_group, _GENERIC_ID_RE, "INTAKE_V1_1_CANONICAL_SCORE_INVALID")
                events[event_id] = event

    return events, canonical_sha


@dataclass(frozen=True, slots=True)
class RealScoreIntakeBindingV1_1:
    document_id: str
    revision: str
    source_artifact_id: str
    source_sha256: str
    engine: str
    candidate_id: str
    candidate_sha256: str
    musicxml_sha256: str
    canonical_sha256: str
    review_binding_count: int
    note_target_count: int
    event_target_count: int
    binding_sha256: str

    def as_safe_dict(self) -> dict[str, Any]:
        return {
            "version": REAL_SCORE_INTAKE_VERSION_V1_1,
            "documentId": self.document_id,
            "revision": self.revision,
            "sourceArtifactId": self.source_artifact_id,
            "sourceSha256": self.source_sha256,
            "engine": self.engine,
            "candidateId": self.candidate_id,
            "candidateSha256": self.candidate_sha256,
            "musicxmlSha256": self.musicxml_sha256,
            "canonicalSha256": self.canonical_sha256,
            "reviewBindingCount": self.review_binding_count,
            "noteTargetCount": self.note_target_count,
            "eventTargetCount": self.event_target_count,
            "bindingSha256": self.binding_sha256,
            "bindingOnly": True,
            "authoritative": False,
            "persistent": False,
            "networkCapable": False,
        }


def validate_real_score_intake_v1_1(
    payload: Mapping[str, Any],
    *,
    musicxml: bytes,
    canonical_score: Mapping[str, Any],
) -> RealScoreIntakeBindingV1_1:
    """Validate v1.1 and bind Canonical events to explicit Core semantic targets.

    The existing v1 validator remains the source of truth for candidate/source/
    MusicXML/canonical metadata and authority checks. v1.1 adds independent
    Canonical Score hash/provenance verification plus explicit Core target rules.
    It performs no file I/O, network access, persistence, rendering, mutation,
    correction, approval, or publication.
    """

    body = _closed_dict(payload, _TOP_KEYS, "INTAKE_V1_1_SCHEMA_CLOSED")
    if body.get("schemaVersion") != REAL_SCORE_INTAKE_VERSION_V1_1:
        _fail("INTAKE_V1_1_VERSION_INVALID")
    if body.get("bindingType") != REAL_SCORE_INTAKE_BINDING_TYPE:
        _fail("INTAKE_V1_1_BINDING_TYPE_INVALID")
    if body.get("mappingPolicy") != MAPPING_POLICY_V1_1:
        _fail("INTAKE_V1_1_MAPPING_POLICY_INVALID")

    raw_bindings = body.get("reviewBindings")
    if type(raw_bindings) is not list or len(raw_bindings) > 1000:
        _fail("INTAKE_V1_1_REVIEW_BINDING_INVALID")

    normalized_bindings: list[dict[str, Any]] = []
    legacy_bindings: list[dict[str, Any]] = []
    for raw in raw_bindings:
        item = _closed_dict(raw, _REVIEW_KEYS, "INTAKE_V1_1_REVIEW_BINDING_INVALID")
        canonical_event_id = _id(
            item.get("canonicalEventId"),
            _GENERIC_ID_RE,
            "INTAKE_V1_1_REVIEW_BINDING_INVALID",
        )
        core_target = _validate_core_target(item.get("coreTarget"))
        provenance = _closed_dict(
            item.get("provenance"),
            _PROVENANCE_KEYS,
            "INTAKE_V1_1_REVIEW_BINDING_INVALID",
        )
        normalized_bindings.append({
            "issueId": item.get("issueId"),
            "sourceRegion": item.get("sourceRegion"),
            "candidateId": item.get("candidateId"),
            "candidateSha256": item.get("candidateSha256"),
            "canonicalSha256": item.get("canonicalSha256"),
            "canonicalEventId": canonical_event_id,
            "coreTarget": core_target,
            "provenance": deepcopy(provenance),
        })
        legacy_bindings.append({
            "issueId": item.get("issueId"),
            "sourceRegion": item.get("sourceRegion"),
            "candidateId": item.get("candidateId"),
            "candidateSha256": item.get("candidateSha256"),
            "canonicalSha256": item.get("canonicalSha256"),
            "canonicalEventId": canonical_event_id,
            "coreEventId": canonical_event_id,
            "provenance": deepcopy(provenance),
        })

    legacy = deepcopy(body)
    legacy["schemaVersion"] = REAL_SCORE_INTAKE_VERSION
    legacy["mappingPolicy"] = dict(_MAPPING_POLICY_V1)
    legacy["reviewBindings"] = legacy_bindings
    base = validate_real_score_intake(legacy, musicxml=musicxml)

    canonical_events, actual_canonical_sha = _canonical_event_index(canonical_score)
    canonical_meta = body["canonical"]
    if actual_canonical_sha != canonical_meta.get("canonicalSha256"):
        _fail("INTAKE_V1_1_CANONICAL_BINDING_MISMATCH")
    canonical_source = canonical_score["source"]
    if (
        canonical_source.get("engine") != canonical_meta.get("sourceEngine")
        or canonical_source.get("artifactRef") != canonical_meta.get("sourceArtifactRef")
        or canonical_source.get("artifactSha256") != canonical_meta.get("sourceArtifactSha256")
    ):
        _fail("INTAKE_V1_1_CANONICAL_BINDING_MISMATCH")

    canonical_to_target: dict[str, tuple[str, str, str | None]] = {}
    target_owner: dict[tuple[str, str, str | None], str] = {}
    chord_to_core_event: dict[str, str] = {}
    note_targets = 0
    event_targets = 0

    for item in normalized_bindings:
        canonical_event_id = item["canonicalEventId"]
        event = canonical_events.get(canonical_event_id)
        if event is None:
            _fail("INTAKE_V1_1_CANONICAL_EVENT_NOT_FOUND")
        if item.get("canonicalSha256") != actual_canonical_sha:
            _fail("INTAKE_V1_1_CANONICAL_BINDING_MISMATCH")
        if item["provenance"] != event.get("provenance"):
            _fail("INTAKE_V1_1_PROVENANCE_MISMATCH")

        target = item["coreTarget"]
        if event["kind"] == "note":
            if target["kind"] != "note":
                _fail("INTAKE_V1_1_TARGET_KIND_MISMATCH")
            note_targets += 1
        elif event["kind"] == "rest":
            if target["kind"] != "event":
                _fail("INTAKE_V1_1_TARGET_KIND_MISMATCH")
            event_targets += 1
        else:
            _fail("INTAKE_V1_1_UNSUPPORTED_CANONICAL_EVENT_KIND")

        target_key = (
            target["kind"],
            target["eventId"],
            target.get("noteId"),
        )
        previous_target = canonical_to_target.get(canonical_event_id)
        if previous_target is not None and previous_target != target_key:
            _fail("INTAKE_V1_1_TARGET_MAPPING_CONFLICT")
        canonical_to_target[canonical_event_id] = target_key

        previous_owner = target_owner.get(target_key)
        if previous_owner is not None and previous_owner != canonical_event_id:
            _fail("INTAKE_V1_1_CORE_TARGET_COLLISION")
        target_owner[target_key] = canonical_event_id

        chord_group = event.get("chordGroup")
        if chord_group is not None:
            previous_core_event = chord_to_core_event.get(chord_group)
            if previous_core_event is not None and previous_core_event != target["eventId"]:
                _fail("INTAKE_V1_1_CHORD_TARGET_MISMATCH")
            chord_to_core_event[chord_group] = target["eventId"]

    normalized_payload = deepcopy(body)
    normalized_payload["reviewBindings"] = normalized_bindings
    binding_sha = sha256(_canonical_json_ascii(normalized_payload)).hexdigest()

    return RealScoreIntakeBindingV1_1(
        document_id=base.document_id,
        revision=base.revision,
        source_artifact_id=base.source_artifact_id,
        source_sha256=base.source_sha256,
        engine=base.engine,
        candidate_id=base.candidate_id,
        candidate_sha256=base.candidate_sha256,
        musicxml_sha256=base.musicxml_sha256,
        canonical_sha256=actual_canonical_sha,
        review_binding_count=len(normalized_bindings),
        note_target_count=note_targets,
        event_target_count=event_targets,
        binding_sha256=binding_sha,
    )
