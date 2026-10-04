"""Command runner / execution backend.

For v0.1 commands run on the local machine via the system shell (a documented
local-developer mode). The ``ExecutionBackend`` protocol exists so a future
Docker/container backend can drop in without touching the orchestrator.

Trust boundary: only user-provided reproduction commands, adapter-selected
commands, and explicitly configured commands are executed. LLM-proposed shell
strings are never executed.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Protocol

from ..domain import CommandResult, utcnow

DEFAULT_MAX_OUTPUT_CHARS = 20_000


def _truncate(text: str, limit: int = DEFAULT_MAX_OUTPUT_CHARS) -> str:
    if text is None:
        return ""
    if len(text) <= limit:
        return text
    head = limit * 3 // 4
    tail = limit - head
    return (
        text[:head]
        + f"\n\n... [truncated {len(text) - limit} characters; full log on disk] ...\n\n"
        + text[-tail:]
    )


def _kill_process_tree(process: subprocess.Popen) -> None:
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        with contextlib.suppress(ProcessLookupError):  # pragma: no cover
            process.kill()


class ExecutionBackend(Protocol):
    def run(self, command: str, cwd: Path, timeout_seconds: int) -> CommandResult: ...


class LocalExecutionBackend:
    """Runs commands locally with the system shell and captures full output."""

    name = "local"

    def __init__(self, max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS) -> None:
        self.max_output_chars = max_output_chars

    def run(self, command: str, cwd: Path, timeout_seconds: int) -> CommandResult:
        cwd = Path(cwd)
        started = utcnow()
        started_perf = time.perf_counter()
        timed_out = False
        exit_code: int | None = None
        stdout_raw = ""
        stderr_raw = ""

        try:
            process = subprocess.Popen(
                command,
                shell=True,
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                errors="replace",
                start_new_session=True,
            )
        except OSError as exc:  # pragma: no cover - unusual environment
            finished = utcnow()
            return CommandResult(
                command=command,
                cwd=str(cwd),
                exit_code=None,
                stdout="",
                stderr=f"Failed to start command: {exc}",
                started_at=started,
                finished_at=finished,
                duration_ms=int((time.perf_counter() - started_perf) * 1000),
                timed_out=False,
            )

        try:
            stdout_raw, stderr_raw = process.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill_process_tree(process)
            try:
                stdout_raw, stderr_raw = process.communicate(timeout=10)
            except subprocess.TimeoutExpired:  # pragma: no cover
                stdout_raw, stderr_raw = "", ""
        finally:
            exit_code = process.returncode

        finished = utcnow()
        return CommandResult(
            command=command,
            cwd=str(cwd),
            exit_code=exit_code,
            stdout=_truncate(stdout_raw or "", self.max_output_chars),
            stderr=_truncate(stderr_raw or "", self.max_output_chars),
            started_at=started,
            finished_at=finished,
            duration_ms=int((time.perf_counter() - started_perf) * 1000),
            timed_out=timed_out,
        )


class CommandRunner:
    """Thin wrapper that records each executed command in a run's artifact dir."""

    def __init__(self, backend: ExecutionBackend | None = None) -> None:
        self.backend: ExecutionBackend = backend or LocalExecutionBackend()
        self._counter = 0

    def run(self, command: str, cwd: Path, timeout_seconds: int = 120) -> CommandResult:
        self._counter += 1
        return self.backend.run(command, Path(cwd), timeout_seconds)

    @property
    def count(self) -> int:
        return self._counter


# TODO(v0.2): DockerExecutionBackend with network isolation, CPU/memory limits,
# and an ephemeral mounted worktree. Do not block the hackathon prototype on it.
__all__ = [
    "DEFAULT_MAX_OUTPUT_CHARS",
    "CommandRunner",
    "ExecutionBackend",
    "LocalExecutionBackend",
]
