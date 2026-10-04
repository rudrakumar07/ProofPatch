"""Static / syntax verification helpers.

The mandatory lightweight check is ``python -m compileall``. When a project
already configures ruff or mypy we can optionally run them, but we never install
tools during a verification run, and a missing tool is reported as skipped
rather than passed.
"""

from __future__ import annotations

import json

from ..domain import StaticCheckResult
from .runner import CommandRunner


def fingerprint_ruff(output: str) -> list[str]:
    """Turn ``ruff check --output-format=json`` output into stable fingerprints."""

    findings: list[str] = []
    try:
        data = json.loads(output or "[]")
    except json.JSONDecodeError:
        return findings
    if not isinstance(data, list):
        return findings
    for item in data:
        if not isinstance(item, dict):
            continue
        code = item.get("code") or ""
        filename = item.get("filename") or ""
        location = item.get("location") or {}
        row = location.get("row", "")
        message = item.get("message") or ""
        findings.append(f"{code}|{filename}|{row}|{message}")
    return findings


def _parse_compileall_findings(output: str) -> list[str]:
    findings: list[str] = []
    for raw_line in (output or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if "Error" in line or "error" in line or "SyntaxError" in line:
            findings.append(line)
    return findings


def interpret_static_result(command: str, exit_code: int | None, output: str) -> StaticCheckResult:
    """Convert a finished command into a :class:`StaticCheckResult`."""

    if "ruff" in command:
        findings = fingerprint_ruff(output)
        ran = True
        available = "command not found" not in output and "No module named" not in output
    elif "compileall" in command:
        findings = _parse_compileall_findings(output) if exit_code != 0 else []
        ran = True
        available = True
    else:
        findings = []
        ran = True
        available = "command not found" not in output and "No module named" not in output

    return StaticCheckResult(
        command=command,
        ran=ran,
        exit_code=exit_code,
        findings=findings,
        output=output[-4000:],
        tool_available=available,
    )


def run_static_checks(
    runner: CommandRunner,
    repo,
    commands: list[str],
    timeout_seconds: int,
) -> list[StaticCheckResult]:
    results: list[StaticCheckResult] = []
    for command in commands:
        result = runner.run(command, repo, timeout_seconds)
        combined = (result.stdout or "") + "\n" + (result.stderr or "")
        # A tool that is missing fails to launch; treat that as skipped.
        if result.exit_code == 127 or "command not found" in combined or "No module named" in combined:
            results.append(
                StaticCheckResult(
                    command=command,
                    ran=False,
                    exit_code=result.exit_code,
                    findings=[],
                    output=combined[-2000:],
                    tool_available=False,
                )
            )
            continue
        results.append(interpret_static_result(command, result.exit_code, combined))
    return results


def new_findings(baseline: list[str], candidate: list[str]) -> list[str]:
    return sorted(set(candidate) - set(baseline))


__all__ = [
    "fingerprint_ruff",
    "interpret_static_result",
    "new_findings",
    "run_static_checks",
]
