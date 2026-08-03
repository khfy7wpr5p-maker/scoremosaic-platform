from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_clarity.config import load_config
from scoremosaic_clarity.runtime import (
    ModelSpec,
    RuntimeExecutionError,
    RuntimeProbe,
    build_transcription_command,
    probe_runtime,
    transcribe_file,
)


class RuntimeTests(unittest.TestCase):
    def _runtime_config(self, root: Path):
        python = root / "bin" / "python"
        python.parent.mkdir(parents=True)
        python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        python.chmod(0o755)
        source = root / "source"
        source.mkdir()
        (source / "omr.py").write_text("print('stub')\n", encoding="utf-8")
        (source / ".scoremosaic-source-revision").write_text(
            "c6bb8a4d2a5b52842a9c41bd0f761f58d02f6f82\n",
            encoding="utf-8",
        )
        return load_config(
            {
                "SCOREMOSAIC_CLARITY_COMPUTE_MODE": "cpu",
                "SCOREMOSAIC_CLARITY_PYTHON_COMMAND": str(python),
                "SCOREMOSAIC_CLARITY_SOURCE_ROOT": str(source),
                "SCOREMOSAIC_CLARITY_WORKSPACE_ROOT": str(root / "workspace"),
            }
        )

    def test_probe_reports_disabled_runtime(self) -> None:
        probe = probe_runtime(load_config({}))
        self.assertFalse(probe.ready)
        self.assertEqual(probe.reason, "clarity_runtime_disabled")

    def test_probe_accepts_exact_source_cpu_and_model_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._runtime_config(root)
            model = config.source_root / "info" / "test.bin"
            model.parent.mkdir(parents=True)
            model.write_bytes(b"verified-model")
            specs = (
                ModelSpec(
                    "info/test.bin",
                    sha256(b"verified-model").hexdigest(),
                ),
            )
            payload = json.dumps(
                {
                    "torch": "2.13.0+cpu",
                    "torchvision": "0.28.0+cpu",
                    "cuda": False,
                }
            )

            result = probe_runtime(
                config,
                runner=lambda *args, **kwargs: subprocess.CompletedProcess(
                    args[0], 0, payload + "\n", ""
                ),
                model_specs=specs,
            )

            self.assertTrue(result.ready)
            self.assertEqual(result.reason, "ready")
            self.assertEqual(result.verified_models, 1)
            self.assertEqual(result.torch_version, "2.13.0+cpu")

    def test_probe_rejects_source_revision_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._runtime_config(root)
            (config.source_root / ".scoremosaic-source-revision").write_text(
                "0" * 40,
                encoding="utf-8",
            )
            result = probe_runtime(config, model_specs=())
            self.assertFalse(result.ready)
            self.assertEqual(result.reason, "clarity_source_revision_mismatch")

    def test_probe_rejects_model_checksum_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._runtime_config(root)
            model = config.source_root / "model.bin"
            model.write_bytes(b"wrong")
            result = probe_runtime(
                config,
                model_specs=(ModelSpec("model.bin", "0" * 64),),
            )
            self.assertFalse(result.ready)
            self.assertTrue(result.reason.startswith("clarity_model_checksum_mismatch:"))

    def test_probe_timeout_is_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._runtime_config(root)

            def timeout_runner(*args, **kwargs):
                raise subprocess.TimeoutExpired(args[0], 1)

            result = probe_runtime(
                config,
                runner=timeout_runner,
                model_specs=(),
            )
            self.assertFalse(result.ready)
            self.assertEqual(result.reason, "clarity_probe_timed_out")

    def test_command_contains_only_fixed_cpu_options_and_safe_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._runtime_config(root)
            output = config.workspace_root / "run"
            output.mkdir(parents=True)
            pdf = config.workspace_root / "score.pdf"
            pdf.write_bytes(b"%PDF-1.4\n")

            command = build_transcription_command(pdf, output, config)

            self.assertEqual(command[0], str(config.python_command))
            self.assertEqual(command[1], str(config.source_root / "omr.py"))
            self.assertEqual(command[2], str(pdf.resolve()))
            self.assertIn("--device", command)
            self.assertEqual(command[command.index("--device") + 1], "cpu")
            self.assertEqual(command[command.index("--beam-width") + 1], "2")
            self.assertEqual(command[command.index("--pdf-dpi") + 1], "300")

    def test_input_outside_workspace_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._runtime_config(root)
            outside = root / "outside.pdf"
            outside.write_bytes(b"%PDF-1.4\n")
            with self.assertRaisesRegex(RuntimeExecutionError, "escapes"):
                build_transcription_command(
                    outside,
                    config.workspace_root / "run",
                    config,
                )

    def test_non_pdf_input_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._runtime_config(root)
            image = config.workspace_root / "score.png"
            image.parent.mkdir(parents=True)
            image.write_bytes(b"png")
            with self.assertRaisesRegex(RuntimeExecutionError, "unsupported"):
                build_transcription_command(
                    image,
                    config.workspace_root / "run",
                    config,
                )

    def test_symlink_input_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._runtime_config(root)
            target = config.workspace_root / "target.pdf"
            target.parent.mkdir(parents=True)
            target.write_bytes(b"%PDF-1.4\n")
            link = config.workspace_root / "score.pdf"
            link.symlink_to(target)
            with self.assertRaisesRegex(RuntimeExecutionError, "symbolic-link"):
                build_transcription_command(
                    link,
                    config.workspace_root / "run",
                    config,
                )

    def test_transcription_requires_valid_musicxml(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._runtime_config(root)
            pdf = config.workspace_root / "score.pdf"
            pdf.parent.mkdir(parents=True)
            pdf.write_bytes(b"%PDF-1.4\n")
            output = config.workspace_root / "run"

            def runner(command, **kwargs):
                output_path = Path(command[command.index("--output") + 1])
                output_path.write_text(
                    "<?xml version='1.0'?><score-partwise version='4.0'/>",
                    encoding="utf-8",
                )
                return subprocess.CompletedProcess(command, 0, "done", "")

            result = transcribe_file(
                pdf,
                output,
                config,
                runner=runner,
                probe=lambda _: RuntimeProbe(
                    True,
                    "ready",
                    config.source_revision,
                    config.model_revision,
                    2,
                    "2.13.0+cpu",
                ),
            )

            self.assertEqual(result.return_code, 0)
            self.assertEqual(result.musicxml_artifacts, (output / "result.musicxml",))

    def test_transcription_rejects_unsafe_xml_declaration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._runtime_config(root)
            pdf = config.workspace_root / "score.pdf"
            pdf.parent.mkdir(parents=True)
            pdf.write_bytes(b"%PDF-1.4\n")
            output = config.workspace_root / "run"

            def runner(command, **kwargs):
                output_path = Path(command[command.index("--output") + 1])
                output_path.write_text(
                    "<!DOCTYPE score-partwise><score-partwise/>",
                    encoding="utf-8",
                )
                return subprocess.CompletedProcess(command, 0, "done", "")

            with self.assertRaisesRegex(RuntimeExecutionError, "unsafe_declaration"):
                transcribe_file(
                    pdf,
                    output,
                    config,
                    runner=runner,
                    probe=lambda _: RuntimeProbe(
                        True,
                        "ready",
                        config.source_revision,
                        config.model_revision,
                        2,
                        "2.13.0+cpu",
                    ),
                )


if __name__ == "__main__":
    unittest.main()
