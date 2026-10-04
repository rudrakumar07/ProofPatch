"""Report builder tests (Phase 14 exit criteria)."""

from proofpatch.domain import (
    CommandResult,
    PatchPolicyResult,
    ReproducibilityMetadata,
    Verdict,
    VerificationResult,
)
from proofpatch.report.builder import ReportBuilder
from proofpatch.report.templates import render_cli_summary, render_markdown
from proofpatch.verification.evidence import EvidenceEngine


def _verification():
    engine = EvidenceEngine()
    return engine.evaluate(
        baseline_repro=CommandResult(command="pytest", cwd="/t", exit_code=1),
        candidate_repro=CommandResult(command="pytest", cwd="/t", exit_code=0),
        baseline_generated=None,
        candidate_generated=None,
        baseline_tests=None,
        candidate_tests=None,
        baseline_static=None,
        candidate_static=None,
        patch_policy=PatchPolicyResult(allowed=True),
    )


def test_report_contains_every_section():
    report = ReportBuilder().build(
        run_id="pp_1",
        verification=_verification(),
        repository={"path": "/repo", "base_commit": "abc123"},
        issue={"title": "Payment bug"},
        reproducibility=ReproducibilityMetadata(),
    )
    markdown = render_markdown(report)
    for section in [
        "# ProofPatch Verification Report",
        "## Run Summary",
        "## Issue Evidence",
        "## Root Cause Analysis",
        "## Candidate Patch",
        "## Generated Verification Tests",
        "## Existing Regression Suite",
        "## Static / Syntax Verification",
        "## Evidence Checklist",
        "## Verdict",
        "## Limitations",
    ]:
        assert section in markdown


def test_skipped_checks_not_shown_as_pass():
    report = ReportBuilder().build(
        run_id="pp_2",
        verification=_verification(),
        reproducibility=ReproducibilityMetadata(),
    )
    markdown = render_markdown(report)
    assert "SKIP | 25" in markdown or "| SKIP | 25 |" in markdown
    assert "not evaluated" not in markdown.lower()  # normal path has real details


def test_verdict_reasons_present():
    report = ReportBuilder().build(
        run_id="pp_3",
        verification=_verification(),
        reproducibility=ReproducibilityMetadata(),
    )
    assert report.verification.verdict_reasons
    assert report.verdict_summary


def test_rejected_report_has_reasons():
    verification = VerificationResult(
        verdict=Verdict.REJECTED,
        score=40,
        verdict_reasons=["Candidate introduced 1 new failing test(s)."],
        limitations=["x"],
        evidence=[],
    )
    report = ReportBuilder().build(run_id="pp_4", verification=verification)
    markdown = render_markdown(report)
    assert "REJECTED" in markdown
    assert "Candidate introduced 1 new failing test(s)." in markdown


def test_cli_summary_has_score_and_verdict():
    report = ReportBuilder().build(
        run_id="pp_5",
        verification=_verification(),
        repository={"base_commit": "deadbeef"},
        issue={"title": "My bug"},
    )
    text = render_cli_summary(report, "/tmp/report.md")
    assert "Evidence score:" in text
    assert "Verdict:" in text
    assert "/tmp/report.md" in text
    assert "deadbeef" in text


def test_no_unsafe_claims():
    report = ReportBuilder().build(
        run_id="pp_6", verification=_verification(), reproducibility=ReproducibilityMetadata()
    )
    markdown = render_markdown(report).lower()
    for banned in ["safe to deploy", "production ready", "guaranteed", "definitely correct"]:
        assert banned not in markdown
