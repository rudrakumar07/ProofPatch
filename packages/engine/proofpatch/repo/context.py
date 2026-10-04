"""Deterministic repository context collection.

We never send the whole repository to the LLM. Instead we build a compact,
inspectable context: a filtered tree plus a small set of files chosen by simple
heuristics (paths in stack traces, symbols mentioned in the issue, nearby tests,
project metadata). Secret-looking files are excluded.
"""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, Field

from ..domain import IssueInput

EXCLUDED_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    "coverage",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".proofpatch",
    ".proofpatch_generated_tests",
    ".tox",
    ".eggs",
}

SECRET_NAMES = {"id_rsa", "id_ed25519", "credentials.json", ".netrc"}

_PATH_RE = re.compile(r"([A-Za-z0-9_][A-Za-z0-9_./-]*\.py)")
_SYMBOL_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]{3,})\b")
_STOPWORDS = {
    "the", "and", "for", "with", "this", "that", "when", "then", "should",
    "error", "value", "class", "return", "import", "from", "self", "true",
    "false", "none", "test", "tests", "line", "file", "def", "print", "expected",
    "actual", "issue", "bug", "code", "given", "which", "into", "not", "but",
}


class ContextFile(BaseModel):
    path: str
    content: str
    reason: str
    truncated: bool = False


class RepoContext(BaseModel):
    tree: str = ""
    files: list[ContextFile] = Field(default_factory=list)
    total_chars: int = 0


class ContextBuilder:
    def __init__(
        self,
        max_files: int = 20,
        max_chars_per_file: int = 12_000,
        max_total_chars: int = 80_000,
        max_depth: int = 5,
    ) -> None:
        self.max_files = max_files
        self.max_chars_per_file = max_chars_per_file
        self.max_total_chars = max_total_chars
        self.max_depth = max_depth

    # -- filtering ---------------------------------------------------------- #
    @staticmethod
    def is_secret(name: str) -> bool:
        if name == ".env" or name.startswith(".env."):
            return True
        if name in SECRET_NAMES:
            return True
        if name.endswith((".pem", ".key", ".p12")):
            return True
        return name.startswith("secrets.")

    def _excluded(self, path: Path) -> bool:
        if path.name in EXCLUDED_DIRS:
            return True
        return bool(path.is_file() and self.is_secret(path.name))

    # -- tree --------------------------------------------------------------- #
    def build_tree(self, repo: Path) -> str:
        repo = Path(repo)
        lines: list[str] = []

        def walk(directory: Path, depth: int) -> None:
            if depth > self.max_depth:
                return
            try:
                entries = sorted(
                    directory.iterdir(), key=lambda p: (p.is_file(), p.name.lower())
                )
            except OSError:
                return
            for entry in entries:
                if self._excluded(entry):
                    continue
                lines.append("  " * depth + entry.name + ("/" if entry.is_dir() else ""))
                if entry.is_dir():
                    walk(entry, depth + 1)

        walk(repo, 0)
        return "\n".join(lines)

    # -- heuristics --------------------------------------------------------- #
    def _paths_from_text(self, text: str) -> list[str]:
        found: list[str] = []
        for match in _PATH_RE.findall(text or ""):
            if match not in found:
                found.append(match)
        return found

    def _symbols_from_text(self, text: str) -> list[str]:
        found: list[str] = []
        for token in _SYMBOL_RE.findall(text or ""):
            if token.lower() in _STOPWORDS:
                continue
            if token not in found:
                found.append(token)
        return found

    def _python_files(self, repo: Path) -> list[str]:
        repo = Path(repo)
        rels: list[str] = []
        for path in repo.rglob("*.py"):
            try:
                rel = path.relative_to(repo)
            except ValueError:  # pragma: no cover - rglob stays inside repo
                continue
            # Only *repository-relative* components may exclude a file. Using the
            # absolute path here would also match the run's own artifact directory,
            # which always contains the worktrees (".proofpatch/runs/<id>/...").
            if any(part in EXCLUDED_DIRS for part in rel.parts):
                continue
            if self.is_secret(path.name):
                continue
            rels.append(rel.as_posix())
        return sorted(rels)

    def _read_limited(self, path: Path) -> tuple[str, bool]:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return "", False
        if len(text) > self.max_chars_per_file:
            return text[: self.max_chars_per_file], True
        return text, False

    def _select(self, repo: Path, issue: IssueInput) -> dict[str, str]:
        """Return an ordered mapping of relative path -> inclusion reason."""

        repo = Path(repo)
        blob = "\n".join(
            filter(
                None,
                [issue.description, issue.error_log, issue.expected_behavior, issue.title],
            )
        )
        selected: dict[str, str] = {}

        # 1. Paths explicitly mentioned in the issue / stack trace.
        for rel in self._paths_from_text(blob):
            candidate = repo / rel
            if candidate.exists() and candidate.is_file() and not self.is_secret(candidate.name):
                selected[rel] = "Referenced by path in the issue or error log."

        # 2. Files whose definitions match symbols mentioned in the issue.
        symbols = self._symbols_from_text(blob)
        if symbols:
            pattern = re.compile(r"\b(?:def|class)\s+(" + "|".join(map(re.escape, symbols)) + r")\b")
            for rel in self._python_files(repo):
                text, _ = self._read_limited(repo / rel)
                hit = pattern.search(text)
                if hit:
                    selected.setdefault(rel, f"Defines symbol {hit.group(1)!r} mentioned in the issue.")

        # 3. Nearby test files for any selected source module.
        for rel in list(selected):
            stem = Path(rel).stem
            for test_rel in self._python_files(repo):
                if test_rel in selected:
                    continue
                name = Path(test_rel).name
                if (name.startswith("test_") or name.endswith("_test.py")) and stem in name:
                    selected[test_rel] = f"Test file related to {rel}."

        # 3b. Local modules imported by selected test files. The issue often only
        # names a reproduction *test*, so following its imports is what surfaces
        # the source file that actually contains the bug.
        python_files = self._python_files(repo)
        for rel in list(selected):
            if not is_test_file(rel):
                continue
            text, _ = self._read_limited(repo / rel)
            for module in _imported_modules(text):
                candidate = _module_to_path(module, python_files)
                if candidate and candidate not in selected:
                    selected[candidate] = f"Imported by {rel}."

        # 4. Project metadata.
        for meta in ("pyproject.toml", "setup.cfg", "requirements.txt", "setup.py"):
            if (repo / meta).exists():
                selected.setdefault(meta, "Project metadata.")

        # 5. Fallback: a buggy *source* file must always be present. Selecting
        # only tests/metadata is not enough to propose a patch.
        if not any(path.endswith(".py") and not is_test_file(path) for path in selected):
            source = [p for p in self._python_files(repo) if not is_test_file(p)]
            source.sort(key=lambda p: (repo / p).stat().st_size)
            for rel in source[: self.max_files]:
                selected.setdefault(rel, "Fallback selection (no explicit match found).")

        return selected

    def build(self, repo: Path, issue: IssueInput) -> RepoContext:
        repo = Path(repo)
        tree = self.build_tree(repo)
        selected = self._select(repo, issue)

        files: list[ContextFile] = []
        total = 0
        for rel, reason in selected.items():
            if len(files) >= self.max_files:
                break
            remaining = self.max_total_chars - total
            if remaining <= 0:
                break
            content, truncated = self._read_limited(repo / rel)
            if len(content) > remaining:
                content = content[:remaining]
                truncated = True
            files.append(ContextFile(path=rel, content=content, reason=reason, truncated=truncated))
            total += len(content)

        return RepoContext(tree=tree, files=files, total_chars=total)

    def for_test_generation(self, repo: Path, issue: IssueInput, root_cause=None) -> RepoContext:
        """Build context for the test generator.

        The patch diff is intentionally never included here so the generated
        tests cannot simply mirror the patch implementation.
        """

        context = self.build(repo, issue)
        if root_cause is not None:
            for suspected in getattr(root_cause, "suspected_files", []):
                if any(f.path == suspected for f in context.files):
                    continue
                candidate = Path(repo) / suspected
                if candidate.exists() and candidate.is_file() and not self.is_secret(candidate.name):
                    content, truncated = self._read_limited(candidate)
                    context.files.append(
                        ContextFile(
                            path=suspected,
                            content=content,
                            reason="Suspected root-cause file from analysis.",
                            truncated=truncated,
                        )
                    )
                    context.total_chars += len(content)
        return context


def is_test_file(path: str) -> bool:
    name = Path(path).name
    parts = Path(path).parts
    if name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py":
        return True
    return any(part in ("test", "tests") for part in parts)


_IMPORT_RE = re.compile(
    r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", re.MULTILINE
)


def _imported_modules(text: str) -> list[str]:
    """Return dotted module names imported by ``text`` (order preserved)."""

    modules: list[str] = []
    for match in _IMPORT_RE.finditer(text or ""):
        module = match.group(1) or match.group(2)
        if module and module not in modules:
            modules.append(module)
    return modules


def _module_to_path(module: str, python_files: list[str]) -> str | None:
    """Map a dotted module name onto a repository-relative ``.py`` path."""

    target = module.replace(".", "/") + ".py"
    suffix = "/" + target
    for path in python_files:
        if path == target or path.endswith(suffix):
            return path
    return None


__all__ = ["ContextBuilder", "ContextFile", "RepoContext", "is_test_file"]

