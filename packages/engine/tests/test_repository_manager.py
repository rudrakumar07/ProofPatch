"""Repository manager tests (Phase 3 exit criteria)."""

import pytest
from proofpatch.domain import RepositoryInput
from proofpatch.repo.manager import (
    DirtyRepository,
    NotAGitRepository,
    RepositoryError,
    RepositoryManager,
)


def test_rejects_non_git_directory(tmp_path):
    plain = tmp_path / "notgit"
    plain.mkdir()
    manager = RepositoryManager(tmp_path / "data")
    with pytest.raises(NotAGitRepository):
        manager.prepare(RepositoryInput(path=str(plain)), "pp_x")


def test_rejects_missing_path(tmp_path):
    manager = RepositoryManager(tmp_path / "data")
    with pytest.raises(RepositoryError):
        manager.prepare(RepositoryInput(path=str(tmp_path / "nope")), "pp_x")


def test_rejects_dirty_repo(temp_dirty_git_repo, tmp_path):
    manager = RepositoryManager(tmp_path / "data")
    with pytest.raises(DirtyRepository):
        manager.prepare(RepositoryInput(path=str(temp_dirty_git_repo)), "pp_dirty")


def test_records_base_sha(temp_git_repo, tmp_path):
    manager = RepositoryManager(tmp_path / "data")
    workspace = manager.prepare(RepositoryInput(path=str(temp_git_repo)), "pp_sha")
    assert len(workspace.base_commit) == 40
    manager.cleanup(workspace)


def test_creates_two_worktrees_at_same_sha(temp_git_repo, tmp_path):
    manager = RepositoryManager(tmp_path / "data")
    workspace = manager.prepare(RepositoryInput(path=str(temp_git_repo)), "pp_wt")
    assert workspace.baseline.is_dir()
    assert workspace.candidate.is_dir()

    def head(path):
        import subprocess

        return subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            stdout=subprocess.PIPE,
            text=True,
            check=True,
        ).stdout.strip()

    assert head(workspace.baseline) == workspace.base_commit
    assert head(workspace.candidate) == workspace.base_commit
    manager.cleanup(workspace)


def test_source_repo_unchanged(temp_git_repo, tmp_path):
    import subprocess

    manager = RepositoryManager(tmp_path / "data")
    workspace = manager.prepare(RepositoryInput(path=str(temp_git_repo)), "pp_src")
    manager.cleanup(workspace)
    status = subprocess.run(
        ["git", "-C", str(temp_git_repo), "status", "--porcelain"],
        stdout=subprocess.PIPE,
        text=True,
    ).stdout.strip()
    assert status == ""


def test_cleanup_removes_worktrees(temp_git_repo, tmp_path):
    manager = RepositoryManager(tmp_path / "data")
    workspace = manager.prepare(RepositoryInput(path=str(temp_git_repo)), "pp_cleanup")
    assert workspace.baseline.exists()
    manager.cleanup(workspace)
    assert not workspace.baseline.exists()
    assert not workspace.candidate.exists()


def test_keep_worktrees_leaves_dirs(temp_git_repo, tmp_path):
    manager = RepositoryManager(tmp_path / "data", keep_worktrees=True)
    workspace = manager.prepare(RepositoryInput(path=str(temp_git_repo)), "pp_keep")
    manager.cleanup(workspace)
    assert workspace.baseline.exists()

    # tidy up so the test leaves nothing behind
    from proofpatch.repo.manager import RepositoryManager as RM

    RM(tmp_path / "data", keep_worktrees=False).cleanup(workspace)
