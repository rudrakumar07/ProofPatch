"""Generated verification test locking and manifest management.

The same locked test files (by SHA-256) must be used on baseline and candidate,
otherwise the differential evidence would be meaningless.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from ..domain import GeneratedTestBundle

GENERATED_DIR = ".proofpatch_generated_tests"


def file_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_bundle(repo: Path, bundle: GeneratedTestBundle) -> list[str]:
    """Write every generated test file into the worktree. Returns relative paths."""

    repo = Path(repo)
    written: list[str] = []
    for item in bundle.files:
        rel = item.relative_path.replace("\\", "/")
        target = repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(item.content, encoding="utf-8")
        written.append(rel)
    return written


def lock_manifest(repo: Path, bundle: GeneratedTestBundle) -> dict:
    """Create a manifest of relative paths and SHA-256 hashes for the bundle."""

    repo = Path(repo)
    files = []
    for item in bundle.files:
        rel = item.relative_path.replace("\\", "/")
        files.append({"path": rel, "sha256": file_sha256(repo / rel)})
    return {"algorithm": "sha256", "files": files}


def verify_manifest(repo: Path, manifest: dict) -> list[str]:
    """Return a list of problems (empty means the hashes are unchanged)."""

    repo = Path(repo)
    problems: list[str] = []
    for entry in manifest.get("files", []):
        rel = entry["path"]
        path = repo / rel
        if not path.exists():
            problems.append(f"Generated test missing: {rel}")
            continue
        actual = file_sha256(path)
        if actual != entry["sha256"]:
            problems.append(f"Generated test was modified: {rel}")
    return problems


def manifest_digest(manifest: dict) -> str:
    joined = "|".join(f"{e['path']}:{e['sha256']}" for e in manifest.get("files", []))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


__all__ = [
    "GENERATED_DIR",
    "file_sha256",
    "lock_manifest",
    "manifest_digest",
    "verify_manifest",
    "write_bundle",
]
