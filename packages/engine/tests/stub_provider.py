"""Deterministic test-double LLM provider.

This is test scaffolding only: unit/integration tests inject a stub through the
``Orchestrator(provider=...)`` seam so they run offline. The product itself only
ever uses the Cline SDK provider. It answers the fixture bug with a correct
root cause, patch, and test bundle.
"""

from __future__ import annotations

import difflib
from pathlib import Path

from proofpatch.domain import GeneratedTestBundle, PatchProposal, RootCauseAnalysis
from proofpatch.llm.provider import LLMCallRecord, LLMError, _hash

FAKE_ROOT_CAUSE = {
    "summary": "The expiry boundary uses '<=', so equality is incorrectly treated as valid.",
    "suspected_files": ["src/payment/session.py"],
    "relevant_symbols": ["can_process_payment"],
    "reasoning_summary": [
        "The bug occurs exactly at the expiry timestamp.",
        "The session validity condition includes equality (now <= expires_at).",
        "Product semantics require the session to be expired once now reaches expires_at.",
    ],
    "test_plan": [
        "Verify before expiry is allowed.",
        "Verify exact expiry is rejected.",
        "Verify after expiry is rejected.",
    ],
    "confidence": "high",
    "uncertainties": [],
}

FAKE_PATCH_FALLBACK = (
    "--- a/src/payment/session.py\n"
    "+++ b/src/payment/session.py\n"
    "@@ -17,7 +17,7 @@\n"
    "     Once ``now`` reaches ``session_expires_at`` the session is expired.\n"
    '     """\n'
    " \n"
    "-    return now <= session_expires_at\n"
    "+    return now < session_expires_at\n"
    " \n"
    " \n"
    " @dataclass(frozen=True)\n"
)

FAKE_PATCH_META = {
    "summary": "Treat the exact expiry instant as expired by using a strict comparison.",
    "why_it_should_work": (
        "The bug is a boundary condition: 'now <= expires_at' accepts a payment "
        "exactly at expiry. Using 'now < expires_at' makes the session invalid at "
        "and after the expiry instant, matching the documented product rule."
    ),
    "affected_files": ["src/payment/session.py"],
    "risks": ["None expected; the change only affects the equality boundary case."],
}

_BUG_TEST = '''"""Generated verification tests (ProofPatch)."""

from datetime import datetime, timedelta, timezone

from payment.session import PaymentSession, can_process_payment

EXPIRES = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def test_exact_expiry_is_rejected():
    """Reported bug: at the exact expiry instant the session must be expired."""

    assert can_process_payment(EXPIRES, EXPIRES) is False


def test_before_expiry_is_allowed():
    assert can_process_payment(EXPIRES, EXPIRES - timedelta(microseconds=1)) is True


def test_after_expiry_is_rejected():
    assert can_process_payment(EXPIRES, EXPIRES + timedelta(microseconds=1)) is False


def test_session_reports_expired_at_exact_expiry():
    session = PaymentSession(session_id="sess_gen", expires_at=EXPIRES)
    assert session.is_expired(EXPIRES) is True
'''

FAKE_TEST_FILES = [
    {
        "relative_path": ".proofpatch_generated_tests/test_generated_session.py",
        "content": _BUG_TEST,
        "purpose": "Reproduce the exact-expiry bug and guard surrounding boundary behavior.",
    }
]

FAKE_TEST_SCENARIOS = [
    "Payment at the exact expiry instant is rejected (reported bug).",
    "Payment just before expiry is allowed.",
    "Payment just after expiry is rejected.",
]
FAKE_TEST_ASSUMPTIONS = [
    "Public API is can_process_payment(session_expires_at, now).",
    "Datetimes are timezone-aware.",
]


class StubLLMProvider:
    """Offline stand-in used by the engine unit/integration tests."""

    name = "stub"
    model = "stub"

    def __init__(self, repo_path: Path | None = None, recorder=None) -> None:
        self.repo_path = Path(repo_path) if repo_path else None
        self.recorder = recorder

    def _patch_diff(self) -> str:
        if self.repo_path:
            target = self.repo_path / "src" / "payment" / "session.py"
            if target.exists():
                original = target.read_text(encoding="utf-8")
                fixed = original.replace(
                    "return now <= session_expires_at", "return now < session_expires_at"
                )
                if fixed != original:
                    return "".join(
                        difflib.unified_diff(
                            original.splitlines(keepends=True),
                            fixed.splitlines(keepends=True),
                            fromfile="a/src/payment/session.py",
                            tofile="b/src/payment/session.py",
                            n=3,
                        )
                    )
        return FAKE_PATCH_FALLBACK

    async def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model,
        temperature: float = 0.0,
        agent: str = "",
    ):
        if response_model is RootCauseAnalysis:
            result = RootCauseAnalysis(**FAKE_ROOT_CAUSE)
        elif response_model is PatchProposal:
            result = PatchProposal(**{**FAKE_PATCH_META, "unified_diff": self._patch_diff()})
        elif response_model is GeneratedTestBundle:
            result = GeneratedTestBundle.model_validate(
                {
                    "files": FAKE_TEST_FILES,
                    "scenarios": FAKE_TEST_SCENARIOS,
                    "assumptions": FAKE_TEST_ASSUMPTIONS,
                }
            )
        else:  # pragma: no cover - defensive
            raise LLMError(f"StubLLMProvider has no canned response for {response_model!r}")

        if self.recorder is not None:
            self.recorder(
                LLMCallRecord(
                    agent=agent,
                    model=self.model,
                    prompt_hash=_hash(system_prompt + user_prompt),
                    response_hash=_hash(result.model_dump_json()),
                    latency_ms=1,
                    validation="ok",
                    attempt=1,
                )
            )
        return result


__all__ = [
    "StubLLMProvider",
    "FAKE_ROOT_CAUSE",
    "FAKE_PATCH_FALLBACK",
    "FAKE_TEST_FILES",
]

