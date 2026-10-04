"""Python project adapter.

Isolates Python-specific command selection so the orchestrator stays
language-neutral and future adapters (JS/TS, etc.) can be added.
"""

from __future__ import annotations

import shlex
import sys
from pathlib import Path
from typing import Any, Protocol

_PYTHON_MARKERS = ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt")
_PYTEST_CONFIG_FILES = ("pytest.ini", "tox.ini", "setup.cfg", "pyproject.toml")


class ProjectAdapter(Protocol):
    name: str

    def matches(self, repo: Path) -> bool: ...

    def collect_project_metadata(self, repo: Path) -> dict[str, Any]: ...

    def default_test_command(self, repo: Path) -> str | None: ...

    def static_commands(self, repo: Path) -> list[str]: ...

    def syntax_check_command(self, repo: Path) -> str: ...


class PythonProjectAdapter:
    name = "python"

    def __init__(self, python_executable: str | None = None) -> None:
        # Use the same interpreter that runs ProofPatch so the fixture's
        # dependencies (e.g. pytest) are guaranteed to be importable.
        self._python = shlex.quote(python_executable or sys.executable)

    def matches(self, repo: Path) -> bool:
        repo = Path(repo)
        if any((repo / marker).exists() for marker in _PYTHON_MARKERS):
            return True
        # Fall back to "any .py file present".
        return any(repo.glob("*.py")) or any(repo.glob("**/*.py"))

    def _has_pytest_config(self, repo: Path) -> bool:
        for name in _PYTEST_CONFIG_FILES:
            config = repo / name
            if not config.exists():
                continue
            try:
                content = config.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if "pytest" in content or "[tool.pytest" in content:
                return True
        return False

    def collect_project_metadata(self, repo: Path) -> dict[str, Any]:
        repo = Path(repo)
        return {
            "adapter": self.name,
            "has_pyproject": (repo / "pyproject.toml").exists(),
            "has_setup_py": (repo / "setup.py").exists(),
            "has_requirements": (repo / "requirements.txt").exists(),
            "has_tests_dir": (repo / "tests").is_dir(),
            "has_src_layout": (repo / "src").is_dir(),
            "has_pytest_config": self._has_pytest_config(repo),
        }

    def default_test_command(self, repo: Path) -> str | None:
        repo = Path(repo)
        if (repo / "tests").is_dir() or self._has_pytest_config(repo):
            return f"{self._python} -m pytest -q --junitxml=.proofpatch_pytest.xml"
        return None

    def static_commands(self, repo: Path) -> list[str]:
        return [self.syntax_check_command(repo)]

    def syntax_check_command(self, repo: Path) -> str:
        return f"{self._python} -m compileall -q ."

    def generated_tests_command(self) -> str:
        return (
            f"{self._python} -m pytest -q .proofpatch_generated_tests "
            "--junitxml=.proofpatch_generated.xml"
        )


__all__ = ["ProjectAdapter", "PythonProjectAdapter"]
