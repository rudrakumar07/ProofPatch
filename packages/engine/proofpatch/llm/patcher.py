"""Patch agent: propose the smallest reasonable patch."""

from __future__ import annotations

from ..domain import IssueInput, PatchProposal, RootCauseAnalysis
from ..repo.context import RepoContext
from .prompts import PATCHER_SYSTEM, patcher_user_prompt
from .provider import LLMProvider


class PatchAgent:
    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider

    async def generate(
        self,
        *,
        issue: IssueInput,
        root_cause: RootCauseAnalysis,
        context: RepoContext,
        max_files: int = 8,
        max_lines: int = 400,
        feedback: str | None = None,
    ) -> PatchProposal:
        return await self.provider.generate_structured(
            system_prompt=PATCHER_SYSTEM,
            user_prompt=patcher_user_prompt(
                issue, root_cause.model_dump_json(indent=2), context, max_files, max_lines, feedback
            ),
            response_model=PatchProposal,
            temperature=0.0,
            agent="patcher",
        )


__all__ = ["PatchAgent"]
