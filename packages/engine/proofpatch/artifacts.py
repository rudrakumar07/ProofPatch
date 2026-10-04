"""Run artifact store.

Every run gets a self-contained directory tree that records exactly what
ProofPatch executed and exactly what the LLM proposed. Writes are atomic
(write to ``*.tmp`` then ``os.replace``) so a crash cannot leave a half-written
artifact.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .domain import CommandResult, RunEventModel


def atomic_write_text(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def atomic_write_json(path: Path, data: Any) -> None:
    atomic_write_text(path, json.dumps(data, indent=2, default=str) + "\n")


class ArtifactStore:
    """Manages the ``.proofpatch/runs/<run_id>/`` directory for a single run."""

    def __init__(self, run_dir: Path) -> None:
        self.run_dir = Path(run_dir)

    # -- construction ------------------------------------------------------- #
    @classmethod
    def create(cls, data_dir: Path, run_id: str) -> ArtifactStore:
        run_dir = Path(data_dir) / "runs" / run_id
        (run_dir / "generated_tests").mkdir(parents=True, exist_ok=True)
        (run_dir / "commands").mkdir(parents=True, exist_ok=True)
        store = cls(run_dir)
        store.touch("events.jsonl")
        return store

    @classmethod
    def for_existing(cls, data_dir: Path, run_id: str) -> ArtifactStore:
        return cls(Path(data_dir) / "runs" / run_id)

    # -- paths -------------------------------------------------------------- #
    def path(self, *parts: str) -> Path:
        return self.run_dir.joinpath(*parts)

    def touch(self, rel: str) -> Path:
        path = self.path(rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text("", encoding="utf-8")
        return path

    # -- writers ------------------------------------------------------------ #
    def write_text(self, rel: str, text: str) -> Path:
        path = self.path(rel)
        atomic_write_text(path, text)
        return path

    def write_json(self, rel: str, data: Any) -> Path:
        path = self.path(rel)
        if isinstance(data, BaseModel):
            data = data.model_dump(mode="json")
        atomic_write_json(path, data)
        return path

    def append_jsonl(self, rel: str, data: Any) -> None:
        path = self.path(rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, BaseModel):
            data = data.model_dump(mode="json")
        line = json.dumps(data, default=str)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    # -- domain helpers ----------------------------------------------------- #
    def append_event(self, event: RunEventModel) -> None:
        self.append_jsonl("events.jsonl", event)

    def write_command_result(self, index: int, name: str, result: CommandResult) -> str:
        rel = f"commands/{index:03d}-{name}.json"
        self.write_json(rel, result)
        return rel

    # -- readers ------------------------------------------------------------ #
    def read_text(self, rel: str) -> str:
        return self.path(rel).read_text(encoding="utf-8")

    def read_json(self, rel: str) -> Any:
        return json.loads(self.path(rel).read_text(encoding="utf-8"))

    def exists(self, rel: str) -> bool:
        return self.path(rel).exists()

    def safe_artifact_path(self, rel: str) -> Path | None:
        """Resolve ``rel`` inside the run directory, or return None if it escapes."""

        candidate = (self.run_dir / rel).resolve()
        run_root = self.run_dir.resolve()
        if run_root == candidate or run_root in candidate.parents:
            return candidate
        return None

    def list_artifacts(self) -> list[str]:
        if not self.run_dir.exists():
            return []
        return sorted(
            str(p.relative_to(self.run_dir))
            for p in self.run_dir.rglob("*")
            if p.is_file()
        )


__all__ = ["ArtifactStore", "atomic_write_json", "atomic_write_text"]
