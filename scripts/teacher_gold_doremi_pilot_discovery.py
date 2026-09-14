#!/usr/bin/env python3
"""Build a non-counting Teacher-Gold pilot manifest from a local DoReMi v1 ZIP.

The script is intentionally read-only. It never admits Teacher-Gold fixtures and never
marks teacher verification complete. It only pairs published PNG pages with their
published MusicXML score artifact and computes SHA-256 digests from the archive bytes.
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
    value = re.sub(r"(?:_?(?:page|pg|p))?_?\d+$", "", value).strip("_")
    return value


def _after_marker(path: str, marker: str) -> list[str]:
    parts = list(PurePosixPath(path).parts)
    folded = [part.casefold() for part in parts]
    try:
        idx = folded.index(marker.casefold())
    except ValueError:
        return []
    return parts[idx + 1 :]


def _score_key(path: str, marker: str) -> str:
    tail = _after_marker(path, marker)
    if not tail:
        return ""
    if len(tail) >= 2:
        # Prefer a score-level directory when the dataset has one directory per score.
        directory_key = _clean(tail[0])
        if directory_key:
            return directory_key
    return _clean(PurePosixPath(tail[-1]).stem)


def _first_by_key(paths: list[str], marker: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(paths):
        key = _score_key(path, marker)
        if key and key not in result:
            result[key] = path
    return result


def build_manifest(zip_path: str, limit: int) -> dict[str, object]:
    with ZipFile(zip_path) as archive:
        members = [info.filename for info in archive.infolist() if not info.is_dir()]
        pngs = [
            path
            for path in members
            if path.casefold().endswith(".png") and "image" in path.casefold()
        ]
        musicxml = [
            path
            for path in members
            if path.casefold().endswith(".xml") and "musicxml" in path.casefold()
        ]

        png_by_key = _first_by_key(pngs, "Images")
        xml_by_key = _first_by_key(musicxml, "MusicXML")
        shared = sorted(set(png_by_key) & set(xml_by_key))

        diagnostics = {
            "memberCount": len(members),
            "pngCount": len(pngs),
            "musicXmlCount": len(musicxml),
            "pngKeyCount": len(png_by_key),
            "musicXmlKeyCount": len(xml_by_key),
            "sharedKeyCount": len(shared),
            "topLevel": sorted({PurePosixPath(path).parts[0] for path in members if PurePosixPath(path).parts}),
            "samplePngPaths": sorted(pngs)[:10],
            "sampleMusicXmlPaths": sorted(musicxml)[:10],
        }

        records: list[dict[str, object]] = []
        for key in shared[:limit]:
            png_path = png_by_key[key]
            xml_path = xml_by_key[key]
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
        raise SystemExit("insufficient exact PNG/MusicXML pilot pairs discovered")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
