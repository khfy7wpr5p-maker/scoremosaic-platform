#!/usr/bin/env python3
"""Build a non-counting Teacher-Gold pilot manifest from a local DoReMi v1 ZIP.

The script is intentionally read-only. It never admits Teacher-Gold fixtures and never
marks teacher verification complete. It pairs a published PNG page with a unique
published MusicXML score artifact and computes SHA-256 digests from archive bytes.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import PurePosixPath
import re
from zipfile import ZipFile


RELEASE_URL = "https://github.com/steinbergmedia/DoReMi/releases/download/v1.0/DoReMi_v1.zip"


def _clean(value: str) -> str:
    value = value.casefold()
    value = re.sub(r"[^a-z0-9]+", "_", value).strip("_")
    return value


def _image_score_stem(path: str) -> str:
    stem = PurePosixPath(path).stem
    return re.sub(r"[-_ ]\d+$", "", stem)


def _image_score_key(path: str) -> str:
    return _clean(_image_score_stem(path))


def _musicxml_name_key(path: str) -> str:
    return _clean(PurePosixPath(path).stem)


def _first_page_by_score(paths: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(paths):
        key = _image_score_key(path)
        if key and key not in result:
            result[key] = path
    return result


def _pair_scores(pngs: list[str], musicxml: list[str]) -> tuple[list[tuple[str, str, str]], list[str], list[str]]:
    first_pages = _first_page_by_score(pngs)
    xml_keys = [(path, _musicxml_name_key(path)) for path in sorted(musicxml)]
    pairs: list[tuple[str, str, str]] = []
    unmatched: list[str] = []
    ambiguous: list[str] = []

    for score_key, png_path in sorted(first_pages.items()):
        candidates = [
            path
            for path, xml_key in xml_keys
            if xml_key == score_key or xml_key.startswith(score_key + "_")
        ]
        if len(candidates) == 1:
            pairs.append((score_key, png_path, candidates[0]))
        elif not candidates:
            unmatched.append(score_key)
        else:
            ambiguous.append(score_key)
    return pairs, unmatched, ambiguous


def _is_repertoire_pair(pair: tuple[str, str, str]) -> bool:
    """Prefer named repertoire over DoReMi notation-feature exercise fixtures."""
    _, png_path, _ = pair
    return " - " in _image_score_stem(png_path)


def build_manifest(zip_path: str, limit: int) -> dict[str, object]:
    with ZipFile(zip_path) as archive:
        members = [info.filename for info in archive.infolist() if not info.is_dir()]
        pngs = [
            path
            for path in members
            if path.startswith("DoReMi_v1/Images/") and path.casefold().endswith(".png")
        ]
        musicxml = [
            path
            for path in members
            if path.startswith("DoReMi_v1/MusicXML/") and path.casefold().endswith(".xml")
        ]

        pairs, unmatched, ambiguous = _pair_scores(pngs, musicxml)
        repertoire_pairs = [pair for pair in pairs if _is_repertoire_pair(pair)]
        first_pages = _first_page_by_score(pngs)

        diagnostics = {
            "memberCount": len(members),
            "pngCount": len(pngs),
            "musicXmlCount": len(musicxml),
            "imageScoreCount": len(first_pages),
            "exactUniquePairCount": len(pairs),
            "repertoirePairCount": len(repertoire_pairs),
            "unmatchedScoreKeys": unmatched,
            "ambiguousScoreKeys": ambiguous,
            "topLevel": sorted(
                {PurePosixPath(path).parts[0] for path in members if PurePosixPath(path).parts}
            ),
            "samplePngPaths": sorted(pngs)[:10],
            "sampleMusicXmlPaths": sorted(musicxml)[:10],
        }

        records: list[dict[str, object]] = []
        for key, png_path, xml_path in repertoire_pairs[:limit]:
            png_bytes = archive.read(png_path)
            xml_bytes = archive.read(xml_path)
            records.append(
                {
                    "pilotId": f"doremi_v1_{len(records) + 1:02d}",
                    "scoreKey": key,
                    "source": {
                        "mediaType": "image/png",
                        "releaseUrl": RELEASE_URL,
                        "archiveMember": png_path,
                        "sha256": sha256(png_bytes).hexdigest(),
                        "byteSize": len(png_bytes),
                    },
                    "gold": {
                        "format": "MUSICXML",
                        "releaseUrl": RELEASE_URL,
                        "archiveMember": xml_path,
                        "sha256": sha256(xml_bytes).hexdigest(),
                        "byteSize": len(xml_bytes),
                    },
                    "teacherVerificationStatus": "DRAFT",
                    "evaluationEligibility": "REVIEW_REQUIRED",
                    "countTowardTeacherGoldMinimum": False,
                }
            )

    return {
        "manifestVersion": "scoremosaic-teacher-gold-doremi-pilot-discovery-v1",
        "dataset": "DoReMi v1",
        "selectionPolicy": "NAMED_REPERTOIRE_FIRST_PAGE_V1",
        "releaseUrl": RELEASE_URL,
        "requestedPilotCount": limit,
        "discoveredPilotCount": len(records),
        "records": records,
        "diagnostics": diagnostics,
        "boundaries": {
            "researchEvaluationOnly": True,
            "teacherVerified": False,
            "automaticFixtureAdmission": False,
            "automaticTrainingAuthorization": False,
            "productionDecisionAuthority": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("zip_path")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if not 1 <= args.limit <= 20:
        raise SystemExit("limit must be between 1 and 20")
    manifest = build_manifest(args.zip_path, args.limit)
    payload = json.dumps(manifest, ensure_ascii=True, sort_keys=True, indent=2) + "\n"
    with open(args.output, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
    print(payload, end="")
    if manifest["discoveredPilotCount"] < args.limit:
        raise SystemExit("insufficient exact repertoire PNG/MusicXML pilot pairs discovered")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
