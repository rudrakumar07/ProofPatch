"""Deterministic evidence engine.

This module -- not an LLM -- decides the score and the verdict. It consumes only
observed command/test outcomes. An LLM may propose a root cause, a patch, or
tests, but it can never set ``VERIFIED`` or award points directly.
"""

from __future__ import annotations

from ..domain import (
    CommandResult,
    EvidenceItem,
    PatchPolicyResult,
    StaticCheckResult,
    TestSuiteResult,
    Verdict,
    VerificationResult,
)
from .score import TITLES, TOTAL_POSSIBLE, VERIFIED_MIN_SCORE, WEIGHTS, score_from_items
from .static import new_findings


class EvidenceEngine:
    """Turns observed command/test outcomes into an evidence score and verdict."""

    def __init__(self, min_score: int = VERIFIED_MIN_SCORE) -> None:
        self.min_score = min_score

    def _item(
        self, key: str, status: str, details: str, refs: list[str] | None = None
    ) -> EvidenceItem:
        return EvidenceItem(
            key=key,
            title=TITLES[key],
            status=status,  # type: ignore[arg-type]
            weight=WEIGHTS[key],
            details=details,
            artifact_refs=refs or [],
        )

    def evaluate(
        self,
        *,
        baseline_repro: CommandResult | None,
        candidate_repro: CommandResult | None,
        baseline_generated: TestSuiteResult | None,
        candidate_generated: TestSuiteResult | None,
        baseline_tests: TestSuiteResult | None,
        candidate_tests: TestSuiteResult | None,
        baseline_static: list[StaticCheckResult] | None,
        candidate_static: list[StaticCheckResult] | None,
        patch_policy: PatchPolicyResult,
        limitations: list[str] | None = None,
    ) -> VerificationResult:
        baseline_static = baseline_static or []
        candidate_static = candidate_static or []
        notes: list[str] = list(limitations or [])
        evidence: list[EvidenceItem] = []

        # --- 1. Original issue reproduction ---------------------------------
        issue_reproduced: bool | None = None
        if baseline_repro is None:
            evidence.append(
                self._item(
                    "issue_reproduced",
                    "skip",
                    "No reproduction command was provided; issue reproduction not established.",
                )
            )
            notes.append("No explicit user-provided reproduction command was available.")
        elif baseline_repro.timed_out:
            evidence.append(
                self._item(
                    "issue_reproduced",
                    "skip",
                    "Baseline reproduction command timed out; reproduction is inconclusive.",
                )
            )
            notes.append("Baseline reproduction command timed out; reproduction status is inconclusive.")
        else:
            issue_reproduced = not baseline_repro.passed
            evidence.append(
                self._item(
                    "issue_reproduced",
                    "pass" if issue_reproduced else "fail",
                    f"Reproduction command exited {baseline_repro.exit_code} on baseline "
                    f"({'reproduced' if issue_reproduced else 'unexpectedly passed'}).",
                )
            )

        # --- 2. Candidate resolves the reproduction --------------------------
        repro_passes_on_candidate: bool | None = None
        if baseline_repro is None or candidate_repro is None:
            evidence.append(
                self._item(
                    "candidate_resolves_repro",
                    "skip",
                    "No reproduction command was available to resolve.",
                )
            )
        elif candidate_repro.timed_out:
            evidence.append(
                self._item(
                    "candidate_resolves_repro",
                    "skip",
                    "Candidate reproduction command timed out; result inconclusive.",
                )
            )
        else:
            repro_passes_on_candidate = candidate_repro.passed
            evidence.append(
                self._item(
                    "candidate_resolves_repro",
                    "pass" if repro_passes_on_candidate else "fail",
                    f"Reproduction command exited {candidate_repro.exit_code} on candidate "
                    f"({'passed' if repro_passes_on_candidate else 'still failing'}).",
                )
            )

        # --- 3. Generated bug-specific differential evidence -----------------
        base_gen_ran = (
            baseline_generated is not None
            and baseline_generated.ran
            and baseline_generated.total > 0
        )
        cand_gen_ran = (
            candidate_generated is not None
            and candidate_generated.ran
            and candidate_generated.total > 0
        )
        generated_differential = False
        generated_candidate_failures = False
        generated_tests_fail_on_baseline: bool | None = None
        generated_tests_pass_on_candidate: bool | None = None

        if not base_gen_ran or not cand_gen_ran:
            evidence.append(
                self._item(
                    "generated_differential",
                    "skip",
                    "Generated verification tests did not run on both revisions; "
                    "differential evidence is unavailable.",
                )
            )
            notes.append("Generated verification tests did not execute on both baseline and candidate.")
        else:
            baseline_failed = baseline_generated.failed_ids
            candidate_failed = candidate_generated.failed_ids
            fixed = baseline_failed - candidate_failed
            new_gen_failures = candidate_failed - baseline_failed
            generated_tests_fail_on_baseline = bool(baseline_failed)
            generated_tests_pass_on_candidate = not candidate_failed
            generated_differential = bool(fixed) and not new_gen_failures
            generated_candidate_failures = bool(candidate_failed)
            evidence.append(
                self._item(
                    "generated_differential",
                    "pass" if generated_differential else "fail",
                    f"Baseline generated failures: {len(baseline_failed)}; "
                    f"candidate generated failures: {len(candidate_failed)}; "
                    f"newly passing: {len(fixed)}; new failures: {len(new_gen_failures)}.",
                )
            )

        # --- 4. Existing regression suite -----------------------------------
        new_regressions: list[str] = []
        suite_ran = (
            baseline_tests is not None and baseline_tests.ran and baseline_tests.total > 0
        )
        if not suite_ran:
            evidence.append(
                self._item(
                    "no_new_regressions",
                    "skip",
                    "Existing test suite was not executed; regression comparison skipped.",
                )
            )
            notes.append("Existing test suite was not available; regression comparison was skipped.")
        else:
            base_fail = baseline_tests.failed_ids
            cand_fail = candidate_tests.failed_ids if candidate_tests else set()
            new_regressions = sorted(cand_fail - base_fail)
            evidence.append(
                self._item(
                    "no_new_regressions",
                    "pass" if not new_regressions else "fail",
                    f"Baseline failures: {len(base_fail)}; candidate failures: {len(cand_fail)}; "
                    f"new failures: {len(new_regressions)}.",
                )
            )
            if base_fail:
                notes.append(
                    f"{len(base_fail)} pre-existing baseline test failure(s) were present before the patch."
                )


        # --- 5. Static / syntax verification --------------------------------
        candidate_syntax_error = any(
            "compileall" in r.command and r.ran and r.exit_code not in (0, None)
            for r in candidate_static
        )
        static_ran = any(r.ran for r in baseline_static + candidate_static)
        static_new_findings: list[str] = []
        if not static_ran:
            evidence.append(
                self._item(
                    "static_no_new_findings",
                    "skip",
                    "No static/syntax analyzer was available; check skipped.",
                )
            )
            notes.append("No static analysis was executed.")
        else:
            base_find = [f for r in baseline_static for f in r.findings]
            cand_find = [f for r in candidate_static for f in r.findings]
            static_new_findings = new_findings(base_find, cand_find)
            if candidate_syntax_error:
                status = "fail"
                detail = "Candidate introduced a Python syntax error (compileall failed)."
            elif static_new_findings:
                status = "fail"
                detail = f"{len(static_new_findings)} new static finding(s) introduced by candidate."
            else:
                status = "pass"
                detail = "No new static/syntax findings introduced by the candidate."
            evidence.append(self._item("static_no_new_findings", status, detail))

        # --- 6. Patch safety/size policy ------------------------------------
        evidence.append(
            self._item(
                "patch_policy",
                "pass" if patch_policy.allowed else "fail",
                "Patch passed all safety and size guards."
                if patch_policy.allowed
                else "Patch violated safety policy: " + "; ".join(patch_policy.reasons),
            )
        )
        if patch_policy.warnings:
            notes.append("Patch warnings: " + "; ".join(patch_policy.warnings))


        # --- Score, gates, verdict ------------------------------------------
        score = score_from_items(evidence)

        repro_causal = issue_reproduced is True and repro_passes_on_candidate is True
        causal_signal = repro_causal or generated_differential

        gates = {
            "patch applied and safe": patch_policy.allowed,
            "no new existing-test regressions": suite_ran and not new_regressions,
            "no candidate syntax failure": not candidate_syntax_error,
            "causal bug-fix signal present": causal_signal,
            "evidence score >= minimum": score >= self.min_score,
        }

        reasons: list[str] = []
        if not patch_policy.allowed:
            verdict = Verdict.REJECTED
            reasons.append("Patch violated the safety policy: " + "; ".join(patch_policy.reasons))
        elif candidate_syntax_error:
            verdict = Verdict.REJECTED
            reasons.append("Candidate introduced a syntax error.")
        elif new_regressions:
            verdict = Verdict.REJECTED
            reasons.append(f"Candidate introduced {len(new_regressions)} new failing test(s).")
        elif issue_reproduced is True and repro_passes_on_candidate is False:
            verdict = Verdict.REJECTED
            reasons.append("Candidate did not resolve the explicit reproduction command.")
        elif base_gen_ran and cand_gen_ran and generated_candidate_failures:
            verdict = Verdict.REJECTED
            reasons.append("Generated verification tests still fail on the candidate.")
        elif all(gates.values()):
            verdict = Verdict.VERIFIED
            reasons.append(
                f"All mandatory gates passed with evidence score {score}/{TOTAL_POSSIBLE}."
            )
        else:
            verdict = Verdict.NEEDS_REVIEW
            failed = [k for k, v in gates.items() if not v]
            reasons.append("Evidence is incomplete: " + "; ".join(failed) + ".")

        return VerificationResult(
            issue_reproduced=issue_reproduced,
            generated_tests_fail_on_baseline=generated_tests_fail_on_baseline,
            generated_tests_pass_on_candidate=generated_tests_pass_on_candidate,
            repro_passes_on_candidate=repro_passes_on_candidate,
            new_regressions=new_regressions,
            static_new_findings=static_new_findings,
            evidence=evidence,
            score=score,
            verdict=verdict,
            verdict_reasons=reasons,
            limitations=notes,
        )


__all__ = ["EvidenceEngine"]

