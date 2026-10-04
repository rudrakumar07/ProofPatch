"""Evidence engine tests: table-driven scenarios (Phase 11 exit criteria)."""

import pytest
from proofpatch.domain import (
    CommandResult,
    PatchPolicyResult,
    StaticCheckResult,
    TestOutcome,
    TestSuiteResult,
    Verdict,
)
from proofpatch.verification.evidence import EvidenceEngine
from proofpatch.verification.score import TOTAL_POSSIBLE, WEIGHTS


def cr(exit_code, timed_out=False):
    return CommandResult(command="pytest", cwd="/tmp", exit_code=exit_code, timed_out=timed_out)


def suite(failed_ids=(), passed_ids=(), ran=True, total=None):
    outcomes = [
        TestOutcome(test_id=tid, outcome="passed") for tid in passed_ids
    ] + [
        TestOutcome(test_id=tid, outcome="failed", message="boom") for tid in failed_ids
    ]
    if total is None:
        total = len(outcomes)
    return TestSuiteResult(
        command="pytest", ran=ran, total=total, passed=len(passed_ids), failed=len(failed_ids), outcomes=outcomes
    )


def static(findings=(), command="python -m compileall -q .", ran=True, exit_code=0):
    return StaticCheckResult(
        command=command, ran=ran, exit_code=exit_code, findings=list(findings)
    )


def evaluate(**overrides):
    defaults = dict(
        baseline_repro=cr(1),
        candidate_repro=cr(0),
        baseline_generated=suite(failed_ids=["t::bug"]),
        candidate_generated=suite(passed_ids=["t::bug"]),
        baseline_tests=suite(passed_ids=["a", "b"]),
        candidate_tests=suite(passed_ids=["a", "b"]),
        baseline_static=[static()],
        candidate_static=[static()],
        patch_policy=PatchPolicyResult(allowed=True),
    )
    defaults.update(overrides)
    return EvidenceEngine().evaluate(**defaults)


def test_full_verified_case():
    result = evaluate()
    assert result.verdict == Verdict.VERIFIED
    assert result.score == TOTAL_POSSIBLE
    assert all(item.status == "pass" for item in result.evidence)


def test_candidate_regression_is_rejected():
    result = evaluate(candidate_tests=suite(passed_ids=["a"], failed_ids=["b"]))
    assert result.verdict == Verdict.REJECTED
    assert result.new_regressions == ["b"]


def test_static_skipped_reduces_score():
    result = evaluate(baseline_static=[static(ran=False)], candidate_static=[static(ran=False)])
    item = next(i for i in result.evidence if i.key == "static_no_new_findings")
    assert item.status == "skip"
    assert result.score == TOTAL_POSSIBLE - WEIGHTS["static_no_new_findings"]
    assert result.verdict == Verdict.VERIFIED  # skipped static alone does not block


def test_generated_passing_both_gets_no_differential_credit():
    result = evaluate(
        baseline_generated=suite(passed_ids=["t::bug"]),
        candidate_generated=suite(passed_ids=["t::bug"]),
        baseline_repro=None,
        candidate_repro=None,
    )
    item = next(i for i in result.evidence if i.key == "generated_differential")
    assert item.status == "fail"
    assert result.verdict == Verdict.NEEDS_REVIEW


def test_syntax_failure_rejected():
    result = evaluate(candidate_static=[static(exit_code=1, findings=["SyntaxError at x"])])
    assert result.verdict == Verdict.REJECTED


def test_new_static_findings_lower_score():
    result = evaluate(candidate_static=[static(findings=["E501|f.py|1|too long"])])
    item = next(i for i in result.evidence if i.key == "static_no_new_findings")
    assert item.status == "fail"
    assert result.score == TOTAL_POSSIBLE - WEIGHTS["static_no_new_findings"]


def test_patch_policy_violation_rejected():
    result = evaluate(patch_policy=PatchPolicyResult(allowed=False, reasons=["too many files"]))
    assert result.verdict == Verdict.REJECTED
    assert any("safety policy" in r for r in result.verdict_reasons)


def test_candidate_repro_still_failing_rejected():
    result = evaluate(candidate_repro=cr(1))
    assert result.verdict == Verdict.REJECTED
    assert result.repro_passes_on_candidate is False


def test_generated_test_still_failing_rejected():
    result = evaluate(
        candidate_generated=suite(failed_ids=["t::bug"], passed_ids=["t::edge"]),
        baseline_tests=suite(passed_ids=["a", "b"]),
        candidate_tests=suite(passed_ids=["a", "b"]),
    )
    assert result.verdict == Verdict.REJECTED


def test_missing_repro_caps_at_needs_review():
    # No repro command loses the two repro weights (40), so the score can no
    # longer reach the >= 80 mandatory gate even though differential evidence exists.
    result = evaluate(baseline_repro=None, candidate_repro=None)
    assert result.verdict == Verdict.NEEDS_REVIEW


def test_no_suite_reports_skipped_not_passed():
    result = evaluate(baseline_tests=None, candidate_tests=None)
    item = next(i for i in result.evidence if i.key == "no_new_regressions")
    assert item.status == "skip"
    assert result.verdict == Verdict.NEEDS_REVIEW
    assert any("not available" in n for n in result.limitations)


def test_baseline_repro_unexpectedly_passing_caps_at_needs_review():
    result = evaluate(
        baseline_repro=cr(0),
        candidate_repro=cr(0),
        baseline_generated=suite(passed_ids=["t::bug"]),
        candidate_generated=suite(passed_ids=["t::bug"]),
    )
    assert result.verdict == Verdict.NEEDS_REVIEW
    assert result.issue_reproduced is False


def test_timed_out_repro_is_inconclusive():
    result = evaluate(baseline_repro=cr(None, timed_out=True), candidate_repro=cr(None, timed_out=True))
    item = next(i for i in result.evidence if i.key == "issue_reproduced")
    assert item.status == "skip"


@pytest.mark.parametrize("key", list(WEIGHTS))
def test_every_weight_has_an_evidence_item(key):
    result = evaluate()
    assert any(item.key == key for item in result.evidence)


def test_score_never_exceeds_total():
    assert TOTAL_POSSIBLE == 100
    result = evaluate()
    assert result.score <= TOTAL_POSSIBLE
