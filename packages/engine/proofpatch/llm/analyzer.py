"""Analyzer agent: produce a compact, inspectable root-cause hypothesis."""

from __future__ import annotations

from ..domain import IssueInput, RootCauseAnalysis
from ..repo.context import RepoContext
from .prompts import ANALYZER_SYSTEM, analyzer_user_prompt
from .provider import LLMError, LLMProvider

_VERDICT_WORDS = ("VERIFIED", "REJECTED", "NEEDS_REVIEW", "NEEDS REVIEW")


class AnalyzerAgent:
    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider

    async def analyze(self, issue: IssueInput, context: RepoContext) -> RootCauseAnalysis:
        result = await self.provider.generate_structured(
            system_prompt=ANALYZER_SYSTEM,
            user_prompt=analyzer_user_prompt(issue, context),
            response_model=RootCauseAnalysis,
            temperature=0.0,
            agent="analyzer",
        )
        self._guard(result)
        return result

    @staticmethod
    def _guard(result: RootCauseAnalysis) -> None:
        blob = " ".join([result.summary, *result.reasoning_summary, *result.test_plan])
        if "diff --git" in blob or "+++ b/" in blob or "@@ " in blob:
            raise LLMError("Analyzer output contained a unified diff; rejecting as out of scope.")
        if any(word in blob for word in _VERDICT_WORDS):
            raise LLMError("Analyzer output attempted to set a verification verdict; rejecting.")


__all__ = ["AnalyzerAgent"]
