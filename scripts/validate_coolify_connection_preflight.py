from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "contracts" / "coolify-connection-preflight-v1.json"
ARCHITECTURE_PATH = ROOT / "contracts" / "architecture-current-state-v1.json"
ENV_PATH = ROOT / "deploy" / "coolify" / "staging" / ".env.example"
COMPOSE_SOURCE_PATH = ROOT / "deploy" / "coolify" / "staging" / "compose.yaml"

VERSION = "scoremosaic-coolify-connection-preflight-v1"
STATUS = "REPOSITORY_COOLIFY_PRIVATE_STAGING_PREFLIGHT_READY_NOT_CONNECTED"
_SECRET_KEY_FRAGMENTS = ("TOKEN", "SECRET", "PASSWORD", "PRIVATE_KEY", "API_KEY")
_EXPECTED_ENV = {
    "COMPOSE_PROJECT_NAME": "scoremosaic-staging",
    "SCOREMOSAIC_GATEWAY_INTERNAL_HOST": "omr-gateway",
    "SCOREMOSAIC_GATEWAY_INTERNAL_PORT": "8090",
    "GATEWAY_CPUS": "0.50",
    "GATEWAY_MEMORY_LIMIT": "512m",
    "GATEWAY_TMPFS_BYTES": "16777216",
    "HOMR_CPUS": "2.00",
    "HOMR_MEMORY_LIMIT": "4096m",
    "HOMR_TMPFS_BYTES": "1073741824",
    "CLARITY_CPUS": "2.00",
    "CLARITY_MEMORY_LIMIT": "6144m",
    "CLARITY_TMPFS_BYTES": "2147483648",
    "AUDIVERIS_CPUS": "2.00",
    "AUDIVERIS_MEMORY_LIMIT": "4096m",
    "AUDIVERIS_TMPFS_BYTES": "805306368",
    "AUDIVERIS_JNA_TMPFS_BYTES": "67108864",
}
_EXPECTED_SERVICES = {
    "homr-foundation": {
        "port": "8080",
        "workspace": "/tmp/scoremosaic-homr",
        "build": "homr-service",
        "pids": 128,
    },
    "clarity-foundation": {
        "port": "8081",
        "workspace": "/tmp/scoremosaic-clarity",
        "build": "clarity-service",
        "pids": 256,
    },
    "audiveris-foundation": {
        "port": "8082",
        "workspace": "/tmp/scoremosaic-audiveris",
        "build": "audiveris-service",
        "pids": 128,
    },
    "omr-gateway": {
        "port": "8090",
        "workspace": "/tmp/scoremosaic-gateway",
        "build": "omr-gateway",
        "pids": 128,
    },
}


class PreflightError(ValueError):
    pass


def _fail(message: str) -> None:
    raise PreflightError(message)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PreflightError(f"invalid JSON input: {path}") from exc
    if type(value) is not dict:
        _fail(f"JSON root must be an object: {path}")
    return value


def validate_contract(contract: Mapping[str, Any]) -> None:
    if contract.get("version") != VERSION:
        _fail("preflight contract version mismatch")
    if contract.get("stageNumberAssigned") is not False:
        _fail("Coolify preflight must remain unnumbered")
    if contract.get("status") != STATUS:
        _fail("Coolify preflight status mismatch")

    target = contract.get("target")
    if not isinstance(target, Mapping):
        _fail("Coolify target contract missing")
    expected_target = {
        "provider": "Coolify",
        "environment": "staging",
        "repository": "khfy7wpr5p-maker/scoremosaic-platform",
        "branch": "main",
        "baseDirectory": "/",
        "composePath": "/deploy/coolify/staging/compose.yaml",
        "environmentTemplate": "/deploy/coolify/staging/.env.example",
        "publicDomains": [],
        "productionFlag": False,
        "gitConnectedApplication": True,
        "buildPack": "docker-compose",
    }
    if dict(target) != expected_target:
        _fail("Coolify target contract drifted")

    locks = contract.get("activationLocks")
    if not isinstance(locks, Mapping) or not locks:
        _fail("activation locks missing")
    if any(value is not False for value in locks.values()):
        _fail("Coolify/provider activation lock opened before connection gate")

    promotion = contract.get("licenseAndPromotionLocks")
    if not isinstance(promotion, Mapping) or not promotion:
        _fail("license/promotion locks missing")
    if any(value is not False for value in promotion.values()):
        _fail("license/promotion lock may not be promoted by preflight")

    external = contract.get("externalInputsRequiredAtConnection")
    if not isinstance(external, list) or len(external) != 4:
        _fail("external connection inputs incomplete")
    names = {item.get("name") for item in external if isinstance(item, Mapping)}
    if names != {
        "coolifyBaseUrl",
        "coolifyProjectOrEnvironmentIdentity",
        "coolifyDestinationServerIdentity",
        "coolifyGitSourceOrRepositoryAccess",
    }:
        _fail("external connection input names drifted")
    for item in external:
        if not isinstance(item, Mapping) or item.get("resolved") is not False:
            _fail("provider facts must remain unresolved in repository preflight")


def validate_architecture(architecture: Mapping[str, Any]) -> None:
    if architecture.get("version") != "scoremosaic-architecture-current-state-v1":
        _fail("architecture source-of-truth version mismatch")
    if architecture.get("sourceOfTruth") is not True:
        _fail("architecture source-of-truth flag missing")
    production = architecture.get("production")
    if not isinstance(production, Mapping) or production.get("productionReady") is not False:
        _fail("productionReady must remain false")
    for key in (
        "providerResourcesCreated",
        "productionCredentialsProvisioned",
        "productionNetworkActivated",
        "productionDatabaseActivated",
        "productionObjectStorageActivated",
        "productionIdentityActivated",
        "productionSecretsActivated",
        "publicApiActivated",
        "publicTrafficActivated",
    ):
        if production.get(key) is not False:
            _fail(f"production activation lock opened: {key}")

    workstream = architecture.get("approvedWorkstreams", {}).get("coolifyConnectionPreflight")
    if not isinstance(workstream, Mapping):
        _fail("architecture does not register Coolify connection preflight")
    if workstream.get("status") != STATUS:
        _fail("architecture Coolify preflight status mismatch")
    if workstream.get("repositoryPreflightReady") is not True:
        _fail("repository preflight readiness not registered")
    for key in (
        "providerConnectionPerformed",
        "providerResourcesCreated",
        "providerCredentialsConfigured",
        "publicRouteEnabled",
        "productionActivation",
    ):
        if workstream.get(key) is not False:
            _fail(f"architecture external-effect lock opened: {key}")


def parse_nonsecret_env(path: Path = ENV_PATH) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise PreflightError("cannot read Coolify environment template") from exc
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            _fail(f"invalid environment line: {raw_line!r}")
        key, value = (part.strip() for part in line.split("=", 1))
        if not key or not value:
            _fail(f"empty environment key/value: {raw_line!r}")
        if any(fragment in key.upper() for fragment in _SECRET_KEY_FRAGMENTS):
            _fail(f"secret-like key must not be committed: {key}")
        if key in values:
            _fail(f"duplicate environment key: {key}")
        values[key] = value
    if values != _EXPECTED_ENV:
        _fail("non-secret Coolify environment template drifted")
    return values


def _labels_disable_traefik(labels: Any) -> bool:
    if isinstance(labels, list):
        return "traefik.enable=false" in labels
    if isinstance(labels, Mapping):
        return str(labels.get("traefik.enable", "")).lower() == "false"
    return False


def _network_names(service: Mapping[str, Any]) -> set[str]:
    networks = service.get("networks", {})
    if isinstance(networks, Mapping):
        return set(networks)
    if isinstance(networks, list):
        return set(networks)
    return set()


def _exposed_ports(service: Mapping[str, Any]) -> set[str]:
    exposed = service.get("expose", [])
    if not isinstance(exposed, list):
        _fail("service expose must be a list")
    return {str(item).split("/")[0] for item in exposed}


def _assert_workspace_tmpfs(service_name: str, service: Mapping[str, Any], workspace: str) -> None:
    tmpfs = [str(item) for item in service.get("tmpfs", [])]
    if not any(workspace in item for item in tmpfs):
        _fail(f"{service_name} missing bounded temporary workspace")
    if service_name != "omr-gateway":
        if not any(
            workspace in item
            and "noexec" in item
            and "nosuid" in item
            and "nodev" in item
            for item in tmpfs
        ):
            _fail(f"{service_name} temporary workspace security options drifted")
    if service_name == "audiveris-foundation":
        if not any(
            "/tmp/scoremosaic-audiveris-jna" in item
            and "exec" in item
            and "nosuid" in item
            and "nodev" in item
            for item in tmpfs
        ):
            _fail("Audiveris JNA temporary workspace security options drifted")


def validate_rendered_compose(config: Mapping[str, Any]) -> None:
    services = config.get("services")
    if not isinstance(services, Mapping) or set(services) != set(_EXPECTED_SERVICES):
        _fail("rendered Compose service set drifted")

    for name, expected in _EXPECTED_SERVICES.items():
        service = services[name]
        if not isinstance(service, Mapping):
            _fail(f"invalid rendered service: {name}")
        if service.get("ports"):
            _fail(f"{name} publishes a host port")
        if service.get("volumes"):
            _fail(f"{name} uses a persistent/bind volume")
        if _exposed_ports(service) != {expected["port"]}:
            _fail(f"{name} exposed port drifted")
        if service.get("read_only") is not True:
            _fail(f"{name} root filesystem is not read-only")
        if service.get("user") != "65532:65532":
            _fail(f"{name} runtime user drifted")
        if service.get("restart") != "unless-stopped":
            _fail(f"{name} restart policy drifted")
        if service.get("pids_limit") != expected["pids"]:
            _fail(f"{name} process limit drifted")
        if "ALL" not in service.get("cap_drop", []):
            _fail(f"{name} does not drop all Linux capabilities")
        if "no-new-privileges:true" not in service.get("security_opt", []):
            _fail(f"{name} no-new-privileges missing")
        if _network_names(service) != {"omr-internal"}:
            _fail(f"{name} network membership drifted")
        if not _labels_disable_traefik(service.get("labels")):
            _fail(f"{name} Traefik route is not explicitly disabled")
        if not service.get("healthcheck", {}).get("test"):
            _fail(f"{name} healthcheck missing")
        if not service.get("cpus") or not service.get("mem_limit"):
            _fail(f"{name} resource limits missing")
        build = service.get("build")
        if not isinstance(build, Mapping) or expected["build"] not in str(build.get("context", "")):
            _fail(f"{name} build context drifted")
        _assert_workspace_tmpfs(name, service, expected["workspace"])

    homr = services["homr-foundation"]["environment"]
    if homr.get("SCOREMOSAIC_HOMR_RUNTIME_MODE") != "homr":
        _fail("HOMR runtime mode drifted")
    if homr.get("SCOREMOSAIC_HOMR_VERSION") != "0.7.0":
        _fail("HOMR version drifted")

    clarity = services["clarity-foundation"]["environment"]
    if clarity.get("SCOREMOSAIC_CLARITY_COMPUTE_MODE") != "cpu":
        _fail("Clarity must remain CPU-only in private staging")
    if clarity.get("SCOREMOSAIC_CLARITY_SOURCE_REVISION") != "c6bb8a4d2a5b52842a9c41bd0f761f58d02f6f82":
        _fail("Clarity source revision drifted")
    if clarity.get("SCOREMOSAIC_CLARITY_MODEL_REVISION") != "ee14c1e41ab371fe27bf8a2707ea588560077e73":
        _fail("Clarity model revision drifted")

    audiveris = services["audiveris-foundation"]["environment"]
    if audiveris.get("SCOREMOSAIC_AUDIVERIS_RUNTIME_MODE") != "audiveris":
        _fail("Audiveris runtime mode drifted")
    if audiveris.get("SCOREMOSAIC_AUDIVERIS_VERSION") != "5.11.0":
        _fail("Audiveris version drifted")

    gateway = services["omr-gateway"]["environment"]
    if gateway.get("SCOREMOSAIC_GATEWAY_ORCHESTRATION_MODE") != "disabled":
        _fail("Gateway orchestration must remain disabled")
    if gateway.get("SCOREMOSAIC_GATEWAY_HOMR_BASE_URL") != "http://homr-foundation:8080":
        _fail("Gateway HOMR destination drifted")
    if gateway.get("SCOREMOSAIC_GATEWAY_CLARITY_BASE_URL") != "http://clarity-foundation:8081":
        _fail("Gateway Clarity destination drifted")
    if gateway.get("SCOREMOSAIC_GATEWAY_AUDIVERIS_BASE_URL") != "http://audiveris-foundation:8082":
        _fail("Gateway Audiveris destination drifted")

    networks = config.get("networks")
    if not isinstance(networks, Mapping):
        _fail("rendered Compose networks missing")
    internal = None
    for key, value in networks.items():
        if key == "omr-internal" or key.endswith("_omr-internal"):
            internal = value
            break
    if not isinstance(internal, Mapping) or internal.get("internal") is not True:
        _fail("Coolify staging network must remain internal")


def validate_compose_source(path: Path = COMPOSE_SOURCE_PATH) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise PreflightError("cannot read Coolify Compose source") from exc
    if re.search(r"(?m)^\s+ports:\s*$", text):
        _fail("Compose source contains a published ports block")
    if re.search(r"(?m)^\s+volumes:\s*$", text):
        _fail("Compose source contains a persistent/bind volumes block")
    if "traefik.enable=false" not in text:
        _fail("Compose source does not disable Traefik")
    if "SCOREMOSAIC_GATEWAY_ORCHESTRATION_MODE: disabled" not in text:
        _fail("Compose source does not keep Gateway orchestration disabled")


def build_handoff(contract: Mapping[str, Any]) -> dict[str, Any]:
    unresolved = [
        item["name"]
        for item in contract["externalInputsRequiredAtConnection"]
        if item["resolved"] is False
    ]
    return {
        "version": VERSION,
        "status": STATUS,
        "repositoryPreflightPassed": True,
        "externalConnectionPerformed": False,
        "deploymentPerformed": False,
        "productionAuthorized": False,
        "realUserDataAuthorized": False,
        "target": {
            "provider": "Coolify",
            "environment": "staging",
            "repository": "khfy7wpr5p-maker/scoremosaic-platform",
            "branch": "main",
            "composePath": "/deploy/coolify/staging/compose.yaml",
            "publicDomains": [],
        },
        "expectedServices": sorted(_EXPECTED_SERVICES),
        "unresolvedExternalInputs": sorted(unresolved),
        "activationLocks": dict(contract["activationLocks"]),
    }


def write_handoff(path: Path, payload: Mapping[str, Any]) -> None:
    if path.exists() or path.is_symlink():
        _fail("preflight output path must not already exist")
    parent = path.parent
    if not parent.exists() or not parent.is_dir() or parent.is_symlink():
        _fail("preflight output parent must be an existing real directory")
    try:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ) + "\n"
        path.write_text(encoded, encoding="utf-8")
    except (OSError, UnicodeError, TypeError, ValueError) as exc:
        raise PreflightError("cannot write preflight handoff") from exc


def run(*, rendered_compose: Path, output: Path) -> dict[str, Any]:
    contract = _load_json(CONTRACT_PATH)
    architecture = _load_json(ARCHITECTURE_PATH)
    rendered = _load_json(rendered_compose)
    validate_contract(contract)
    validate_architecture(architecture)
    parse_nonsecret_env()
    validate_compose_source()
    validate_rendered_compose(rendered)
    handoff = build_handoff(contract)
    write_handoff(output, handoff)
    return handoff


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate ScoreMosaic Coolify private-staging connection preflight.")
    parser.add_argument("--rendered-compose", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        run(rendered_compose=args.rendered_compose, output=args.output)
    except PreflightError as exc:
        print(f"Coolify connection preflight failed: {exc}", file=sys.stderr)
        return 2
    print(f"Coolify connection preflight PASS: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
