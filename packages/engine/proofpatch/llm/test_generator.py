"""Test generation agent: independent, black-box verification tests.

The generator never sees the candidate patch. It receives the issue, the root
cause, public interfaces, and existing test patterns only.
"""

from __future__ import annotations

from ..domain import GeneratedTestBundle, IssueInput, RootCauseAnalysis
from ..repo.context import RepoContext
from .prompts import TESTGEN_SYSTEM, testgen_user_prompt
from .provider import LLMProvider

GENERATED_DIR = ".proofpatch_generated_tests"


class GeneratedTestError(Exception):
    pass


class TestGeneratorAgent:
    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider

    async def generate(
        self,
        *,
        issue: IssueInput,
        root_cause: RootCauseAnalysis,
        context: RepoContext,
    ) -> GeneratedTestBundle:
        bundle = await self.provider.generate_structured(
            system_prompt=TESTGEN_SYSTEM,
            user_prompt=testgen_user_prompt(issue, root_cause.model_dump_json(indent=2), context),
            response_model=GeneratedTestBundle,
            temperature=0.0,
            agent="test_generator",
        )
        validate_bundle(bundle)
        return bundle


def validate_bundle(bundle: GeneratedTestBundle) -> None:
    """Reject generated tests outside the ProofPatch-owned directory or with bad syntax."""

    if not bundle.files:
        raise GeneratedTestError("Test generator returned no files.")
    for item in bundle.files:
        path = item.relative_path.replace("\\", "/")
        if not path.startswith(GENERATED_DIR + "/"):
            raise GeneratedTestError(
                f"Generated test path must live under {GENERATED_DIR}/: {item.relative_path}"
            )
        if not path.endswith(".py"):
            raise GeneratedTestError(f"Generated test is not a Python file: {item.relative_path}")
        if ".." in path.split("/"):
            raise GeneratedTestError(f"Generated test path traversal rejected: {item.relative_path}")
        try:
            compile(item.content, item.relative_path, "exec")
        except SyntaxError as exc:
            raise GeneratedTestError(
                f"Generated test has a syntax error ({item.relative_path}): {exc}"
            ) from exc


__all__ = ["GENERATED_DIR", "GeneratedTestError", "TestGeneratorAgent", "validate_bundle"]
