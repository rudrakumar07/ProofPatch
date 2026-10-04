"""LLM provider abstraction.

ProofPatch v0.1 has exactly one LLM integration: the Cline SDK
(:mod:`proofpatch.llm.cline_sdk`). This module keeps the provider-neutral seam,
the shared call-record type, and the JSON extraction helper so the agents do not
depend on how the model is reached.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from datetime import datetime
from typing import Protocol, TypeVar

from pydantic import BaseModel, Field

from ..domain import utcnow

T = TypeVar("T", bound=BaseModel)

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


class LLMCallRecord(BaseModel):
    agent: str = ""
    model: str = ""
    timestamp: datetime = Field(default_factory=utcnow)
    prompt_hash: str = ""
    response_hash: str = ""
    latency_ms: int = 0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    validation: str = "ok"
    attempt: int = 1


CallRecorder = Callable[[LLMCallRecord], None]


def _hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def extract_json(text: str) -> str:
    """Pull a JSON object out of a model response (handles code fences)."""

    text = (text or "").strip()
    match = _FENCE_RE.search(text)
    if match:
        text = match.group(1).strip()
    if text.startswith(("{", "[")):
        return text
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


class LLMProvider(Protocol):
    name: str
    model: str

    async def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: type[T],
        temperature: float = 0.0,
        agent: str = "",
    ) -> T: ...


class LLMError(Exception):
    """Raised when a provider cannot produce a valid structured response."""


__all__ = [
    "LLMProvider",
    "LLMCallRecord",
    "LLMError",
    "extract_json",
    "CallRecorder",
]
