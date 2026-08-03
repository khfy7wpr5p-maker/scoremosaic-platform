from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_homr.config import load_config
from scoremosaic_homr.runtime import (
    ModelSpec,
    RuntimeExecutionError,
    RuntimeProbe,
    build_transcription_command,
    probe_runtime,
    transcribe_file,
)


class RuntimeTests(unittest.TestCase):
    def _runtime_config(self, root: Path):
        command = root / "bin" / "homr"
        command.parent.mkdir(parents=True)
        command.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        command.chmod(0o755)
        return load_config(
            {
                "SCOREMOSAIC_HOMR_RUNTIME_MODE": "homr",
                "SCOREMOSAIC_HOMR_COMMAND": str(command),
                "SCOREMOSAIC_HOMR_WORKSPACE_ROOT": str(root / "workspace"),
            }
        )

    def test_probe_reports_disabled_runtime(self) -> None:
        probe = probe_runtime(load_config({}))
        self.assertFalse(probe.ready)
        self.assertEqual(probe.reason, "homr_runtime_disabled")

    def test_probe_accepts_exact_package_and_model_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._runtime_config(root)
            package_root = root / "package"
            model = package_root / "models" / "test.onnx"
            model.parent.mkdir(parents=True)
            model.write_bytes(b"verified-model")
            specs = (ModelSpec("models/test.onnx", sha256(b"verified-model").hexdigest()),)

            result = probe_runtime(
                config,
                runner=lambda *args, **kwargs: subprocess.CompletedProcess(
                    args[0], 0, "usage: homr", ""
                ),
                version_reader=lambda _: "0.7.0",
                package_root_resolver=lambda: package_root,
                model_specs=specs,
            )

            self.assertTrue(result.ready)
            self.assertEqual(result.reason, "ready")
            self.assertEqual(result.version, "0.7.0")
            self.assertEqual(result.verified_models, 1)

    def test_probe_rejects_package_version_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._runtime_config(root)
            result = probe_runtime(config, version_reader=lambda _: "0.6.0")
            self.assertFalse(result.ready)
            self.assertEqual(result.reason, "homr_version_mismatch")

    def test_probe_rejects_model_checksum_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._runtime_config(root)
            package_root = root / "package"
            model = package_root / "test.onnx"
            package_root.mkdir()
            model.write_bytes(b"wrong")

            result = probe_runtime(
                config,
                version_reader=lambda _: "0.7.0",
                package_root_resolver=lambda: package_root,
                model_specs=(ModelSpec("test.onnx", "0" * 64),),
            )

            self.assertFalse(result.ready)
            self.assertTrue(result.reason.startswith("homr_model_checksum_mismatch:"))

    def test_probe_timeout_is_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._runtime_config(root)
            package_root = root / "package"
            package_root.mkdir()

            def timeout_runner(*args, **kwargs):
                raise subprocess.TimeoutExpired(args[0], 1)

            result = probe_runtime(
                config,
                runner=timeout_runner,
                version_reader=lambda _: "0.7.0",
                package_root_resolver=lambda: package_root,
                model_specs=(),
            )
            self.assertFalse(result.ready)
            self.assertEqual(result.reason, "homr_probe_timed_out")

    def test_command_contains_only_fixed_options_and_safe_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._runtime_config(root)
            output = config.workspace_root / "run"
            output.mkdir(parents=True)
            image = output / "score.png"
            image.write_bytes(b"png")

            command = build_transcription_command(image, output, config)

            self.assertEqual(
                command,
                (
                    str(config.homr_command),
                    "--gpu",
                    "no",
                    str(image.resolve()),
                ),
            )

    def test_input_outside_workspace_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._runtime_config(root)
            outside = root / "outside.png"
            outside.write_bytes(b"png")
            with self.assertRaisesRegex(RuntimeExecutionError, "escapes"):
                build_transcription_command(outside, config.workspace_root / "run", config)

    def test_symlink_input_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._runtime_config(root)
            output = config.workspace_root / "run"
            output.mkdir(parents=True)
            target = output / "target.png"
            target.write_bytes(b"png")
            link = output / "score.png"
            link.symlink_to(target)
            with self.assertRaisesRegex(RuntimeExecutionError, "symbolic-link"):
                build_transcription_command(link, output, config)

    def test_transcription_requires_valid_musicxml(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._runtime_config(root)
            output = config.workspace_root / "run"
            output.mkdir(parents=True)
            image = output / "score.png"
            image.write_bytes(b"png")

            def runner(command, **kwargs):
                Path(command[-1]).with_suffix(".musicxml").write_text(
                    "<?xml version='1.0'?><score-partwise version='4.0'/>",
                    encoding="utf-8",
                )
                return subprocess.CompletedProcess(command, 0, "done", "")

            result = transcribe_file(
                image,
                output,
                config,
                runner=runner,
                probe=lambda _: RuntimeProbe(True, "ready", "0.7.0", 3),
            )

            self.assertEqual(result.return_code, 0)
            self.assertEqual(result.musicxml_artifacts, (output / "score.musicxml",))


if __name__ == "__main__":
    unittest.main()
