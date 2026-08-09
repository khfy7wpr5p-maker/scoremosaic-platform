from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
import zipfile

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT / "src"))

from scoremosaic_audiveris.config import load_config
from scoremosaic_audiveris.runtime import (
    RuntimeExecutionError,
    _run_bounded_process,
    build_transcription_command,
    probe_runtime,
    transcribe_file,
)


class RuntimeTests(unittest.TestCase):
    @unittest.skipUnless(
        os.name == "posix" and Path("/proc").is_dir(),
        "Audiveris runtime process containment requires Linux",
    )
    def test_bounded_process_kills_descendant_holding_captured_output(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            process_group_file = root / "process-group"
            descendant_file = root / "descendant"
            child_code = (
                "import os, pathlib, signal, time; "
                "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                f"pathlib.Path({str(descendant_file)!r}).write_text(str(os.getpid())); "
                "time.sleep(60)"
            )
            parent_code = (
                "import os, pathlib, subprocess, sys, time; "
                f"pathlib.Path({str(process_group_file)!r}).write_text(str(os.getpgrp())); "
                f"subprocess.Popen([sys.executable, '-c', {child_code!r}]); "
                "print('descendant-started', flush=True); "
                "time.sleep(60)"
            )

            previous_handler = signal.getsignal(signal.SIGALRM)

            def fail_if_runner_hangs(_signum, _frame):
                raise AssertionError("bounded process runner did not return")

            signal.signal(signal.SIGALRM, fail_if_runner_hangs)
            signal.setitimer(signal.ITIMER_REAL, 5)
            started = time.monotonic()
            runner_returned = False
            try:
                with self.assertRaises(subprocess.TimeoutExpired):
                    _run_bounded_process(
                        [sys.executable, "-c", parent_code],
                        cwd=root,
                        env=dict(os.environ),
                        capture_output=True,
                        text=True,
                        timeout=0.5,
                        check=False,
                    )
                runner_returned = True
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)
                signal.signal(signal.SIGALRM, previous_handler)
                if not runner_returned and process_group_file.is_file():
                    try:
                        os.killpg(
                            int(process_group_file.read_text(encoding="utf-8")),
                            signal.SIGKILL,
                        )
                    except ProcessLookupError:
                        pass

            self.assertLess(time.monotonic() - started, 4)
            descendant_pid = int(descendant_file.read_text(encoding="utf-8"))
            descendant_stat = Path(f"/proc/{descendant_pid}/stat")
            if descendant_stat.is_file():
                self.assertEqual(
                    descendant_stat.read_text(encoding="utf-8").split()[2],
                    "Z",
                    "descendant process is still running after timeout",
                )

    def test_probe_accepts_exact_pinned_version(self) -> None:
        with TemporaryDirectory() as temp_dir:
            command = Path(temp_dir) / "audiveris"
            command.write_text("stub", encoding="utf-8")
            command.chmod(0o755)
            config = load_config(
                {
                    "SCOREMOSAIC_AUDIVERIS_RUNTIME_MODE": "audiveris",
                    "SCOREMOSAIC_AUDIVERIS_COMMAND": str(command),
                    "SCOREMOSAIC_AUDIVERIS_WORKSPACE_ROOT": str(
                        Path(temp_dir) / "workspace"
                    ),
                }
            )
            runner = lambda *args, **kwargs: subprocess.CompletedProcess(
                args[0],
                0,
                "- Tesseract:    5.5.2\n- Library:      1.4.14\n- Version:      5.11.0\n",
                "",
            )
            probe = probe_runtime(config, runner=runner)
            self.assertTrue(probe.ready)
            self.assertEqual(probe.version, "5.11.0")
            self.assertIn("1.4.14", probe.diagnostic)

    def test_probe_rejects_version_mismatch(self) -> None:
        with TemporaryDirectory() as temp_dir:
            command = Path(temp_dir) / "audiveris"
            command.write_text("stub", encoding="utf-8")
            command.chmod(0o755)
            config = load_config(
                {
                    "SCOREMOSAIC_AUDIVERIS_RUNTIME_MODE": "audiveris",
                    "SCOREMOSAIC_AUDIVERIS_COMMAND": str(command),
                    "SCOREMOSAIC_AUDIVERIS_WORKSPACE_ROOT": str(
                        Path(temp_dir) / "workspace"
                    ),
                }
            )
            runner = lambda *args, **kwargs: subprocess.CompletedProcess(
                args[0], 0, "- Version:      5.10.2\n", ""
            )
            probe = probe_runtime(config, runner=runner)
            self.assertFalse(probe.ready)
            self.assertEqual(probe.reason, "audiveris_version_mismatch")
            self.assertEqual(probe.version, "5.10.2")

    def test_probe_timeout_is_isolated(self) -> None:
        with TemporaryDirectory() as temp_dir:
            command = Path(temp_dir) / "audiveris"
            command.write_text("stub", encoding="utf-8")
            command.chmod(0o755)
            config = load_config(
                {
                    "SCOREMOSAIC_AUDIVERIS_RUNTIME_MODE": "audiveris",
                    "SCOREMOSAIC_AUDIVERIS_COMMAND": str(command),
                    "SCOREMOSAIC_AUDIVERIS_WORKSPACE_ROOT": str(
                        Path(temp_dir) / "workspace"
                    ),
                }
            )

            def timeout(*args, **kwargs):
                raise subprocess.TimeoutExpired(args[0], 1)

            probe = probe_runtime(config, runner=timeout)
            self.assertFalse(probe.ready)
            self.assertEqual(probe.reason, "audiveris_probe_timed_out")

    def test_command_contains_only_fixed_options_and_safe_paths(self) -> None:
        with TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            workspace.mkdir()
            command_path = Path(temp_dir) / "audiveris"
            command_path.write_text("stub", encoding="utf-8")
            command_path.chmod(0o755)
            input_path = workspace / "input.png"
            input_path.write_bytes(b"png")
            output_dir = workspace / "out"
            config = load_config(
                {
                    "SCOREMOSAIC_AUDIVERIS_RUNTIME_MODE": "audiveris",
                    "SCOREMOSAIC_AUDIVERIS_COMMAND": str(command_path),
                    "SCOREMOSAIC_AUDIVERIS_WORKSPACE_ROOT": str(workspace),
                }
            )
            command = build_transcription_command(input_path, output_dir, config)
            self.assertEqual(
                command[1:7],
                ("-batch", "-transcribe", "-export", "-save", "-swap", "-output"),
            )
            self.assertEqual(command[-2], "--")
            self.assertEqual(Path(command[-1]), input_path.resolve())

    def test_input_outside_workspace_is_rejected(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir()
            outside = root / "outside.png"
            outside.write_bytes(b"png")
            config = load_config(
                {
                    "SCOREMOSAIC_AUDIVERIS_WORKSPACE_ROOT": str(workspace),
                    "SCOREMOSAIC_AUDIVERIS_COMMAND": "/bin/true",
                }
            )
            with self.assertRaisesRegex(RuntimeExecutionError, "escapes"):
                build_transcription_command(outside, workspace / "out", config)

    def test_symlink_input_is_rejected(self) -> None:
        with TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            workspace.mkdir()
            target = workspace / "target.png"
            target.write_bytes(b"png")
            link = workspace / "link.png"
            link.symlink_to(target)
            config = load_config(
                {
                    "SCOREMOSAIC_AUDIVERIS_WORKSPACE_ROOT": str(workspace),
                    "SCOREMOSAIC_AUDIVERIS_COMMAND": "/bin/true",
                }
            )
            with self.assertRaisesRegex(RuntimeExecutionError, "symbolic-link"):
                build_transcription_command(link, workspace / "out", config)

    def test_transcription_rejects_unsafe_mxl_candidate(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir()
            command_path = root / "audiveris"
            command_path.write_text("stub", encoding="utf-8")
            command_path.chmod(0o755)
            input_path = workspace / "input.png"
            input_path.write_bytes(b"png")
            output_dir = workspace / "out"
            config = load_config(
                {
                    "SCOREMOSAIC_AUDIVERIS_RUNTIME_MODE": "audiveris",
                    "SCOREMOSAIC_AUDIVERIS_COMMAND": str(command_path),
                    "SCOREMOSAIC_AUDIVERIS_WORKSPACE_ROOT": str(workspace),
                }
            )

            def runner(command, **kwargs):
                if "-version" in command:
                    return subprocess.CompletedProcess(
                        command, 0, "- Version:      5.11.0\n", ""
                    )
                output_root = Path(command[command.index("-output") + 1])
                output_root.mkdir(parents=True, exist_ok=True)
                mxl = output_root / "unsafe.mxl"
                with zipfile.ZipFile(mxl, "w") as archive:
                    archive.writestr(
                        "META-INF/container.xml",
                        '<container><rootfiles><rootfile full-path="../score.musicxml"/></rootfiles></container>',
                    )
                    archive.writestr("../score.musicxml", "<score-partwise/>")
                return subprocess.CompletedProcess(command, 0, "done", "")

            with self.assertRaisesRegex(
                RuntimeExecutionError, "audiveris_candidate_unsafe:mxl_member_path_unsafe"
            ):
                transcribe_file(input_path, output_dir, config, runner=runner)


if __name__ == "__main__":
    unittest.main()
