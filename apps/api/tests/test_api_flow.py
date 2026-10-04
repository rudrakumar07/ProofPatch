"""API tests (Phase 16): POST/GET runs, events, report, diff, artifact guards.

Uses an isolated SQLite database and data directory so the real demo artifacts
are never touched.
"""

from __future__ import annotations

import os
import shlex
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE = REPO_ROOT / "fixtures" / "python-session-bug"


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("api")
    os.environ["PROOFPATCH_DATABASE_URL"] = f"sqlite:///{tmp}/test.db"
    os.environ["PROOFPATCH_DATA_DIR"] = str(tmp / "data")

    # Deterministic + offline: the API builds its own provider, so swap in the
    # engine's stub test double instead of calling the live Cline SDK.
    # (MonkeyPatch.context(), not the monkeypatch fixture, because `client` is
    # module-scoped.)
    import proofpatch.orchestrator as orchestrator_module
    from stub_provider import StubLLMProvider

    patcher = pytest.MonkeyPatch()
    patcher.setattr(
        orchestrator_module,
        "build_provider",
        lambda settings, recorder=None: StubLLMProvider(
            repo_path=FIXTURE, recorder=recorder
        ),
    )

    from proofpatch_api.db import get_engine, get_session_factory

    get_engine.cache_clear()
    get_session_factory.cache_clear()
    from proofpatch_api.main import app

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        patcher.undo()
        for key in ("PROOFPATCH_DATABASE_URL", "PROOFPATCH_DATA_DIR"):
            os.environ.pop(key, None)
        get_engine.cache_clear()
        get_session_factory.cache_clear()


def _wait_for(client, run_id, timeout_seconds=45):
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        response = client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200
        payload = response.json()
        status = payload["status"]
        if status in ("VERIFIED", "NEEDS_REVIEW", "REJECTED", "ERROR"):
            return payload
        time.sleep(0.4)
    raise AssertionError(f"run {run_id} did not finish in time")


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_create_run_requires_repository(client):
    response = client.post("/api/runs", json={"issue": {"title": "t", "description": "d"}})
    assert response.status_code == 422


def test_unknown_run_is_404(client):
    assert client.get("/api/runs/pp_DOESNOTEXIST").status_code == 404


def test_non_git_repository_becomes_error(client, tmp_path):
    plain = tmp_path / "notgit"
    plain.mkdir()
    response = client.post(
        "/api/runs",
        json={"repository": {"path": str(plain)}, "issue": {"title": "t", "description": "d"}},
    )
    assert response.status_code == 202
    run_id = response.json()["run_id"]
    final = _wait_for(client, run_id, timeout_seconds=20)
    assert final["status"] == "ERROR"


def test_full_fixture_run_is_verified(client):
    repro = (
        f"{shlex.quote(sys.executable)} -m pytest -q "
        "tests/test_session.py::test_payment_rejected_at_exact_expiry"
    )
    response = client.post(
        "/api/runs",
        json={
            "repository": {"path": str(FIXTURE)},
            "issue": {
                "title": "Payment allowed at exact session expiry",
                "description": "Equality at expiry is wrongly accepted.",
                "repro_command": repro,
            },
            "verification": {"timeout_seconds": 60},
        },
    )
    assert response.status_code == 202
    run_id = response.json()["run_id"]
    final = _wait_for(client, run_id, timeout_seconds=60)
    assert final["status"] == "VERIFIED", f"run ended {final['status']}: {final.get('error_message')}"
    assert final["verdict"] == "VERIFIED"
    assert final["score"] >= 80

    markdown = client.get(f"/api/runs/{run_id}/report.md")
    assert markdown.status_code == 200
    assert markdown.headers["content-type"].startswith("text/markdown")
    assert "## Evidence Checklist" in markdown.text

    report = client.get(f"/api/runs/{run_id}/report")
    assert report.status_code == 200
    assert report.json()["verdict"] == "VERIFIED"

    diff = client.get(f"/api/runs/{run_id}/diff")
    assert diff.status_code == 200
    assert "return now < session_expires_at" in diff.text


def test_events_and_artifact_guards(client):
    runs = client.get("/api/runs").json()
    assert runs
    # Prefer the verified fixture run created by the test above.
    verified = next((r for r in runs if r.get("verdict") == "VERIFIED"), runs[0])
    run_id = verified["run_id"]

    events = client.get(f"/api/runs/{run_id}/events.json").json()
    types = {e["type"] for e in events}
    assert {"run_created", "step_completed", "run_completed"} <= types

    ok = client.get(f"/api/runs/{run_id}/artifact/root_cause.json")
    assert ok.status_code == 200
    assert ok.json()["json"]["suspected_files"]

    blocked = client.get(f"/api/runs/{run_id}/artifact/subdir%2f..%2f..%2frun.json")
    assert blocked.status_code == 404, blocked.text

    missing = client.get(f"/api/runs/{run_id}/artifact/does-not-exist.txt")
    assert missing.status_code == 404
