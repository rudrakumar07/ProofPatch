"""Markdown / CLI rendering for the Proof report.

The Markdown structure mirrors section 24 of the implementation plan so a
developer can read ``report.md`` without the web UI and understand exactly why
the patch received its verdict.
"""

from __future__ import annotations

from .builder import ProofReport

_STATUS_MARK = {
    "pass": "PASS",
    "fail": "FAIL",
    "skip": "SKIP",
    "error": "ERROR",
}


def _kv(label: str, value) -> str:
    return f"- **{label}:** {value if value not in (None, '') else '—'}"


def render_markdown(report: ProofReport) -> str:
    v = report.verification
    repo = report.repository or {}
    issue = report.issue or {}
    lines: list[str] = []

    lines.append("# ProofPatch Verification Report\n")
    lines.append("## Run Summary\n")
    lines.append(_kv("Run ID", report.run_id))
    lines.append(_kv("Repository", repo.get("path")))
    lines.append(_kv("Base commit", repo.get("base_commit")))
    lines.append(_kv("Branch (not modified)", repo.get("branch")))
    lines.append(_kv("Issue", issue.get("title")))
    lines.append(_kv("Started", report.started_at))
    lines.append(_kv("Completed", report.completed_at))
    lines.append(_kv("Verdict", report.verdict))
    lines.append(_kv("Evidence score", f"{report.evidence_score} / 100"))
    lines.append("")

    ie = report.issue_evidence or {}
    lines.append("## Issue Evidence\n")
    lines.append(_kv("Reproduction command", ie.get("repro_command")))
    lines.append(_kv("Baseline result", ie.get("baseline_result")))
    lines.append(_kv("Candidate result", ie.get("candidate_result")))
    lines.append(_kv("Issue reproduced", v.issue_reproduced))
    lines.append("")

    rc = report.root_cause
    lines.append("## Root Cause Analysis\n")
    if rc:
        lines.append(_kv("Summary", rc.get("summary")))
        lines.append(_kv("Confidence", rc.get("confidence")))
        lines.append(_kv("Suspected files", ", ".join(rc.get("suspected_files") or []) or "—"))
        lines.append(_kv("Relevant symbols", ", ".join(rc.get("relevant_symbols") or []) or "—"))
        reasoning = rc.get("reasoning_summary") or []
        if reasoning:
            lines.append("- **Reasoning:**")
            lines.extend(f"  - {item}" for item in reasoning)
        uncertainties = rc.get("uncertainties") or []
        if uncertainties:
            lines.append("- **Uncertainties:**")
            lines.extend(f"  - {item}" for item in uncertainties)
    else:
        lines.append("_No root-cause analysis was produced._")
    lines.append("")

    patch = report.patch
    lines.append("## Candidate Patch\n")
    if patch:
        lines.append(_kv("Summary", patch.get("summary")))
        lines.append(_kv("Why it should work", patch.get("why_it_should_work")))
        lines.append(_kv("Files changed", ", ".join(patch.get("affected_files") or []) or "—"))
        risks = patch.get("risks") or []
        lines.append(_kv("Risk notes", "; ".join(risks) if risks else "—"))
        lines.append(_kv("Diff artifact", patch.get("diff_artifact")))
        if patch.get("unified_diff"):
            lines.append("\n```diff\n" + patch["unified_diff"].rstrip() + "\n```")
    else:
        lines.append("_No patch was produced._")
    lines.append("")

    gen = report.generated_tests
    lines.append("## Generated Verification Tests\n")
    if gen:
        lines.append(_kv("Scenarios", "; ".join(gen.get("scenarios") or []) or "—"))
        lines.append(_kv("Test files", ", ".join(gen.get("files") or []) or "—"))
        lines.append(_kv("Manifest digest", gen.get("manifest_digest")))
        lines.append(_kv("Baseline outcomes", gen.get("baseline_outcomes")))
        lines.append(_kv("Candidate outcomes", gen.get("candidate_outcomes")))
        assumptions = gen.get("assumptions") or []
        lines.append(_kv("Assumptions", "; ".join(assumptions) if assumptions else "—"))
    else:
        lines.append("_No generated verification tests._")
    lines.append("")

    reg = report.regression or {}
    lines.append("## Existing Regression Suite\n")
    lines.append(_kv("Baseline failures", reg.get("baseline_failures", "—")))
    lines.append(_kv("Candidate failures", reg.get("candidate_failures", "—")))
    lines.append(_kv("New regressions", reg.get("new_regressions") or "none"))
    lines.append("")

    stat = report.static or {}
    lines.append("## Static / Syntax Verification\n")
    lines.append(_kv("Baseline findings", stat.get("baseline_findings", 0)))
    lines.append(_kv("Candidate findings", stat.get("candidate_findings", 0)))
    lines.append(_kv("New findings", stat.get("new_findings") or "none"))
    lines.append("")

    lines.append("## Evidence Checklist\n")
    lines.append("| Check | Status | Weight | Details |")
    lines.append("|---|---|---:|---|")
    for item in v.evidence:
        mark = _STATUS_MARK.get(item.status, item.status)
        lines.append(f"| {item.title} | {mark} | {item.weight} | {item.details} |")
    lines.append("")

    lines.append("## Verdict\n")
    lines.append(f"- **{report.verdict}** — {report.verdict_summary}")
    for reason in v.verdict_reasons:
        lines.append(f"- {reason}")
    lines.append("")

    lines.append("## Limitations\n")
    if report.limitations:
        lines.extend(f"- {item}" for item in report.limitations)
    else:
        lines.append("- None recorded.")
    lines.append("")
    lines.append(
        "> ProofPatch reports *evidence*, not proof of correctness. "
        "The evidence score is not a calibrated probability."
    )
    return "\n".join(lines) + "\n"


_CLI_MARK = {"pass": "✓", "fail": "✗", "skip": "–", "error": "!"}


def render_cli_summary(report: ProofReport, report_path: str | None = None) -> str:
    """Compact terminal summary shown by the CLI and the API log tail."""

    repo = report.repository or {}
    issue = report.issue or {}
    v = report.verification

    lines = [
        "[ProofPatch]",
        f"Run: {report.run_id}",
        f"Base commit: {repo.get('base_commit') or '—'}",
        f"Issue: {issue.get('title') or '—'}",
        "",
    ]
    for item in v.evidence:
        lines.append(f"{_CLI_MARK.get(item.status, '?')} {item.title}")
    lines.append("")
    lines.append(f"Evidence score: {report.evidence_score} / 100")
    lines.append(f"Verdict: {report.verdict} — {report.verdict_summary}")
    if report_path:
        lines.append(f"Report: {report_path}")
    return "\n".join(lines)


__all__ = ["render_cli_summary", "render_markdown"]

