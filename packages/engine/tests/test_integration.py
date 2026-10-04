"""End-to-end integration tests (Phase 12 exit criteria).

Runs the full orchestrator against the deterministic fixture with the fake LLM
provider and asserts a VERIFIED verdict plus a complete artifact set.
"""

import asyncio
import shlex
import subprocess
import sys
from pathlib import Path

from proofpatch.config import Settings
from proofpatch.domain import (
    IssueInput,
    RepositoryInput,
    RunRequest,
    Verdict,
    VerificationOptions,
)
from proofpatch.orchestrator import Orchestrator
from stub_provider import StubLLMProvider

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE = REPO_ROOT / "fixtures" / "python-session-bug"

REPRO = (
    f"{shlex.quote(sys.executable)} -m pytest -q "
    "tests/test_session.py::test_payment_rejected_at_exact_expiry"
)


def _git(path, *args):
    return subprocess.run(
        ["git", "-C", str(path), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    ).stdout


def _request():
    issue = IssueInput(
        title="Payment allowed at exact session expiry",
        description=(
            "A payment session should no longer be usable once its expiry timestamp "
            "is reached. Currently a payment attempted exactly at expires_at is accepted."
        ),
        expected_behavior="now >= expires_at should be treated as expired",
        repro_command=REPRO,
    )
    return RunRequest(
        repository=RepositoryInput(path=str(FIXTURE)),
        issue=issue,
        verification=VerificationOptions(timeout_seconds=120),
    )


def _stub():
    return StubLLMProvider(repo_path=FIXTURE)


def test_full_run_produces_verified(tmp_path):
    settings = Settings(data_dir=tmp_path / "data")
    orchestrator = Orchestrator(settings=settings, provider=_stub())
    result = asyncio.run(orchestrator.execute_run(_request()))

    assert result.verdict == Verdict.VERIFIED, result.error
    assert result.score >= 80
    assert result.status.value == "VERIFIED"

    run_dir = Path(result.artifact_dir)
    for rel in [
        "run.json",
        "issue.json",
        "root_cause.json",
        "patch.json",
        "patch_policy.json",
        "candidate.diff",
        "generated_tests/manifest.json",
        "verification.json",
        "report.json",
        "report.md",
        "events.jsonl",
        "context.json",
    ]:
        assert (run_dir / rel).exists(), f"missing artifact {rel}"


def test_source_repo_is_never_modified(tmp_path):
    before_head = _git(FIXTURE, "rev-parse", "HEAD").strip()
    before_status = _git(FIXTURE, "status", "--porcelain")

    settings = Settings(data_dir=tmp_path / "data")
    orchestrator = Orchestrator(settings=settings, provider=_stub())
    asyncio.run(orchestrator.execute_run(_request()))

    assert _git(FIXTURE, "rev-parse", "HEAD").strip() == before_head
    assert _git(FIXTURE, "status", "--porcelain") == before_status
    assert "return now <= session_expires_at" in (FIXTURE / "src/payment/session.py").read_text()


def test_worktrees_are_cleaned_up(tmp_path):
    settings = Settings(data_dir=tmp_path / "data")
    result = asyncio.run(Orchestrator(settings=settings, provider=_stub()).execute_run(_request()))
    worktrees = Path(result.artifact_dir) / "worktrees"
    assert not (worktrees / "baseline").exists()
    assert not (worktrees / "candidate").exists()


def test_generated_test_manifest_locked(tmp_path):
    import json

    settings = Settings(data_dir=tmp_path / "data")
    result = asyncio.run(Orchestrator(settings=settings, provider=_stub()).execute_run(_request()))
    manifest_path = Path(result.artifact_dir) / "generated_tests/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    assert manifest["algorithm"] == "sha256"
    assert manifest["files"]
    assert all(len(f["sha256"]) == 64 for f in manifest["files"])


def test_events_are_persisted(tmp_path):
    import json

    settings = Settings(data_dir=tmp_path / "data")
    result = asyncio.run(Orchestrator(settings=settings, provider=_stub()).execute_run(_request()))
    events = [
        json.loads(line)
        for line in (Path(result.artifact_dir) / "events.jsonl").read_text().splitlines()
        if line.strip()
    ]
    types = {e["type"] for e in events}
    assert {"run_created", "step_completed", "run_completed"} <= types
    sequences = [e["sequence"] for e in events]
    assert sequences == sorted(sequences)


class _TestEditingProvider:
    """Provider whose patch touches an existing test file (must be rejected)."""

    name = "stub"
    model = "stub"

    async def generate_structured(
        self, *, system_prompt, user_prompt, response_model, temperature=0.0, agent=""
    ):
        from proofpatch.domain import GeneratedTestBundle, GeneratedTestFile
        from proofpatch.domain import PatchProposal as PP
        from proofpatch.domain import RootCauseAnalysis as RC

        if response_model is RC:
            return RC(summary="boundary bug", suspected_files=["src/payment/session.py"])
        if response_model is PP:
            diff = (
                "--- a/tests/test_session.py\n"
                "+++ b/tests/test_session.py\n"
                "@@ -1,1 +1,1 @@\n"
                "-assert can_process_payment(EXPIRES, EXPIRES) is False\n"
                "+assert can_process_payment(EXPIRES, EXPIRES) is True\n"
            )
            return PP(summary="cheat", unified_diff=diff)
        return GeneratedTestBundle(
            files=[
                GeneratedTestFile(
                    relative_path=".proofpatch_generated_tests/t.py",
                    content="def test_a():\n    assert True\n",
                )
            ]
        )


def test_patch_touching_tests_is_rejected(tmp_path):
    settings = Settings(data_dir=tmp_path / "data")
    orchestrator = Orchestrator(settings=settings, provider=_TestEditingProvider())
    result = asyncio.run(orchestrator.execute_run(_request()))
    assert result.verdict == Verdict.REJECTED
    assert "safety policy" in (result.report.verification.verdict_reasons[0] or "")
    # The candidate was never patched, so nothing can be claimed as verified.
    assert result.score < 100


def test_dirty_repository_is_error(tmp_path, temp_dirty_git_repo):
    settings = Settings(data_dir=tmp_path / "data")
    request = RunRequest(
        repository=RepositoryInput(path=str(temp_dirty_git_repo)),
        issue=IssueInput(title="t", description="d"),
    )
    orchestrator = Orchestrator(settings=settings)
    result = asyncio.run(orchestrator.execute_run(request))
    assert result.verdict == Verdict.ERROR
    assert result.error and "uncommitted changes" in result.error

