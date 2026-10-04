"""Versioned prompt templates for the ProofPatch agents.

Every prompt carries a version string that is recorded in run artifacts so a
report can be reproduced. Keep the templates here; do not bury prompts in the
agent modules.
"""

from __future__ import annotations

from ..domain import IssueInput
from ..repo.context import RepoContext

PROMPT_VERSIONS = {
    "analyzer": "proofpatch-analyzer-v1",
    "patcher": "proofpatch-patcher-v1",
    "test_generator": "proofpatch-testgen-v1",
}

ANALYZER_SYSTEM = """You are the root-cause analysis component of ProofPatch.
Your job is to inspect the supplied issue, error output, repository tree, and
selected files, then produce a concise root-cause hypothesis.

You must reply with ONE JSON object containing EXACTLY these keys (no other
keys, no prose, no markdown):
- "summary": the likely source of failure in one or two sentences.
- "suspected_files": repository-relative file paths most likely responsible.
- "relevant_symbols": function/class names relevant to the hypothesis.
- "reasoning_summary": a short user-facing rationale, as a list of bullet strings.
- "test_plan": a list of test scenarios that would distinguish the bug from the
  expected behavior.
- "confidence": one of "low", "medium" or "high".
- "uncertainties": a list of uncertainty notes (use [] when there are none).

Do not propose a code diff.
Do not claim that a hypothesis is proven.
Separate observed facts from assumptions.
Reference repository-relative file paths and symbols.
Output only the requested JSON object."""

PATCHER_SYSTEM = """You are the patch-generation component of ProofPatch.
Generate the smallest code change that addresses the supplied issue and
root-cause hypothesis.

You must reply with ONE JSON object containing EXACTLY these keys (no other
keys, no prose, no markdown):
- "summary": one short sentence describing the fix.
- "why_it_should_work": two or three sentences explaining why this change fixes
  the reported bug and nothing else.
- "affected_files": the list of repository-relative file paths touched by the diff.
- "unified_diff": the complete unified diff. Use "a/<path>" and "b/<path>"
  headers and valid @@ hunk headers; include 3 lines of context. The diff must
  apply cleanly with `git apply`.
- "risks": a list of short risk notes (use [] when there is nothing notable).

CRITICAL - the diff must match the file exactly:
- Every context line, function signature, parameter name, and identifier in the
  diff MUST be copied verbatim, character for character, from the RELEVANT FILES
  section. Do not rename parameters, reformat code, re-indent, or summarise.
- The "@@" hunk header line numbers MUST correspond to the real line numbers in
  the provided file contents.
- Only the removal/insertion lines may differ from the original file.
- A diff whose context does not match the file will fail `git apply` and the
  whole patch will be rejected.

Constraints:
- Only change source files needed to fix the reported issue. Never touch tests.
- Do not edit .git, .proofpatch, generated verification tests, lock files,
  vendored dependencies, or unrelated files.
- Do not disable tests, delete assertions, broadly catch exceptions, or
  suppress errors merely to make tests pass.
- Do not change public behavior outside the described issue unless required.
- Output only the requested JSON object."""

TESTGEN_SYSTEM = """You are the verification test generation component of ProofPatch.
Generate independent, black-box tests that encode the behavior described by the
bug report and its likely edge cases.

You must reply with ONE JSON object containing EXACTLY these keys (no other
keys, no prose, no markdown):
- "files": a list of objects with keys "relative_path", "content", and
  "purpose". Every "relative_path" MUST start with ".proofpatch_generated_tests/"
  and end with ".py". The "content" must be complete, runnable pytest files.
- "scenarios": the list of behavior scenarios covered.
- "assumptions": the list of assumptions the tests rely on.

You are NOT shown the candidate patch. Do not mirror any specific implementation.
Generate 2-5 tests. At least one must specifically reproduce the reported bug.
Prefer behavior over implementation-detail assertions.
Do not modify existing tests.
Output only the requested JSON object."""


def _issue_block(issue: IssueInput) -> str:
    return (
        "ISSUE\n"
        f"Title: {issue.title}\n"
        "Description:\n"
        f"{issue.description or '(none provided)'}\n\n"
        "Expected behavior:\n"
        f"{issue.expected_behavior or '(none provided)'}\n\n"
        "Error / stack trace:\n"
        f"{issue.error_log or '(none provided)'}\n\n"
        "Reproduction command:\n"
        f"{issue.repro_command or '(none provided)'}\n"
    )


def _files_block(context: RepoContext) -> str:
    parts: list[str] = []
    for item in context.files:
        parts.append(f"--- {item.path} --- (reason: {item.reason})\n{item.content}\n")
    return "\n".join(parts) if parts else "(no files selected)\n"


def analyzer_user_prompt(issue: IssueInput, context: RepoContext) -> str:
    return (
        _issue_block(issue)
        + "\nREPOSITORY TREE\n"
        + (context.tree or "(empty)")
        + "\n\nSELECTED FILES\n"
        + _files_block(context)
        + "\nProduce the required RootCauseAnalysis JSON."
    )


def patcher_user_prompt(
    issue: IssueInput,
    root_cause_json: str,
    context: RepoContext,
    max_files: int,
    max_lines: int,
    feedback: str | None = None,
) -> str:
    prompt = (
        _issue_block(issue)
        + "\nROOT CAUSE HYPOTHESIS\n"
        + root_cause_json
        + "\n\nRELEVANT FILES\n"
        + _files_block(context)
        + "\nPATCH POLICY\n"
        + f"- max files: {max_files}\n"
        + f"- max changed lines: {max_lines}\n"
        + "- no existing test modification\n"
        + "- no generated-test modification\n"
        + "- no unrelated refactor\n"
        + "\nReturn PatchProposal JSON with a valid unified diff."
    )
    if feedback:
        prompt += (
            "\n\nThe previous patch could not be applied. Fix it using this feedback:\n"
            + feedback
            + "\nReturn the corrected PatchProposal JSON."
        )
    return prompt


def testgen_user_prompt(
    issue: IssueInput,
    root_cause_json: str,
    context: RepoContext,
) -> str:
    return (
        _issue_block(issue)
        + "\nROOT CAUSE HYPOTHESIS\n"
        + root_cause_json
        + "\n\nPUBLIC/RELEVANT SOURCE CONTEXT\n"
        + _files_block(context)
        + "\nGenerate 2-5 verification tests.\n"
        + "At least one should specifically reproduce the reported bug.\n"
        + "Prefer black-box behavior over implementation-detail assertions.\n"
        + "Do not modify existing tests.\n"
        + "Place every generated file under .proofpatch_generated_tests/.\n"
        + "Return GeneratedTestBundle JSON."
    )


__all__ = [
    "ANALYZER_SYSTEM",
    "PATCHER_SYSTEM",
    "PROMPT_VERSIONS",
    "TESTGEN_SYSTEM",
    "analyzer_user_prompt",
    "patcher_user_prompt",
    "testgen_user_prompt",
]
