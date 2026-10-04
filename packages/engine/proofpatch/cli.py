"""ProofPatch command-line interface.

The CLI is the primary integration point for Cline or any terminal-centric AI
coding workflow. It streams events as they occur and returns meaningful exit
codes so other agents can make decisions without parsing English text.

Exit codes: 0 = VERIFIED, 2 = NEEDS_REVIEW, 3 = REJECTED, 4 = ERROR.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import typer

from .artifacts import ArtifactStore
from .config import Settings
from .domain import (
    IssueInput,
    RepositoryInput,
    RunRequest,
    Verdict,
    VerificationOptions,
)
from .events import RunEventModel
from .orchestrator import Orchestrator
from .report.templates import render_cli_summary

app = typer.Typer(
    name="proofpatch",
    help="Evidence-backed verification for AI-generated patches.",
    add_completion=False,
)

EXIT_CODES = {
    Verdict.VERIFIED: 0,
    Verdict.NEEDS_REVIEW: 2,
    Verdict.REJECTED: 3,
    Verdict.ERROR: 4,
}

_HEAD_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)


def _load_issue(
    issue: Path | None,
    issue_text: str | None,
    issue_title: str | None,
    repro: str | None,
) -> IssueInput:
    title = issue_title or "Reported issue"
    description = issue_text or ""

    if issue is not None:
        if not issue.exists():
            typer.echo(f"Error: issue file not found: {issue}", err=True)
            raise typer.Exit(4)
        raw = issue.read_text(encoding="utf-8")
        description = raw
        if issue_title is None:
            match = _HEAD_RE.search(raw)
            title = match.group(1).strip() if match else issue.stem

    if not description:
        description = issue_text or ""
    return IssueInput(title=title, description=description, repro_command=repro)


@app.command("verify")
def verify(
    repo: Path = typer.Option(..., "--repo", help="Path to a local Git repository."),
    issue: Path | None = typer.Option(
        None, "--issue", help="Path to a bug report file (e.g. bug.md)."
    ),
    issue_text: str | None = typer.Option(
        None, "--issue-text", help="Inline issue description."
    ),
    issue_title: str | None = typer.Option(None, "--issue-title", help="Inline issue title."),
    repro: str | None = typer.Option(
        None, "--repro", help="Reproduction command expected to fail on the baseline."
    ),
    full_test: str | None = typer.Option(
        None, "--full-test", help="Full existing-test command (defaults to detection)."
    ),
    timeout: int = typer.Option(120, "--timeout", help="Per-command timeout in seconds."),
    keep_worktrees: bool = typer.Option(
        False, "--keep-worktrees", help="Keep baseline/candidate worktrees for inspection."
    ),
    data_dir: Path | None = typer.Option(
        None, "--data-dir", help="Artifact directory (default .proofpatch)."
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit final JSON to stdout."),
) -> None:
    """Run the full ProofPatch verification pipeline."""

    if not issue and not issue_text:
        typer.echo("Error: provide --issue or --issue-text.", err=True)
        raise typer.Exit(4)

    overrides = {}
    if keep_worktrees:
        overrides["keep_worktrees"] = True
    if data_dir:
        overrides["data_dir"] = data_dir
    settings = Settings(**overrides)

    problems = settings.validate_for_run()
    if problems:
        for problem in problems:
            typer.echo(f"Configuration error: {problem}", err=True)
        raise typer.Exit(4)

    issue_input = _load_issue(issue, issue_text, issue_title, repro)
    request = RunRequest(
        repository=RepositoryInput(path=str(repo)),
        issue=issue_input,
        verification=VerificationOptions(
            full_test_command=full_test,
            timeout_seconds=timeout,
        ),
    )

    quiet = json_output

    def listener(event: RunEventModel) -> None:
        if quiet:
            return
        if event.type == "run_status_changed":
            typer.echo(f"  → status: {event.message}")
        elif event.type == "step_completed":
            marker = {"PASSED": "✓", "FAILED": "✗", "SKIPPED": "–"}.get(
                event.status or "", "·"
            )
            typer.echo(f"  {marker} {event.message}")
        elif event.type in ("run_error", "warning"):
            typer.echo(f"  ! {event.message}", err=True)

    orchestrator = Orchestrator(settings=settings, listener=listener)
    try:
        result = asyncio.run(orchestrator.execute_run(request))
    except KeyboardInterrupt:  # pragma: no cover
        typer.echo("Interrupted.", err=True)
        raise typer.Exit(4) from None

    report_path = str(Path(result.artifact_dir) / "report.md")
    if json_output:
        payload = {
            "run_id": result.run_id,
            "status": result.status.value,
            "verdict": result.verdict.value,
            "score": result.score,
            "artifact_dir": result.artifact_dir,
            "report_markdown": result.report_markdown,
        }
        typer.echo(json.dumps(payload, indent=2))
    else:
        if result.report is not None:
            typer.echo("")
            typer.echo(render_cli_summary(result.report, report_path))

    raise typer.Exit(EXIT_CODES.get(result.verdict, 4))


@app.command("doctor")
def doctor() -> None:
    """Check that the Cline SDK provider is configured and reachable."""

    from .llm.cline_sdk import ClineSDKProvider

    settings = Settings()
    try:
        provider = ClineSDKProvider(
            provider_id=settings.cline_provider_id,
            model_id=settings.cline_model_id or None,
            api_key=settings.cline_api_key or None,
            base_url=settings.cline_base_url or None,
            node_bin=settings.cline_node_bin or None,
            bridge_dir=settings.cline_bridge_dir or None,
            timeout_seconds=settings.cline_timeout_seconds,
        )
    except Exception as exc:  # misconfiguration is the message
        typer.echo(f"Cline SDK provider is NOT ready: {exc}", err=True)
        raise typer.Exit(4) from None

    problems = settings.validate_for_run() + provider.preflight()
    if problems:
        for problem in problems:
            typer.echo(f"Cline SDK provider is NOT ready: {problem}", err=True)
        raise typer.Exit(4)
    typer.echo(
        f"Cline SDK provider ready: providerId={provider.provider_id} model={provider.model_id}"
    )


@app.command("cleanup")
def cleanup(
    repo: Path = typer.Option(..., "--repo", help="Repository to clean orphaned worktrees from."),
) -> None:
    """Remove ProofPatch worktrees left behind by an interrupted run.

    Only worktrees registered under a ProofPatch ``.proofpatch/runs/`` directory
    are removed; unrelated developer worktrees are never touched.
    """

    from .repo.manager import RepositoryManager, cleanup_proofpatch_worktrees

    if not RepositoryManager.is_git_repository(repo):
        typer.echo(f"Not a Git repository: {repo}", err=True)
        raise typer.Exit(4)
    removed = cleanup_proofpatch_worktrees(Path(repo))
    if removed:
        for path in removed:
            typer.echo(f"removed {path}")
    else:
        typer.echo("No orphaned ProofPatch worktrees found.")


@app.command("report")
def show_report(
    run_id: str = typer.Option(..., "--run", help="Run id, e.g. pp_01J..."),
    data_dir: Path | None = typer.Option(None, "--data-dir", help="Artifact directory."),
    json_output: bool = typer.Option(False, "--json", help="Emit the JSON report instead."),
) -> None:
    """Print the stored Proof Report for a previous run."""

    settings = Settings(**({"data_dir": data_dir} if data_dir else {}))
    store = ArtifactStore.for_existing(settings.data_dir, run_id)
    if not store.exists("report.md"):
        typer.echo(f"Error: no report found for run {run_id}", err=True)
        raise typer.Exit(4)
    if json_output:
        typer.echo(store.read_text("report.json"))
    else:
        typer.echo(store.read_text("report.md"))


def main() -> None:
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
