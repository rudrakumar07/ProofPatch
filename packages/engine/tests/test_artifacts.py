"""Artifact store tests: directory creation, atomic writes, JSONL events."""

import json

from proofpatch.artifacts import ArtifactStore
from proofpatch.domain import CommandResult, IssueInput, RunEventModel


def test_create_run_directory(tmp_path):
    store = ArtifactStore.create(tmp_path, "pp_test1")
    assert (store.run_dir / "generated_tests").is_dir()
    assert (store.run_dir / "commands").is_dir()
    assert (store.run_dir / "events.jsonl").exists()


def test_atomic_json_roundtrip(tmp_path):
    store = ArtifactStore.create(tmp_path, "pp_test2")
    store.write_json("run.json", {"run_id": "pp_test2", "score": 42})
    assert not (store.run_dir / "run.json.tmp").exists()
    assert store.read_json("run.json")["score"] == 42


def test_write_pydantic_model(tmp_path):
    store = ArtifactStore.create(tmp_path, "pp_test3")
    store.write_json("issue.json", IssueInput(title="hello", description="d"))
    data = store.read_json("issue.json")
    assert data["title"] == "hello"


def test_event_append_is_valid_jsonl(tmp_path):
    store = ArtifactStore.create(tmp_path, "pp_test4")
    for seq in range(1, 4):
        store.append_event(
            RunEventModel(run_id="pp_test4", sequence=seq, type="step_completed", message=f"m{seq}")
        )
    lines = (store.run_dir / "events.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
    parsed = [json.loads(line) for line in lines]
    assert [p["sequence"] for p in parsed] == [1, 2, 3]


def test_command_result_artifact(tmp_path):
    store = ArtifactStore.create(tmp_path, "pp_test5")
    result = CommandResult(command="echo hi", cwd="/tmp", exit_code=0, stdout="hi")
    rel = store.write_command_result(1, "baseline-repro", result)
    assert rel == "commands/001-baseline-repro.json"
    assert store.read_json(rel)["exit_code"] == 0


def test_safe_artifact_path_blocks_escape(tmp_path):
    store = ArtifactStore.create(tmp_path, "pp_test6")
    assert store.safe_artifact_path("report.md") is not None
    assert store.safe_artifact_path("../../etc/passwd") is None
