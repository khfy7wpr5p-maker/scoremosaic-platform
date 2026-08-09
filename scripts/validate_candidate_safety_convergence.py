"""Verify all engine adapters implement the same Candidate Safety v1 policy."""

from __future__ import annotations

import json
from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "contracts" / "candidate-safety-policy-v1.json"
MODULE_PATHS = (
    ROOT
    / "services"
    / "audiveris-service"
    / "src"
    / "scoremosaic_audiveris"
    / "candidate_safety.py",
    ROOT
    / "services"
    / "homr-service"
    / "src"
    / "scoremosaic_homr"
    / "candidate_safety.py",
    ROOT
    / "services"
    / "clarity-service"
    / "src"
    / "scoremosaic_clarity"
    / "candidate_safety.py",
)

EXPECTED_CONSTANTS = {
    "maxArtifactBytes": "MAX_ARTIFACT_BYTES",
    "maxXmlBytes": "MAX_XML_BYTES",
    "maxZipEntries": "MAX_ZIP_ENTRIES",
    "maxTotalUncompressedBytes": "MAX_TOTAL_UNCOMPRESSED_BYTES",
    "maxCompressionRatio": "MAX_COMPRESSION_RATIO",
    "maxXmlDepth": "MAX_XML_DEPTH",
    "maxXmlElements": "MAX_XML_ELEMENTS",
    "maxXmlAttributes": "MAX_XML_ATTRIBUTES",
    "maxAttributesPerElement": "MAX_ATTRIBUTES_PER_ELEMENT",
    "maxContainerXmlBytes": "MAX_CONTAINER_XML_BYTES",
}

EXPECTED_MUSIC_XML_POLICY = {
    "allowedRoots": ["score-partwise", "score-timewise"],
    "rejectEntityDeclarations": True,
    "rejectNulBytes": True,
    "canonicalMusicXmlDoctypeMayBeSanitizedBeforeParse": True,
    "externalEntityResolution": False,
    "externalNetworkResolution": False,
}

EXPECTED_MXL_POLICY = {
    "requireContainerXml": True,
    "requireExactlyOneRootfile": True,
    "rejectEncryptedEntries": True,
    "rejectSymlinkEntries": True,
    "rejectAbsoluteOrTraversalPaths": True,
    "rejectDuplicateMembers": True,
    "containerDeclarationsAllowed": False,
}


def main() -> None:
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    if policy.get("contractVersion") != "candidate-safety-v1":
        raise SystemExit("candidate safety contract version mismatch")
    if policy.get("trustBoundary") != "untrusted-engine-output":
        raise SystemExit("candidate safety trust boundary mismatch")
    if (
        policy.get("activationRule")
        != "candidate-must-pass-before-canonical-or-ensemble-processing"
    ):
        raise SystemExit("candidate safety activation rule mismatch")

    module_documents = [path.read_bytes() for path in MODULE_PATHS]
    if any(document != module_documents[0] for document in module_documents[1:]):
        raise SystemExit("candidate safety implementations have diverged")

    module = runpy.run_path(str(MODULE_PATHS[0]))
    if module.get("POLICY_VERSION") != policy.get("contractVersion"):
        raise SystemExit("candidate safety policy version mismatch")
    limits = policy.get("limits", {})
    for contract_name, constant_name in EXPECTED_CONSTANTS.items():
        actual = module.get(constant_name)
        expected = limits.get(contract_name)
        if actual != expected:
            raise SystemExit(
                f"candidate safety limit mismatch: {contract_name}={expected!r}, "
                f"{constant_name}={actual!r}"
            )

    if policy.get("musicXml") != EXPECTED_MUSIC_XML_POLICY:
        raise SystemExit("candidate safety MusicXML policy mismatch")
    if policy.get("mxl") != EXPECTED_MXL_POLICY:
        raise SystemExit("candidate safety MXL policy mismatch")
    if policy.get("engines") != ["audiveris", "homr", "clarity"]:
        raise SystemExit("candidate safety engine set mismatch")

    print("Candidate Safety v1 convergence validated for Audiveris, HOMR, and Clarity.")


if __name__ == "__main__":
    main()
