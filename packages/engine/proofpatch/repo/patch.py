"""Patch validation and application.

The patch validator is central to the product's credibility: it rejects
path traversal, binary patches, modifications outside the repo, disallowed file
changes, and oversized diffs *before* anything is applied. The patch is only
ever applied to the isolated candidate worktree.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from ..domain import PatchPolicyResult, VerificationOptions

_MANIFESTS = {
    "requirements.txt",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "poetry.lock",
    "pipfile",
    "pipfile.lock",
    "environment.yml",
}


def _normalize_header_path(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith('"') and raw.endswith('"'):
        raw = raw[1:-1]
    raw = raw.split("\t")[0]
    if raw == "/dev/null":
        return raw
    if raw.startswith(("a/", "b/")):
        raw = raw[2:]
    return raw


def is_test_path(path: str) -> bool:
    parts = Path(path).parts
    name = Path(path).name
    if name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py":
        return True
    return any(part in ("test", "tests") for part in parts)


@dataclass
class DiffInfo:
    touched_files: list[str] = field(default_factory=list)
    changed_lines: int = 0
    is_binary: bool = False
    has_symlink: bool = False
    deletions: list[str] = field(default_factory=list)
    added_lines: list[str] = field(default_factory=list)
    removed_lines: list[str] = field(default_factory=list)


def parse_unified_diff(diff_text: str) -> DiffInfo:
    info = DiffInfo()
    old_path = ""
    for line in (diff_text or "").splitlines():
        if line.startswith("--- "):
            old_path = _normalize_header_path(line[4:])
            continue
        if line.startswith("+++ "):
            new_path = _normalize_header_path(line[4:])
            target = old_path if new_path == "/dev/null" else new_path
            if target and target != "/dev/null":
                info.touched_files.append(target)
            if new_path == "/dev/null" and old_path and old_path != "/dev/null":
                info.deletions.append(old_path)
            continue
        if line.startswith(("GIT binary patch", "Binary files")):
            info.is_binary = True
            continue
        if "120000" in line and "mode" in line:
            info.has_symlink = True
            continue
        if line.startswith(("+++", "---", "@@")):
            continue
        if line.startswith("+"):
            info.changed_lines += 1
            info.added_lines.append(line[1:])
        elif line.startswith("-"):
            info.changed_lines += 1
            info.removed_lines.append(line[1:])
    seen: set[str] = set()
    info.touched_files = [p for p in info.touched_files if not (p in seen or seen.add(p))]
    return info


class PatchValidator:
    def __init__(self, options: VerificationOptions | None = None) -> None:
        self.options = options or VerificationOptions()

    def validate(self, diff_text: str, candidate_repo: Path | None = None) -> PatchPolicyResult:
        info = parse_unified_diff(diff_text)
        reasons: list[str] = []
        warnings: list[str] = []

        if not info.touched_files and not info.deletions:
            reasons.append("Patch does not modify any files.")
        if info.is_binary:
            reasons.append("Binary patches are not allowed.")
        if info.has_symlink:
            reasons.append("Symlink creation is not allowed in v0.1.")

        for path in info.touched_files + info.deletions:
            if path.startswith("/"):
                reasons.append(f"Absolute path rejected: {path}")
            if ".." in Path(path).parts:
                reasons.append(f"Path traversal rejected: {path}")
            if path == ".git" or path.startswith(".git/"):
                reasons.append(f"Modification of .git is not allowed: {path}")
            if path.startswith((".proofpatch/", ".proofpatch_generated_tests/")):
                reasons.append(f"Modification of ProofPatch artifacts is not allowed: {path}")

        if info.deletions:
            reasons.append(f"File deletion is not allowed by default: {', '.join(info.deletions)}")

        if len(info.touched_files) > self.options.max_patch_files:
            reasons.append(
                f"Patch touches {len(info.touched_files)} files; limit is "
                f"{self.options.max_patch_files}."
            )
        if info.changed_lines > self.options.max_patch_changed_lines:
            reasons.append(
                f"Patch changes {info.changed_lines} lines; limit is "
                f"{self.options.max_patch_changed_lines}."
            )

        if not self.options.allow_test_file_changes_in_patch:
            edits = [p for p in info.touched_files if is_test_path(p)]
            if edits:
                reasons.append(
                    "Modification of existing test files is not allowed by default: "
                    + ", ".join(edits)
                )

        for path in info.touched_files:
            name = Path(path).name.lower()
            if name in _MANIFESTS:
                warnings.append(f"Dependency manifest changed: {path}")
            elif Path(path).suffix in (".ini", ".cfg", ".toml", ".yaml", ".yml"):
                warnings.append(f"Configuration file changed: {path}")
        if any(re.search(r"^\s*(def |class )", line) for line in info.removed_lines):
            warnings.append("Patch removes a function or class definition (possible API change).")
        if any(
            re.search(r"except\b", line) and ("pass" in line or line.strip().endswith("Exception:"))
            for line in info.added_lines
        ):
            warnings.append("Patch may swallow exceptions (added bare/except-Exception handling).")

        return PatchPolicyResult(
            allowed=not reasons,
            reasons=reasons,
            warnings=warnings,
            touched_files=info.touched_files,
            changed_lines=info.changed_lines,
        )



class PatchApplicationError(Exception):
    pass


def _write_temp_diff(diff_text: str) -> str:
    with tempfile.NamedTemporaryFile("w", suffix=".diff", delete=False, encoding="utf-8") as handle:
        handle.write(diff_text if diff_text.endswith("\n") else diff_text + "\n")
        return handle.name


def check_apply(diff_text: str, candidate_repo: Path) -> tuple[bool, str]:
    """Run ``git apply --check`` in the candidate worktree."""

    path = _write_temp_diff(diff_text)
    try:
        proc = subprocess.run(  # noqa: PLW1510, UP022 -- fixed argv, separate streams parsed below
            ["git", "-C", str(candidate_repo), "apply", "--check", "--whitespace=nowarn", path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            errors="replace",
        )
        message = (proc.stdout + proc.stderr).strip()
        return proc.returncode == 0, message
    finally:
        Path(path).unlink(missing_ok=True)


class PatchApplier:
    def apply(self, diff_text: str, candidate_repo: Path) -> None:
        """Apply the diff to the candidate worktree only."""

        path = _write_temp_diff(diff_text)
        try:
            proc = subprocess.run(  # noqa: PLW1510, UP022 -- fixed argv, separate streams parsed below
                ["git", "-C", str(candidate_repo), "apply", "--whitespace=nowarn", path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                errors="replace",
            )
            if proc.returncode != 0:
                raise PatchApplicationError(
                    f"git apply failed: {(proc.stdout + proc.stderr).strip()}"
                )
        finally:
            Path(path).unlink(missing_ok=True)


__all__ = [
    "DiffInfo",
    "PatchApplicationError",
    "PatchApplier",
    "PatchValidator",
    "check_apply",
    "is_test_path",
    "parse_unified_diff",
]

