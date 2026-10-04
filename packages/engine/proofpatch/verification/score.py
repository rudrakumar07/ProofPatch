"""Deterministic evidence scoring table.

Skipped checks contribute 0 and we do NOT renormalize to 100. The displayed
number is an *evidence score*, not a calibrated probability of correctness.
"""

from __future__ import annotations

WEIGHTS: dict[str, int] = {
    "issue_reproduced": 20,
    "candidate_resolves_repro": 20,
    "generated_differential": 25,
    "no_new_regressions": 20,
    "static_no_new_findings": 10,
    "patch_policy": 5,
}

TITLES: dict[str, str] = {
    "issue_reproduced": "Original issue reproduction established",
    "candidate_resolves_repro": "Candidate resolves explicit reproduction",
    "generated_differential": "Generated bug-specific differential evidence",
    "no_new_regressions": "Existing regression suite introduces no new failures",
    "static_no_new_findings": "Static/syntax verification introduces no new findings",
    "patch_policy": "Patch safety/size policy passes",
}

VERIFIED_MIN_SCORE = 80
TOTAL_POSSIBLE = sum(WEIGHTS.values())


def score_from_items(items) -> int:
    return sum(item.weight for item in items if item.status == "pass")


__all__ = ["TITLES", "TOTAL_POSSIBLE", "VERIFIED_MIN_SCORE", "WEIGHTS", "score_from_items"]
