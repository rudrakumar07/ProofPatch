"""Isolated repository preparation via Git worktrees.

ProofPatch never modifies the developer's original branch. It records the base
commit and creates two detached worktrees (``baseline`` and ``candidate``) that
both point at the same base revision.

Because worktrees are registered inside the *source* repository's ``.git``,
leaving them behind would still pollute that repository's metadata. We therefore
register every open workspace with an ``atexit``/signal safety net, and expose
:func:`cleanup_proofpatch_worktrees` so leftovers from a hard kill can be removed.
"""

from __future__ import annotations

import atexit
import os
import signal
import subprocess
import threading
from dataclasses import asdict, dataclass
from pathlib import Path

from ..domain import RepositoryInput


class RepositoryError(Exception):
    """Base class for repository preparation failures."""


class NotAGitRepository(RepositoryError):
    pass


class DirtyRepository(RepositoryError):
    pass


@dataclass
class RepoWorkspace:
    repo_root: Path
    base_commit: str
    branch: str | None
    baseline: Path
    candidate: Path
    worktrees_root: Path
    dirty: bool = False

    def as_dict(self) -> dict:
        data = asdict(self)
        return {k: (str(v) if isinstance(v, Path) else v) for k, v in data.items()}


def _run_git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: PLW1510, UP022 -- fixed argv, PIPE required for parsing
        ["git", "-C", str(repo), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        errors="replace",
    )


# --------------------------------------------------------------------------- #
# Safety net for interrupted runs
# --------------------------------------------------------------------------- #
# Maps a worktree path to the repo that owns it. Entries are removed by
# RepositoryManager.cleanup() under normal operation; anything still present at
# interpreter exit was left by an interrupted run.
_OPEN_WORKTREES: dict[str, Path] = {}
_HOOKS_STATE = {"installed": False}
_ORPHAN_PREFIX = "/.proofpatch/runs/"


def _cleanup_all_open_worktrees() -> None:
    pairs = list(_OPEN_WORKTREES.items())
    _OPEN_WORKTREES.clear()
    repos: set[Path] = set()
    for worktree_path, repo_root in pairs:
        repos.add(repo_root)
        _run_git(repo_root, "worktree", "remove", "--force", worktree_path)
    for repo_root in repos:
        _run_git(repo_root, "worktree", "prune")


def _install_safety_net() -> None:
    if _HOOKS_STATE["installed"]:
        return
    _HOOKS_STATE["installed"] = True
    atexit.register(_cleanup_all_open_worktrees)

    def _handler(signum, _frame):
        _cleanup_all_open_worktrees()
        signal.signal(signum, signal.SIG_DFL)
        os.kill(os.getpid(), signum)

    # signal.signal only works on the main thread; the API runs runs in workers.
    if threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                signal.signal(sig, _handler)
            except (ValueError, OSError):  # pragma: no cover - unsupported platform
                continue


def cleanup_proofpatch_worktrees(repo_root: Path) -> list[str]:
    """Remove any ProofPatch-owned worktrees registered under ``repo_root``.

    Only paths containing ``/.proofpatch/runs/`` are touched, so unrelated
    developer worktrees are never affected. Returns the removed worktree paths.
    """

    proc = _run_git(Path(repo_root), "worktree", "list", "--porcelain")
    if proc.returncode != 0:
        raise RepositoryError(f"Unable to list worktrees: {proc.stderr.strip()}")

    orphaned: list[str] = []
    for line in proc.stdout.splitlines():
        if line.startswith("worktree "):
            path = line[len("worktree ") :].strip()
            if _ORPHAN_PREFIX in path:
                orphaned.append(path)

    for path in orphaned:
        _run_git(Path(repo_root), "worktree", "remove", "--force", path)
        _OPEN_WORKTREES.pop(path, None)
    if orphaned:
        _run_git(Path(repo_root), "worktree", "prune")
    return orphaned


class RepositoryManager:
    """Prepares and cleans up isolated worktrees for a single run."""

    def __init__(
        self, data_dir: Path, keep_worktrees: bool = False, allow_dirty: bool = False
    ) -> None:
        self.data_dir = Path(data_dir)
        self.keep_worktrees = keep_worktrees
        self.allow_dirty = allow_dirty

    # -- detection helpers -------------------------------------------------- #
    @staticmethod
    def is_git_repository(path: Path) -> bool:
        path = Path(path)
        if not path.exists():
            return False
        proc = _run_git(path, "rev-parse", "--is-inside-work-tree")
        return proc.returncode == 0 and proc.stdout.strip() == "true"

    def base_commit(self, repo_root: Path, ref: str | None = None) -> str:
        target = ref or "HEAD"
        proc = _run_git(repo_root, "rev-parse", target)
        if proc.returncode != 0:
            raise RepositoryError(f"Unable to resolve revision {target!r}: {proc.stderr.strip()}")
        return proc.stdout.strip()

    def is_dirty(self, repo_root: Path) -> bool:
        proc = _run_git(repo_root, "status", "--porcelain")
        if proc.returncode != 0:
            raise RepositoryError(f"Unable to read git status: {proc.stderr.strip()}")
        return bool(proc.stdout.strip())

    # -- lifecycle ---------------------------------------------------------- #
    def prepare(self, repository: RepositoryInput, run_id: str) -> RepoWorkspace:
        path = Path(repository.path).expanduser()
        if not path.exists():
            raise RepositoryError(f"Repository path does not exist: {path}")
        if not self.is_git_repository(path):
            raise NotAGitRepository(f"Not a Git working tree: {path}")

        top = _run_git(path, "rev-parse", "--show-toplevel")
        repo_root = Path(top.stdout.strip())
        base_commit = self.base_commit(repo_root, repository.ref)

        branch_proc = _run_git(repo_root, "rev-parse", "--abbrev-ref", "HEAD")
        branch = branch_proc.stdout.strip() if branch_proc.returncode == 0 else ""
        branch = branch if branch and branch != "HEAD" else None

        dirty = self.is_dirty(repo_root)
        if dirty and not self.allow_dirty:
            raise DirtyRepository(
                "Source repository has uncommitted changes. Commit or stash them before "
                "running ProofPatch, or rerun with --allow-dirty in development mode."
            )

        worktrees_root = self.data_dir / "runs" / run_id / "worktrees"
        worktrees_root.mkdir(parents=True, exist_ok=True)
        baseline = worktrees_root / "baseline"
        candidate = worktrees_root / "candidate"

        self._add_worktree(repo_root, baseline, base_commit)
        try:
            self._add_worktree(repo_root, candidate, base_commit)
        except RepositoryError:
            self._remove_worktree(repo_root, baseline)
            raise

        return RepoWorkspace(
            repo_root=repo_root,
            base_commit=base_commit,
            branch=branch,
            baseline=baseline,
            candidate=candidate,
            worktrees_root=worktrees_root,
            dirty=dirty,
        )

    def _add_worktree(self, repo_root: Path, target: Path, commit: str) -> None:
        proc = _run_git(repo_root, "worktree", "add", "--detach", "--force", str(target), commit)
        if proc.returncode != 0:
            raise RepositoryError(
                f"Unable to create worktree at {target}: {proc.stderr.strip() or proc.stdout.strip()}"
            )
        # Register with the interrupt safety net before anything else can fail.
        _install_safety_net()
        _OPEN_WORKTREES[str(target)] = repo_root

    def _remove_worktree(self, repo_root: Path, target: Path) -> None:
        _OPEN_WORKTREES.pop(str(target), None)
        if not target.exists():
            return
        _run_git(repo_root, "worktree", "remove", "--force", str(target))
        _run_git(repo_root, "worktree", "prune")

    def cleanup(self, workspace: RepoWorkspace) -> None:
        """Remove worktrees unless the environment asks us to keep them."""

        if self.keep_worktrees:
            # Release the safety net so intentionally kept worktrees survive atexit.
            _OPEN_WORKTREES.pop(str(workspace.baseline), None)
            _OPEN_WORKTREES.pop(str(workspace.candidate), None)
            return
        self._remove_worktree(workspace.repo_root, workspace.baseline)
        self._remove_worktree(workspace.repo_root, workspace.candidate)


__all__ = [
    "DirtyRepository",
    "NotAGitRepository",
    "RepoWorkspace",
    "RepositoryError",
    "RepositoryManager",
    "cleanup_proofpatch_worktrees",
]
