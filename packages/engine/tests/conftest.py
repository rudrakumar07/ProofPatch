"""Shared fixtures for ProofPatch engine tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE = REPO_ROOT / "fixtures" / "python-session-bug"


def _git(path: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(path), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )


@pytest.fixture
def fixture_repo() -> Path:
    """The committed payment-session demo fixture."""

    assert FIXTURE.exists(), f"missing fixture at {FIXTURE}"
    _git(FIXTURE, "status")  # sanity: it is a git repo
    return FIXTURE


@pytest.fixture
def temp_git_repo(tmp_path: Path) -> Path:
    """A tiny committed Git repository used for repository-manager tests."""

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (repo / "README.md").write_text("# demo\n", encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "initial")
    return repo


@pytest.fixture
def temp_dirty_git_repo(temp_git_repo: Path) -> Path:
    (temp_git_repo / "untracked.py").write_text("x = 1\n", encoding="utf-8")
    return temp_git_repo
