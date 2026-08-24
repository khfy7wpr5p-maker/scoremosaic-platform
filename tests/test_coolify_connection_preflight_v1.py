from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_coolify_connection_preflight.py"
CONTRACT = json.loads(
    (ROOT / "contracts" / "coolify-connection-preflight-v1.json").read_text(encoding="utf-8")
)
SOURCE = SCRIPT.read_text(encoding="utf-8")

spec = importlib.util.spec_from_file_location("coolify_preflight", SCRIPT)
assert spec is not None and spec.loader is not None
preflight = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = preflight
spec.loader.exec_module(preflight)


def service(
    name: str,
    *,
    port: str,
    workspace: str,
    build: str,
    pids: int,
    environment: dict[str, str],
    tmpfs: list[str] | None = None,
) -> dict:
    return {
        "build": {"context": f"../../../services/{build}", "dockerfile": "Dockerfile"},
        "environment": environment,
        "expose": [port],
        "cpus": 2.0 if name != "omr-gateway" else 0.5,
        "mem_limit": "536870912" if name == "omr-gateway" else "4294967296",
        "read_only": True,
        "user": "65532:65532",
        "restart": "unless-stopped",
        "pids_limit": pids,
        "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges:true"],
        "labels": {"traefik.enable": "false"},
        "networks": {"omr-internal": None},
        "healthcheck": {"test": ["CMD", "python", "-c", "pass"]},
        "tmpfs": tmpfs
        or [f"{workspace}:rw,noexec,nosuid,nodev,size=1048576,mode=0700,uid=65532,gid=65532"],
    }


def rendered_fixture() -> dict:
    return {
        "services": {
            "homr-foundation": service(
                "homr-foundation",
                port="8080",
                workspace="/tmp/scoremosaic-homr",
                build="homr-service",
                pids=128,
                environment={
                    "SCOREMOSAIC_HOMR_RUNTIME_MODE": "homr",
                    "SCOREMOSAIC_HOMR_VERSION": "0.7.0",
                },
            ),
            "clarity-foundation": service(
                "clarity-foundation",
                port="8081",
                workspace="/tmp/scoremosaic-clarity",
                build="clarity-service",
                pids=256,
                environment={
                    "SCOREMOSAIC_CLARITY_COMPUTE_MODE": "cpu",
                    "SCOREMOSAIC_CLARITY_SOURCE_REVISION": "c6bb8a4d2a5b52842a9c41bd0f761f58d02f6f82",
                    "SCOREMOSAIC_CLARITY_MODEL_REVISION": "ee14c1e41ab371fe27bf8a2707ea588560077e73",
                },
            ),
            "audiveris-foundation": service(
                "audiveris-foundation",
                port="8082",
                workspace="/tmp/scoremosaic-audiveris",
                build="audiveris-service",
                pids=128,
                environment={
                    "SCOREMOSAIC_AUDIVERIS_RUNTIME_MODE": "audiveris",
                    "SCOREMOSAIC_AUDIVERIS_VERSION": "5.11.0",
                },
                tmpfs=[
                    "/tmp/scoremosaic-audiveris:rw,noexec,nosuid,nodev,size=1048576,mode=0700,uid=65532,gid=65532",
                    "/tmp/scoremosaic-audiveris-jna:rw,exec,nosuid,nodev,size=1048576,mode=0700,uid=65532,gid=65532",
                ],
            ),
            "omr-gateway": service(
                "omr-gateway",
                port="8090",
                workspace="/tmp/scoremosaic-gateway",
                build="omr-gateway",
                pids=128,
                environment={
                    "SCOREMOSAIC_GATEWAY_ORCHESTRATION_MODE": "disabled",
                    "SCOREMOSAIC_GATEWAY_HOMR_BASE_URL": "http://homr-foundation:8080",
                    "SCOREMOSAIC_GATEWAY_CLARITY_BASE_URL": "http://clarity-foundation:8081",
                    "SCOREMOSAIC_GATEWAY_AUDIVERIS_BASE_URL": "http://audiveris-foundation:8082",
                },
                tmpfs=["/tmp/scoremosaic-gateway:rw,noexec,nosuid,size=1048576,mode=0700"],
            ),
        },
        "networks": {"omr-internal": {"internal": True}},
    }


class CoolifyConnectionPreflightV1Tests(unittest.TestCase):
    def test_contract_is_repository_only_and_all_external_effects_are_locked(self) -> None:
        self.assertEqual("scoremosaic-coolify-connection-preflight-v1", CONTRACT["version"])
        self.assertIs(CONTRACT["stageNumberAssigned"], False)
        self.assertEqual(
            "REPOSITORY_COOLIFY_PRIVATE_STAGING_PREFLIGHT_READY_NOT_CONNECTED",
            CONTRACT["status"],
        )
        self.assertEqual([], CONTRACT["target"]["publicDomains"])
        self.assertIs(CONTRACT["target"]["productionFlag"], False)
        self.assertTrue(CONTRACT["activationLocks"])
        self.assertTrue(all(value is False for value in CONTRACT["activationLocks"].values()))
        self.assertTrue(
            all(item["resolved"] is False for item in CONTRACT["externalInputsRequiredAtConnection"])
        )
        self.assertIs(CONTRACT["repositoryPreflight"]["preflightArtifactIsDeployment"], False)

    def test_validator_has_no_network_or_provider_mutation_client(self) -> None:
        forbidden = (
            "import requests",
            "from requests",
            "import httpx",
            "from httpx",
            "urllib.request",
            "import socket",
            "subprocess",
            "api.coolify",
            "Authorization:",
            "Bearer ",
        )
        for marker in forbidden:
            with self.subTest(marker=marker):
                self.assertNotIn(marker, SOURCE)

    def test_reference_rendered_compose_passes(self) -> None:
        preflight.validate_contract(CONTRACT)
        preflight.parse_nonsecret_env()
        preflight.validate_compose_source()
        preflight.validate_rendered_compose(rendered_fixture())

    def test_published_port_fails_closed(self) -> None:
        config = rendered_fixture()
        config["services"]["omr-gateway"]["ports"] = ["8090:8090"]
        with self.assertRaisesRegex(preflight.PreflightError, "publishes a host port"):
            preflight.validate_rendered_compose(config)

    def test_persistent_or_bind_volume_fails_closed(self) -> None:
        config = rendered_fixture()
        config["services"]["homr-foundation"]["volumes"] = ["score-data:/data"]
        with self.assertRaisesRegex(preflight.PreflightError, "persistent/bind volume"):
            preflight.validate_rendered_compose(config)

    def test_non_internal_network_fails_closed(self) -> None:
        config = rendered_fixture()
        config["networks"]["omr-internal"]["internal"] = False
        with self.assertRaisesRegex(preflight.PreflightError, "must remain internal"):
            preflight.validate_rendered_compose(config)

    def test_gateway_orchestration_enablement_fails_closed(self) -> None:
        config = rendered_fixture()
        config["services"]["omr-gateway"]["environment"][
            "SCOREMOSAIC_GATEWAY_ORCHESTRATION_MODE"
        ] = "enabled"
        with self.assertRaisesRegex(preflight.PreflightError, "orchestration must remain disabled"):
            preflight.validate_rendered_compose(config)

    def test_public_proxy_enablement_fails_closed(self) -> None:
        config = rendered_fixture()
        config["services"]["clarity-foundation"]["labels"] = {"traefik.enable": "true"}
        with self.assertRaisesRegex(preflight.PreflightError, "Traefik route"):
            preflight.validate_rendered_compose(config)

    def test_handoff_is_non_deployment_and_contains_no_secret_values(self) -> None:
        payload = preflight.build_handoff(CONTRACT)
        self.assertIs(payload["repositoryPreflightPassed"], True)
        self.assertIs(payload["externalConnectionPerformed"], False)
        self.assertIs(payload["deploymentPerformed"], False)
        self.assertIs(payload["productionAuthorized"], False)
        self.assertEqual([], payload["target"]["publicDomains"])
        serialized = json.dumps(payload)
        for forbidden in ("token=", "password=", "api_key=", "private_key="):
            self.assertNotIn(forbidden, serialized.lower())

    def test_output_writer_refuses_overwrite(self) -> None:
        payload = preflight.build_handoff(CONTRACT)
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "handoff.json"
            output.write_text("sentinel", encoding="utf-8")
            with self.assertRaisesRegex(preflight.PreflightError, "must not already exist"):
                preflight.write_handoff(output, payload)
            self.assertEqual("sentinel", output.read_text(encoding="utf-8"))

    def test_mutating_architecture_production_lock_fails(self) -> None:
        architecture = json.loads(
            (ROOT / "contracts" / "architecture-current-state-v1.json").read_text(encoding="utf-8")
        )
        broken = deepcopy(architecture)
        broken["production"]["providerResourcesCreated"] = True
        with self.assertRaisesRegex(preflight.PreflightError, "production activation lock opened"):
            preflight.validate_architecture(broken)


if __name__ == "__main__":
    unittest.main()
